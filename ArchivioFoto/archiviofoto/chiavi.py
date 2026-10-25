"""Chiavi API. Ordine di ricerca: portachiavi del sistema, file CHIAVE.md, variabile d'ambiente.

CHIAVE.md è un file Markdown locale (cartella dell'archivio, cartella utente o cartella del programma):
non va mai pubblicato né condiviso. Il programma lo esclude da Git e non lo copia nelle viste o nei backup.
"""
import os
import re
import sys
from pathlib import Path

from .core import ErroreArchivio

SERVIZIO = "ArchivioFoto"
FILE = "CHIAVE.md"
RIGA = re.compile(r"^\s*[-*]\s+`?([A-Za-z0-9_.-]+)`?\s*:\s*`?([^`\s]+)`?\s*$")

MODELLO = """# Chiave API di ArchivioFoto

> ATTENZIONE: questo file contiene una chiave segreta. Non pubblicarlo, non inviarlo, non metterlo su GitHub.
> Chi ha la chiave può usare il tuo credito NVIDIA. Se il file finisce in mani altrui, rigenera la chiave su build.nvidia.com.
> Formato: una riga "- nome: chiave". Il nome deve corrispondere a 'nome_chiave' in CONFIGURAZIONE.md (predefinito: nvidia).

- {nome}: {chiave}
"""


def _keyring():
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return None
    if isinstance(keyring.get_keyring(), fail.Keyring):
        return None
    return keyring


def _cartelle(root=None):
    out = []
    if root is None:
        try:
            from .core import find_root
            root = find_root()
        except Exception:
            root = None
    if root:
        out.append(Path(root))
    try:
        from .app import cartella_utente
        out.append(cartella_utente())
    except Exception:
        pass
    # cartella del programma: accanto all'eseguibile, oppure la cartella dei sorgenti
    out.append(Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent)
    return out


def file_chiave(root=None):
    for d in _cartelle(root):
        p = d / FILE
        if p.is_file():
            return p
    return None


def _da_file(nome, root=None):
    p = file_chiave(root)
    if not p:
        return "", None
    for r in p.read_text(encoding="utf-8").splitlines():
        m = RIGA.match(r)
        if m and m.group(1) == nome:
            return m.group(2), p
    return "", p


def leggi(ai, root=None):
    """Restituisce (chiave, fonte)."""
    nome = ai.get("nome_chiave", "nvidia")
    kr = _keyring()
    if kr:
        try:
            k = kr.get_password(SERVIZIO, nome)
            if k:
                return k, "portachiavi"
        except Exception:
            pass
    k, p = _da_file(nome, root)
    if k:
        return k, f"file {p}"
    k = os.environ.get(ai.get("chiave_env", "NVIDIA_API_KEY"), "")
    return (k, "variabile " + ai.get("chiave_env", "")) if k else ("", "")


def _valida(valore):
    valore = valore.strip()
    if len(valore) < 8 or " " in valore:
        raise ErroreArchivio("la chiave sembra non valida (troppo corta o con spazi)")
    return valore


def salva(ai, valore, dove="portachiavi", root=None):
    """dove: 'portachiavi' (consigliato) oppure 'file' (CHIAVE.md nella cartella dell'archivio)."""
    valore = _valida(valore)
    nome = ai.get("nome_chiave", "nvidia")
    if dove == "file":
        if root is None:
            from .core import find_root
            root = find_root()
        p = Path(root) / FILE
        righe = p.read_text(encoding="utf-8").splitlines() if p.exists() else MODELLO.format(nome=nome, chiave=valore).splitlines()
        trovata = False
        for i, r in enumerate(righe):
            m = RIGA.match(r)
            if m and m.group(1) == nome:
                righe[i] = f"- {nome}: {valore}"
                trovata = True
        if not trovata:
            righe.append(f"- {nome}: {valore}")
        p.write_text("\n".join(righe) + "\n", encoding="utf-8")
        _proteggi(Path(root))
        return p
    kr = _keyring()
    if not kr:
        raise ErroreArchivio("portachiavi del sistema non disponibile: salva la chiave nel file CHIAVE.md "
                             "(archivio chiave imposta --file) oppure nella variabile d'ambiente " + ai.get("chiave_env", ""))
    kr.set_password(SERVIZIO, nome, valore)
    return None


def _proteggi(root):
    """Se l'archivio è dentro un repository Git, CHIAVE.md viene escluso dai commit."""
    for d in [root, *root.parents]:
        if (d / ".git").exists():
            gi = d / ".gitignore"
            testo = gi.read_text(encoding="utf-8") if gi.exists() else ""
            if FILE not in testo.split():
                gi.write_text(testo + ("" if testo.endswith("\n") or not testo else "\n") + FILE + "\n", encoding="utf-8")
            break


def rimuovi(ai, root=None):
    nome = ai.get("nome_chiave", "nvidia")
    tolta = False
    kr = _keyring()
    if kr:
        try:
            kr.delete_password(SERVIZIO, nome)
            tolta = True
        except Exception:
            pass
    p = file_chiave(root)
    if p:
        righe = [r for r in p.read_text(encoding="utf-8").splitlines() if not ((m := RIGA.match(r)) and m.group(1) == nome)]
        if len(righe) != len(p.read_text(encoding="utf-8").splitlines()):
            p.write_text("\n".join(righe) + "\n", encoding="utf-8")
            tolta = True
    return tolta


def mascherata(k):
    return f"…{k[-4:]}" if k else ""


def richiesta(ai):
    """True se l'indirizzo configurato richiede una chiave (servizi remoti, non localhost)."""
    url = ai.get("base_url", "")
    return not any(h in url for h in ("localhost", "127.0.0.1", "[::1]"))
