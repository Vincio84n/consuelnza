import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from archiviofoto import configurazione, istruzioni, note, registro
from archiviofoto.cli import main


@pytest.fixture
def arch(tmp_path, monkeypatch):
    scan = tmp_path / "scan"
    scan.mkdir()
    for i, c in enumerate([(120, 150, 200), (90, 90, 90)]):
        Image.new("RGB", (900, 600), c).save(scan / f"{i}.jpg")
    assert main(["init", str(tmp_path / "arch")]) == 0
    monkeypatch.chdir(tmp_path / "arch")
    assert main(["ingest", str(scan), "--rullino", "7", "--anno", "1975"]) == 0
    return tmp_path / "arch"


def leggi(p):
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- CONFIGURAZIONE.md

def test_file_md_creati(arch):
    for f in ("CONFIGURAZIONE.md", "ISTRUZIONI.md", "REGISTRO.md"):
        assert (arch / f).exists()
    cfg = configurazione.carica(arch)
    assert cfg["ai"]["modello"] == "nvidia/nemotron-3-ultra-550b-a55b" and cfg["_versione"] == 1
    assert cfg["ai"]["modello_riserva"] == "nvidia/nemotron-nano-12b-v2-vl"
    assert "**ingest**" in leggi(arch / "REGISTRO.md")


def test_imposta_preserva_commenti_e_registra(arch):
    p = arch / "CONFIGURAZIONE.md"
    p.write_text(leggi(p).replace("## Volti", "## Volti\n\nNota mia: non toccare.\n"), encoding="utf-8")
    assert main(["config", "imposta", "soglia_somiglianza=0,5", "porta=9000"]) == 0
    testo = leggi(p)
    assert "- soglia_somiglianza: 0.5" in testo and "Nota mia: non toccare." in testo
    cfg = configurazione.carica(arch)
    assert cfg["volti"]["soglia_somiglianza"] == 0.5 and cfg["webapp"]["porta"] == 9000 and cfg["_versione"] == 2
    assert "soglia_somiglianza: 0.363 → 0.5" in leggi(arch / "REGISTRO.md")


def test_modifica_a_mano_non_valida_blocca_con_riga(arch, capsys):
    p = arch / "CONFIGURAZIONE.md"
    p.write_text(leggi(p).replace("- porta: 8765", "- porta: ottomila"), encoding="utf-8")
    assert main(["analizza"]) == 1
    err = capsys.readouterr().err
    assert "riga" in err and "'porta'" in err
    assert any("porta" in x["messaggio"] for x in note.aperte(arch, livello="errore"))
    assert configurazione.carica(arch, rigoroso=False)["webapp"]["porta"] == 8765  # la webapp parte comunque


def test_valori_rifiutati(arch):
    assert main(["config", "imposta", "modello_visione=nvapi-abcdefghijklmnop"]) == 1  # chiave nel file: mai
    assert main(["config", "imposta", "indirizzo_api=ftp://x"]) == 1
    assert main(["config", "imposta", "inesistente=1"]) == 1
    assert "nvapi-" not in leggi(arch / "CONFIGURAZIONE.md")


def test_migrazione_da_json(tmp_path, monkeypatch):
    root = tmp_path / "vecchio"
    for d in ("master", "dati"):
        (root / d).mkdir(parents=True)
    (root / "archivio.json").write_text(json.dumps({"prefisso": "FAM", "ai": {"modello": "x/y-vl", "base_url": "http://localhost:11434/v1"}}))
    monkeypatch.chdir(root)
    assert main(["config"]) == 0
    cfg = configurazione.carica(root)
    assert cfg["prefisso"] == "FAM" and cfg["ai"]["modello"] == "x/y-vl" and cfg["ai"]["base_url"] == "http://localhost:11434/v1"
    assert (root / "archivio.json.migrato").exists() and "migrata" in leggi(root / "REGISTRO.md")


# ---------------------------------------------------------------- chiavi

