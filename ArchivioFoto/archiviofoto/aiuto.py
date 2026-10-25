"""Guida: ricerca negli articoli, prossimi passi calcolati sull'archivio, assistente AI."""
import json
import re
import unicodedata
from pathlib import Path

from . import note
from .core import all_ids, load_config, load_rec

WEB = Path(__file__).resolve().parent / "web"


def articoli():
    return json.loads((WEB / "guida.json").read_text(encoding="utf-8"))


def _norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def cerca(domanda, n=4):
    """Punteggio semplice: titolo > parole chiave > testo, con corrispondenza per prefisso."""
    parole = [w for w in re.findall(r"\w+", _norm(domanda)) if len(w) > 2]
    out = []
    for a in articoli():
        campi = [(_norm(a["titolo"]), 5), (_norm(a["chiavi"]), 3), (_norm(a["testo"]), 1)]
        score = 0
        for w in parole:
            radice = w[:max(4, len(w) - 2)]  # "rinominare" trova anche "rinomina"
            for testo, peso in campi:
                if re.search(r"\b" + re.escape(radice), testo):
                    score += peso
        if score:
            out.append((score, a))
    return [a for _, a in sorted(out, key=lambda x: -x[0])[:n]]


def prossimi_passi(root):
    """Cosa fare adesso, in ordine di priorità, calcolato sullo stato reale dell'archivio."""
    ids = all_ids(root)
    if not ids:
        return [{"testo": "L'archivio è vuoto: importa il primo rullino.", "comando": "archivio ingest <cartella> --rullino 1 --anno AAAA", "guida": "ingest"}]
    recs = [load_rec(root, i) for i in ids]
    passi = []
    errori = note.aperte(root, livello="errore")
    if errori:
        passi.append({"testo": f"{len(errori)} errori aperti: qualcosa non è stato completato.", "link": "/note", "guida": "note"})

    def manca(cond, testo, comando, guida):
        rull = sorted({r["fisico"].get("rullino") for r in recs if cond(r)})
        if rull:
            n = sum(1 for r in recs if cond(r))
            arg = f" --rullino {rull[0]}" if len(rull) == 1 else ""
            passi.append({"testo": f"{n} foto {testo} (rullini: {', '.join(f'R{x:03d}' for x in rull[:8])}{'…' if len(rull) > 8 else ''}).",
                          "comando": comando + arg, "guida": guida})

    manca(lambda r: not r["tecnico"], "senza analisi tecnica", "archivio analizza", "analizza")
    manca(lambda r: not r["ai"], "senza lettura AI", "archivio ai", "ai")
    try:
        import importlib.util
        if importlib.util.find_spec("cv2"):
            manca(lambda r: "volti" not in r, "senza rilevamento volti", "archivio volti rileva", "volti")
    except Exception:
        pass
    senza_gruppo = sum(1 for r in recs for f in r.get("volti", []) if not f.get("gruppo"))
    if senza_gruppo:
        passi.append({"testo": f"{senza_gruppo} volti non ancora raggruppati.", "comando": "archivio volti raggruppa", "guida": "volti"})
    senza_nome = {f["gruppo"] for r in recs for f in r.get("volti", []) if f.get("gruppo") and not f.get("nome")}
    if senza_nome:
        passi.append({"testo": f"{len(senza_nome)} gruppi di volti senza nome.", "comando": "archivio volti anteprima", "guida": "volti"})
    qual = note.aperte(root, livello="qualita")
    if qual:
        passi.append({"testo": f"{len(qual)} allarmi di qualità da valutare.", "link": "/note", "guida": "allarmi-qualita"})
    da_ver = sorted({r["fisico"].get("rullino") for r in recs if not r["umano"].get("verificato")})
    if da_ver:
        passi.append({"testo": f"{sum(1 for r in recs if not r['umano'].get('verificato'))} foto da verificare, a partire dal rullino R{da_ver[0]:03d}.",
                      "link": f"/r/{da_ver[0]}", "guida": "revisione"})
    if not passi:
        passi.append({"testo": "Tutto verificato. Aggiorna XMP e viste, poi fai il backup.", "comando": "archivio xmp", "guida": "backup"})
    return passi


def riepilogo(root):
    ids = all_ids(root)
    recs = [load_rec(root, i) for i in ids]
    conta = {}
    for x in note.aperte(root):
        conta[x["livello"]] = conta.get(x["livello"], 0) + 1
    return (f"Foto {len(recs)}; con analisi tecnica {sum(bool(r['tecnico']) for r in recs)}; con AI {sum(bool(r['ai']) for r in recs)}; "
            f"verificate {sum(bool(r['umano'].get('verificato')) for r in recs)}; note aperte {conta or 'nessuna'}.")


SISTEMA = """Sei l'assistente di ArchivioFoto, uno strumento a riga di comando e webapp per catalogare un archivio di negativi scansionati.
Rispondi in italiano, in modo pratico e breve: indica i comandi esatti da eseguire (in `codice`) e l'ordine dei passi.
Basati SOLO sugli articoli della guida e sullo stato dell'archivio forniti qui sotto. Se la risposta non è lì, dillo e suggerisci l'articolo più vicino.
Non inventare comandi o opzioni che non compaiono negli articoli."""


def chiedi(root, domanda, storia=None):
    from .ai import _post
    cfg = load_config(root)
    fonti = cerca(domanda) or articoli()[:2]
    contesto = "\n\n".join(f"## {a['titolo']}\n{a['testo']}" for a in fonti)
    passi = "\n".join(f"- {p['testo']} {p.get('comando', '')}" for p in prossimi_passi(root))
    messaggi = [{"role": "system", "content": f"{SISTEMA}\n\n# Stato dell'archivio\n{riepilogo(root)}\nProssimi passi suggeriti:\n{passi}\n\n# Articoli della guida\n{contesto}"}]
    for m in (storia or [])[-6:]:
        if m.get("ruolo") in ("utente", "assistente") and m.get("testo"):
            messaggi.append({"role": "user" if m["ruolo"] == "utente" else "assistant", "content": str(m["testo"])[:2000]})
    messaggi.append({"role": "user", "content": domanda[:2000]})
    modello = cfg["ai"]["modello_testo"]
    body = {"model": modello, "temperature": 0.2, "max_tokens": 900, "messages": messaggi}
    if "nemotron" in modello.lower():
        body["chat_template_kwargs"] = {"enable_thinking": False}
    resp = _post(cfg["ai"], body)
    testo = resp["choices"][0]["message"].get("content") or ""
    testo = re.sub(r"<think>.*?</think>", "", testo, flags=re.S).strip()
    return {"risposta": testo, "fonti": [{"id": a["id"], "titolo": a["titolo"]} for a in fonti]}
