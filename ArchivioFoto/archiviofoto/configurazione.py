"""CONFIGURAZIONE.md: tutte le scelte del programma in un file Markdown leggibile e modificabile.

Formato: le righe "- chiave: valore" sono le impostazioni; titoli, citazioni (>) e testo sono spiegazioni.
Ogni modifica (da file, da riga di comando o dalla webapp) viene controllata e annotata in REGISTRO.md.
"""
import json
import os
import re

from . import registro
from .core import ErroreArchivio

FILE = "CONFIGURAZIONE.md"
VECCHIO_JSON = "archivio.json"
PRESET_VISTE = ("cronologico", "luogo", "tipologia", "persone", "fisico", "tecnico")


class Voce:
    def __init__(self, sezione, chiave, percorso, tipo, default, aiuto, scelte=None, minimo=None, massimo=None, vuoto=False):
        self.sezione, self.chiave, self.percorso, self.tipo, self.default = sezione, chiave, percorso, tipo, default
        self.aiuto, self.scelte, self.minimo, self.massimo, self.vuoto = aiuto, scelte, minimo, massimo, vuoto


SCHEMA = [
    Voce("Archivio", "prefisso", ("prefisso",), "testo", "ARC",
         "Prefisso degli ID delle foto (es. ARC-1987-R042-F07). Cambialo solo prima del primo ingest."),
    Voce("Motori AI", "indirizzo_api", ("ai", "base_url"), "url", "https://integrate.api.nvidia.com/v1",
         "Indirizzo dell'API compatibile OpenAI. NVIDIA: https://integrate.api.nvidia.com/v1 · Ollama locale: http://localhost:11434/v1"),
    Voce("Motori AI", "modello_visione", ("ai", "modello"), "testo", "nvidia/nemotron-nano-12b-v2-vl",
         "Modello che legge le foto: deve essere un modello di VISIONE. Elenco: archivio motori elenca"),
    Voce("Motori AI", "modello_testo", ("ai", "modello_testo"), "testo", "nvidia/nemotron-3-ultra-550b-a55b",
         "Modello solo testo usato dall'assistente della guida."),
    Voce("Motori AI", "modello_riserva", ("ai", "modello_riserva"), "testo", "", vuoto=True,
         aiuto="Modello di visione usato in automatico se quello principale fallisce (modello inesistente, server in errore). Vuoto = nessuna riserva."),
    Voce("Motori AI", "nome_chiave", ("ai", "nome_chiave"), "testo", "nvidia",
         "Nome con cui la chiave API è salvata nel portachiavi del sistema. La chiave NON va scritta qui: usa  archivio chiave imposta  o la pagina Impostazioni."),
    Voce("Motori AI", "variabile_chiave", ("ai", "chiave_env"), "testo", "NVIDIA_API_KEY",
         "Variabile d'ambiente usata come alternativa al portachiavi."),
    Voce("Motori AI", "lato_massimo_px", ("ai", "lato_max_px"), "intero", 1024,
         "Lato massimo della copia ridotta inviata all'AI. Più grande = più dettagli, più lento e costoso.", minimo=256, massimo=4096),
    Voce("Motori AI", "timeout_secondi", ("ai", "timeout_s"), "intero", 120, "Attesa massima di una risposta dell'API.", minimo=10, massimo=600),
    Voce("Motori AI", "errori_consecutivi_max", ("ai", "errori_max"), "intero", 3,
         "Dopo questo numero di errori di fila la lettura AI si ferma, per non consumare richieste.", minimo=1, massimo=50),
    Voce("Volti", "soglia_somiglianza", ("volti", "soglia_somiglianza"), "decimale", 0.363,
         "Più alta = gruppi più severi (meno errori, più gruppi). Più bassa = unisce di più.", minimo=0.1, massimo=0.9),
    Voce("Qualità", "megapixel_minimi", ("qualita", "megapixel_minimi"), "decimale", 6,
         "Sotto questa risoluzione la foto riceve un allarme di qualità.", minimo=0, massimo=500),
    Voce("Qualità", "luci_bruciate_max_pct", ("qualita", "luci_bruciate_max_pct"), "decimale", 5,
         "Percentuale massima di pixel bianchi pieni prima dell'allarme.", minimo=0, massimo=100),
    Voce("Viste", "vista_predefinita", ("viste", "predefinita"), "scelta", "cronologico",
         "Vista proposta dalla webapp. Valori: " + ", ".join(PRESET_VISTE), scelte=PRESET_VISTE),
    Voce("Webapp", "porta", ("webapp", "porta"), "intero", 8765, "Porta locale della webapp.", minimo=1024, massimo=65535),
    Voce("Aggiornamenti", "controlla_aggiornamenti", ("aggiornamenti", "controlla"), "sino", True,
         "Se sì, la webapp controlla una volta al giorno se su GitHub c'è una versione nuova."),
]
PER_CHIAVE = {v.chiave: v for v in SCHEMA}
RIGA = re.compile(r"^(\s*[-*]\s+`?)([a-z_]+)(`?\s*:\s*)(.*?)\s*$")


