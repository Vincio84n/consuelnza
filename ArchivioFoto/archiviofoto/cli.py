"""Riga di comando: archivio <comando> ..."""
import argparse
import csv
import importlib.util
import json
import os
import platform
import shutil
import sys
import traceback
from pathlib import Path

from . import __version__, configurazione, istruzioni, note, registro
from .analisi import allarmi_qualita, distanza, technical
from .core import (IMG_EXT, LIST_FIELDS, ErroreArchivio, all_ids, console_utf8,
                   data_path, find_root, is_readonly, load_config, load_rec, master_path, merged, now, open_image, save_rec,
                   select_ids, set_readonly, sha256, slug, split_list)


def _ids(root, args):
    return select_ids(root, getattr(args, "rullino", None), getattr(args, "id", None))


def _fallimento(root, cmd, pid, e):
    """Errore su una singola foto: lo segnala e lo registra nelle note, poi il comando prosegue."""
    msg = str(e) if isinstance(e, ErroreArchivio) else f"{type(e).__name__}: {e}"
    note.registra(root, "errore", msg, cmd, pid)
    print(f"  {pid}: ERRORE {msg}")


# ---------------------------------------------------------------- archivio

def cmd_init(args):
    root = Path(args.cartella).resolve()
    for sub in ("master", "dati", "viste"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    nuovo = not (root / configurazione.FILE).exists()
    configurazione.crea(root, {"prefisso": args.prefisso})
    istruzioni.crea(root)
    if nuovo:
        registro.scrivi(root, "init", f"archivio creato in {root}")
    print(f"Archivio pronto in {root}")
    print(f"  {configurazione.FILE}: le scelte del programma · {istruzioni.FILE}: le tue indicazioni per l'AI · {registro.FILE}: il diario")


def cmd_ingest(args):
    root = find_root()
    cfg = load_config(root)
    src = Path(args.sorgente)
    if not src.is_dir():
        raise ErroreArchivio(f"cartella sorgente inesistente: {src}")
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in IMG_EXT and p.is_file())
    if not files:
        raise ErroreArchivio(f"nessuna immagine in {src}")
    known = {load_rec(root, pid)["file"]["sha256"]: pid for pid in all_ids(root)}
    anno = args.anno or "0000"
    for n, f in enumerate(files, start=args.primo):
        pid = f"{cfg['prefisso']}-{anno}-R{args.rullino:03d}-F{n:02d}"
        dest = root / "master" / f"{pid}{f.suffix.lower()}"
        digest = sha256(f)
        if digest in known:
            note.registra(root, "attenzione", f"{f} già in archivio come {known[digest]}: saltato", "ingest", known[digest])
            print(f"  salto {f.name}: già in archivio come {known[digest]}")
            continue
        if dest.exists() or data_path(root, pid).exists():
            raise ErroreArchivio(f"ID {pid} già usato: controlla rullino/--primo. Nessun file sovrascritto.")
        if args.dry_run:
            print(f"  {f.name} -> {dest.name}")
            continue
        shutil.copy2(f, dest)
        if sha256(dest) != digest:
            dest.unlink()
            raise ErroreArchivio(f"copia corrotta di {f.name}: controlla il disco. Interrotto.")
        set_readonly(dest)
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
    nuovi = sum(1 for pid in known.values() if f"-R{args.rullino:03d}-" in pid)
    registro.esito(f"rullino R{args.rullino:03d} da {src}: {nuovi} foto in archivio")
    print("Ingest completato." if not args.dry_run else "Prova a vuoto: nessun file copiato.")


def cmd_analizza(args):
    root = find_root()
    cfg = load_config(root)
    fatte = 0
    for pid in _ids(root, args):
        rec = load_rec(root, pid)
        if rec.get("tecnico") and not args.forza:
            continue
        try:
            im, exif = open_image(master_path(root, rec))
            rec["tecnico"] = technical(im, exif) | {"analizzato": now()}
            save_rec(root, rec)
            note.risolvi(root, pid=pid, comando="analizza")  # i vecchi allarmi vengono sostituiti dai nuovi
            for msg in allarmi_qualita(rec["tecnico"], cfg):
                note.registra(root, "qualita", msg, "analizza", pid)
            t = rec["tecnico"]
            fatte += 1
            print(f"  {pid}: {'B/N' if t['bianco_nero'] else 'colore'}, {t['esposizione']}, {t['nitidezza_giudizio']}")
        except Exception as e:
            _fallimento(root, "analizza", pid, e)
    registro.esito(f"{fatte} foto analizzate")


