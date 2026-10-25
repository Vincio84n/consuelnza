"""Lettura tecnica dell'immagine, impronta visiva e allarmi di qualità."""
import base64

import numpy as np
from PIL import Image

from .core import preview


def technical(im, exif):
    w, h = im.size
    out = {"larghezza": w, "altezza": h, "megapixel": round(w * h / 1e6, 1),
           "modo": im.mode, "orientamento": "orizzontale" if w > h else "verticale" if h > w else "quadrato"}
    dpi = im.info.get("dpi")
    if dpi and float(dpi[0]) >= 50:  # alcuni TIFF riportano 1 dpi = valore assente
        out["dpi"] = round(float(dpi[0]))
    out["bit_per_canale"] = 16 if im.mode.startswith("I;16") or im.mode == "I" else 8
    if exif:
        out["exif_scanner"] = {k: exif[k] for k in ("Make", "Model", "Software", "DateTime") if k in exif}

    rgb = preview(im, 1024)
    a = np.asarray(rgb, dtype=np.float32) / 255.0
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    mean_sat = float(sat.mean())
    out["bianco_nero"] = bool(mean_sat < 0.06)
    out["saturazione_media"] = round(mean_sat, 3)
    out["luminosita_media"] = round(float(lum.mean()), 3)
    out["contrasto"] = round(float(lum.std()), 3)
    out["ombre_chiuse_pct"] = round(float((lum < 0.02).mean() * 100), 1)
    out["luci_bruciate_pct"] = round(float((lum > 0.98).mean() * 100), 1)
    m = out["luminosita_media"]
    out["esposizione"] = "sottoesposta" if m < 0.25 else "sovraesposta" if m > 0.75 else "corretta"

    # Nitidezza: varianza del laplaciano sulla luminanza (valori bassi = mosso/sfocato)
    L = lum * 255
    lap = (-4 * L[1:-1, 1:-1] + L[:-2, 1:-1] + L[2:, 1:-1] + L[1:-1, :-2] + L[1:-1, 2:])
    var = float(lap.var())
    out["nitidezza"] = round(var, 1)
    out["nitidezza_giudizio"] = "nitida" if var > 300 else "discreta" if var > 80 else "morbida_o_mossa"

    # Negativo non invertito? Maschera arancione: rosso >> blu e immagine chiara
    r, g, b = (float(a[..., i].mean()) for i in range(3))
    out["negativo_non_invertito_probabile"] = bool(r > b + 0.15 and m > 0.45 and not out["bianco_nero"])
    out["dominante"] = "calda" if r - b > 0.05 else "fredda" if r - b < -0.05 else "neutra"

    q = rgb.resize((200, max(1, int(200 * rgb.height / rgb.width)))).quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    out["palette"] = [{"hex": "#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]),
                       "pct": round(c / total * 100, 1)} for c, i in counts]
    out["impronta"] = impronta(rgb)
    return out


def impronta(rgb):
    """dHash a 64 bit (struttura) + miniatura 8x8 a colori (palette e composizione)."""
    g = np.asarray(rgb.convert("L").resize((9, 8), Image.LANCZOS), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    dhash = int("".join("1" if x else "0" for x in bits), 2)
    mini = rgb.resize((8, 8), Image.LANCZOS).tobytes()
    return {"dhash": f"{dhash:016x}", "mini": base64.b64encode(mini).decode()}


def distanza(a, b):
    """0 = identiche, 1 = del tutto diverse."""
    ham = bin(int(a["dhash"], 16) ^ int(b["dhash"], 16)).count("1") / 64
    ma = np.frombuffer(base64.b64decode(a["mini"]), np.uint8).astype(np.float32)
    mb = np.frombuffer(base64.b64decode(b["mini"]), np.uint8).astype(np.float32)
    col = float(np.abs(ma - mb).mean() / 255)
    return round(0.6 * ham + 0.4 * col, 4)


def allarmi_qualita(t, cfg):
    q = cfg["qualita"]
    out = []
    if t["esposizione"] != "corretta":
        out.append(f"immagine {t['esposizione']} (luminosità media {t['luminosita_media']})")
    if t["nitidezza_giudizio"] == "morbida_o_mossa":
        out.append(f"immagine morbida o mossa (nitidezza {t['nitidezza']})")
    if t["luci_bruciate_pct"] > q["luci_bruciate_max_pct"]:
        out.append(f"luci bruciate sul {t['luci_bruciate_pct']}% dell'immagine")
    if t["negativo_non_invertito_probabile"]:
        out.append("sembra un negativo non invertito (maschera arancione)")
    if t["megapixel"] < q["megapixel_minimi"]:
        out.append(f"risoluzione bassa: {t['megapixel']} MP (minimo {q['megapixel_minimi']})")
    return out