def test_chiave_nel_portachiavi_mai_nei_file(arch, isolamento, capsys):
    assert main(["chiave", "imposta", "--valore", "nvapi-SEGRETISSIMA1234"]) == 0
    assert isolamento.d[("ArchivioFoto", "nvidia")] == "nvapi-SEGRETISSIMA1234"
    assert main(["chiave"]) == 0
    assert "…1234 (portachiavi)" in capsys.readouterr().out
    for f in arch.rglob("*"):
        if f.is_file() and f.suffix in (".md", ".json"):
            assert "SEGRETISSIMA" not in leggi(f), f
    assert main(["chiave", "rimuovi"]) == 0
    assert not isolamento.d


def test_chiave_in_file_md(arch, capsys):
    from archiviofoto import chiavi
    (arch / ".git").mkdir()  # l'archivio dentro un repository: CHIAVE.md va escluso dai commit
    assert main(["chiave", "imposta", "--file", "--valore", "nvapi-DAFILE987654"]) == 0
    testo = leggi(arch / "CHIAVE.md")
    assert "- nvidia: nvapi-DAFILE987654" in testo and "Non pubblicarlo" in testo
    assert "CHIAVE.md" in leggi(arch / ".gitignore").split()
    assert chiavi.leggi(configurazione.carica(arch)["ai"], arch) == ("nvapi-DAFILE987654", f"file {arch / 'CHIAVE.md'}")
    assert "DAFILE" not in leggi(arch / "REGISTRO.md")
    assert main(["verifica"]) == 0
    assert any("in chiaro" in x["messaggio"] for x in note.aperte(arch))
    assert main(["chiave", "rimuovi"]) == 0
    assert "DAFILE" not in leggi(arch / "CHIAVE.md")


# ---------------------------------------------------------------- ISTRUZIONI.md e motori (API finta)

