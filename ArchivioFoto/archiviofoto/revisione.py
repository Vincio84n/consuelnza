"""Webapp locale: revisione dei rullini, note e allarmi, guida con suggerimenti, tutorial e assistente."""
import html
import json
import mimetypes
import os
import re
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, aiuto, configurazione, istruzioni, note, registro
from .core import LIST_FIELDS, ErroreArchivio, all_ids, load_config, load_rec, save_rec, select_ids, split_list, thumbnail
from .lavori import Lavori

CAMPI = [
    ("data", "Data", "Formato AAAA-MM-GG, oppure solo AAAA-MM o AAAA se non conosci il giorno."),
    ("luogo", "Luogo", "Città o località. Diventa il campo {luogo} delle viste e la località nell'XMP."),
    ("evento", "Evento", "Occasione dello scatto: matrimonio, gita, Ferragosto… Diventa il titolo nell'XMP."),
    ("persone", "Persone", "Nomi separati da virgola. Si aggiungono a quelli dati ai gruppi di volti."),
    ("tipo_scatto", "Tipo di scatto", "Sostituisce la classificazione dell'AI. Lascia vuoto per tenere quella dell'AI."),
    ("descrizione", "Descrizione", "Se compilata sostituisce quella dell'AI, in ricerca e nell'XMP."),
    ("tag", "Tag", "Parole chiave separate da virgola. Si sommano a quelle dell'AI."),
    ("note", "Note", "Appunti liberi sulla foto, ad esempio lo stato del negativo."),
]
TIPI = ["", "ritratto", "gruppo", "paesaggio", "architettura", "interno", "evento", "street", "still_life", "documento", "altro"]
LIVELLI_AIUTO = {
    "errore": "Qualcosa non è stato fatto: va risolto e poi chiuso.",
    "attenzione": "Da controllare: potrebbe essere un problema.",
    "qualita": "Problema della singola foto: valuta se riscansionare.",
    "nota": "Appunto inserito da te.",
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


STATO = {"token": "", "aggiornamento": None}


def pagina(titolo, corpo, root, nome="pagina"):
    n = len(note.aperte(root))
    avvisi = ""
    cfg = load_config(root, rigoroso=False)
    if cfg["_problemi"]:
        avvisi += ('<div class="banner errore">Configurazione non valida: ' + esc("; ".join(cfg["_problemi"]))
                   + ' — <a href="/impostazioni">correggi nelle Impostazioni</a></div>')
    agg = STATO.get("aggiornamento")
    if agg and agg.get("nuova"):
        avvisi += (f'<div class="banner">È disponibile ArchivioFoto {esc(agg["versione"])} (in uso {__version__}). '
                   f'<a href="{esc(agg["pagina"])}" target="_blank" rel="noopener">Novità e download</a></div>')
    # ogni form POST porta il token di sessione: un sito esterno non può inviare richieste alla webapp
    corpo = re.sub(r'(<form method="post"[^>]*>)', lambda m: m.group(1) + f'<input type="hidden" name="_t" value="{STATO["token"]}">', corpo)
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="token" content="{STATO['token']}"><title>{esc(titolo)} · ArchivioFoto</title><link rel="stylesheet" href="/static/app.css"></head>
<body data-pagina="{nome}"><header data-tour="Questa barra è sempre in alto: da qui raggiungi rullini, lavori, note, impostazioni, istruzioni, registro e guida." data-tour-titolo="Barra di navigazione" data-tour-ordine="0">
<strong>ArchivioFoto</strong><nav><a href="/">Rullini</a><a href="/lavori" data-aiuto="Esegui importazione, analisi, AI, volti e XMP senza usare il terminale.">Lavori</a>
<a href="/note" data-aiuto="Errori, avvisi, problemi di qualità e note tue: tutto ciò che va guardato.">Note ({n})</a>
<a href="/impostazioni" data-aiuto="Motori NVIDIA, chiave API e tutte le scelte, salvate in CONFIGURAZIONE.md.">Impostazioni</a>
<a href="/istruzioni" data-aiuto="Le tue indicazioni per l'AI, salvate in ISTRUZIONI.md.">Istruzioni</a><a href="/registro">Registro</a><a href="/guida">Guida</a></nav>
<span class="spazio"></span>
<button id="btn-aiuti" class="sec" aria-pressed="true" title="Attiva o disattiva le finestre di suggerimento">Suggerimenti: sì</button>
<button id="btn-tour" class="sec" title="Visita guidata di questa pagina">Tutorial</button>
<button id="btn-guida" title="Guida e assistente (tasto /)" data-tour="Cerca negli articoli della guida o fai una domanda all'assistente. Si apre anche con il tasto /." data-tour-titolo="Guida e assistente" data-tour-ordine="99">? Guida</button>
<button id="btn-esci" class="sec" title="Chiude la webapp">Esci</button>
<span class="mut">v{__version__}</span></header>
{avvisi}<main>{corpo}</main>
<aside id="pannello" class="pannello" aria-hidden="true" aria-label="Guida e assistente">
<div class="testa"><strong>Guida e assistente</strong><button id="btn-chiudi-guida" class="sec" aria-label="Chiudi">✕</button></div>
<div class="corpo"></div>
<div class="piede"><form id="form-chiedi"><input id="q" placeholder="Cerca o chiedi: come rinomino per luogo?" autocomplete="off" aria-label="Cerca nella guida o chiedi all'assistente"><button>Chiedi</button></form>
<div class="mut">Mentre scrivi, cerca negli articoli. <strong>Chiedi</strong> invia la domanda all'assistente AI.</div></div></aside>
<script src="/static/app.js"></script></body></html>"""


def campi_html(u, prefix=""):
    out = []
    for k, label, aiuto_txt in CAMPI:
        v = u.get(k, "")
        if k in LIST_FIELDS:
            v = ", ".join(split_list(v))
        lab = f'<label data-aiuto="{esc(aiuto_txt)}">{label}</label>'
        if k == "tipo_scatto":
            opts = "".join(f'<option{" selected" if t == v else ""}>{t}</option>' for t in TIPI)
            out.append(f'{lab}<select name="{prefix}{k}">{opts}</select>')
        elif k in ("descrizione", "note"):
            out.append(f'{lab}<textarea name="{prefix}{k}" rows="2">{esc(v)}</textarea>')
        else:
            out.append(f'{lab}<input name="{prefix}{k}" value="{esc(v)}">')
    return "".join(out)


def passi_html(root):
    items = []
    for p in aiuto.prossimi_passi(root):
        azione = f' <code>{esc(p["comando"])}</code>' if p.get("comando") else ""
        if p.get("link"):
            azione += f' <a href="{esc(p["link"])}">apri</a>'
        items.append(f'<li>{esc(p["testo"])}{azione} <a href="#" data-guida="{esc(p["guida"])}" class="mut">come si fa?</a></li>')
    return "".join(items)


def make_handler(root):
    lavori = Lavori()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _host_ok(self):
            # protezione da DNS rebinding: si accetta solo l'indirizzo locale
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return host in ("127.0.0.1", "localhost", "::1")

        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

        def _redirect(self, to):
            self.send_response(303)
            self.send_header("Location", to)
            self.end_headers()

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, "host non consentito", "text/plain")
            try:
                self._get()
            except Exception as e:
                note.registra(root, "errore", f"webapp: {e}", "revisione")
                self._send(500, pagina("Errore", f'<p class="errore">{esc(e)}</p>', root))

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, "host non consentito", "text/plain")
            try:
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n).decode()
                if self.path.startswith("/api/"):
                    if not secrets.compare_digest(self.headers.get("X-Token", ""), STATO["token"]):
                        return self._json(403, {"errore": "sessione scaduta: ricarica la pagina"})
                    return self._api(json.loads(raw or "{}"))
                form = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
                if not secrets.compare_digest(form.pop("_t", ""), STATO["token"]):
                    return self._send(403, pagina("Sessione scaduta", "<p>Sessione scaduta: torna indietro e ricarica la pagina.</p>", root))
                self._post(form)
            except Exception as e:
                note.registra(root, "errore", f"webapp: {e}", "revisione")
                self._send(500, pagina("Errore", f'<p class="errore">{esc(e)}</p>', root))

        def _get(self):
            url = urllib.parse.urlparse(self.path)
            parts = [urllib.parse.unquote(p) for p in url.path.split("/") if p]
            if not parts:
                return self._send(200, self.home())
            if parts[0] == "static" and len(parts) == 2:
                f = aiuto.WEB / parts[1]
                if f.parent != aiuto.WEB or not f.is_file():
                    return self._send(404, "non trovato", "text/plain")
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/j")) else ""))
            if parts[0] == "r" and len(parts) == 2:
                return self._send(200, self.rullino(int(parts[1])))
            if parts[0] == "img" and len(parts) == 2:
                size = int(urllib.parse.parse_qs(url.query).get("s", ["480"])[0])
                if parts[1] not in all_ids(root):
                    return self._send(404, "non trovato", "text/plain")
                return self._send(200, thumbnail(root, load_rec(root, parts[1]), min(size, 2000)).read_bytes(), "image/jpeg")
            if parts[0] == "note":
                return self._send(200, self.note_page())
            if parts[0] == "guida":
                return self._send(200, self.guida_page())
            if parts[0] == "api" and parts[1:] == ["passi"]:
                return self._json(200, aiuto.prossimi_passi(root))
            if parts[0] == "api" and parts[1:] == ["lavoro"]:
                return self._json(200, lavori.istantanea())
            if parts[0] == "impostazioni":
                return self._send(200, self.impostazioni_page())
            if parts[0] == "istruzioni":
                return self._send(200, self.istruzioni_page())
            if parts[0] == "registro":
                return self._send(200, self.registro_page())
            if parts[0] == "lavori":
                return self._send(200, self.lavori_page())
            self._send(404, pagina("Non trovato", "<p>Pagina non trovata</p>", root))

        def _api(self, data):
            if self.path == "/api/chiedi":
                domanda = str(data.get("domanda", "")).strip()
                if not domanda:
                    return self._json(400, {"errore": "domanda vuota"})
                try:
                    return self._json(200, aiuto.chiedi(root, domanda, data.get("storia")))
                except ErroreArchivio as e:
                    note.registra(root, "attenzione", f"assistente della guida: {e}", "revisione")
                    return self._json(200, {"errore": str(e)})
            if self.path == "/api/modelli":
                from . import motori
                try:
                    return self._json(200, {"modelli": motori.elenca(load_config(root, rigoroso=False))})
                except ErroreArchivio as e:
                    return self._json(200, {"errore": str(e)})
            if self.path == "/api/prova":
                from . import motori
                ruolo = data.get("ruolo") if data.get("ruolo") in ("visione", "testo") else "visione"
                esito = motori.prova(load_config(root, rigoroso=False), ruolo, data.get("modello") or None)
                registro.scrivi(root, "motori", f"prova {ruolo} {esito['modello']} dalla webapp: {esito['dettaglio'][:120]}",
                                "ok" if esito["ok"] else "errore")
                if not esito["ok"]:
                    note.registra(root, "errore", f"prova motore {ruolo} {esito['modello']}: {esito['dettaglio']}", "motori")
                return self._json(200, esito)
            if self.path == "/api/sfoglia":
                from .app import scegli_cartella
                return self._json(200, {"cartella": scegli_cartella("Cartella con le scansioni del rullino") or ""})
            if self.path == "/api/esci":
                registro.scrivi(root, "app", "webapp chiusa dall'utente")
                self._json(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self._json(404, {"errore": "non trovato"})

        def _post(self, form):
            if self.path == "/salva":
                rec = load_rec(root, form["id"])
                for k, _, _ in CAMPI:
                    v = form.get(k, "").strip()
                    if v:
                        rec["umano"][k] = split_list(v) if k in LIST_FIELDS else v
                    else:
                        rec["umano"].pop(k, None)
                rec["umano"]["verificato"] = "verificato" in form
                save_rec(root, rec)
                return self._redirect(f"/r/{rec['fisico']['rullino']}#{rec['id']}")
            if self.path == "/salva-rullino":
                r = int(form["rullino"])
                vals = {k: form.get("r_" + k, "").strip() for k, _, _ in CAMPI}
                for pid in all_ids(root):
                    rec = load_rec(root, pid)
                    if rec["fisico"].get("rullino") != r:
                        continue
                    for k, v in vals.items():
                        if v:
                            rec["umano"][k] = split_list(v) if k in LIST_FIELDS else v
                    save_rec(root, rec)
                return self._redirect(f"/r/{r}")
            if self.path == "/risolvi":
                note.risolvi(root, numeri={int(form["n"])})
                return self._redirect("/note")
            if self.path == "/impostazioni":
                mod = {k: v for k, v in form.items() if k in configurazione.PER_CHIAVE}
                try:
                    cambi = configurazione.imposta(root, mod, "webapp")
                    note.risolvi(root, comando="configurazione")
                    msg = ("Salvato: " + "; ".join(cambi)) if cambi else "Nessuna modifica."
                    return self._send(200, self.impostazioni_page(msg))
                except ErroreArchivio as e:
                    return self._send(200, self.impostazioni_page(str(e), errore=True, valori=mod))
            if self.path == "/chiave":
                from . import chiavi
                ai = load_config(root, rigoroso=False)["ai"]
                try:
                    if form.get("azione") == "rimuovi":
                        chiavi.rimuovi(ai)
                        registro.scrivi(root, "chiave", f"chiave '{ai['nome_chiave']}' rimossa dalla webapp")
                        msg = "Chiave rimossa dal portachiavi."
                    else:
                        chiavi.salva(ai, form.get("chiave", ""))
                        registro.scrivi(root, "chiave", f"chiave '{ai['nome_chiave']}' salvata dalla webapp ({chiavi.mascherata(form['chiave'].strip())})")
                        msg = "Chiave salvata nel portachiavi del sistema. Ora premi «Prova»."
                    return self._send(200, self.impostazioni_page(msg))
                except ErroreArchivio as e:
                    return self._send(200, self.impostazioni_page(str(e), errore=True))
            if self.path == "/istruzioni":
                vecchia = istruzioni.carica(root)["versione"]
                p = root / istruzioni.FILE
                tmp = p.with_suffix(".tmp")
                tmp.write_text(form.get("testo", "").replace("\r\n", "\n"), encoding="utf-8")
                os.replace(tmp, p)
                nuova = istruzioni.carica(root)["versione"]
                if nuova != vecchia:
                    registro.scrivi(root, "istruzioni", f"modificate dalla webapp: versione {vecchia} → {nuova}")
                return self._send(200, self.istruzioni_page("Salvato." + (" Le foto già lette ora risultano da rileggere." if nuova != vecchia else "")))
            if self.path == "/lavori/avvia":
                return self._avvia_lavoro(form)
            if self.path == "/nota":
                if form.get("messaggio", "").strip():
                    note.registra(root, "nota", form["messaggio"].strip(), "revisione", form.get("id") or None)
                return self._redirect("/note")
            self._send(404, "non trovato", "text/plain")

        def home(self):
            rull = {}
            for pid in all_ids(root):
                rec = load_rec(root, pid)
                r = rull.setdefault(rec["fisico"].get("rullino"), {"n": 0, "ver": 0, "busta": rec["fisico"].get("busta", ""),
                                                                   "anno": rec["fisico"].get("anno", ""), "luogo": ""})
                r["n"] += 1
                r["ver"] += bool(rec["umano"].get("verificato"))
                r["luogo"] = r["luogo"] or rec["umano"].get("luogo", "")
            rows = "".join(
                f'<tr><td><a href="/r/{k}">R{k:03d}</a></td><td>{esc(v["busta"])}</td><td>{esc(v["anno"])}</td>'
                f'<td>{esc(v["luogo"])}</td><td>{v["n"]}</td><td class="{"ok" if v["ver"] == v["n"] else ""}">{v["ver"]}/{v["n"]}</td></tr>'
                for k, v in sorted(rull.items()))
            corpo = f"""<section class="card" data-tour="Il prossimo passo da fare, calcolato sullo stato reale dell'archivio. Con «come si fa?» apri la guida su quel punto." data-tour-titolo="Cosa fare adesso" data-tour-ordine="1">
<h2 data-aiuto="Si aggiorna da solo: mostra cosa manca, in ordine di priorità.">Cosa fare adesso</h2><ol class="passi">{passi_html(root)}</ol></section>
<h2 style="margin-top:18px">Rullini</h2>
<div class="tabella" data-tour="Ogni riga è un rullino. Clicca sul numero per rivedere le sue foto. «Verificate» indica quante schede hai già confermato." data-tour-titolo="Elenco rullini" data-tour-ordine="2">
<table><tr><th>Rullino</th><th>Busta</th><th>Anno</th><th>Luogo</th><th>Foto</th><th data-aiuto="Foto confermate a mano con la spunta «verificata». In verde i rullini completi.">Verificate</th></tr>{rows}</table></div>"""
            return pagina("Rullini", corpo, root, "home")

        def rullino(self, r):
            recs = [load_rec(root, pid) for pid in all_ids(root) if f"-R{r:03d}-" in pid]
            if not recs:
                return pagina("Rullino", "<p>Rullino vuoto</p>", root)
            common = {k: v for k, v in recs[0]["umano"].items() if all(x["umano"].get(k) == v for x in recs)}
            cards = []
            for i, rec in enumerate(recs):
                t, a, u = rec["tecnico"], rec["ai"], rec["umano"]
                tour = (lambda txt, tit, o: f' data-tour="{esc(txt)}" data-tour-titolo="{esc(tit)}" data-tour-ordine="{o}"') if i == 0 else (lambda *_: "")
                pal = "".join(f'<span style="background:{p["hex"]}" title="{p["hex"]} · {p["pct"]}%"></span>' for p in t.get("palette", []))
                tech = (f'{"B/N" if t.get("bianco_nero") else "colore"} · {t.get("esposizione", "")} · {t.get("nitidezza_giudizio", "")}'
                        if t else "analisi tecnica non eseguita")
                alarms = "".join(f'<div class="{x["livello"]}" data-aiuto="{esc(LIVELLI_AIUTO[x["livello"]])} Chiudilo dalla pagina Note e allarmi.">⚠ {esc(x["messaggio"])}</div>'
                                 for x in note.aperte(root, pid=rec["id"]))
                ai = (f'<div class="mut"><span data-aiuto="Lettura del modello AI. Le tue correzioni nei campi qui sotto hanno sempre la precedenza.">AI</span>: '
                      f'{esc(a.get("tipo_scatto", ""))} — {esc(a.get("descrizione", ""))}</div>') if a else ""
                faces = rec.get("volti", [])
                volti = (f'<div class="mut"><span data-aiuto="Volti rilevati in locale. Dai un nome a un gruppo con: archivio volti nomina G001 &quot;Nome&quot;">Volti</span>: {len(faces)} '
                         + ", ".join(esc(f.get("nome") or f.get("gruppo") or "?") for f in faces) + "</div>") if faces else ""
                cards.append(f"""<div class="card" id="{rec['id']}"{tour("Ogni scheda è una foto. Clicca la miniatura per vederla grande.", "Scheda della foto", 3)}>
<a href="/img/{rec['id']}?s=1800" target="_blank"><img loading="lazy" src="/img/{rec['id']}?s=480" alt="{rec['id']}"></a>
<div><strong data-aiuto="ID immutabile: archivio-anno-rullino-fotogramma. Il file master non viene mai rinominato.">{rec['id']}</strong> <span class="mut">{esc(rec['file'].get('originale', ''))}</span></div>
<div class="mut"{tour("Dati misurati dall'analisi tecnica: colore o B/N, esposizione, nitidezza e i 6 colori principali.", "Lettura tecnica", 4)}>{tech} <span class="pal">{pal}</span></div>{ai}{volti}{alarms}
<form method="post" action="/salva"{tour("Correggi o completa i dati, poi Salva. Un campo vuoto toglie il dato. Le tue correzioni battono sempre l'AI.", "Correzioni", 5)}>
<input type="hidden" name="id" value="{rec['id']}">{campi_html(u)}
<label{tour("Spunta quando la scheda è corretta: serve a tenere il conto di cosa resta da rivedere.", "Verificata", 6)}><input type="checkbox" name="verificato" style="width:auto"{" checked" if u.get("verificato") else ""}> verificata</label>
<button>Salva</button></form></div>""")
            corpo = f"""<h2>Rullino R{r:03d} <span class="mut">{len(recs)} foto</span></h2>
<details class="card" data-tour="Compila qui i dati comuni a tutto il rullino (es. luogo ed evento della busta): vengono applicati a tutte le foto, solo i campi compilati." data-tour-titolo="Applica a tutto il rullino" data-tour-ordine="2">
<summary data-aiuto="Imposta in un colpo solo i campi comuni a tutte le foto del rullino.">Applica a tutto il rullino</summary>
<form method="post" action="/salva-rullino"><input type="hidden" name="rullino" value="{r}">{campi_html(common, "r_")}<button>Applica a {len(recs)} foto</button></form></details>
<div class="grid" style="margin-top:14px">{''.join(cards)}</div>"""
            return pagina(f"Rullino R{r:03d}", corpo, root, "rullino")

        def note_page(self):
            items = sorted(note.aperte(root), key=lambda x: (list(LIVELLI_AIUTO).index(x["livello"]), x["n"]))

            def foto(x):
                if not x.get("id"):
                    return ""
                try:
                    return f'<a href="/r/{int(x["id"].split("-R")[1][:3])}#{esc(x["id"])}">{esc(x["id"])}</a>'
                except (IndexError, ValueError):
                    return esc(x["id"])
            rows = "".join(
                f'<tr><td>{x["n"]}</td><td class="{x["livello"]}"><span data-aiuto="{esc(LIVELLI_AIUTO[x["livello"]])}">{x["livello"]}</span></td><td>{esc(x["comando"])}</td>'
                f'<td>{foto(x)}</td><td>{esc(x["messaggio"])}{" (×%d)" % x["ripetuta"] if x.get("ripetuta") else ""}</td><td class="mut">{esc(x["quando"][:16])}</td>'
                f'<td><form method="post" action="/risolvi"><input type="hidden" name="n" value="{x["n"]}"><button class="sec">Chiudi</button></form></td></tr>'
                for x in items)
            corpo = f"""<h2>Note e allarmi aperti ({len(items)}) <a href="#" data-guida="note" class="mut" style="font-size:14px">come funzionano?</a></h2>
<form method="post" action="/nota" class="card" data-tour="Scrivi un appunto, anche legato a una foto tramite il suo ID: resterà qui finché non lo chiudi." data-tour-titolo="Nuova nota" data-tour-ordine="1">
<label data-aiuto="Un promemoria tuo: busta rovinata, negativo da riscansionare, dubbio su una data…">Nuova nota</label><input name="messaggio">
<label data-aiuto="Facoltativo, ad esempio ARC-1987-R042-F07">ID foto</label><input name="id"><button>Aggiungi</button></form>
<div class="tabella" style="margin-top:14px" data-tour="Ordinati per gravità: prima gli errori, poi gli avvisi, la qualità e le note. «Chiudi» quando il problema è risolto." data-tour-titolo="Elenco" data-tour-ordine="2">
<table><tr><th>#</th><th>Livello</th><th>Comando</th><th>Foto</th><th>Messaggio</th><th>Quando</th><th></th></tr>{rows}</table></div>"""
            return pagina("Note e allarmi", corpo, root, "note")

        def guida_page(self):
            cats = {}
            for a in aiuto.articoli():
                cats.setdefault(a["categoria"], []).append(a)
            indice = "".join(f'<h3>{esc(c)}</h3><ul>' + "".join(f'<li><a href="#" data-guida="{a["id"]}">{esc(a["titolo"])}</a></li>' for a in arts) + "</ul>"
                             for c, arts in cats.items())
            corpo = f"""<h2>Guida</h2><div class="grid"><div class="card" data-tour="Tutti gli articoli, per argomento. Clicca un titolo per leggerlo nel pannello a destra." data-tour-titolo="Indice della guida" data-tour-ordine="1">{indice}</div>
<div class="card"><h3>Come usare l'aiuto</h3><ul>
<li><strong>Suggerimenti</strong>: passa sopra agli elementi con ⓘ. Si attivano e disattivano dal pulsante in alto.</li>
<li><strong>Tutorial</strong>: visita guidata della pagina in cui ti trovi.</li>
<li><strong>? Guida</strong> o tasto <code>/</code>: cerca negli articoli mentre scrivi; <strong>Chiedi</strong> invia la domanda all'assistente AI.</li></ul>
<h3>Cosa fare adesso</h3><ol class="passi">{passi_html(root)}</ol></div></div>"""
            return pagina("Guida", corpo, root, "guida")

        def impostazioni_page(self, msg="", errore=False, valori=None):
            from . import chiavi
            cfg = load_config(root, rigoroso=False)
            correnti = configurazione.valori_correnti(root) | (valori or {})
            chiave, fonte = chiavi.leggi(cfg["ai"])
            sezioni, sezione, campi = [], None, []
            for v in configurazione.SCHEMA:
                if v.sezione != sezione:
                    if campi:
                        sezioni.append((sezione, campi))
                    sezione, campi = v.sezione, []
                val = correnti.get(v.chiave, "")
                if v.tipo == "scelta" or v.tipo == "sino":
                    opzioni = v.scelte if v.tipo == "scelta" else ("sì", "no")
                    ctrl = f'<select name="{v.chiave}">' + "".join(f'<option{" selected" if o == val else ""}>{o}</option>' for o in opzioni) + "</select>"
                else:
                    lista = ' list="modelli"' if v.chiave.startswith("modello_") else ""
                    ctrl = f'<input name="{v.chiave}" value="{esc(val)}"{lista}>'
                campi.append(f'<label data-aiuto="{esc(v.aiuto)}">{esc(v.chiave.replace("_", " "))}</label>{ctrl}')
            sezioni.append((sezione, campi))
            form = "".join(f'<fieldset class="card"><legend>{esc(n)}</legend>{"".join(c)}</fieldset>' for n, c in sezioni)
            stato_chiave = (f'<span class="ok">impostata {esc(chiavi.mascherata(chiave))}</span> <span class="mut">({esc(fonte)})</span>' if chiave
                            else ('<span class="mut">non serve per un motore locale</span>' if not chiavi.richiesta(cfg["ai"]) else '<span class="errore">non impostata</span>'))
            avviso = f'<div class="banner {"errore" if errore else "ok"}">{esc(msg)}</div>' if msg else ""
            corpo = f"""<h2>Impostazioni <span class="mut">CONFIGURAZIONE.md · versione {cfg['_versione']}</span></h2>{avviso}
<p class="mut">Tutto ciò che salvi qui viene scritto in <code>{esc(root / configurazione.FILE)}</code> e annotato nel Registro. Puoi anche modificare il file a mano.</p>
<div class="grid">
<section class="card" data-tour="La chiave API NVIDIA si salva nel portachiavi del sistema (Windows o macOS), mai nei file dell'archivio. Si crea su build.nvidia.com." data-tour-titolo="Chiave API" data-tour-ordine="1">
<h3>Chiave API</h3><p>Stato: {stato_chiave}</p>
<form method="post" action="/chiave"><label data-aiuto="Inizia con nvapi-. Si crea gratis su build.nvidia.com. Non viene mai mostrata né scritta nei file.">Nuova chiave</label>
<input type="password" name="chiave" autocomplete="off" placeholder="nvapi-..."><button>Salva chiave</button></form>
<form method="post" action="/chiave"><input type="hidden" name="azione" value="rimuovi"><button class="sec">Rimuovi chiave</button></form></section>
<section class="card" data-tour="Prova i motori con una chiamata vera: vedi se funzionano, quanto ci mettono e cosa rispondono. Carica l'elenco per scegliere tra i modelli disponibili." data-tour-titolo="Prova dei motori" data-tour-ordine="2">
<h3>Motori AI</h3><p class="mut">Visione: <code>{esc(cfg['ai']['modello'])}</code><br>Testo: <code>{esc(cfg['ai']['modello_testo'])}</code><br>Riserva: <code>{esc(cfg['ai']['modello_riserva'] or '—')}</code></p>
<button class="sec" id="btn-modelli">Carica elenco modelli</button> <button id="btn-prova-visione">Prova visione</button> <button id="btn-prova-testo">Prova testo</button>
<div id="esito-motori" class="mut" style="margin-top:8px"></div><div id="elenco-modelli" class="mut"></div></section></div>
<datalist id="modelli"></datalist>
<form method="post" action="/impostazioni" data-tour="Tutte le scelte, divise per sezione. Passa sopra ai nomi per la spiegazione. «Salva» controlla i valori: se uno non va bene, non viene salvato nulla." data-tour-titolo="Configurazione" data-tour-ordine="3">
<div class="grid" style="margin-top:14px">{form}</div><button>Salva impostazioni</button></form>"""
            return pagina("Impostazioni", corpo, root, "impostazioni")

        def istruzioni_page(self, msg=""):
            p = root / istruzioni.FILE
            if not p.exists():
                istruzioni.crea(root)
            istr = istruzioni.carica(root)
            vecchie = sum(1 for pid in all_ids(root) if (a := load_rec(root, pid)["ai"]) and a.get("istruzioni") != istr["versione"])
            avviso = f'<div class="banner ok">{esc(msg)}</div>' if msg else ""
            rilettura = (f'<form method="post" action="/lavori/avvia"><input type="hidden" name="lavoro" value="ai"><input type="hidden" name="obsolete" value="1">'
                         f'<button>Rileggi le {vecchie} foto</button></form>') if vecchie else ""
            corpo = f"""<h2>Istruzioni <span class="mut">ISTRUZIONI.md · versione {istr['versione']}</span></h2>{avviso}
<div class="grid"><section class="card" data-tour="Quello che il programma ha capito del file: contesto, regole e vocabolario passati all'AI a ogni lettura." data-tour-titolo="Riepilogo" data-tour-ordine="1">
<h3>Cosa usa il programma</h3><p><strong>Contesto:</strong> {esc(istr['contesto']) or '<span class=mut>(vuoto)</span>'}</p>
<p><strong>Regole:</strong> {len(istr['regole'])} · <strong>Vocabolario:</strong> {len(istr['vocabolario'])} termini · <strong>Tag vietati:</strong> {len(istr['vietati'])}</p>
<p data-aiuto="Le foto lette con una versione diversa delle istruzioni possono avere tag o descrizioni non allineati.">Foto lette con istruzioni diverse: <strong>{vecchie}</strong></p>{rilettura}</section>
<section class="card"><h3>Come si scrive</h3><ul><li><strong>Contesto</strong>: testo libero su chi, dove, quando.</li>
<li><strong>Regole</strong>: una per riga, con il trattino.</li><li><strong>Vocabolario</strong>: <code>- termine: sinonimo, sinonimo</code></li>
<li>Le righe con <code>&gt;</code> sono spiegazioni, ignorate.</li></ul></section></div>
<form method="post" action="/istruzioni" data-tour="Modifica il file qui, oppure con un editor di testo: sono la stessa cosa. Salvando, la modifica viene annotata nel Registro." data-tour-titolo="Modifica" data-tour-ordine="2">
<label>{esc(p)}</label><textarea name="testo" rows="24" style="font-family:ui-monospace,Consolas,monospace">{esc(p.read_text(encoding="utf-8"))}</textarea><button>Salva istruzioni</button></form>"""
            return pagina("Istruzioni", corpo, root, "istruzioni")

        def registro_page(self):
            righe = registro.ultime(root, 400)[::-1]

            def fmt(r):
                r = esc(r[2:])
                r = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", r)
                cls = "errore" if r.endswith("✖") else "attenzione" if r.endswith("⚠") else ""
                return f'<li class="{cls}">{r}</li>'
            corpo = f"""<h2>Registro <span class="mut">REGISTRO.md · ultime {len(righe)} operazioni, dalla più recente</span></h2>
<p class="mut" data-tour="Ogni operazione e ogni modifica di configurazione o istruzioni lascia qui una riga: data, versione del programma, comando, dettagli ed esito (✔ ✖ ⚠)." data-tour-titolo="Diario" data-tour-ordine="1">File: <code>{esc(root / registro.FILE)}</code></p>
<ul class="registro">{"".join(fmt(r) for r in righe) or "<li>Registro vuoto.</li>"}</ul>"""
            return pagina("Registro", corpo, root, "registro")

        def lavori_page(self):
            rullini = sorted({load_rec(root, pid)["fisico"].get("rullino") for pid in all_ids(root)})
            opz = '<option value="">tutti</option>' + "".join(f'<option value="{r}">R{r:03d}</option>' for r in rullini)
            sel = f'<label>Rullino</label><select name="rullino">{opz}</select>'
            preset = "".join(f"<option>{p}</option>" for p in configurazione.PRESET_VISTE)

            def scheda(nome, titolo, aiuto_txt, campi="", tour=""):
                return (f'<form method="post" action="/lavori/avvia" class="card"{tour}><input type="hidden" name="lavoro" value="{nome}">'
                        f'<h3 data-aiuto="{esc(aiuto_txt)}">{titolo}</h3>{campi}<button>Avvia</button></form>')
            corpo = f"""<h2>Lavori</h2>
<section class="card" id="stato-lavoro" data-tour="Qui vedi il lavoro in corso: avanzamento e messaggi in tempo reale. Si esegue un lavoro alla volta; tutto finisce anche nel Registro." data-tour-titolo="Avanzamento" data-tour-ordine="2">
<strong id="lav-titolo">Nessun lavoro in corso</strong><progress id="lav-barra" max="1" value="0" style="width:100%"></progress><pre id="lav-log" class="log"></pre></section>
<div class="grid" style="margin-top:14px" data-tour="Ogni scheda avvia un comando, come dal terminale. Ordine consigliato: Importa, Analizza, Lettura AI, Volti, poi XMP e Viste." data-tour-titolo="Comandi" data-tour-ordine="1">
{scheda("ingest", "1 · Importa rullino", "Copia le scansioni nell'archivio assegnando gli ID. I file originali non vengono toccati.",
        '<label>Cartella delle scansioni</label><div class="riga-input"><input name="cartella" id="cartella" required><button type="button" class="sec" id="btn-sfoglia">Sfoglia…</button></div>'
        '<label>Numero rullino</label><input name="rullino" type="number" min="1" required><label>Anno</label><input name="anno" placeholder="AAAA">'
        '<label>Busta</label><input name="busta"><label>Pellicola</label><input name="pellicola">')}
{scheda("analizza", "2 · Analisi tecnica", "Colori, esposizione, nitidezza e allarmi di qualità.", sel)}
{scheda("ai", "3 · Lettura AI", "Usa il modello di visione e le tue Istruzioni. Richiede la chiave API.", sel + '<label><input type="checkbox" name="obsolete" value="1" style="width:auto"> rileggi le foto lette con istruzioni vecchie</label>')}
{scheda("volti", "4 · Volti", "Rileva e raggruppa i volti, in locale.", sel)}
{scheda("xmp", "5 · XMP", "Scrive i dati per Lightroom e digiKam.")}
{scheda("viste", "6 · Viste", "Rigenera le cartelle rinominate.", f'<label>Vista</label><select name="schema">{preset}</select>')}
{scheda("verifica", "Controllo completo", "Ambiente, chiave, master, integrità.", '<label><input type="checkbox" name="hash" value="1" style="width:auto"> verifica hash (lento)</label>')}
{scheda("doppioni", "Cerca doppioni", "Scansioni doppie o quasi identiche.")}
</div>"""
            return pagina("Lavori", corpo, root, "lavori")

        def _avvia_lavoro(self, form):
            lav = form.get("lavoro")
            r = form.get("rullino", "").strip()
            sel = ["--rullino", r] if r else []
            totale = len(select_ids(root, int(r) if r else None))
            if lav == "ingest":
                argv = ["ingest", form.get("cartella", ""), "--rullino", r]
                for k in ("anno", "busta", "pellicola"):
                    if form.get(k, "").strip():
                        argv += [f"--{k}", form[k].strip()]
                comandi, totale = [argv], 0
            elif lav == "analizza":
                comandi = [["analizza"] + sel]
            elif lav == "ai":
                comandi = [["ai"] + sel + (["--obsolete"] if form.get("obsolete") else [])]
            elif lav == "volti":
                comandi, totale = [["volti", "rileva"] + sel, ["volti", "raggruppa"]], totale
            elif lav == "xmp":
                comandi, totale = [["xmp"]], 0
            elif lav == "viste":
                comandi, totale = [["viste", form.get("schema", "cronologico")]], 0
            elif lav == "verifica":
                comandi, totale = [["verifica"] + (["--hash"] if form.get("hash") else [])], 0
            elif lav == "doppioni":
                comandi, totale = [["doppioni"]], 0
            else:
                return self._send(400, pagina("Errore", "<p>Lavoro sconosciuto</p>", root))
            if not lavori.avvia(lav, comandi, totale):
                return self._send(409, pagina("Occupato", '<p>C\'è già un lavoro in corso. <a href="/lavori">Guarda l\'avanzamento</a></p>', root))
            return self._redirect("/lavori")

    return H


def avvia(root, porta=8765, apri=True):
    STATO["token"] = secrets.token_urlsafe(24)
    srv = ThreadingHTTPServer(("127.0.0.1", porta), make_handler(root))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    try:
        controlla = load_config(root, rigoroso=False)["aggiornamenti"]["controlla"]
    except Exception:
        controlla = False
    if controlla:
        from .aggiornamenti import controlla_in_cache
        threading.Thread(target=lambda: STATO.update(aggiornamento=controlla_in_cache(root)), daemon=True).start()
    if apri:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    return srv, url
