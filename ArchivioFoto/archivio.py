#!/usr/bin/env python3
"""ArchivioFoto: digitalizzazione e catalogazione di un archivio di negativi.

Principi:
- il file master ha un ID immutabile (PREFISSO-ANNO-Rrrr-Fff) e non viene mai rinominato;
- i dati stanno in un JSON per foto (dati/<id>.json) + sidecar XMP leggibile da Lightroom/digiKam;
- ogni dato ha una provenienza: "fisico" e "umano" (inseriti da te), "tecnico" (misurato), "ai" (dedotto);
- le "rinomine" sono viste (cartelle di link) generate da modelli, rigenerabili in qualsiasi momento.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ExifTags

Image.MAX_IMAGE_PIXELS = None  # le scansioni a 4000+ dpi superano il limite di default

CONFIG_FILE = "archivio.json"
IMG_EXT = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".dng", ".nef", ".cr2", ".cr3", ".arw", ".orf", ".raf", ".rw2"}
RAW_EXT = {".dng", ".nef", ".cr2", ".cr3", ".arw", ".orf", ".raf", ".rw2"}

DEFAULT_CONFIG = {
    "prefisso": "ARC",
    "ai": {
        # Qualsiasi endpoint OpenAI-compatibile: NVIDIA build.nvidia.com, OpenRouter, Ollama, LM Studio...
        "base_url": "https://integrate.api.nvidia.com/v1",
        # Serve un modello VISIONE: i Nemotron 3 solo testo (es. nemotron-3-super) non leggono le immagini.
        "modello": "nvidia/nemotron-nano-12b-v2-vl",
        "chiave_env": "NVIDIA_API_KEY",
        "lato_max_px": 1024,
        "timeout_s": 120,
    },
}

AI_PROMPT = """Analizza questa fotografia d'archivio (scansione di negativo) e rispondi SOLO con un oggetto JSON con queste chiavi:
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


# ---------------------------------------------------------------- utilità

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_root(start=None):
    p = Path(start or os.getcwd()).resolve()
    for d in [p, *p.parents]:
        if (d / CONFIG_FILE).exists():
            return d
    sys.exit(f"Nessun archivio trovato (manca {CONFIG_FILE}). Esegui prima: archivio.py init <cartella>")


def load_config(root):
    cfg = json.loads((root / CONFIG_FILE).read_text(encoding="utf-8"))
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update({k: v for k, v in cfg.items() if k != "ai"})
    merged["ai"].update(cfg.get("ai", {}))
    return merged


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def data_path(root, pid):
    return root / "dati" / f"{pid}.json"


def load_rec(root, pid):
    return json.loads(data_path(root, pid).read_text(encoding="utf-8"))