def cmd_ai(args):
    from .ai import call_ai
    root = find_root()
    cfg = load_config(root)
    istr = istruzioni.carica(root)
    fatte, riserva, errori_di_fila = 0, 0, 0
    for pid in _ids(root, args):
        rec = load_rec(root, pid)
        if rec.get("ai") and not args.forza:
            if not (args.obsolete and rec["ai"].get("istruzioni") != istr["versione"]):
                continue
        try:
            im, _ = open_image(master_path(root, rec))
            res, usato = call_ai(cfg, im, istr, args.modello)
            rec["ai"] = res | {"modello": usato, "istruzioni": istr["versione"], "analizzato": now()}
            save_rec(root, rec)
            note.risolvi(root, pid=pid, comando="ai")
            errori_di_fila = 0
            fatte += 1
            if usato != (args.modello or cfg["ai"]["modello"]):
                riserva += 1
                note.registra(root, "attenzione", f"letta con il modello di riserva {usato}", "ai", pid)
            print(f"  {pid}: {res.get('tipo_scatto')} - {str(res.get('descrizione', ''))[:70]}")
        except Exception as e:
            _fallimento(root, "ai", pid, e)
            errori_di_fila += 1
            if errori_di_fila >= cfg["ai"]["errori_max"]:
                registro.esito(f"{fatte} foto lette prima dell'interruzione")
                raise ErroreArchivio(f"{errori_di_fila} errori AI consecutivi: interrotto. Controlla chiave, modello e rete con  archivio motori prova")
    registro.esito(f"{fatte} foto lette con {args.modello or cfg['ai']['modello']} (istruzioni {istr['versione']})"
                   + (f", {riserva} con il modello di riserva" if riserva else ""))


