"""Registro note e allarmi: errori, problemi di qualità e note manuali, con stato aperto/risolto."""
import json
import os

from .core import now

LIVELLI = ("errore", "attenzione", "qualita", "nota")
FILE = "note.json"


def _path(root):
    return root / FILE


def carica(root):
    p = _path(root)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def _salva(root, items):
    p = _path(root)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def registra(root, livello, messaggio, comando="", pid=None):
    """Aggiunge una nota; non duplica una nota identica ancora aperta. Restituisce il numero."""
    assert livello in LIVELLI, livello
    items = carica(root)
    for it in items:
        if not it["risolta"] and (it["livello"], it["messaggio"], it.get("id")) == (livello, messaggio, pid):
            it["ripetuta"] = it.get("ripetuta", 1) + 1
            it["ultima"] = now()
            _salva(root, items)
            return it["n"]
    n = max((it["n"] for it in items), default=0) + 1
    items.append({"n": n, "quando": now(), "livello": livello, "comando": comando,
                  "id": pid, "messaggio": messaggio, "risolta": False})
    _salva(root, items)
    return n


def risolvi(root, numeri=None, pid=None, livello=None, comando=None):
    """Chiude le note indicate per numero, oppure tutte quelle aperte che corrispondono ai filtri."""
    items = carica(root)
    n = 0
    for it in items:
        if it["risolta"]:
            continue
        if numeri is not None:
            hit = it["n"] in numeri
        else:
            hit = ((pid is None or it.get("id") == pid) and (livello is None or it["livello"] == livello)
                   and (comando is None or it["comando"] == comando))
        if hit:
            it["risolta"] = True
            it["risolta_il"] = now()
            n += 1
    _salva(root, items)
    return n


def aperte(root, livello=None, pid=None):
    return [it for it in carica(root) if not it["risolta"]
            and (livello is None or it["livello"] == livello) and (pid is None or it.get("id") == pid)]
