import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from xml.dom import minidom

import numpy as np
import pytest
from PIL import Image, ImageDraw

from archiviofoto import note
from archiviofoto.cli import main
from archiviofoto.core import is_readonly
from archiviofoto.volti import raggruppa


@pytest.fixture
def arch(tmp_path, monkeypatch):
    scan = tmp_path / "scan"
    scan.mkdir()
    im = Image.new("RGB", (3000, 2000), (120, 150, 200))
    ImageDraw.Draw(im).rectangle([600, 400, 2400, 1600], fill=(200, 180, 120))
    im.save(scan / "a.tif")
    Image.fromarray((np.random.default_rng(1).random((2000, 3000)) * 255).astype("uint8")).save(scan / "b.jpg")
    Image.new("RGB", (800, 1200), (220, 140, 90)).save(scan / "c.tif")  # chiara e arancione: negativo non invertito
    assert main(["init", str(tmp_path / "arch")]) == 0
    monkeypatch.chdir(tmp_path / "arch")
    assert main(["ingest", str(scan), "--rullino", "42", "--anno", "1987", "--busta", "B12"]) == 0
    return tmp_path / "arch"


def rec(arch, pid):
    return json.loads((arch / "dati" / f"{pid}.json").read_text(encoding="utf-8"))


IDS = ["ARC-1987-R042-F01", "ARC-1987-R042-F02", "ARC-1987-R042-F03"]


def test_ingest_ids_readonly_e_doppioni(arch):
    assert sorted(p.stem for p in (arch / "dati").glob("*.json")) == IDS
    assert is_readonly(arch / "master" / "ARC-1987-R042-F01.tif")
    assert main(["ingest", str(arch.parent / "scan"), "--rullino", "43"]) == 0
    assert len(list((arch / "dati").glob("*.json"))) == 3
    assert any("già in archivio" in x["messaggio"] for x in note.aperte(arch))


def test_ingest_non_sovrascrive(arch, tmp_path):
    other = tmp_path / "altro"
    other.mkdir()
    Image.new("RGB", (100, 100), (1, 2, 3)).save(other / "x.jpg")
    assert main(["ingest", str(other), "--rullino", "42", "--anno", "1987"]) == 1
    assert any("già usato" in x["messaggio"] for x in note.aperte(arch, livello="errore"))


def test_analizza_e_allarmi(arch):
    assert main(["analizza"]) == 0
    t = rec(arch, IDS[1])["tecnico"]
    assert t["bianco_nero"] and "impronta" in t
    assert rec(arch, IDS[2])["tecnico"]["negativo_non_invertito_probabile"]
    q = [x["messaggio"] for x in note.aperte(arch, livello="qualita", pid=IDS[2])]
    assert any("negativo" in m for m in q) and any("risoluzione bassa" in m for m in q)
    # rianalizzare non duplica gli allarmi
    n = len(note.aperte(arch))
    assert main(["analizza", "--forza"]) == 0
    assert len(note.aperte(arch)) == n


def test_annota_imposta_viste_ripetute_xmp(arch):
    (arch.parent / "buste.csv").write_text(
        "rullino;fotogramma;data;luogo;persone\n42;;1987-08-15;Matera;Mario Rossi, Anna\n42;3;;Bari;\n99;;;Nessuno;\n",
        encoding="utf-8")
    assert main(["annota", str(arch.parent / "buste.csv")]) == 0
    assert rec(arch, IDS[0])["umano"]["persone"] == ["Mario Rossi", "Anna"]
    assert rec(arch, IDS[2])["umano"]["luogo"] == "Bari"
    assert any("rullino 99" in x["messaggio"] for x in note.aperte(arch))
    assert main(["imposta", "--id", IDS[1], "luogo=Lecce", "evento=Festa"]) == 0
    assert rec(arch, IDS[1])["umano"]["verificato"] is True
    for _ in range(2):  # la seconda volta cancella la vista precedente (su Windows i link sono in sola lettura)
        assert main(["viste", "cronologico"]) == 0
    files = sorted(p.relative_to(arch / "viste").as_posix() for p in (arch / "viste").rglob("*") if p.is_file())
    assert "cronologico/1987/1987-08-15_Bari_ARC-1987-R042-F03.tif" in files
    assert is_readonly(arch / "master" / "ARC-1987-R042-F01.tif")
    assert main(["viste", "{nonesiste}/{id}"]) == 1
    assert main(["xmp"]) == 0
    minidom.parse(str(arch / "master" / f"{IDS[0]}.xmp"))


