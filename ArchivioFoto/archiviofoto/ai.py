"""Lettura semantica tramite API di visione OpenAI-compatibile (NVIDIA, OpenRouter, Ollama, LM Studio...)."""
import base64
import io
import json
import re
import urllib.error
import urllib.request

from .core import ErroreArchivio, preview

PROMPT = """Analizza questa fotografia d'archivio (scansione di negativo) e rispondi SOLO con un oggetto JSON con queste chiavi:
"tipo_scatto": uno tra ritratto, gruppo, paesaggio, architettura, interno, evento, street, still_life, documento, altro;
"inquadratura": uno tra primissimo_piano, primo_piano, mezza_figura, figura_intera, campo_medio, campo_lungo;
"ambiente": "interno" o "esterno";
"momento": giorno, sera, notte o non_determinabile;
"persone": numero intero di persone visibili;
"soggetti": lista dei soggetti principali;
"oggetti": lista di oggetti rilevanti (veicoli, insegne, abiti, strumenti...);
"sfondo": breve descrizione dello sfondo;
"testo_visibile": testo leggibile nell'immagine (insegne, targhe, scritte), "" se assente;
"epoca_stimata": decennio stimato da abiti, auto, architettura (es. "anni '70") o "non_determinabile";
"descrizione": una frase in italiano;
"tag": da 5 a 12 parole chiave in italiano, minuscole;
"confidenza": numero tra 0 e 1 sulla tua lettura complessiva.
Non inventare nomi di persone o luoghi che non siano scritti nell'immagine."""


class ErroreAPI(ErroreArchivio):
    def __init__(self, msg, codice=None):
        super().__init__(msg)
        self.codice = codice


def _key(ai):
    from . import chiavi
    key, _ = chiavi.leggi(ai)
    if not key and chiavi.richiesta(ai):
        raise ErroreAPI("chiave API mancante: impostala con  archivio chiave imposta  oppure dalla pagina Impostazioni della webapp", 401)
    return key


def _richiesta(ai, percorso, body=None):
    key = _key(ai)
    req = urllib.request.Request(
        ai["base_url"].rstrip("/") + percorso, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=ai["timeout_s"]) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode(errors="replace")
        hint = {401: " (chiave non valida)", 403: " (chiave senza accesso a questo modello)",
                404: " (modello o URL inesistente)", 429: " (troppe richieste: rallenta o attendi)"}
        raise ErroreAPI(f"API HTTP {e.code}{hint.get(e.code, '')}: {detail}", e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroreAPI(f"API non raggiungibile ({ai['base_url']}): {getattr(e, 'reason', e)}")


def _post(ai, body):
    return _richiesta(ai, "/chat/completions", body)


def _corpo(modello, messaggi, max_tokens):
    body = {"model": modello, "temperature": 0, "max_tokens": max_tokens, "messages": messaggi}
    if "nemotron" in modello.lower():
        # Nemotron ragiona per default: disattivato per avere solo il JSON, più veloce ed economico
        body["chat_template_kwargs"] = {"enable_thinking": False}
    return body


def call_ai(cfg, img, istr=None, modello=None):
    """Legge una foto. Restituisce (risultato, modello usato). Se il modello principale fallisce
    per un motivo che non dipende dalla chiave, prova il modello di riserva configurato."""
    from .istruzioni import normalizza_tag, prompt_extra
    ai = cfg["ai"]
    buf = io.BytesIO()
    preview(img, ai["lato_max_px"]).save(buf, "JPEG", quality=85)
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    testo = PROMPT + ("\n\n" + prompt_extra(istr) if istr else "")
    messaggi = [
        {"role": "system", "content": "Sei un archivista fotografico. Rispondi solo con JSON valido."},
        {"role": "user", "content": [{"type": "text", "text": testo},
                                     {"type": "image_url", "image_url": {"url": data_url}}]},
    ]
    principale = modello or ai["modello"]
    candidati = [principale] + ([ai["modello_riserva"]] if ai.get("modello_riserva") and ai["modello_riserva"] != principale else [])
    ultimo = None
    for m in candidati:
        try:
            resp = _post(ai, _corpo(m, messaggi, 1500))
            try:
                text = resp["choices"][0]["message"].get("content") or ""
            except (KeyError, IndexError, TypeError):
                raise ErroreAPI(f"risposta API inattesa: {str(resp)[:200]}")
            res = parse_json(text)
            if istr:
                res["tag"] = normalizza_tag(res.get("tag"), istr)
            return res, m
        except ErroreArchivio as e:
            ultimo = e
            if getattr(e, "codice", None) in (401, 403):  # chiave: inutile provare un altro modello
                break
    raise ultimo


def parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ErroreArchivio(f"il modello non ha risposto in JSON: {text[:120]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ErroreArchivio(f"JSON del modello non valido ({e}): {m.group(0)[:120]!r}")


def chat_testo(ai, messaggi, max_tokens=900, temperature=0.2):
    """Chiamata solo testo: modello_testo, poi modello_testo_riserva se il primo ha problemi.
    Restituisce (testo, modello usato). Gli errori di chiave (401/403) non passano alla riserva."""
    candidati = [ai["modello_testo"]] + ([ai["modello_testo_riserva"]] if ai.get("modello_testo_riserva")
                                         and ai["modello_testo_riserva"] != ai["modello_testo"] else [])
    ultimo = None
    for m in candidati:
        try:
            body = _corpo(m, messaggi, max_tokens)
            body["temperature"] = temperature
            resp = _post(ai, body)
            testo = (resp["choices"][0]["message"].get("content") or "")
            testo = re.sub(r"<think>.*?</think>", "", testo, flags=re.S).strip()
            if not testo:
                raise ErroreAPI(f"risposta vuota da {m}")
            return testo, m
        except (KeyError, IndexError, TypeError):
            ultimo = ErroreAPI(f"risposta API inattesa da {m}")
        except ErroreArchivio as e:
            ultimo = e
            if getattr(e, "codice", None) in (401, 403):
                break
    raise ultimo


def modelli(cfg):
    """Elenco dei modelli disponibili con la chiave configurata."""
    resp = _richiesta(cfg["ai"], "/models")
    return sorted({m.get("id") for m in resp.get("data", []) if m.get("id")})


def prova(cfg):
    """Verifica chiave e modello di visione con una richiesta minima solo testo."""
    _post(cfg["ai"], _corpo(cfg["ai"]["modello"], [{"role": "user", "content": "ok"}], 5))