class FakeAPI(BaseHTTPRequestHandler):
    richieste = []
    modello_rotto = None

    def _ok(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._ok({"data": [{"id": "nvidia/nemotron-nano-12b-v2-vl"}, {"id": "meta/llama-3.2-11b-vision-instruct"},
                           {"id": "nvidia/nemotron-3-ultra-550b-a55b"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeAPI.richieste.append(body)
        if body["model"] == FakeAPI.modello_rotto:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"model not found")
            return
        if isinstance(body["messages"][-1]["content"], str):
            return self._ok({"choices": [{"message": {"content": "pronto"}}]})
        c = '{"tipo_scatto":"architettura","descrizione":"Un duomo.","tag":["Duomo","foto","piazza","auto"]}'
        self._ok({"choices": [{"message": {"content": c}}]})

    def log_message(self, *a):
        pass


@pytest.fixture
def api(arch):
    srv = HTTPServer(("127.0.0.1", 0), FakeAPI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    FakeAPI.richieste, FakeAPI.modello_rotto = [], None
    assert main(["config", "imposta", f"indirizzo_api=http://127.0.0.1:{srv.server_address[1]}/v1"]) == 0
    yield
    srv.shutdown()


def test_istruzioni_guidano_ai_e_versione(arch, api):
    p = arch / "ISTRUZIONI.md"
    p.write_text(leggi(p).replace("## Regole per la lettura AI", "Foto di famiglia a Matera, anni '70.\n\n## Regole per la lettura AI\n- Indica sempre se è estate."),
                 encoding="utf-8")
    assert main(["ai"]) == 0
    prompt = FakeAPI.richieste[0]["messages"][1]["content"][0]["text"]
    assert "Matera, anni '70" in prompt and "Indica sempre se è estate" in prompt
    rec = json.loads(leggi(arch / "dati" / "ARC-1975-R007-F01.json"))
    assert rec["ai"]["tag"] == ["chiesa", "piazza", "automobile"]  # vocabolario applicato, "foto" scartato
    v1 = rec["ai"]["istruzioni"]
    p.write_text(leggi(p) + "\n> un commento non cambia le istruzioni\n", encoding="utf-8")
    assert istruzioni.carica(arch)["versione"] == v1
    p.write_text(leggi(p).replace("Indica sempre se è estate.", "Indica la stagione."), encoding="utf-8")
    assert istruzioni.carica(arch)["versione"] != v1
    n = len(FakeAPI.richieste)
    assert main(["ai"]) == 0 and len(FakeAPI.richieste) == n  # già lette: niente
    assert main(["ai", "--obsolete"]) == 0 and len(FakeAPI.richieste) == n + 2


def test_motore_selezionato_e_riserva(arch, api):
    # il motore selezionato (Ultra) viene sempre provato; se non legge le immagini subentra la riserva
    FakeAPI.modello_rotto = "nvidia/nemotron-3-ultra-550b-a55b"
    assert main(["ai"]) == 0
    modelli = [r["model"] for r in FakeAPI.richieste]
    assert modelli[0] == "nvidia/nemotron-3-ultra-550b-a55b"
    rec = json.loads(leggi(arch / "dati" / "ARC-1975-R007-F01.json"))
    assert rec["ai"]["modello"] == "nvidia/nemotron-nano-12b-v2-vl"
    assert any("riserva" in x["messaggio"] for x in note.aperte(arch))


def test_motore_selezionato_funzionante(arch, api):
    assert main(["ai"]) == 0
    assert {r["model"] for r in FakeAPI.richieste} == {"nvidia/nemotron-3-ultra-550b-a55b"}


def test_passa_alla_riserva_dopo_due_foto(arch, api, tmp_path):
    scan = tmp_path / "altre"
    scan.mkdir()
    for i in range(4):
        Image.new("RGB", (300, 200), (i * 40, 90, 90)).save(scan / f"{i}.jpg")
    assert main(["ingest", str(scan), "--rullino", "8"]) == 0
    FakeAPI.modello_rotto = "nvidia/nemotron-3-ultra-550b-a55b"
    assert main(["ai"]) == 0
    tentativi_ultra = sum(1 for r in FakeAPI.richieste if r["model"] == FakeAPI.modello_rotto)
    assert tentativi_ultra == 2  # dopo 2 foto non lo riprova a ogni immagine
    assert any("non ha letto le immagini" in x["messaggio"] for x in note.aperte(arch))


def test_motori_elenca_prova_usa(arch, api, capsys):
    assert main(["motori", "elenca"]) == 0
    out = capsys.readouterr().out
    assert "llama-3.2-11b-vision-instruct" in out and "← in uso come visione" in out and "← in uso come riserva" in out
    assert main(["motori", "prova"]) == 0
    out = capsys.readouterr().out
    assert out.count("OK") == 2
    assert main(["motori", "usa", "visione", "meta/llama-3.2-11b-vision-instruct"]) == 0
    assert "nvidia/nemotron-3-ultra-550b-a55b → meta/llama-3.2-11b-vision-instruct" in leggi(arch / "REGISTRO.md")
    assert configurazione.carica(arch)["ai"]["modello"] == "meta/llama-3.2-11b-vision-instruct"
    FakeAPI.modello_rotto = "meta/llama-3.2-11b-vision-instruct"
    assert main(["motori", "prova", "visione"]) == 1
    assert "**motori**" in leggi(arch / "REGISTRO.md")


# ---------------------------------------------------------------- registro e aggiornamenti

def test_registro_esiti(arch):
    assert main(["analizza"]) == 0
    righe = registro.ultime(arch)
    assert any("**analizza**" in r and "2 foto analizzate" in r and r.endswith("✔") for r in righe)
    assert main(["ingest", str(arch / "nonesiste"), "--rullino", "9"]) == 1
    assert registro.ultime(arch)[-1].endswith("✖")


def test_aggiorna(arch, monkeypatch, capsys):
    class R(BaseHTTPRequestHandler):
        def do_GET(self):
            data = json.dumps({"name": "ArchivioFoto v9.9.9", "body": "## Novità", "html_url": "http://x",
                               "assets": [{"name": "ArchivioFoto-Windows.zip", "browser_download_url": "http://x/w.zip"}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), R)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("ARCHIVIOFOTO_RELEASE_URL", f"http://127.0.0.1:{srv.server_address[1]}/")
    assert main(["aggiorna"]) == 0
    assert "Disponibile ArchivioFoto 9.9.9" in capsys.readouterr().out
    srv.shutdown()


# ---------------------------------------------------------------- webapp

@pytest.fixture
def web(arch):
    from archiviofoto.revisione import STATO, avvia
    srv, url = avvia(arch, porta=0, apri=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def post(percorso, dati, token=True):
        d = dict(dati, _t=STATO["token"]) if token else dati
        return urllib.request.urlopen(url + percorso.lstrip("/"), data=urllib.parse.urlencode(d).encode()).read().decode()

    def api_(percorso, dati=None):
        req = urllib.request.Request(url + percorso.lstrip("/"), data=json.dumps(dati or {}).encode(),
                                     headers={"Content-Type": "application/json", "X-Token": STATO["token"]})
        return json.loads(urllib.request.urlopen(req).read())
    yield url, post, api_
    srv.shutdown()
    srv.server_close()


def test_webapp_protezioni(arch, web):
    url, post, _ = web
    with pytest.raises(urllib.error.HTTPError) as e:
        post("impostazioni", {"porta": "9001"}, token=False)
    assert e.value.code == 403
    req = urllib.request.Request(url, headers={"Host": "attacco.example:8765"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403
    assert configurazione.carica(arch)["webapp"]["porta"] == 8765


def test_webapp_impostazioni_chiave_istruzioni(arch, web, isolamento):
    url, post, _ = web
    pag = urllib.request.urlopen(url + "impostazioni").read().decode()
    assert "modello visione" in pag and 'name="_t"' in pag
    out = post("impostazioni", {"soglia_somiglianza": "0.4", "porta": "8765"})
    assert "Salvato" in out and configurazione.carica(arch)["volti"]["soglia_somiglianza"] == 0.4
    righe = len(registro.ultime(arch))
    tutti = configurazione.valori_correnti(arch)
    assert "Nessuna modifica" in post("impostazioni", tutti)  # salvare senza cambiare nulla non scrive nulla
    assert len(registro.ultime(arch)) == righe
    out = post("impostazioni", {"porta": "12"})
    assert "minimo" in out and configurazione.carica(arch)["webapp"]["porta"] == 8765
    out = post("chiave", {"chiave": "nvapi-WEBAPP99999"})
    assert "salvata" in out and "…9999" in out and "nvapi-WEBAPP99999" not in out
    assert isolamento.d[("ArchivioFoto", "nvidia")] == "nvapi-WEBAPP99999"
    testo = leggi(arch / "ISTRUZIONI.md").replace("## Regole per la lettura AI", "Archivio di prova.\n\n## Regole per la lettura AI")
    assert "Salvato" in post("istruzioni", {"testo": testo})
    assert istruzioni.carica(arch)["contesto"] == "Archivio di prova."
    reg = urllib.request.urlopen(url + "registro").read().decode()
    assert "istruzioni" in reg and "configurazione" in reg and "nvapi-WEBAPP" not in reg


def test_webapp_lavori(arch, web):
    url, post, api_ = web
    assert "Lavori" in urllib.request.urlopen(url + "lavori").read().decode()
    post("lavori/avvia", {"lavoro": "analizza", "rullino": "7"})
    for _ in range(100):
        s = json.loads(urllib.request.urlopen(url + "api/lavoro").read())
        if not s["attivo"] and s["codice"] is not None:
            break
        time.sleep(0.1)
    assert s["codice"] == 0 and s["fatti"] == 2 and s["totale"] == 2
    assert any("$ archivio analizza --rullino 7" in r for r in s["righe"])
    assert json.loads(leggi(arch / "dati" / "ARC-1975-R007-F01.json"))["tecnico"]


def test_app_ricorda_archivio(arch, tmp_path, monkeypatch):
    from archiviofoto import app
    app.ricorda(arch)
    monkeypatch.chdir(tmp_path)
    assert app.trova_archivio() == arch
