"""Interfaccia web locale per rivedere e correggere un rullino alla volta (si apre nel browser, funziona offline)."""
import html
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, note
from .core import all_ids, load_rec, save_rec, split_list, thumbnail, LIST_FIELDS

CAMPI = [("data", "Data (AAAA-MM-GG)"), ("luogo", "Luogo"), ("evento", "Evento"), ("persone", "Persone (separate da virgola)"),
         ("tipo_scatto", "Tipo di scatto"), ("descrizione", "Descrizione"), ("tag", "Tag"), ("note", "Note")]
TIPI = ["", "ritratto", "gruppo", "paesaggio", "architettura", "interno", "evento", "street", "still_life", "documento", "altro"]

CSS = """
:root{--bg:#f7f6f3;--fg:#1d1d1b;--mut:#6b6a65;--card:#fff;--bd:#dedcd5;--acc:#2f5d8a;--err:#b3261e;--warn:#9a6700;--ok:#2e7d32}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececea;--mut:#9d9c97;--card:#232326;--bd:#38383c;--acc:#7fb0e0;--err:#f2867e;--warn:#e0b44c;--ok:#7cc883}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{display:flex;gap:16px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--bd);flex-wrap:wrap}
header a{color:var(--acc);text-decoration:none}main{padding:16px;max-width:1400px;margin:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:10px}
.card img{width:100%;border-radius:4px;background:#0002}.mut{color:var(--mut);font-size:13px}
label{display:block;font-size:12px;color:var(--mut);margin-top:6px}input,select,textarea{width:100%;padding:5px 7px;border:1px solid var(--bd);border-radius:5px;background:var(--bg);color:var(--fg);font:inherit}
button{margin-top:8px;padding:6px 14px;border:0;border-radius:5px;background:var(--acc);color:#fff;font:inherit;cursor:pointer}
.ok{color:var(--ok)}.errore{color:var(--err)}.attenzione,.qualita{color:var(--warn)}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--bd);padding:6px;text-align:left;vertical-align:top}
.pal span{display:inline-block;width:16px;height:16px;border-radius:3px;margin-right:2px;border:1px solid var(--bd)}
"""


def esc(s):
    return html.escape(str(s if s is not None else ""))


def pagina(titolo, corpo, root):
    n = len(note.aperte(root))
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titolo)}</title><style>{CSS}</style></head><body><header><strong>ArchivioFoto</strong>
<a href="/">Rullini</a><a href="/note">Note e allarmi ({n})</a><span class="mut">v{__version__}</span></header><main>{corpo}</main></body></html>"""


def campi_html(u, prefix=""):
    out = []
    for k, label in CAMPI:
        v = u.get(k, "")
        if k in LIST_FIELDS:
            v = ", ".join(split_list(v))
        if k == "tipo_scatto":
            opts = "".join(f'<option{" selected" if t == v else ""}>{t}</option>' for t in TIPI)
            out.append(f'<label>{label}</label><select name="{prefix}{k}">{opts}</select>')
        elif k in ("descrizione", "note"):
            out.append(f'<label>{label}</label><textarea name="{prefix}{k}" rows="2">{esc(v)}</textarea>')
        else:
            out.append(f'<label>{label}</label><input name="{prefix}{k}" value="{esc(v)}">')
    return "".join(out)


def make_handler(root):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, to):
            self.send_response(303)
            self.send_header("Location", to)
            self.end_headers()

        def do_GET(self):
            try:
                self._get()
            except Exception as e:
                note.registra(root, "errore", f"revisione: {e}", "revisione")
                self._send(500, pagina("Errore", f'<p class="errore">{esc(e)}</p>', root))

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode(), keep_blank_values=True).items()}
                self._post(form)
            except Exception as e:
                note.registra(root, "errore", f"revisione: {e}", "revisione")
                self._send(500, pagina("Errore", f'<p class="errore">{esc(e)}</p>', root))

        def _get(self):
            url = urllib.parse.urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            if not parts:
                return self._send(200, self.home())
            if parts[0] == "r" and len(parts) == 2:
                return self._send(200, self.rullino(int(parts[1])))
            if parts[0] == "img" and len(parts) == 2:
                size = int(urllib.parse.parse_qs(url.query).get("s", ["480"])[0])
                pid = urllib.parse.unquote(parts[1])
                if pid not in all_ids(root):
                    return self._send(404, "non trovato", "text/plain")
                return self._send(200, thumbnail(root, load_rec(root, pid), min(size, 2000)).read_bytes(), "image/jpeg")
            if parts[0] == "note":
                return self._send(200, self.note_page())
            self._send(404, pagina("Non trovato", "<p>Pagina non trovata</p>", root))

        def _post(self, form):
            if self.path == "/salva":
                rec = load_rec(root, form["id"])
                for k, _ in CAMPI:
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
                vals = {k: form.get("r_" + k, "").strip() for k, _ in CAMPI}
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
            return pagina("Rullini", f"<h2>Rullini</h2><table><tr><th>Rullino</th><th>Busta</th><th>Anno</th><th>Luogo</th>"
                                     f"<th>Foto</th><th>Verificate</th></tr>{rows}</table>", root)

        def rullino(self, r):
            recs = [load_rec(root, pid) for pid in all_ids(root) if f"-R{r:03d}-" in pid]
            if not recs:
                return pagina("Rullino", "<p>Rullino vuoto</p>", root)
            common = {k: v for k, v in recs[0]["umano"].items() if all(x["umano"].get(k) == v for x in recs)}
            cards = []
            for rec in recs:
                t, a, u = rec["tecnico"], rec["ai"], rec["umano"]
                pal = "".join(f'<span style="background:{p["hex"]}" title="{p["pct"]}%"></span>' for p in t.get("palette", []))
                tech = (f'{"B/N" if t.get("bianco_nero") else "colore"} · {t.get("esposizione", "")} · {t.get("nitidezza_giudizio", "")}'
                        if t else "analisi tecnica non eseguita")
                alarms = "".join(f'<div class="{x["livello"]}">⚠ {esc(x["messaggio"])}</div>' for x in note.aperte(root, pid=rec["id"]))
                ai = f'<div class="mut">AI: {esc(a.get("tipo_scatto", ""))} — {esc(a.get("descrizione", ""))}</div>' if a else ""
                faces = [f for f in rec.get("volti", [])]
                volti = f'<div class="mut">Volti: {len(faces)} ' + ", ".join(esc(f.get("nome") or f.get("gruppo") or "?") for f in faces) + "</div>" if faces else ""
                cards.append(f"""<div class="card" id="{rec['id']}"><a href="/img/{rec['id']}?s=1800" target="_blank"><img loading="lazy" src="/img/{rec['id']}?s=480" alt=""></a>
