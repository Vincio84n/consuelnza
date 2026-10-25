"""Controllo delle nuove versioni pubblicate su GitHub."""
import json
import os
import re
import time
import urllib.request

from . import __version__

RELEASE_API = "https://api.github.com/repos/Vincio84n/consuelnza/releases/tags/archiviofoto"
PAGINA = "https://github.com/Vincio84n/consuelnza/releases/tag/archiviofoto"


def _tupla(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def controlla(timeout=10):
    """{'versione', 'nuova', 'note', 'pagina', 'download'}; solleva eccezione se la rete non risponde."""
    url = os.environ.get("ARCHIVIOFOTO_RELEASE_URL", RELEASE_API)
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ArchivioFoto"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    m = re.search(r"v?(\d+\.\d+\.\d+)", d.get("name") or d.get("tag_name") or "")
    remota = m.group(1) if m else "0.0.0"
    return {"versione": remota, "attuale": __version__, "nuova": _tupla(remota) > _tupla(__version__),
            "note": d.get("body", ""), "pagina": d.get("html_url", PAGINA),
            "download": {a["name"]: a["browser_download_url"] for a in d.get("assets", [])}}


def controlla_in_cache(root, ore=24):
    """Al massimo un controllo al giorno; non solleva mai eccezioni."""
    p = root / "cache" / "aggiornamento.json"
    try:
        if p.exists() and time.time() - p.stat().st_mtime < ore * 3600:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("attuale") == __version__:
                return d
        d = controlla()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d), encoding="utf-8")
        return d
    except Exception:
        return None
