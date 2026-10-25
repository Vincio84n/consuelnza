"""Lettura semantica tramite API di visione OpenAI-compatibile (NVIDIA, OpenRouter, Ollama, LM Studio...)."""
import base64
import io
import json
import os
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


def _key(ai):
    key = os.environ.get(ai["chiave_env"], "")
    if not key and "integrate.api.nvidia.com" in ai["base_url"]:
        raise ErroreArchivio(f"variabile d'ambiente {ai['chiave_env']} mancante: impostala con la chiave di build.nvidia.com")
    return key


def _post(ai, body):
    key = _key(ai)
    req = urllib.request.Request(
        ai["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=ai["timeout_s"]) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode(errors="replace")
        hint = {401: " (chiave non valida)", 404: " (modello o URL inesistente)", 429: " (troppe richieste: rallenta o attendi)"}
        raise ErroreArchivio(f"API HTTP {e.code}{hint.get(e.code, '')}: {detail}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErroreArchivio(f"API non raggiungibile ({ai['base_url']}): {getattr(e, 'reason', e)}")


def call_ai(cfg, img):
    ai = cfg["ai"]
    buf = io.BytesIO()
    preview(img, ai["lato_max_px"]).save(buf, "JPEG", quality=85)
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    body = {
        "model": ai["modello"], "temperature": 0, "max_tokens": 1500,
        "messages": [
            {"role": "system", "content": "Sei un archivista fotografico. Rispondi solo con JSON valido."},
            {"role": "user", "content": [{"type": "text", "text": PROMPT},
                                         {"type": "image_url", "image_url": {"url": data_url}}]},
        ],
    }
    if "nemotron" in ai["modello"].lower():
        # Nemotron ragiona per default: disattivato per avere solo il JSON, più veloce ed economico
        body["chat_template_kwargs"] = {"enable_thinking": False}
    resp = _post(ai, body)
    try:
        text = resp["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        raise ErroreArchivio(f"risposta API inattesa: {str(resp)[:200]}")
    return parse_json(text)


def parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ErroreArchivio(f"il modello non ha risposto in JSON: {text[:120]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ErroreArchivio(f"JSON del modello non valido ({e}): {m.group(0)[:120]!r}")


def prova(cfg):
    """Verifica chiave e modello con una richiesta minima solo testo."""
    ai = cfg["ai"]
    body = {"model": ai["modello"], "max_tokens": 5, "messages": [{"role": "user", "content": "ok"}]}
    if "nemotron" in ai["modello"].lower():
        body["chat_template_kwargs"] = {"enable_thinking": False}
    _post(ai, body)
