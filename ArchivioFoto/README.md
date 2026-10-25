# ArchivioFoto

Strumento da riga di comando per digitalizzare e catalogare un archivio di negativi scansionati.

## Principi
- **ID immutabile**: ogni master si chiama `ARC-ANNO-Rrrr-Fff` (archivio-anno-rullino-fotogramma), resta in sola lettura e non viene mai rinominato. È il legame con il negativo fisico.
- **Dati con provenienza**: `dati/<id>.json` separa `fisico` (busta, pellicola), `umano` (annotazioni e correzioni), `tecnico` (misurato) e `ai` (dedotto). I dati umani hanno sempre la precedenza.
- **Rinomine = viste**: le diverse "rinomine" sono cartelle di hard link in `viste/`, generate da uno schema e rigenerabili quando vuoi, senza spazio extra.
- **Standard aperti**: i sidecar XMP/IPTC rendono i dati leggibili anche da Lightroom, digiKam e Bridge.

> Una scansione non contiene l'EXIF dello scatto originale (tempo, diaframma, data). Quei dati arrivano dalle buste o dalle tue correzioni, non dal file.

## Installazione
```bash
pip install -r requirements.txt
export NVIDIA_API_KEY=nvapi-...   # chiave da https://build.nvidia.com
```

## Flusso per rullino
```bash
python archivio.py init /dati/archivio --prefisso ARC
cd /dati/archivio
python archivio.py ingest /scansioni/busta12 --rullino 42 --anno 1987 --busta B12 --pellicola "Kodak Gold 200"
python archivio.py analizza --rullino 42        # colori, palette, B/N, esposizione, nitidezza, dominante
python archivio.py ai --rullino 42              # tipo di scatto, soggetti, oggetti, sfondo, testo, epoca, tag
python archivio.py annota buste.csv             # annotazioni delle buste (vedi sotto)
python archivio.py imposta --id ARC-1987-R042-F07 luogo=Bari "persone=Mario Rossi, Anna"
python archivio.py xmp
python archivio.py viste cronologico
python archivio.py stato
```

`ingest` verifica l'hash di ogni copia, salta i duplicati già importati e non sovrascrive mai un ID esistente (`--dry-run` per provare).

## Annotazioni delle buste (CSV)
Separatore `;` o `,`. `rullino` è obbligatorio. Se manca `fotogramma`, la riga vale per tutto il rullino.
```
rullino;fotogramma;data;luogo;evento;persone;note
42;;1987-08-15;Matera;Ferragosto;Mario Rossi, Anna;
42;7;;Bari;;;foto sul porto
```

## Viste (rinomina multipla)
Preset: `cronologico`, `luogo`, `tipologia`, `persone`, `fisico`, `tecnico`. In alternativa, uno schema libero:
```bash
python archivio.py viste "{anno}/{tipo}/{data}_{luogo}_{id}" --nome per-tipo
```
Campi: `id anno data rullino fotogramma busta formato pellicola luogo evento persone tipo ambiente epoca soggetto colore esposizione nitidezza`.
`--modo copia` crea copie vere, ad esempio per consegnare una selezione.

## Ricerca ed esportazione
```bash
python archivio.py cerca chiesa matera
python archivio.py esporta indice.csv
```

## Motore AI
Va bene qualsiasi API **OpenAI-compatibile con supporto immagini**. Configurala in `archivio.json`:
```json
"ai": {"base_url": "https://integrate.api.nvidia.com/v1", "modello": "nvidia/nemotron-nano-12b-v2-vl", "chiave_env": "NVIDIA_API_KEY"}
```
Il modello deve essere **di visione**: Nemotron 3 Super/Nano solo testo non leggono le immagini. Per lavorare in locale, senza inviare le foto all'esterno, imposta ad esempio Ollama (`http://localhost:11434/v1`) con un modello VL. Per provare un modello su un rullino: `python archivio.py ai --rullino 42 --forza --modello <nome>`.
