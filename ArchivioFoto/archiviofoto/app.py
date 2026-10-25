"""Avvio con doppio clic: sceglie l'archivio, apre la webapp nel browser, ricorda l'ultima cartella usata."""
import json
import os
import sys
from pathlib import Path

from .core import CONFIG_FILE, CONFIG_VECCHIO


def cartella_utente():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "ArchivioFoto"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prefs():
    p = cartella_utente() / "preferenze.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ricorda(root):
    p = cartella_utente() / "preferenze.json"
    d = _prefs()
    d["ultimo_archivio"] = str(root)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def e_archivio(p):
    return p and ((Path(p) / CONFIG_FILE).exists() or (Path(p) / CONFIG_VECCHIO).exists())


def scegli_cartella(titolo):
    """Finestra di sistema per scegliere una cartella; None se non disponibile o annullata."""
    try:
        import tkinter
        from tkinter import filedialog
        tk = tkinter.Tk()
        tk.withdraw()
        tk.attributes("-topmost", True)
        d = filedialog.askdirectory(title=titolo, mustexist=False)
        tk.destroy()
        return d or None
    except Exception:
        return None


def trova_archivio(esplicito=None, scegli=False):
    """Ordine: cartella indicata, cartella corrente, ultima usata, finestra di scelta, ~/ArchivioFoto."""
    if esplicito:
        return Path(esplicito).resolve()
    if not scegli:
        if e_archivio(Path.cwd()):
            return Path.cwd()
        ultimo = _prefs().get("ultimo_archivio")
        if e_archivio(ultimo):
            return Path(ultimo)
    d = scegli_cartella("Scegli la cartella dell'archivio (o una cartella vuota per crearne uno nuovo)")
    return Path(d).resolve() if d else Path.home() / "ArchivioFoto"
