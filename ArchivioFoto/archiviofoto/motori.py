"""Scelta e prova dei motori AI (NVIDIA o qualsiasi API compatibile OpenAI)."""
import re
import time

from PIL import Image, ImageDraw

from .ai import _corpo, _post, call_ai, modelli
from .core import ErroreArchivio

# Riconoscimento euristico dai nomi: la prova reale resta l'unica conferma
VISIONE = re.compile(r"(\bvl\b|-vl\b|-vl-|vision|vlm|llava|paligemma|kosmos|fuyu|neva|vila|cosmos|qwen.*vl|gemma-3|pixtral|llama-4)", re.I)


def e_visione(nome):
    return bool(VISIONE.search(nome))


def elenca(cfg):
    out = []
    for m in modelli(cfg):
        out.append({"id": m, "visione": e_visione(m)})
    return out


def immagine_prova():
    im = Image.new("RGB", (640, 420), (200, 215, 230))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 300, 640, 420], fill=(120, 140, 90))
    d.polygon([(220, 300), (320, 170), (420, 300)], fill=(170, 80, 60))
    d.rectangle([250, 300, 390, 380], fill=(230, 220, 190))
    d.ellipse([500, 40, 580, 120], fill=(250, 220, 90))
    d.text((20, 20), "PROVA 1987", fill=(20, 20, 20))
    return im


def prova(cfg, ruolo="visione", modello=None):
    """Chiamata reale: tempo di risposta ed esito. Non salva nulla."""
    ai = cfg["ai"]
    t0 = time.monotonic()
    try:
        if ruolo == "visione":
            m = modello or ai["modello"]
            solo = dict(cfg, ai=dict(ai, modello_riserva=""))  # la prova riguarda solo il modello indicato
            res, _ = call_ai(solo, immagine_prova(), modello=m)
            mancanti = [k for k in ("tipo_scatto", "descrizione", "tag") if k not in res]
            ok = not mancanti
            dettaglio = (f"JSON valido. Descrizione: {str(res.get('descrizione', ''))[:120]}" if ok
                         else f"JSON incompleto, mancano: {', '.join(mancanti)}")
        else:
            m = modello or ai["modello_testo"]
            resp = _post(ai, _corpo(m, [{"role": "user", "content": "Rispondi solo con la parola: pronto"}], 20))
            testo = (resp["choices"][0]["message"].get("content") or "").strip()
            ok = bool(testo)
            dettaglio = f"Risposta: {testo[:80]}"
    except ErroreArchivio as e:
        return {"ok": False, "modello": modello or ai["modello" if ruolo == "visione" else "modello_testo"],
                "secondi": round(time.monotonic() - t0, 1), "dettaglio": str(e)}
    return {"ok": ok, "modello": m, "secondi": round(time.monotonic() - t0, 1), "dettaglio": dettaglio}