def test_note_comandi(arch, capsys):
    assert main(["note", "aggiungi", "busta", "12", "rovinata", "--id", IDS[0]]) == 0
    n = note.aperte(arch, livello="nota")[0]["n"]
    assert main(["note"]) == 0
    assert "busta 12 rovinata" in capsys.readouterr().out
    assert main(["note", "risolvi", str(n)]) == 0
    assert not note.aperte(arch, livello="nota")


def test_verifica(arch, monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    os.chmod(arch / "master" / "ARC-1987-R042-F01.tif", 0o644)
    (arch / "master" / "orfano.jpg").write_bytes(b"x")
    assert main(["verifica", "--hash"]) == 0
    msgs = " ".join(x["messaggio"] for x in note.aperte(arch))
    assert "chiave API assente" in msgs and "orfano.jpg" in msgs and "sola lettura" in msgs
    assert is_readonly(arch / "master" / "ARC-1987-R042-F01.tif")


def test_simili_e_doppioni(arch, capsys):
    assert main(["analizza"]) == 0
    assert main(["simili", IDS[0], "-n", "2"]) == 0
    assert "somiglianza" in capsys.readouterr().out
    assert main(["doppioni", "--soglia", "0"]) == 0


class FakeAI(BaseHTTPRequestHandler):
    risposte = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeAI.risposte.append(body)
        if not FakeAI.ok:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"bad key")
            return
        c = '```json\n{"tipo_scatto":"architettura","descrizione":"Una chiesa.","tag":["chiesa"],"soggetti":["chiesa"]}\n```'
        data = json.dumps({"choices": [{"message": {"content": c}}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_ai(arch, monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = json.loads((arch / "archivio.json").read_text(encoding="utf-8"))
    cfg["ai"]["base_url"] = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    (arch / "archivio.json").write_text(json.dumps(cfg), encoding="utf-8")
    FakeAI.risposte = []
    yield
    srv.shutdown()


def test_ai_ok(arch, fake_ai):
    FakeAI.ok = True
    assert main(["ai"]) == 0
    r = rec(arch, IDS[0])
    assert r["ai"]["tipo_scatto"] == "architettura"
    body = FakeAI.risposte[0]
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_ai_errori_registrati_e_stop(arch, fake_ai):
    FakeAI.ok = False
    assert main(["ai"]) == 1
    errs = note.aperte(arch, livello="errore")
    assert any("chiave non valida" in x["messaggio"] for x in errs)
    assert any("3 errori AI consecutivi" in x["messaggio"] for x in errs)


def test_raggruppa_volti():
    rng = np.random.default_rng(0)
    a, b = rng.normal(size=128), rng.normal(size=128)
    faces = [{"emb": list(a + rng.normal(scale=0.1, size=128))} for _ in range(3)]
    faces += [{"emb": list(b + rng.normal(scale=0.1, size=128))} for _ in range(2)]
    faces[3]["nome"] = "Anna"
    gruppi = sorted(sorted(g) for g in raggruppa(faces, 0.363))
    assert gruppi == [[0, 1, 2], [3, 4]]


def test_revisione_web(arch):
    from archiviofoto.revisione import avvia
    assert main(["analizza"]) == 0
    srv, url = avvia(arch, porta=0, apri=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert "R042" in urllib.request.urlopen(url).read().decode()
        page = urllib.request.urlopen(url + "r/42").read().decode()
        assert IDS[0] in page and "negativo" in page
        img = urllib.request.urlopen(url + f"img/{IDS[0]}?s=200").read()
        assert img[:2] == b"\xff\xd8"
        data = urllib.parse.urlencode({"id": IDS[0], "luogo": "Matera", "persone": "Anna, Luca", "verificato": "on"}).encode()
        urllib.request.urlopen(url + "salva", data=data).read()
        u = rec(arch, IDS[0])["umano"]
        assert u["luogo"] == "Matera" and u["persone"] == ["Anna", "Luca"] and u["verificato"]
        data = urllib.parse.urlencode({"rullino": "42", "r_evento": "Gita"}).encode()
        urllib.request.urlopen(url + "salva-rullino", data=data).read()
        assert all(rec(arch, i)["umano"]["evento"] == "Gita" for i in IDS)
        assert "Note e allarmi" in urllib.request.urlopen(url + "note").read().decode()
        assert "Indice della guida" in urllib.request.urlopen(url + "guida").read().decode()
        assert b"avviaTour" in urllib.request.urlopen(url + "static/app.js").read()
        assert len(json.loads(urllib.request.urlopen(url + "static/guida.json").read())) >= 15
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(url + "static/..%2F__init__.py")
        passi = json.loads(urllib.request.urlopen(url + "api/passi").read())
        assert any("lettura AI" in p["testo"] for p in passi)
    finally:
        srv.shutdown()
        srv.server_close()


def test_versione(capsys):
    assert main(["versione", "--log"]) == 0
    out = capsys.readouterr().out
    assert "ArchivioFoto 0." in out and "Registro delle versioni" in out


def test_volti_pipeline(arch):
    pytest.importorskip("cv2")
    assert main(["volti", "rileva"]) == 0  # scarica i modelli e analizza: le immagini sintetiche non hanno volti
    assert all("volti" in rec(arch, i) for i in IDS)
    assert main(["volti", "raggruppa"]) == 0
    assert main(["volti", "nomina", "G001", "Anna"]) == 1  # nessun gruppo: errore registrato


def test_guida_ricerca_e_passi(arch):
    from archiviofoto import aiuto
    ids = {a["id"] for a in aiuto.articoli()}
    assert {"primi-passi", "installazione", "note", "volti", "problemi"} <= ids
    assert aiuto.cerca("come rinomino i file per luogo")[0]["id"] in ("viste", "id-immutabile")
    assert aiuto.cerca("errore 401 chiave")[0]["id"] in ("chiave-api", "problemi")
    testi = " ".join(p["testo"] for p in aiuto.prossimi_passi(arch))
    assert "senza analisi tecnica" in testi and "da verificare" in testi


class FakeChat(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ok = "Viste e rinomine" in body["messages"][0]["content"] and body["model"] == "nvidia/nemotron-3-super-120b-a12b"
        data = json.dumps({"choices": [{"message": {"content": "<think>x</think>Usa `archivio viste luogo`" if ok else "contesto mancante"}}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_assistente(arch, monkeypatch):
    from archiviofoto.revisione import avvia
    srv_ai = HTTPServer(("127.0.0.1", 0), FakeChat)
    threading.Thread(target=srv_ai.serve_forever, daemon=True).start()
    srv, url = avvia(arch, porta=0, apri=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def chiedi(d):
        req = urllib.request.Request(url + "api/chiedi", data=json.dumps({"domanda": d}).encode(), headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req).read())
    try:
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        r = chiedi("come rinomino per luogo?")
        assert "NVIDIA_API_KEY" in r["errore"]  # senza chiave: errore chiaro, la ricerca offline resta disponibile
        assert any("assistente" in x["messaggio"] for x in note.aperte(arch))
        cfg = json.loads((arch / "archivio.json").read_text(encoding="utf-8"))
        cfg["ai"]["base_url"] = f"http://127.0.0.1:{srv_ai.server_address[1]}/v1"
        (arch / "archivio.json").write_text(json.dumps(cfg), encoding="utf-8")
        r = chiedi("come rinomino i file per luogo?")
        assert r["risposta"] == "Usa `archivio viste luogo`"
        assert any(f["id"] == "viste" for f in r["fonti"])
    finally:
        srv.shutdown()
        srv.server_close()
        srv_ai.shutdown()
