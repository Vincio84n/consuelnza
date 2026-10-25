"""Configurazione, record JSON, apertura immagini e vista unificata dei dati."""
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import ExifTags, Image

from . import __version__

Image.MAX_IMAGE_PIXELS = None  # le scansioni a 4000+ dpi superano il limite di default

CONFIG_FILE = "CONFIGURAZIONE.md"
CONFIG_VECCHIO = "archivio.json"  # archivi creati con la 0.2/0.3, migrati in automatico
IMG_EXT = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".dng", ".nef", ".cr2", ".cr3", ".arw", ".orf", ".raf", ".rw2"}
RAW_EXT = {".dng", ".nef", ".cr2", ".cr3", ".arw", ".orf", ".raf", ".rw2"}
LIST_FIELDS = ("persone", "tag")

class ErroreArchivio(Exception):
    """Errore previsto, con messaggio per l'utente."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_root(start=None):
    p = Path(start or os.getcwd()).resolve()
    for d in [p, *p.parents]:
        if (d / CONFIG_FILE).exists() or (d / CONFIG_VECCHIO).exists():
            return d
    raise ErroreArchivio(f"Nessun archivio trovato (manca {CONFIG_FILE}). Esegui prima: archivio init <cartella>")


def load_config(root, rigoroso=True):
    from .configurazione import carica
    return carica(root, rigoroso)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def set_readonly(path, readonly=True):
    """Sola lettura su Windows, macOS e Linux (su Windows os.chmod gestisce l'attributo di sola lettura)."""
    mode = os.stat(path).st_mode
    if readonly:
        os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    else:
        os.chmod(path, mode | stat.S_IWUSR)


def is_readonly(path):
    return not (os.stat(path).st_mode & stat.S_IWUSR)


def data_path(root, pid):
    return root / "dati" / f"{pid}.json"


def master_path(root, rec):
    return root / "master" / rec["file"]["nome"]


def load_rec(root, pid):
    return json.loads(data_path(root, pid).read_text(encoding="utf-8"))


def save_rec(root, rec):
    rec["aggiornato"] = now()
    rec["versione_tool"] = __version__
    p = data_path(root, rec["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def all_ids(root):
    return sorted(p.stem for p in (root / "dati").glob("*.json"))


def select_ids(root, rullino=None, ids=None):
    out = all_ids(root)
    if rullino is not None:
        tag = f"-R{int(rullino):03d}-"
        out = [i for i in out if tag in i]
    if ids:
        missing = set(ids) - set(out)
        if missing and rullino is None:
            raise ErroreArchivio(f"ID non trovati: {', '.join(sorted(missing))}")
        out = [i for i in out if i in set(ids)]
    return out


def split_list(v):
    if isinstance(v, list):
        return v
    return [x.strip() for x in re.split(r"[;,]", v or "") if x.strip()]


def open_image(path):
    """Apre TIFF/JPEG/PNG con Pillow, i RAW con rawpy se installato. Restituisce (immagine, exif)."""
    path = Path(path)
    if path.suffix.lower() in RAW_EXT:
        try:
            import rawpy
        except ImportError:
            raise ErroreArchivio("file RAW: installa 'rawpy' (pip install rawpy) per leggerlo")
        with rawpy.imread(str(path)) as raw:
            return Image.fromarray(raw.postprocess(use_camera_wb=True, output_bps=8)), {}
    im = Image.open(path)
    exif = {}
    try:
        for k, v in im.getexif().items():
            name = ExifTags.TAGS.get(k, str(k))
            if isinstance(v, (str, int, float)):
                exif[name] = v.strip("\x00 ") if isinstance(v, str) else v
    except Exception:
        pass
    return im, exif


def preview(im, max_side):
    im = im.copy()
    if im.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        a = np.asarray(im, dtype=np.float32)
        im = Image.fromarray((a / max(float(a.max()), 1) * 255).astype(np.uint8))
    im.thumbnail((max_side, max_side))
    return im.convert("RGB")


def thumbnail(root, rec, size):
    """Miniatura JPEG in cache (usata da revisione e volti)."""
    cache = root / "cache" / "miniature"
    cache.mkdir(parents=True, exist_ok=True)
    p = cache / f"{rec['id']}_{size}.jpg"
    if not p.exists():
        im, _ = open_image(master_path(root, rec))
        preview(im, size).save(p, "JPEG", quality=82)
    return p


def persone(rec):
    names = list(split_list(rec["umano"].get("persone", [])))
    for f in rec.get("volti", []):
        if f.get("nome") and f["nome"] not in names:
            names.append(f["nome"])
    return names


def merged(rec):
    """Vista piatta con precedenza umano > fisico > ai > tecnico."""
    f, t, a, u = rec["fisico"], rec["tecnico"], rec["ai"], rec["umano"]
    data = u.get("data") or ""
    anno = (data[:4] if re.match(r"\d{4}", data) else "") or str(f.get("anno") or "")
    return {
        "id": rec["id"], "anno": anno, "data": data or anno,
        "rullino": f"R{int(f.get('rullino', 0)):03d}", "fotogramma": f"F{int(f.get('fotogramma', 0)):02d}",
        "busta": f.get("busta", ""), "formato": f.get("formato", ""), "pellicola": f.get("pellicola", ""),
        "luogo": u.get("luogo", ""), "evento": u.get("evento", ""),
        "persone": "+".join(persone(rec)),
        "tipo": u.get("tipo_scatto") or a.get("tipo_scatto") or "",
        "ambiente": a.get("ambiente", ""), "epoca": a.get("epoca_stimata", ""),
        "soggetto": (a.get("soggetti") or [""])[0],
        "colore": "" if not t else ("bn" if t.get("bianco_nero") else "colore"),
        "esposizione": t.get("esposizione", ""), "nitidezza": t.get("nitidezza_giudizio", ""),
        "descrizione": u.get("descrizione") or a.get("descrizione", ""),
        "tag": sorted(set(split_list(u.get("tag", [])) + list(a.get("tag", [])))),
    }


def slug(s):
    s = re.sub(r"[^\w\-+'. ]", "", str(s), flags=re.UNICODE).strip().replace(" ", "-")
    # Windows non accetta nomi che finiscono con punto o spazio, né nomi riservati
    s = s.rstrip(". ")
    if s.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        s = "_" + s
    return s[:60] or "x"


def console_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
