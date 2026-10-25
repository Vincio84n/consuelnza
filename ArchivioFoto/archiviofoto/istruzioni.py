"""ISTRUZIONI.md: le tue indicazioni che il programma segue (contesto per l'AI, regole, vocabolario dei tag)."""
import hashlib
import re
import unicodedata

FILE = "ISTRUZIONI.md"

MODELLO = """# Istruzioni per ArchivioFoto

> Il programma legge questo file a ogni lettura AI. Scrivi in italiano normale.
> Le righe che iniziano con > sono spiegazioni e vengono ignorate.
> Quando cambi il contenuto, le foto già lette risultano "lette con istruzioni vecchie":
> `archivio ai --obsolete` le rilegge (oppure Lavori → Lettura AI nella webapp).

## Contesto dell'archivio
> Descrivi l'archivio: chi ha scattato, dove, in che anni, cosa contiene. Viene passato all'AI con ogni foto.
> Esempio: Fotografie di famiglia scattate in Basilicata tra il 1965 e il 1990, soprattutto Matera e Bari.

## Regole per la lettura AI
> Una regola per riga, iniziando con un trattino. Esempi:
> - Le persone in divisa sono spesso carabinieri o bande musicali.
> - Se compare il mare, indica nei tag se è spiaggia o porto.

## Vocabolario dei tag
> Termine da usare: sinonimi da sostituire. I tag dell'AI vengono uniformati in automatico.
- chiesa: duomo, cattedrale, basilica
- automobile: auto, macchina, vettura
- bambini: bambino, bimbi, bimbo

## Tag da non usare
> Tag troppo generici che verranno scartati.
- foto
- immagine
- fotografia
"""


def _norm(s):
    s = unicodedata.normalize("NFD", s.lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def crea(root):
    p = root / FILE
    if not p.exists():
        p.write_text(MODELLO, encoding="utf-8")


def carica(root):
    p = root / FILE
    testo = p.read_text(encoding="utf-8") if p.exists() else ""
    sezioni, cur = {}, None
    for r in testo.splitlines():
        if r.startswith("#"):
            cur = _norm(r.lstrip("#"))
            sezioni.setdefault(cur, [])
        elif cur is not None and r.strip() and not r.lstrip().startswith(">"):
            sezioni[cur].append(r.rstrip())

    def sez(*nomi):
        for k, v in sezioni.items():
            if any(n in k for n in nomi):
                return v
        return []

    def voci(righe):
        return [re.sub(r"^\s*[-*]\s+", "", r).strip() for r in righe if re.match(r"^\s*[-*]\s+\S", r)]

    contesto = " ".join(r.strip() for r in sez("contesto"))
    regole = voci(sez("regole"))
    vocab = {}
    for v in voci(sez("vocabolario")):
        canon, _, sin = v.partition(":")
        canon = canon.strip().lower()
        if canon:
            vocab[canon] = [s.strip().lower() for s in sin.split(",") if s.strip()]
    vietati = [v.lower() for v in voci(sez("non usare", "vietat"))]
    sostanza = repr((contesto, regole, sorted(vocab.items()), sorted(vietati)))
    return {"contesto": contesto, "regole": regole, "vocabolario": vocab, "vietati": vietati,
            "versione": hashlib.sha256(sostanza.encode()).hexdigest()[:10]}


def prompt_extra(istr):
    parti = []
    if istr["contesto"]:
        parti.append("Contesto dell'archivio fornito dal proprietario: " + istr["contesto"])
    if istr["regole"]:
        parti.append("Regole da seguire:\n" + "\n".join("- " + r for r in istr["regole"]))
    if istr["vocabolario"]:
        parti.append("Nei tag usa preferibilmente questi termini: " + ", ".join(istr["vocabolario"]))
    if istr["vietati"]:
        parti.append("Non usare questi tag: " + ", ".join(istr["vietati"]))
    return "\n\n".join(parti)


def normalizza_tag(tag, istr):
    mappa = {}
    for canon, sin in istr["vocabolario"].items():
        mappa[_norm(canon)] = canon
        for s in sin:
            mappa[_norm(s)] = canon
    vietati = {_norm(v) for v in istr["vietati"]}
    out = []
    for t in tag or []:
        t = str(t).strip().lower()
        n = _norm(t)
        if not t or n in vietati:
            continue
        t = mappa.get(n, t)
        if t not in out:
            out.append(t)
    return out