def cmd_annota(args):
    """Importa le annotazioni delle buste da CSV (colonne: rullino, [fotogramma], data, luogo, evento, persone, note, ...)."""
    root = find_root()
    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = "excel"
        rows = list(csv.DictReader(f, dialect=dialect))
    fisici = {"busta", "pellicola", "formato", "anno"}
    recs = {pid: load_rec(root, pid) for pid in all_ids(root)}
    toccati = set()
    for riga, row in enumerate(rows, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        try:
            rull = int(row.pop("rullino", ""))
        except ValueError:
            note.registra(root, "attenzione", f"{args.csv} riga {riga}: rullino mancante o non numerico", "annota")
            continue
        frame = row.pop("fotogramma", "")
        trovati = [r for r in recs.values() if r["fisico"].get("rullino") == rull
                   and (not frame or r["fisico"].get("fotogramma") == int(frame))]
        if not trovati:
            note.registra(root, "attenzione", f"{args.csv} riga {riga}: nessuna foto per rullino {rull} {frame}", "annota")
        for rec in trovati:
            for k, v in row.items():
                if not v:
                    continue
                if k in fisici:
                    rec["fisico"][k] = v
                else:
                    rec["umano"][k] = split_list(v) if k in LIST_FIELDS else v
            rec["umano"]["fonte"] = "annotazione busta"
            toccati.add(rec["id"])
    for pid in toccati:
        save_rec(root, recs[pid])
    registro.esito(f"{args.csv}: {len(toccati)} foto annotate")
    print(f"Annotazioni applicate a {len(toccati)} foto.")


def cmd_imposta(args):
    """Correzione manuale di un campo 'umano' su una o più foto (ha sempre la precedenza sull'AI)."""
    root = find_root()
    ids = _ids(root, args)
    if not ids:
        raise ErroreArchivio("nessuna foto selezionata: usa --id o --rullino")
    for pid in ids:
        rec = load_rec(root, pid)
        for kv in args.campo:
            k, sep, v = kv.partition("=")
            if not sep:
                raise ErroreArchivio(f"formato non valido '{kv}': usa campo=valore")
            rec["umano"][k.strip()] = split_list(v) if k.strip() in LIST_FIELDS else v.strip()
        rec["umano"]["verificato"] = True
        save_rec(root, rec)
    registro.esito(f"{', '.join(args.campo)} su {len(ids)} foto")
    print(f"Aggiornate {len(ids)} foto.")


# ---------------------------------------------------------------- viste ed esportazioni

PRESET = {
    "cronologico": "{anno}/{data}_{luogo}_{id}",
    "luogo": "{luogo}/{anno}/{id}",
    "tipologia": "{tipo}/{anno}/{id}_{soggetto}",
    "persone": "{persone}/{anno}/{id}",
    "fisico": "{busta}/{rullino}/{id}",
    "tecnico": "{colore}/{esposizione}/{id}",
}


def _rimuovi(func, path, *_):
    # su Windows i link a un master in sola lettura ereditano l'attributo: lo togliamo per cancellare il link
    set_readonly(path, False)
    func(path)


def cmd_viste(args):
    root = find_root()
    if not args.schema:
        args.schema = load_config(root)["viste"]["predefinita"]
    schema = PRESET.get(args.schema, args.schema)
    name = args.nome or (args.schema if args.schema in PRESET else "personalizzata")
    out = root / "viste" / slug(name)
    if out.exists():
        if sys.version_info >= (3, 12):
            shutil.rmtree(out, onexc=_rimuovi)
        else:
            shutil.rmtree(out, onerror=_rimuovi)
    n, ripieghi = 0, 0
    for pid in all_ids(root):
        rec = load_rec(root, pid)
        m = merged(rec)
        try:
            rel = schema.format(**{k: slug(v) if v not in ("", []) else "senza-" + k for k, v in m.items()})
        except (KeyError, IndexError, ValueError) as e:
            raise ErroreArchivio(f"schema non valido ({e}). Campi disponibili: {', '.join(m)}")
        src = master_path(root, rec)
        dest = out / (rel + src.suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest = dest.with_name(f"{dest.stem}_{pid}{dest.suffix}")
        if args.modo == "copia":
            shutil.copy2(src, dest)
            set_readonly(dest, False)
        else:
            try:
                if args.modo == "symlink":
                    dest.symlink_to(os.path.relpath(src, dest.parent))
                else:
                    os.link(src, dest)  # hard link: nessuno spazio extra
            except OSError:
                # FAT/exFAT non supportano i link; su Windows i symlink richiedono la modalità sviluppatore
                shutil.copy2(src, dest)
                set_readonly(dest, False)
                ripieghi += 1
        n += 1
    for pid in all_ids(root):  # ripristina la sola lettura tolta cancellando la vista precedente
        set_readonly(master_path(root, load_rec(root, pid)))
    if ripieghi:
        note.registra(root, "attenzione", f"vista '{name}': {ripieghi} link non supportati dal disco, creati come copie "
                                          "(occupano spazio). Usa un disco NTFS/APFS o --modo copia.", "viste")
    registro.esito(f"vista '{name}' ({schema}): {n} foto")
    print(f"Vista '{name}' creata in {out} ({n} foto, schema {schema})")


def xmp_for(rec):
    m = merged(rec)
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    bag = "".join(f"<rdf:li>{esc(t)}</rdf:li>" for t in m["tag"] + ([m["tipo"]] if m["tipo"] else []))
    from .core import persone
    pbag = "".join(f"<rdf:li>{esc(p)}</rdf:li>" for p in persone(rec))
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
    ids = _ids(root, args)
    for pid in ids:
        rec = load_rec(root, pid)
        (root / "master" / f"{pid}.xmp").write_text(xmp_for(rec), encoding="utf-8")
    registro.esito(f"{len(ids)} file XMP")
    print(f"Scritti {len(ids)} sidecar XMP in master/ (leggibili da Lightroom, digiKam, Bridge).")


def cmd_cerca(args):
    root = find_root()
    terms = [t.lower() for t in args.testo]
    n = 0
    for pid in all_ids(root):
        rec = load_rec(root, pid)
        blob = json.dumps({k: rec.get(k) for k in ("fisico", "ai", "umano")}, ensure_ascii=False).lower()
        blob += " " + " ".join(f.get("nome") or "" for f in rec.get("volti", [])).lower()
        if all(t in blob for t in terms):
            m = merged(rec)
            print(f"{pid}  {m['data']}  {m['luogo']}  {m['tipo']}  {m['descrizione'][:60]}")
            n += 1
    print(f"{n} risultati.")


def cmd_simili(args):
    root = find_root()
    base = load_rec(root, args.foto)
    if "impronta" not in base["tecnico"]:
        raise ErroreArchivio(f"{args.foto} non ha l'impronta visiva: esegui  archivio analizza --forza --id {args.foto}")
    out = []
    for pid in all_ids(root):
        if pid == args.foto:
            continue
        t = load_rec(root, pid)["tecnico"]
        if "impronta" in t:
            out.append((distanza(base["tecnico"]["impronta"], t["impronta"]), pid))
    for d, pid in sorted(out)[:args.n]:
        print(f"{pid}  somiglianza {1 - d:.0%}")


def cmd_doppioni(args):
    root = find_root()
    items = [(pid, load_rec(root, pid)["tecnico"].get("impronta")) for pid in all_ids(root)]
    items = [(p, i) for p, i in items if i]
    n = 0
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            d = distanza(items[a][1], items[b][1])
            if d <= args.soglia:
                n += 1
                msg = f"possibile doppione di {items[b][0]} (somiglianza {1 - d:.0%})"
                note.registra(root, "attenzione", msg, "doppioni", items[a][0])
                print(f"  {items[a][0]} ~ {items[b][0]}  {1 - d:.0%}")
    registro.esito(f"{n} coppie sospette")
    print(f"{n} coppie sospette (registrate nelle note).")


def cmd_esporta(args):
    root = find_root()
    rows = [merged(load_rec(root, pid)) for pid in all_ids(root)]
    if not rows:
        raise ErroreArchivio("archivio vuoto")
    # utf-8-sig + ';' perché Excel su Windows e Mac apra correttamente accenti e colonne
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow(r | {"tag": ", ".join(r["tag"])})
    print(f"Esportate {len(rows)} righe in {args.csv}")


# ---------------------------------------------------------------- volti

def cmd_volti(args):
    root = find_root()
    cfg = load_config(root)
    from . import volti
    if args.azione == "rileva":
        motore = volti.Motore(root)
        for pid in _ids(root, args):
            rec = load_rec(root, pid)
            if "volti" in rec and not args.forza:
                continue
            try:
                im, _ = open_image(master_path(root, rec))
                vecchi = {tuple(f["box"]): f for f in rec.get("volti", [])}
                trovati = motore.analizza(im)
                for f in trovati:  # conserva i nomi già assegnati se il volto è lo stesso
                    if tuple(f["box"]) in vecchi:
                        f["nome"] = vecchi[tuple(f["box"])].get("nome")
                rec["volti"] = trovati
                save_rec(root, rec)
                print(f"  {pid}: {len(trovati)} volti")
            except Exception as e:
                _fallimento(root, "volti", pid, e)
        registro.esito("rilevamento volti completato")
        print("Ora esegui  archivio volti raggruppa")
    elif args.azione == "raggruppa":
        recs = {pid: load_rec(root, pid) for pid in all_ids(root)}
        refs = [(pid, k) for pid, r in recs.items() for k in range(len(r.get("volti", [])))]
        faces = [recs[p]["volti"][k] for p, k in refs]
        gruppi = volti.raggruppa(faces, cfg["volti"]["soglia_somiglianza"])
        gruppi.sort(key=len, reverse=True)
        for g, members in enumerate(gruppi, start=1):
            for i in members:
                p, k = refs[i]
                recs[p]["volti"][k]["gruppo"] = f"G{g:03d}"
        for pid in {p for p, _ in refs}:
            save_rec(root, recs[pid])
        registro.esito(f"{len(faces)} volti in {len(gruppi)} gruppi")
        print(f"{len(faces)} volti in {len(gruppi)} gruppi. Vedi  archivio volti elenco  e  archivio volti anteprima")
    elif args.azione == "elenco":
        gruppi = {}
        for pid in all_ids(root):
            for f in load_rec(root, pid).get("volti", []):
                g = gruppi.setdefault(f.get("gruppo") or "-", {"n": 0, "nome": None, "foto": []})
                g["n"] += 1
                g["nome"] = g["nome"] or f.get("nome")
                g["foto"].append(pid)
        for g, v in sorted(gruppi.items(), key=lambda kv: -kv[1]["n"]):
            print(f"{g}  {v['n']:4d} volti  {v['nome'] or '(senza nome)':25s}  es. {', '.join(sorted(set(v['foto']))[:3])}")
    elif args.azione == "anteprima":
        out = root / "viste" / "_volti"
        if out.exists():
            shutil.rmtree(out)
        n = 0
        for pid in all_ids(root):
            rec = load_rec(root, pid)
            for k, f in enumerate(rec.get("volti", [])):
                d = out / slug(f.get("nome") or f.get("gruppo") or "senza-gruppo")
                d.mkdir(parents=True, exist_ok=True)
                volti.ritaglio(root, rec, f["box"]).save(d / f"{pid}_{k}.jpg", "JPEG", quality=85)
                n += 1
        print(f"{n} ritagli in {out}: una cartella per gruppo. Dai un nome con  archivio volti nomina G001 \"Nome\"")
    elif args.azione == "nomina":
        if len(args.valori) != 2:
            raise ErroreArchivio('uso: archivio volti nomina G001 "Nome Cognome"')
        gruppo, nome = args.valori
        n = 0
        for pid in all_ids(root):
            rec = load_rec(root, pid)
            hit = False
            for f in rec.get("volti", []):
                if f.get("gruppo") == gruppo:
                    f["nome"] = nome
                    hit = True
                    n += 1
            if hit:
                save_rec(root, rec)
        if not n:
            raise ErroreArchivio(f"gruppo {gruppo} non trovato")
        registro.esito(f"{gruppo} = {nome} ({n} volti)")
        print(f"{n} volti chiamati '{nome}'.")


# ---------------------------------------------------------------- note, verifica, revisione, stato

def cmd_note(args):
    root = find_root()
    if args.azione == "aggiungi":
        if not args.valori:
            raise ErroreArchivio('uso: archivio note aggiungi "testo" [--id ID]')
        n = note.registra(root, "nota", " ".join(args.valori), "note", (args.id or [None])[0])
        print(f"Nota #{n} registrata.")
    elif args.azione == "risolvi":
        if not args.valori and not args.livello:
            raise ErroreArchivio("uso: archivio note risolvi N [N...]  oppure  --livello qualita")
        nums = {int(x) for x in args.valori} if args.valori else None
        print(f"{note.risolvi(root, numeri=nums, livello=args.livello)} note chiuse.")
    else:
        items = note.carica(root) if args.tutte else note.aperte(root, args.livello)
        if args.livello:
            items = [x for x in items if x["livello"] == args.livello]
        if args.id:
            items = [x for x in items if x.get("id") in args.id]
        for x in items:
            stato_n = "chiusa" if x["risolta"] else "aperta"
            rip = f" (×{x['ripetuta']})" if x.get("ripetuta") else ""
            print(f"#{x['n']:<4} {x['livello']:10s} {stato_n:6s} {x['quando'][:16]}  {x.get('id') or '':20s} {x['messaggio']}{rip}")
        conta = {}
        for x in note.aperte(root):
            conta[x["livello"]] = conta.get(x["livello"], 0) + 1
        print("Aperte: " + (", ".join(f"{k} {v}" for k, v in conta.items()) or "nessuna"))


def cmd_verifica(args):
    """Controlla ambiente, dipendenze, integrità dei master e (con --rete) l'API. Registra i problemi nelle note."""
    root = find_root()
    note.risolvi(root, comando="verifica")
    note.risolvi(root, comando="configurazione")  # ricontrollata subito sotto
    cfg = load_config(root, rigoroso=False)
    problemi = []

    def problema(livello, msg, pid=None):
        problemi.append(msg)
        note.registra(root, livello, msg, "verifica", pid)
        print(f"  [{livello}] {pid + ': ' if pid else ''}{msg}")

    print(f"ArchivioFoto {__version__} · Python {platform.python_version()} · {platform.system()} {platform.release()}")
    if sys.version_info < (3, 10):
        problema("errore", "serve Python 3.10 o successivo")
    for mod, uso in (("cv2", "riconoscimento volti"), ("rawpy", "lettura file RAW")):
        if importlib.util.find_spec(mod) is None:
            print(f"  [info] modulo opzionale '{mod}' assente: {uso} non disponibile")
    from . import chiavi
    chiave, fonte = chiavi.leggi(cfg["ai"])
    if chiave:
        print(f"  chiave API: {chiavi.mascherata(chiave)} ({fonte})")
    if not chiave and chiavi.richiesta(cfg["ai"]):
        problema("attenzione", "chiave API assente: impostala con  archivio chiave imposta  o dalla pagina Impostazioni")
    elif args.rete:
        from .ai import prova
        try:
            prova(cfg)
            print(f"  API ok: {cfg['ai']['base_url']} · {cfg['ai']['modello']}")
        except Exception as e:
            problema("errore", f"API: {e}")
    for msg in cfg["_problemi"]:
        problemi.append(msg)
        print(f"  [errore] {msg}")
    istr = istruzioni.carica(root)
    vecchie = sum(1 for pid in all_ids(root) if (a := load_rec(root, pid)["ai"]) and a.get("istruzioni") != istr["versione"])
    if vecchie:
        problema("attenzione", f"{vecchie} foto lette con istruzioni diverse da quelle attuali: archivio ai --obsolete")
    libero = shutil.disk_usage(root).free / 1e9
    if libero < 10:
        problema("attenzione", f"spazio libero su disco basso: {libero:.1f} GB")

    nomi = set()
    for pid in all_ids(root):
        try:
            rec = load_rec(root, pid)
        except Exception as e:
            problema("errore", f"JSON illeggibile: {e}", pid)
            continue
        p = master_path(root, rec)
        nomi.add(p.name)
        if not p.exists():
            problema("errore", "file master mancante", pid)
            continue
        if not is_readonly(p):
            problema("attenzione", "il master non è in sola lettura (ripristinato)", pid)
            set_readonly(p)
        if args.hash and sha256(p) != rec["file"]["sha256"]:
            problema("errore", "hash diverso dall'originale: file modificato o corrotto", pid)
    for p in (root / "master").iterdir():
        if p.suffix.lower() in IMG_EXT and p.name not in nomi:
            problema("attenzione", f"file in master/ senza scheda dati: {p.name}")
    registro.esito(f"{len(problemi)} problemi" + (" (con hash)" if args.hash else ""))
    print("Nessun problema trovato." if not problemi else f"{len(problemi)} problemi registrati nelle note.")


def cmd_revisione(args):
    from .revisione import avvia
    root = find_root()
    porta = args.porta or load_config(root, rigoroso=False)["webapp"]["porta"]
    srv, url = avvia(root, porta, not args.no_browser)
    print(f"Revisione aperta su {url}  (Ctrl+C per chiudere)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def cmd_stato(args):
    root = find_root()
    recs = [load_rec(root, i) for i in all_ids(root)]
    print(f"ArchivioFoto {__version__} · archivio {root}")
    print(f"Foto: {len(recs)}")
    print(f"  analisi tecnica: {sum(bool(r['tecnico']) for r in recs)}")
    print(f"  analisi AI:      {sum(bool(r['ai']) for r in recs)}")
    print(f"  volti rilevati:  {sum(len(r.get('volti', [])) for r in recs)} in {sum('volti' in r for r in recs)} foto")
    print(f"  annotate:        {sum(bool(r['umano']) for r in recs)}")
    print(f"  verificate:      {sum(bool(r['umano'].get('verificato')) for r in recs)}")
    conta = {}
    for x in note.aperte(root):
        conta[x["livello"]] = conta.get(x["livello"], 0) + 1
    print("Note aperte: " + (", ".join(f"{k} {v}" for k, v in conta.items()) or "nessuna"))


def cmd_versione(args):
    print(f"ArchivioFoto {__version__}")
    if args.log:
        for log in (Path(getattr(sys, "_MEIPASS", "")) / "CHANGELOG.md", Path(__file__).resolve().parent.parent / "CHANGELOG.md"):
            if log.is_file():
                print(log.read_text(encoding="utf-8"))
                break


# ---------------------------------------------------------------- configurazione, chiavi, motori, istruzioni, registro

def cmd_config(args):
    root = find_root()
    if args.azione == "imposta":
        if not args.valori:
            raise ErroreArchivio("uso: archivio config imposta chiave=valore [chiave=valore ...]")
        mod = {}
        for kv in args.valori:
            k, sep, v = kv.partition("=")
            if not sep:
                raise ErroreArchivio(f"formato non valido '{kv}': usa chiave=valore")
            mod[k.strip()] = v.strip()
        cambi = configurazione.imposta(root, mod, "riga di comando")
        registro.esito("; ".join(cambi) or "nessuna modifica")
        print("\n".join(cambi) if cambi else "Nessuna modifica: i valori erano già quelli.")
    else:
        cfg = load_config(root, rigoroso=False)
        print(f"{root / configurazione.FILE}  (versione {cfg['_versione']})")
        valori = configurazione.valori_correnti(root)
        sezione = None
        for v in configurazione.SCHEMA:
            if v.sezione != sezione:
                sezione = v.sezione
                print(f"\n[{sezione}]")
            print(f"  {v.chiave:24s} {valori[v.chiave] or '(vuoto)'}")
        for p in cfg["_problemi"]:
            print(f"  ERRORE: {p}")


def cmd_chiave(args):
    from . import chiavi
    root = find_root()
    ai = load_config(root, rigoroso=False)["ai"]
    if args.azione == "imposta":
        valore = args.valore
        if not valore:
            import getpass
            valore = getpass.getpass("Incolla la chiave API (non verrà mostrata): ")
        chiavi.salva(ai, valore)
        registro.esito(f"chiave '{ai['nome_chiave']}' salvata nel portachiavi ({chiavi.mascherata(valore)})")
        print(f"Chiave salvata nel portachiavi del sistema ({chiavi.mascherata(valore)}). Prova: archivio motori prova")
    elif args.azione == "rimuovi":
        ok = chiavi.rimuovi(ai)
        registro.esito(f"chiave '{ai['nome_chiave']}' " + ("rimossa" if ok else "non presente"))
        print("Chiave rimossa." if ok else "Nessuna chiave da rimuovere nel portachiavi.")
    else:
        k, fonte = chiavi.leggi(ai)
        print(f"Chiave: {chiavi.mascherata(k)} ({fonte})" if k else
              "Nessuna chiave impostata." + (" Non serve per un motore locale." if not chiavi.richiesta(ai) else " Usa: archivio chiave imposta"))


def cmd_motori(args):
    from . import motori
    root = find_root()
    cfg = load_config(root, rigoroso=False)
    if args.azione == "elenca":
        elenco = motori.elenca(cfg)
        attivi = {cfg["ai"]["modello"]: "visione", cfg["ai"]["modello_testo"]: "testo", cfg["ai"]["modello_riserva"]: "riserva"}
        for m in elenco:
            if args.tutti or m["visione"] or m["id"] in attivi:
                tag = "visione?" if m["visione"] else "testo"
                uso = f"  ← in uso come {attivi[m['id']]}" if m["id"] in attivi else ""
                print(f"  {m['id']:55s} {tag}{uso}")
        print(f"{len(elenco)} modelli disponibili" + ("" if args.tutti else " (mostro i probabili modelli di visione; --tutti per l'elenco completo)"))
        print("'visione?' è dedotto dal nome: conferma con  archivio motori prova visione --modello NOME")
    elif args.azione == "prova":
        if args.valori and args.valori[0] not in ("visione", "testo"):
            raise ErroreArchivio("uso: archivio motori prova [visione|testo] [--modello NOME]")
        ruoli = args.valori[:1] or ["visione", "testo"]
        tutto_ok = True
        for r in ruoli:
            esito = motori.prova(cfg, r, args.modello)
            tutto_ok &= esito["ok"]
            print(f"  {r:8s} {esito['modello']}: {'OK' if esito['ok'] else 'NON FUNZIONA'} in {esito['secondi']} s — {esito['dettaglio']}")
            if not esito["ok"]:
                note.registra(root, "errore", f"prova motore {r} {esito['modello']}: {esito['dettaglio']}", "motori")
        registro.esito("prova " + ("superata" if tutto_ok else "fallita"))
        if not tutto_ok:
            raise ErroreArchivio("almeno un motore non funziona: dettagli sopra e nelle note")
    elif args.azione == "usa":
        if len(args.valori) != 2 or args.valori[0] not in ("visione", "testo", "riserva"):
            raise ErroreArchivio("uso: archivio motori usa visione|testo|riserva NOME_MODELLO")
        ruolo, nome = args.valori
        chiave = {"visione": "modello_visione", "testo": "modello_testo", "riserva": "modello_riserva"}[ruolo]
        cambi = configurazione.imposta(root, {chiave: nome}, "motori usa")
        registro.esito("; ".join(cambi) or "nessuna modifica")
        print("\n".join(cambi) or "Già in uso.")
        print("Consigliato: archivio motori prova " + ("visione" if ruolo != "testo" else "testo"))


def cmd_istruzioni(args):
    root = find_root()
    istr = istruzioni.carica(root)
    ids = all_ids(root)
    lette = [load_rec(root, i)["ai"] for i in ids]
    vecchie = sum(1 for a in lette if a and a.get("istruzioni") != istr["versione"])
    print(f"{root / istruzioni.FILE}  (versione {istr['versione']})")
    print(f"  contesto: {istr['contesto'][:100] or '(vuoto)'}")
    print(f"  regole: {len(istr['regole'])} · vocabolario: {len(istr['vocabolario'])} termini · tag vietati: {len(istr['vietati'])}")
    print(f"  foto lette con istruzioni diverse dalle attuali: {vecchie}" + ("  → archivio ai --obsolete" if vecchie else ""))
    if args.prompt:
        print("\nTesto aggiunto alla richiesta AI:\n" + (istruzioni.prompt_extra(istr) or "(nulla)"))


def cmd_registro(args):
    root = find_root()
    for r in registro.ultime(root, args.n):
        print(r)


def cmd_aggiorna(args):
    from . import aggiornamenti
    try:
        d = aggiornamenti.controlla()
    except Exception as e:
        raise ErroreArchivio(f"impossibile controllare gli aggiornamenti: {e}")
    if not d["nuova"]:
        print(f"Versione attuale {__version__}: è la più recente.")
        return
    print(f"Disponibile ArchivioFoto {d['versione']} (in uso: {__version__})\n")
    print(d["note"][:3000])
    print(f"\nScarica: {d['pagina']}")
    for nome, url in d["download"].items():
        print(f"  {nome}: {url}")
    print("\nIl tuo archivio non viene toccato: configurazione, istruzioni e registro restano nella cartella dell'archivio.")


def cmd_app(args):
    from . import app
    from .revisione import avvia
    root = app.trova_archivio(args.archivio, args.scegli)
    if not app.e_archivio(root):
        cmd_init(argparse.Namespace(cartella=str(root), prefisso="ARC"))
    os.chdir(root)
    app.ricorda(root)
    porta = load_config(root, rigoroso=False)["webapp"]["porta"]
    for tentativo in range(10):
        try:
            srv, url = avvia(root, porta + tentativo, not args.no_browser)
            break
        except OSError:
            continue
    else:
        raise ErroreArchivio(f"nessuna porta libera tra {porta} e {porta + 9}")
    print(f"ArchivioFoto {__version__} · archivio {root}")
    print(f"Webapp aperta su {url}  — per chiudere usa il pulsante Esci oppure chiudi questa finestra")
    registro.scrivi(root, "app", f"webapp avviata su {url}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


# ---------------------------------------------------------------- parser

def build_parser():
    p = argparse.ArgumentParser(prog="archivio", description="Catalogazione di un archivio di negativi scansionati.")
    p.add_argument("--version", action="version", version=f"ArchivioFoto {__version__}")
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

    q = sel(sp.add_parser("analizza", help="lettura tecnica e allarmi di qualità"))
    q.add_argument("--forza", action="store_true")
    q.set_defaults(fn=cmd_analizza)

    q = sel(sp.add_parser("ai", help="lettura semantica tramite API visione OpenAI-compatibile"))
    q.add_argument("--forza", action="store_true")
    q.add_argument("--obsolete", action="store_true", help="rileggi le foto lette con istruzioni diverse da quelle attuali")
    q.add_argument("--modello")
    q.set_defaults(fn=cmd_ai)

    q = sp.add_parser("annota", help="importa le annotazioni delle buste da CSV")
    q.add_argument("csv")
    q.set_defaults(fn=cmd_annota)

    q = sel(sp.add_parser("imposta", help="correzione manuale: campo=valore"))
    q.add_argument("campo", nargs="+")
    q.set_defaults(fn=cmd_imposta)

    q = sel(sp.add_parser("volti", help="volti: rileva | raggruppa | elenco | anteprima | nomina G001 \"Nome\""))
    q.add_argument("azione", choices=["rileva", "raggruppa", "elenco", "anteprima", "nomina"])
    q.add_argument("valori", nargs="*")
    q.add_argument("--forza", action="store_true")
    q.set_defaults(fn=cmd_volti)

    q = sp.add_parser("viste", help=f"crea una vista rinominata: preset {', '.join(PRESET)} o schema libero")
    q.add_argument("schema", nargs="?", help="preset o schema; vuoto = vista_predefinita della configurazione")
    q.add_argument("--nome")
    q.add_argument("--modo", choices=["link", "copia", "symlink"], default="link")
    q.set_defaults(fn=cmd_viste)

    q = sel(sp.add_parser("xmp", help="scrive i sidecar XMP/IPTC"))
    q.set_defaults(fn=cmd_xmp)

    q = sp.add_parser("cerca", help="ricerca testuale nei dati")
    q.add_argument("testo", nargs="+")
    q.set_defaults(fn=cmd_cerca)

    q = sp.add_parser("simili", help="foto visivamente simili a una data")
    q.add_argument("foto")
    q.add_argument("-n", type=int, default=10)
    q.set_defaults(fn=cmd_simili)

    q = sp.add_parser("doppioni", help="cerca scansioni doppie o quasi identiche")
    q.add_argument("--soglia", type=float, default=0.06)
    q.set_defaults(fn=cmd_doppioni)

    q = sp.add_parser("esporta", help="esporta l'indice in CSV (compatibile Excel)")
    q.add_argument("csv")
    q.set_defaults(fn=cmd_esporta)

    q = sp.add_parser("note", help="note e allarmi: elenca | aggiungi \"testo\" | risolvi N")
    q.add_argument("azione", nargs="?", default="elenca", choices=["elenca", "aggiungi", "risolvi"])
    q.add_argument("valori", nargs="*")
    q.add_argument("--livello", choices=note.LIVELLI)
    q.add_argument("--id", action="append")
    q.add_argument("--tutte", action="store_true", help="includi le note chiuse")
    q.set_defaults(fn=cmd_note)

    q = sp.add_parser("verifica", help="controlla ambiente, master e API; registra i problemi nelle note")
    q.add_argument("--hash", action="store_true", help="ricalcola l'hash di ogni master (lento)")
    q.add_argument("--rete", action="store_true", help="prova la chiamata all'API")
    q.set_defaults(fn=cmd_verifica)

    q = sp.add_parser("revisione", help="apre l'interfaccia di revisione nel browser")
    q.add_argument("--porta", type=int, help="predefinita: 'porta' in CONFIGURAZIONE.md")
    q.add_argument("--no-browser", action="store_true")
    q.set_defaults(fn=cmd_revisione)

    sp.add_parser("stato", help="riepilogo avanzamento").set_defaults(fn=cmd_stato)

    q = sp.add_parser("config", help="configurazione: mostra | imposta chiave=valore")
    q.add_argument("azione", nargs="?", default="mostra", choices=["mostra", "imposta"])
    q.add_argument("valori", nargs="*")
    q.set_defaults(fn=cmd_config)

    q = sp.add_parser("chiave", help="chiave API nel portachiavi: stato | imposta | rimuovi")
    q.add_argument("azione", nargs="?", default="stato", choices=["stato", "imposta", "rimuovi"])
    q.add_argument("--valore", help="sconsigliato: resta nella cronologia del terminale; senza, viene chiesta")
    q.set_defaults(fn=cmd_chiave)

    q = sp.add_parser("motori", help="motori AI: elenca | prova [visione|testo] | usa visione|testo|riserva NOME")
    q.add_argument("azione", choices=["elenca", "prova", "usa"])
    q.add_argument("valori", nargs="*")
    q.add_argument("--tutti", action="store_true")
    q.add_argument("--modello")
    q.set_defaults(fn=cmd_motori)

    q = sp.add_parser("istruzioni", help="stato di ISTRUZIONI.md e foto da rileggere")
    q.add_argument("--prompt", action="store_true", help="mostra il testo aggiunto alla richiesta AI")
    q.set_defaults(fn=cmd_istruzioni)

    q = sp.add_parser("registro", help="ultime righe di REGISTRO.md")
    q.add_argument("-n", type=int, default=30)
    q.set_defaults(fn=cmd_registro)

    sp.add_parser("aggiorna", help="controlla se su GitHub c'è una versione nuova").set_defaults(fn=cmd_aggiorna)

    q = sp.add_parser("app", help="avvio completo: sceglie l'archivio e apre la webapp (usato dal doppio clic)")
    q.add_argument("archivio", nargs="?")
    q.add_argument("--scegli", action="store_true", help="chiedi la cartella anche se ne ricordo una")
    q.add_argument("--no-browser", action="store_true")
    q.set_defaults(fn=cmd_app)

    q = sp.add_parser("versione", help="versione e registro delle modifiche")
    q.add_argument("--log", action="store_true")
    q.set_defaults(fn=cmd_versione)
    return p


# comandi che cambiano qualcosa: finiscono in REGISTRO.md con il loro esito
REGISTRATI = {"ingest", "analizza", "ai", "annota", "imposta", "volti", "viste", "xmp", "doppioni", "esporta",
              "verifica", "config", "chiave", "motori", "note"}


def _descrizione(args, argv):
    parti = [a for a in (argv if argv is not None else sys.argv[1:]) if not a.startswith("--valore")]
    if getattr(args, "valore", None):
        parti = [p for p in parti if p != args.valore]  # la chiave non finisce mai nel registro
    return " ".join(parti[1:])[:200]


def main(argv=None):
    console_utf8()
    args = build_parser().parse_args(argv)
    registro.prendi_esito()
    da_registrare = args.cmd in REGISTRATI and not (args.cmd in ("config", "chiave") and args.azione in ("mostra", "stato")) \
        and not (args.cmd == "note" and args.azione == "elenca") and not (args.cmd == "motori" and args.azione == "elenca")
    codice, stato = 0, "ok"
    try:
        args.fn(args)
    except ErroreArchivio as e:
        _registra_globale(args, str(e))
        print(f"ERRORE: {e}", file=sys.stderr)
        codice, stato = 1, "errore"
        registro.esito(str(e).splitlines()[0])
    except KeyboardInterrupt:
        print("Interrotto.", file=sys.stderr)
        codice, stato = 130, "attenzione"
        registro.esito("interrotto dall'utente")
    except Exception as e:
        _registra_globale(args, f"errore imprevisto {type(e).__name__}: {e} @ {traceback.extract_tb(e.__traceback__)[-1].name}")
        traceback.print_exc()
        print("ERRORE imprevisto: registrato nelle note (archivio note).", file=sys.stderr)
        codice, stato = 2, "errore"
        registro.esito(f"errore imprevisto {type(e).__name__}")
    if da_registrare:
        try:
            dett = _descrizione(args, argv)
            esito = registro.prendi_esito()
            registro.scrivi(find_root(), args.cmd, " — ".join(x for x in (dett, esito) if x), stato)
        except Exception:
            pass
    return codice


def _registra_globale(args, msg):
    try:
        note.registra(find_root(), "errore", msg, args.cmd)
    except Exception:
        pass  # fuori da un archivio non c'è dove registrare
