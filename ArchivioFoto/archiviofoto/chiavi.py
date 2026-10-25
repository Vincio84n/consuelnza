"""Chiavi API: nel portachiavi del sistema (Gestione credenziali di Windows, Portachiavi di macOS), mai nei file."""
import os

from .core import ErroreArchivio

SERVIZIO = "ArchivioFoto"


def _keyring():
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return None
    if isinstance(keyring.get_keyring(), fail.Keyring):
        return None
    return keyring


def leggi(ai):
    """Restituisce (chiave, fonte). Prima il portachiavi, poi la variabile d'ambiente."""
    kr = _keyring()
    if kr:
        try:
            k = kr.get_password(SERVIZIO, ai.get("nome_chiave", "nvidia"))
            if k:
                return k, "portachiavi"
        except Exception:
            pass
    k = os.environ.get(ai.get("chiave_env", "NVIDIA_API_KEY"), "")
    return (k, "variabile " + ai.get("chiave_env", "")) if k else ("", "")


def salva(ai, valore):
    valore = valore.strip()
    if len(valore) < 8 or " " in valore:
        raise ErroreArchivio("la chiave sembra non valida (troppo corta o con spazi)")
    kr = _keyring()
    if not kr:
        raise ErroreArchivio(f"portachiavi del sistema non disponibile: imposta la variabile d'ambiente {ai.get('chiave_env')} "
                             "(vedi INSTALLAZIONE.md)")
    kr.set_password(SERVIZIO, ai.get("nome_chiave", "nvidia"), valore)


def rimuovi(ai):
    kr = _keyring()
    if not kr:
        return False
    try:
        kr.delete_password(SERVIZIO, ai.get("nome_chiave", "nvidia"))
        return True
    except Exception:
        return False


def mascherata(k):
    return f"…{k[-4:]}" if k else ""


def richiesta(ai):
    """True se l'indirizzo configurato richiede una chiave (servizi remoti, non localhost)."""
    url = ai.get("base_url", "")
    return not any(h in url for h in ("localhost", "127.0.0.1", "[::1]"))