def _fmt(v):
    if isinstance(v, bool):
        return "sì" if v else "no"
    if isinstance(v, float):
        return format(v, "g")  # 6.0 -> "6", 0.363 -> "0.363"
    return str(v)


def converti(voce, testo):
    """Valore testuale -> valore tipizzato. Solleva ValueError con un messaggio in italiano."""
    t = testo.strip().strip("`").strip('"').strip("'").strip()
    if t == "":
        if voce.vuoto:
            return ""
        raise ValueError("valore mancante")
    if voce.tipo == "intero":
        v = int(t)
    elif voce.tipo == "decimale":
        v = float(t.replace(",", "."))
    elif voce.tipo == "sino":
        low = t.lower()
        if low in ("sì", "si", "s", "yes", "true", "1", "vero"):
            return True
        if low in ("no", "n", "false", "0", "falso"):
            return False
        raise ValueError("scrivi sì oppure no")
    elif voce.tipo == "url":
        if not re.match(r"^https?://\S+$", t):
            raise ValueError("deve iniziare con http:// o https://")
        v = t.rstrip("/")
    elif voce.tipo == "scelta":
        if t not in voce.scelte:
            raise ValueError("valori ammessi: " + ", ".join(voce.scelte))
        v = t
    else:
        if voce.chiave in ("prefisso",) and not re.match(r"^[A-Za-z0-9]{1,10}$", t):
            raise ValueError("solo lettere e numeri, massimo 10")
        if t.lower().startswith("nvapi-") or re.match(r"^sk-[A-Za-z0-9]{16,}", t):
            raise ValueError("sembra una chiave API: non scriverla nel file, usa  archivio chiave imposta")
        v = t
    if voce.minimo is not None and v < voce.minimo:
        raise ValueError(f"minimo {voce.minimo}")
    if voce.massimo is not None and v > voce.massimo:
        raise ValueError(f"massimo {voce.massimo}")
    return v


def modello_md(valori=None, versione=1):
    valori = valori or {}
    out = ["# Configurazione di ArchivioFoto", "",
           "> Tutte le scelte del programma stanno in questo file. Modifica solo il testo dopo i due punti delle righe `- nome: valore`.",
           "> Il resto è spiegazione e puoi aggiungere note tue. Il file viene controllato a ogni avvio: un valore non valido",
           "> blocca i comandi con un messaggio che indica la riga. Ogni modifica è annotata in REGISTRO.md.",
           "> Le chiavi API NON vanno scritte qui: stanno nel portachiavi del sistema (`archivio chiave imposta`).", "",
           f"- versione_configurazione: {versione}", ""]
    sezione = None
    for v in SCHEMA:
        if v.sezione != sezione:
            sezione = v.sezione
            out += [f"## {sezione}", ""]
        out.append(f"- {v.chiave}: {_fmt(valori.get(v.chiave, v.default))}")
        out.append(f"  > {v.aiuto}")
    return "\n".join(out) + "\n"


def leggi_valori(root):
    """Restituisce (valori grezzi per chiave con numero di riga, versione, righe del file)."""
    p = root / FILE
    righe = p.read_text(encoding="utf-8").splitlines()
    trovati, versione = {}, 1
    for i, r in enumerate(righe, start=1):
        m = RIGA.match(r)
        if not m:
            continue
        k, val = m.group(2), m.group(4)
        if k == "versione_configurazione":
            try:
                versione = int(val)
            except ValueError:
                pass
        else:
            trovati[k] = (val, i)
    return trovati, versione, righe


