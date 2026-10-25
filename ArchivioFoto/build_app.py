"""Crea l'eseguibile autonomo con PyInstaller (Windows: cartella con ArchivioFoto.exe; macOS: ArchivioFoto.app).
Uso: python build_app.py   (richiede: pip install ".[volti]" pyinstaller)"""
import os
import sys

import PyInstaller.__main__

sep = ";" if os.name == "nt" else ":"
opzioni = [
    "avvio_app.py", "--name", "ArchivioFoto", "--noconfirm", "--clean", "--onedir",
    "--collect-data", "archiviofoto",
    "--collect-submodules", "keyring",
    "--copy-metadata", "keyring",
    "--add-data", f"CHANGELOG.md{sep}.",
    "--hidden-import", "tkinter", "--hidden-import", "tkinter.filedialog",
]
if sys.platform == "darwin":
    opzioni += ["--windowed", "--osx-bundle-identifier", "it.archiviofoto.app"]
PyInstaller.__main__.run(opzioni)
