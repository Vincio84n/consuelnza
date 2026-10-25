#!/bin/bash
# Installa ArchivioFoto in un ambiente Python isolato (.venv). Doppio clic dal Finder.
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3 non trovato: installalo da https://www.python.org/downloads/"; read -r; exit 1; }
python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -e ".[volti]" \
  || { echo "Installazione fallita"; read -r; exit 1; }
echo
echo "Installato. Nel Terminale, da questa cartella:  .venv/bin/archivio --help"
read -r
