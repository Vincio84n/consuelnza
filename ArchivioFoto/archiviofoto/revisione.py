"""Webapp locale: revisione dei rullini, note e allarmi, guida con suggerimenti, tutorial e assistente."""
import html
import json
import mimetypes
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, aiuto, note
from .core import LIST_FIELDS, ErroreArchivio, all_ids, load_rec, save_rec, split_list, thumbnail

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


def pagina(titolo, corpo, root, nome="pagina"):
    n = len(note.aperte(root))
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titolo)} · ArchivioFoto</title><link rel="stylesheet" href="/static/app.css"></head>
<body data-pagina="{nome}"><header data-tour="Questa barra è sempre in alto: da qui raggiungi i rullini, le note e la guida." data-tour-titolo="Barra di navigazione" data-tour-ordine="0">
<strong>ArchivioFoto</strong><nav><a href="/">Rullini</a><a href="/note" data-aiuto="Errori, avvisi, problemi di qualità e note tue: tutto ciò che va guardato.">Note e allarmi ({n})</a><a href="/guida">Guida</a></nav>
<span class="spazio"></span>
<button id="btn-aiuti" class="sec" aria-pressed="true" title="Attiva o disattiva le finestre di suggerimento">Suggerimenti: sì</button>
<button id="btn-tour" class="sec" title="Visita guidata di questa pagina">Tutorial</button>
<button id="btn-guida" title="Guida e assistente (tasto /)" data-tour="Cerca negli articoli della guida o fai una domanda all'assistente. Si apre anche con il tasto /." data-tour-titolo="Guida e assistente" data-tour-ordine="99">? Guida</button>
<span class="mut">v{__version__}</span></header>
<main>{corpo}</main>
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
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

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
            try:
                self._get()
            except Exception as e:
                note.registra(root, "errore", f"webapp: {e}", "revisione")
                self._send(500, pagina("Errore", f'<p class="errore">{esc(e)}</p>', root))

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n).decode()
                if self.path.startswith("/api/"):
                    return self._api(json.loads(raw or "{}"))
                form = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
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

    return H


def avvia(root, porta=8765, apri=True):
    srv = ThreadingHTTPServer(("127.0.0.1", porta), make_handler(root))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    if apri:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    return srv, url