def save_rec(root, rec):
    rec["aggiornato"] = now()
    p = data_path(root, rec["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def all_ids(root):
    return sorted(p.stem for p in (root / "dati").glob("*.json"))


def select_ids(root, args):
    ids = all_ids(root)
    if getattr(args, "rullino", None) is not None:
        tag = f"-R{int(args.rullino):03d}-"
        ids = [i for i in ids if tag in i]
    if getattr(args, "id", None):
        ids = [i for i in ids if i in set(args.id)]
    return ids


def open_image(path):
    """Apre TIFF/JPEG/PNG con Pillow, i RAW con rawpy se installato."""
    if path.suffix.lower() in RAW_EXT:
        try:
            import rawpy
        except ImportError:
            raise RuntimeError("file RAW: installa 'rawpy' (pip install rawpy) per analizzarlo")
        with rawpy.imread(str(path)) as raw:
            return Image.fromarray(raw.postprocess(use_camera_wb=True, output_bps=8)), {}
    im = Image.open(path)
    exif = {}
    try:
        for k, v in im.getexif().items():
            name = ExifTags.TAGS.get(k, str(k))
            if isinstance(v, (str, int, float)):
                exif[name] = v.strip("\x00 ") if isinstance(v, str) else v
    except Exception:
        pass
    return im, exif


def preview(im, max_side):
    im = im.copy()
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        a = np.asarray(im, dtype=np.float32)
        im = Image.fromarray((a / max(a.max(), 1) * 255).astype(np.uint8))
    im.thumbnail((max_side, max_side))
    return im.convert("RGB")


# ---------------------------------------------------------------- comandi

def cmd_init(args):
    root = Path(args.cartella).resolve()
    for sub in ("master", "dati", "viste"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    cfgp = root / CONFIG_FILE
    if not cfgp.exists():
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        cfg["prefisso"] = args.prefisso
        cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Archivio pronto in {root}")


def cmd_ingest(args):
    root = find_root()
    cfg = load_config(root)
    src = Path(args.sorgente)
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in IMG_EXT and p.is_file())
    if not files:
        sys.exit(f"Nessuna immagine in {src}")
    known = {}
    for pid in all_ids(root):
        known[load_rec(root, pid)["file"]["sha256"]] = pid
    anno = args.anno or "0000"
    for n, f in enumerate(files, start=args.primo):
        pid = f"{cfg['prefisso']}-{anno}-R{args.rullino:03d}-F{n:02d}"
        dest = root / "master" / f"{pid}{f.suffix.lower()}"
        digest = sha256(f)
        if digest in known:
            print(f"  salto {f.name}: già in archivio come {known[digest]}")
            continue
        if dest.exists() or data_path(root, pid).exists():
            sys.exit(f"ID {pid} già usato: controlla rullino/--primo. Nessun file sovrascritto.")
        if args.dry_run:
            print(f"  {f.name} -> {dest.name}")
            continue
        shutil.copy2(f, dest)
        if sha256(dest) != digest:
            dest.unlink()
            sys.exit(f"Copia corrotta di {f.name}: interrotto.")
        os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # master in sola lettura
        rec = {
            "id": pid,
            "file": {"nome": dest.name, "originale": f.name, "sha256": digest,
                     "byte": dest.stat().st_size, "importato": now()},
            "fisico": {k: v for k, v in {
                "rullino": args.rullino, "fotogramma": n, "busta": args.busta,
                "formato": args.formato, "pellicola": args.pellicola, "anno": args.anno,
            }.items() if v not in (None, "")},
            "tecnico": {}, "ai": {}, "umano": {},
        }
        save_rec(root, rec)
        known[digest] = pid
        print(f"  {f.name} -> {pid}")
    print("Ingest completato." if not args.dry_run else "Prova a vuoto: nessun file copiato.")


def technical(im, exif):
    w, h = im.size
    out = {"larghezza": w, "altezza": h, "megapixel": round(w * h / 1e6, 1),
           "modo": im.mode, "orientamento": "orizzontale" if w > h else "verticale" if h > w else "quadrato"}
    dpi = im.info.get("dpi")
    if dpi and float(dpi[0]) >= 50:  # alcuni TIFF riportano 1 dpi = valore assente
        out["dpi"] = round(float(dpi[0]))
    out["bit_per_canale"] = 16 if im.mode.startswith("I;16") or im.mode == "I" else 8
    if exif:
        out["exif_scanner"] = {k: exif[k] for k in ("Make", "Model", "Software", "DateTime") if k in exif}

    rgb = preview(im, 1024)
    a = np.asarray(rgb, dtype=np.float32) / 255.0
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    mean_sat = float(sat.mean())
    out["bianco_nero"] = bool(mean_sat < 0.06)
    out["saturazione_media"] = round(mean_sat, 3)
    out["luminosita_media"] = round(float(lum.mean()), 3)
    out["contrasto"] = round(float(lum.std()), 3)
    out["ombre_chiuse_pct"] = round(float((lum < 0.02).mean() * 100), 1)
    out["luci_bruciate_pct"] = round(float((lum > 0.98).mean() * 100), 1)
    m = out["luminosita_media"]
    out["esposizione"] = "sottoesposta" if m < 0.25 else "sovraesposta" if m > 0.75 else "corretta"

    # Nitidezza: varianza del laplaciano sulla luminanza (valori bassi = mosso/sfocato)
    L = lum * 255
    lap = (-4 * L[1:-1, 1:-1] + L[:-2, 1:-1] + L[2:, 1:-1] + L[1:-1, :-2] + L[1:-1, 2:])
    var = float(lap.var())
    out["nitidezza"] = round(var, 1)
    out["nitidezza_giudizio"] = "nitida" if var > 300 else "discreta" if var > 80 else "morbida_o_mossa"

    # Negativo non invertito? Maschera arancione: rosso >> blu e immagine chiara
    r, g, b = (float(a[..., i].mean()) for i in range(3))
    out["negativo_non_invertito_probabile"] = bool(r > b + 0.15 and m > 0.45 and not out["bianco_nero"])
    r_b = r - b
    out["dominante"] = "calda" if r_b > 0.05 else "fredda" if r_b < -0.05 else "neutra"

    q = rgb.resize((200, int(200 * rgb.height / rgb.width) or 1)).quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    out["palette"] = [{"hex": "#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]),
                       "pct": round(c / total * 100, 1)} for c, i in counts]
    return out


def cmd_analizza(args):
    root = find_root()
    ids = select_ids(root, args)
    for pid in ids:
        rec = load_rec(root, pid)
        if rec.get("tecnico") and not args.forza:
            continue
        try:
            im, exif = open_image(root / "master" / rec["file"]["nome"])
            rec["tecnico"] = technical(im, exif) | {"analizzato": now()}
            save_rec(root, rec)
            t = rec["tecnico"]
            print(f"  {pid}: {'B/N' if t['bianco_nero'] else 'colore'}, {t['esposizione']}, {t['nitidezza_giudizio']}")
        except Exception as e:
            print(f"  {pid}: ERRORE {e}")


def call_ai(cfg, img):
    ai = cfg["ai"]
    key = os.environ.get(ai["chiave_env"], "")
    if not key and "integrate.api.nvidia.com" in ai["base_url"]:
        raise RuntimeError(f"variabile d'ambiente {ai['chiave_env']} mancante")
    buf = io.BytesIO()
    preview(img, ai["lato_max_px"]).save(buf, "JPEG", quality=85)
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    body = {
        "model": ai["modello"], "temperature": 0, "max_tokens": 1500,
        "messages": [
            {"role": "system", "content": "Sei un archivista fotografico. Rispondi solo con JSON valido."},
            {"role": "user", "content": [{"type": "text", "text": AI_PROMPT},
                                         {"type": "image_url", "image_url": {"url": data_url}}]},
        ],
    }
    if "nemotron" in ai["modello"].lower():
        # Nemotron ragiona per default: disattivato per avere solo il JSON, più veloce ed economico
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(
        ai["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=ai["timeout_s"]) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200].decode(errors='replace')}")
    text = resp["choices"][0]["message"].get("content") or ""
    return parse_json(text)


def parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise RuntimeError(f"risposta non JSON: {text[:120]!r}")
    return json.loads(m.group(0))


def cmd_ai(args):
    root = find_root()
    cfg = load_config(root)
    if args.modello:
        cfg["ai"]["modello"] = args.modello
    for pid in select_ids(root, args):
        rec = load_rec(root, pid)
        if rec.get("ai") and not args.forza:
            continue
        try:
            im, _ = open_image(root / "master" / rec["file"]["nome"])
            res = call_ai(cfg, im)
            rec["ai"] = res | {"modello": cfg["ai"]["modello"], "analizzato": now()}
            save_rec(root, rec)
            print(f"  {pid}: {res.get('tipo_scatto')} - {res.get('descrizione', '')[:70]}")
        except Exception as e:
            print(f"  {pid}: ERRORE {e}")


def split_list(v):
    return [x.strip() for x in re.split(r"[;,]", v) if x.strip()]


def cmd_annota(args):
    """Importa le annotazioni delle buste da CSV (colonne: rullino, [fotogramma], data, luogo, evento, persone, note, ...)."""
    root = find_root()
    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        sample = f.read(2048)
        f.seek(0)
        reader = csv.DictReader(f, dialect=csv.Sniffer().sniff(sample, delimiters=",;\t"))
        rows = list(reader)
    fisici = {"busta", "pellicola", "formato", "anno"}
    n = 0
    for row in rows:
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if not row.get("rullino"):
            continue
        rull = int(row.pop("rullino"))
        frame = row.pop("fotogramma", "")
        for pid in all_ids(root):
            rec = load_rec(root, pid)
            if rec["fisico"].get("rullino") != rull:
                continue
            if frame and rec["fisico"].get("fotogramma") != int(frame):
                continue
            for k, v in row.items():
                if not v:
                    continue
                if k in fisici:
                    rec["fisico"][k] = v
                else:
                    rec["umano"][k] = split_list(v) if k in ("persone", "tag") else v
            rec["umano"]["fonte"] = "annotazione busta"
            save_rec(root, rec)
            n += 1
    print(f"Annotazioni applicate a {n} foto.")


def cmd_imposta(args):
    """Correzione manuale di un campo 'umano' su una o più foto (ha sempre la precedenza sull'AI)."""
    root = find_root()
    ids = select_ids(root, args)
    for pid in ids:
        rec = load_rec(root, pid)
        for kv in args.campo:
            k, _, v = kv.partition("=")
            rec["umano"][k.strip()] = split_list(v) if k.strip() in ("persone", "tag") else v.strip()
        rec["umano"]["verificato"] = True
        save_rec(root, rec)
    print(f"Aggiornate {len(ids)} foto.")


def merged(rec):
    """Vista piatta con precedenza umano > fisico > ai > tecnico."""
    f, t, a, u = rec["fisico"], rec["tecnico"], rec["ai"], rec["umano"]
    data = u.get("data") or ""
    anno = (data[:4] if re.match(r"\d{4}", data) else "") or str(f.get("anno") or "")
    return {
        "id": rec["id"], "anno": anno or "senza-anno", "data": data or anno or "senza-data",
        "rullino": f"R{f.get('rullino', 0):03d}", "fotogramma": f"F{f.get('fotogramma', 0):02d}",
        "busta": f.get("busta", ""), "formato": f.get("formato", ""), "pellicola": f.get("pellicola", ""),
        "luogo": u.get("luogo", ""), "evento": u.get("evento", ""),
        "persone": "+".join(u.get("persone", [])) if isinstance(u.get("persone"), list) else u.get("persone", ""),
        "tipo": u.get("tipo_scatto") or a.get("tipo_scatto") or "non-classificato",
        "ambiente": a.get("ambiente", ""), "epoca": a.get("epoca_stimata", ""),
        "soggetto": (a.get("soggetti") or [""])[0],
        "colore": "" if not t else ("bn" if t.get("bianco_nero") else "colore"),
        "esposizione": t.get("esposizione", ""), "nitidezza": t.get("nitidezza_giudizio", ""),
        "descrizione": u.get("descrizione") or a.get("descrizione", ""),
        "tag": sorted(set(u.get("tag", []) + a.get("tag", []))),
    }


def slug(s):
    s = re.sub(r"[^\w\-+'. ]", "", str(s), flags=re.UNICODE).strip().replace(" ", "-")
    return s[:60] or "x"


PRESET = {
    "cronologico": "{anno}/{data}_{luogo}_{id}",
    "luogo": "{luogo}/{anno}/{id}",
    "tipologia": "{tipo}/{anno}/{id}_{soggetto}",
    "persone": "{persone}/{anno}/{id}",
    "fisico": "{busta}/{rullino}/{id}",
    "tecnico": "{colore}/{esposizione}/{id}",
}


def cmd_viste(args):
    root = find_root()
    schema = PRESET.get(args.schema, args.schema)
    name = args.nome or (args.schema if args.schema in PRESET else "personalizzata")
    out = root / "viste" / slug(name)
    if out.exists():
        shutil.rmtree(out)  # le viste sono sempre rigenerabili: i master non vengono mai toccati
    n = 0
    for pid in all_ids(root):
        rec = load_rec(root, pid)
        m = merged(rec)
        try:
            rel = schema.format(**{k: slug(v) if v not in ("", []) else "senza-" + k for k, v in m.items()})
        except KeyError as e:
            sys.exit(f"Campo sconosciuto nello schema: {e}. Campi: {', '.join(m)}")
        src = root / "master" / rec["file"]["nome"]
        dest = out / (rel + src.suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if args.modo == "copia":
            shutil.copy2(src, dest)
        elif args.modo == "symlink":
            dest.symlink_to(os.path.relpath(src, dest.parent))
        else:
            try:
                os.link(src, dest)  # hard link: nessuno spazio extra
            except OSError:
                shutil.copy2(src, dest)
        n += 1
    print(f"Vista '{name}' creata in {out} ({n} foto, schema {schema})")


def xmp_for(rec):
    m = merged(rec)
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    bag = "".join(f"<rdf:li>{esc(t)}</rdf:li>" for t in m["tag"] + ([m["tipo"]] if m["tipo"] else []))
    people = rec["umano"].get("persone", [])
    people = people if isinstance(people, list) else split_list(people)
    pbag = "".join(f"<rdf:li>{esc(p)}</rdf:li>" for p in people)
    date = rec["umano"].get("data", "")
    return f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
    xmlns:Iptc4xmpCore="http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/"
    xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
    photoshop:DateCreated="{esc(date)}"
    photoshop:City="{esc(m['luogo'])}"
    Iptc4xmpCore:Location="{esc(m['luogo'])}">
   <dc:identifier>{esc(rec['id'])}</dc:identifier>
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{esc(m['evento'] or rec['id'])}</rdf:li></rdf:Alt></dc:title>
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{esc(m['descrizione'])}</rdf:li></rdf:Alt></dc:description>
   <dc:subject><rdf:Bag>{bag}</rdf:Bag></dc:subject>
   <Iptc4xmpExt:PersonInImage><rdf:Bag>{pbag}</rdf:Bag></Iptc4xmpExt:PersonInImage>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


def cmd_xmp(args):
    root = find_root()
    ids = select_ids(root, args)
    for pid in ids:
        rec = load_rec(root, pid)
        (root / "master" / f"{pid}.xmp").write_text(xmp_for(rec), encoding="utf-8")
    print(f"Scritti {len(ids)} sidecar XMP in master/ (leggibili da Lightroom, digiKam, Bridge).")


def cmd_cerca(args):
    root = find_root()
    terms = [t.lower() for t in args.testo]
    for pid in all_ids(root):
        rec = load_rec(root, pid)
        blob = json.dumps({k: rec[k] for k in ("fisico", "ai", "umano")}, ensure_ascii=False).lower()
        if all(t in blob for t in terms):
            m = merged(rec)
            print(f"{pid}  {m['data']}  {m['luogo']}  {m['tipo']}  {m['descrizione'][:60]}")


def cmd_esporta(args):
    root = find_root()
    rows = [merged(load_rec(root, pid)) for pid in all_ids(root)]
    if not rows:
        sys.exit("Archivio vuoto.")
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow(r | {"tag": ", ".join(r["tag"])})
    print(f"Esportate {len(rows)} righe in {args.csv}")


def cmd_stato(args):
    root = find_root()
    ids = all_ids(root)
    recs = [load_rec(root, i) for i in ids]
    print(f"Foto: {len(ids)}")
    print(f"  analisi tecnica: {sum(bool(r['tecnico']) for r in recs)}")
    print(f"  analisi AI:      {sum(bool(r['ai']) for r in recs)}")
    print(f"  annotate:        {sum(bool(r['umano']) for r in recs)}")
    print(f"  verificate:      {sum(bool(r['umano'].get('verificato')) for r in recs)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="archivio.py", description=__doc__.splitlines()[0])
    sp = p.add_subparsers(dest="cmd", required=True)

    def sel(q):
        q.add_argument("--rullino", type=int, help="limita a un rullino")
        q.add_argument("--id", action="append", help="limita a questo ID (ripetibile)")
        return q

    q = sp.add_parser("init", help="crea un nuovo archivio")
    q.add_argument("cartella")
    q.add_argument("--prefisso", default="ARC")
    q.set_defaults(fn=cmd_init)

    q = sp.add_parser("ingest", help="importa le scansioni di un rullino assegnando gli ID")
    q.add_argument("sorgente")
    q.add_argument("--rullino", type=int, required=True)
    q.add_argument("--anno")
    q.add_argument("--busta")
    q.add_argument("--formato", default="35mm")
    q.add_argument("--pellicola")
    q.add_argument("--primo", type=int, default=1, help="numero del primo fotogramma")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(fn=cmd_ingest)

    q = sel(sp.add_parser("analizza", help="lettura tecnica (colori, esposizione, nitidezza, B/N)"))
    q.add_argument("--forza", action="store_true")
    q.set_defaults(fn=cmd_analizza)

    q = sel(sp.add_parser("ai", help="lettura semantica tramite API visione OpenAI-compatibile"))
    q.add_argument("--forza", action="store_true")
    q.add_argument("--modello")
    q.set_defaults(fn=cmd_ai)

    q = sp.add_parser("annota", help="importa le annotazioni delle buste da CSV")
    q.add_argument("csv")
    q.set_defaults(fn=cmd_annota)

    q = sel(sp.add_parser("imposta", help="correzione manuale: campo=valore"))
    q.add_argument("campo", nargs="+")
    q.set_defaults(fn=cmd_imposta)

    q = sp.add_parser("viste", help=f"crea una vista rinominata: preset {', '.join(PRESET)} o schema libero")
    q.add_argument("schema")
    q.add_argument("--nome")
    q.add_argument("--modo", choices=["link", "copia", "symlink"], default="link")
    q.set_defaults(fn=cmd_viste)

    q = sel(sp.add_parser("xmp", help="scrive i sidecar XMP/IPTC"))
    q.set_defaults(fn=cmd_xmp)

    q = sp.add_parser("cerca", help="ricerca testuale nei dati")
    q.add_argument("testo", nargs="+")
    q.set_defaults(fn=cmd_cerca)

    q = sp.add_parser("esporta", help="esporta l'indice in CSV")
    q.add_argument("csv")
    q.set_defaults(fn=cmd_esporta)

    sp.add_parser("stato", help="riepilogo avanzamento").set_defaults(fn=cmd_stato)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
