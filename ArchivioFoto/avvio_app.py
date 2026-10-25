"""Punto d'ingresso dell'eseguibile: doppio clic = app completa; con argomenti = riga di comando."""
import os
import sys


def _senza_console():
    # app macOS "a finestra": niente console, quindi stdout/stderr vanno su file nella cartella utente
    if sys.stdout is None or sys.stderr is None:
        from archiviofoto.app import cartella_utente
        f = open(os.path.join(cartella_utente(), "ultimo-avvio.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


if __name__ == "__main__":
    _senza_console()
    from archiviofoto.cli import main
    args = sys.argv[1:]
    # macOS passa "-psn_..." alle app avviate dal Finder
    args = [a for a in args if not a.startswith("-psn_")]
    sys.exit(main(args or ["app"]))
