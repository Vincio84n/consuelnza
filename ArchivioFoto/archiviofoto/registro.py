"""REGISTRO.md: diario leggibile e solo in aggiunta di operazioni, esiti e modifiche alla configurazione."""
from datetime import datetime

from . import __version__

FILE = "REGISTRO.md"
INTESTAZIONE = """# Registro di ArchivioFoto

> Diario automatico: ogni operazione e ogni modifica alla configurazione aggiunge una riga in fondo.
> Il programma non cancella né modifica mai le righe esistenti. Formato: data · versione del programma · comando · dettagli · esito.

"""

_esito = []  # dettagli raccolti dal comando in corso


def esito(testo):
    """Un comando annota qui il proprio riepilogo (es. '36 importate, 2 saltate')."""
    _esito.append(str(testo))


def prendi_esito():
    t = "; ".join(_esito)
    _esito.clear()
    return t


def scrivi(root, comando, dettagli="", stato="ok"):
    p = root / FILE
    if not p.exists():
        p.write_text(INTESTAZIONE, encoding="utf-8")
    simbolo = {"ok": "✔", "errore": "✖", "attenzione": "⚠"}.get(stato, stato)
    dettagli = " ".join(str(dettagli).split())  # una riga sola
    riga = f"- {datetime.now().strftime('%Y-%m-%d %H:%M')} · v{__version__} · **{comando}** · {dettagli or '-'} · {simbolo}\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(riga)


def ultime(root, n=200):
    p = root / FILE
    if not p.exists():
        return []
    righe = [r for r in p.read_text(encoding="utf-8").splitlines() if r.startswith("- ")]
    return righe[-n:]