def carica(root, rigoroso=True):
    """Configurazione tipizzata nella forma usata dal programma (cfg["ai"]["modello"], ...).
    rigoroso=False sostituisce i valori non validi con il default (serve alla webapp per poterli correggere)."""
    migra_json(root)
    from . import note
    trovati, versione, _ = leggi_valori(root)
    cfg = {"_versione": versione, "_problemi": []}
    for v in SCHEMA:
        val = v.default
        if v.chiave in trovati:
            testo, riga = trovati[v.chiave]
            try:
                val = converti(v, testo)
            except ValueError as e:
                msg = f"{FILE} riga {riga}, '{v.chiave}': {e}"
                cfg["_problemi"].append(msg)
                note.registra(root, "errore", msg, "configurazione")
        d = cfg
        for k in v.percorso[:-1]:
            d = d.setdefault(k, {})
        d[v.percorso[-1]] = val
    for k, (_, riga) in trovati.items():
        if k not in PER_CHIAVE:
            note.registra(root, "attenzione", f"{FILE} riga {riga}: impostazione sconosciuta '{k}' (ignorata)", "configurazione")
    if cfg["_problemi"] and rigoroso:
        raise ErroreArchivio("configurazione non valida — correggi CONFIGURAZIONE.md o usa la pagina Impostazioni:\n  "
                             + "\n  ".join(cfg["_problemi"]))
    return cfg


def valori_correnti(root):
    """Valori testuali per chiave (per la webapp)."""
    trovati, _, _ = leggi_valori(root)
    return {v.chiave: trovati.get(v.chiave, (_fmt(v.default), 0))[0] for v in SCHEMA}


def imposta(root, modifiche, origine="riga di comando"):
    """Valida e scrive le modifiche nel file preservando commenti e note; incrementa la versione e registra."""
    errori = []
    tipizzati = {}
    for k, testo in modifiche.items():
        if k not in PER_CHIAVE:
            errori.append(f"'{k}': impostazione sconosciuta")
            continue
        try:
            tipizzati[k] = converti(PER_CHIAVE[k], str(testo))
        except ValueError as e:
            errori.append(f"'{k}': {e}")
    if errori:
        raise ErroreArchivio("valori non validi: " + "; ".join(errori))
    trovati, versione, righe = leggi_valori(root)
    cambi = []
    for k, val in tipizzati.items():
        nuovo = _fmt(val)
        if k in trovati:
            vecchio, n = trovati[k]
            try:
                uguale = converti(PER_CHIAVE[k], vecchio) == val
            except ValueError:
                uguale = False  # il vecchio valore non era valido: va comunque riscritto
            if uguale:
                continue
            m = RIGA.match(righe[n - 1])
            righe[n - 1] = f"{m.group(1)}{k}{m.group(3)}{nuovo}"
        else:
            vecchio = "(assente)"
            righe += ["", f"- {k}: {nuovo}", f"  > {PER_CHIAVE[k].aiuto}"]
        cambi.append(f"{k}: {vecchio or '(vuoto)'} → {nuovo or '(vuoto)'}")
    if not cambi:
        return []
    versione += 1
    for i, r in enumerate(righe):
        m = RIGA.match(r)
        if m and m.group(2) == "versione_configurazione":
            righe[i] = f"{m.group(1)}versione_configurazione{m.group(3)}{versione}"
            break
    else:
        righe.insert(0, f"- versione_configurazione: {versione}")
    p = root / FILE
    tmp = p.with_suffix(".tmp")
    tmp.write_text("\n".join(righe) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    registro.scrivi(root, "configurazione", f"v{versione} ({origine}): " + "; ".join(cambi))
    return cambi


def crea(root, valori=None):
    p = root / FILE
    if not p.exists():
        p.write_text(modello_md(valori), encoding="utf-8")


def migra_json(root):
    """Archivi creati con la 0.2/0.3: converte archivio.json in CONFIGURAZIONE.md una volta sola."""
    vecchio = root / VECCHIO_JSON
    if (root / FILE).exists() or not vecchio.exists():
        return
    try:
        j = json.loads(vecchio.read_text(encoding="utf-8"))
    except Exception:
        j = {}
    valori = {}
    for v in SCHEMA:
        d = j
        try:
            for k in v.percorso:
                d = d[k]
            valori[v.chiave] = d
        except (KeyError, TypeError):
            pass
    crea(root, valori)
    os.replace(vecchio, root / (VECCHIO_JSON + ".migrato"))
    registro.scrivi(root, "configurazione", f"migrata da {VECCHIO_JSON} a {FILE}")