<div><strong>{rec['id']}</strong> <span class="mut">{esc(rec['file'].get('originale', ''))}</span></div>
<div class="mut">{tech} <span class="pal">{pal}</span></div>{ai}{volti}{alarms}
<form method="post" action="/salva"><input type="hidden" name="id" value="{rec['id']}">{campi_html(u)}
<label><input type="checkbox" name="verificato" style="width:auto"{" checked" if u.get("verificato") else ""}> verificata</label>
<button>Salva</button></form></div>""")
            corpo = f"""<h2>Rullino R{r:03d}</h2><details class="card"><summary>Applica a tutto il rullino (compila solo i campi da impostare)</summary>
<form method="post" action="/salva-rullino"><input type="hidden" name="rullino" value="{r}">{campi_html(common, "r_")}<button>Applica a {len(recs)} foto</button></form></details>
<div class="grid" style="margin-top:14px">{''.join(cards)}</div>"""
            return pagina(f"Rullino R{r:03d}", corpo, root)

        def note_page(self):
            items = sorted(note.aperte(root), key=lambda x: (["errore", "attenzione", "qualita", "nota"].index(x["livello"]), x["n"]))
            rows = "".join(
                f'<tr><td>{x["n"]}</td><td class="{x["livello"]}">{x["livello"]}</td><td>{esc(x["comando"])}</td>'
                f'<td>{"<a href=/r/%d#%s>%s</a>" % (int(x["id"].split("-R")[1][:3]), esc(x["id"]), esc(x["id"])) if x.get("id") else ""}</td>'
                f'<td>{esc(x["messaggio"])}{" (×%d)" % x["ripetuta"] if x.get("ripetuta") else ""}</td><td class="mut">{esc(x["quando"][:16])}</td>'
                f'<td><form method="post" action="/risolvi"><input type="hidden" name="n" value="{x["n"]}"><button>Risolta</button></form></td></tr>'
                for x in items)
            return pagina("Note e allarmi", f"""<h2>Note e allarmi aperti ({len(items)})</h2>
<form method="post" action="/nota" class="card"><label>Nuova nota</label><input name="messaggio"><label>ID foto (facoltativo)</label><input name="id"><button>Aggiungi</button></form>
<table style="margin-top:14px"><tr><th>#</th><th>Livello</th><th>Comando</th><th>Foto</th><th>Messaggio</th><th>Quando</th><th></th></tr>{rows}</table>""", root)

    return H


def avvia(root, porta=8765, apri=True):
    srv = ThreadingHTTPServer(("127.0.0.1", porta), make_handler(root))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    if apri:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    return srv, url
