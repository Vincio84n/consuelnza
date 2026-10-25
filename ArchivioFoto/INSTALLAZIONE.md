# Installazione di ArchivioFoto

Tempo richiesto: circa 10 minuti. Serve una connessione a Internet solo per l'installazione, per la lettura AI e per il primo download dei modelli dei volti.

## 1. Scarica il programma
- **Windows**: https://github.com/Vincio84n/consuelnza/releases/download/archiviofoto/ArchivioFoto-Windows.zip
- **macOS**: https://github.com/Vincio84n/consuelnza/releases/download/archiviofoto/ArchivioFoto-macOS.zip

Estrai lo ZIP in una cartella stabile, ad esempio `C:\ArchivioFoto` oppure `~/Applicazioni`. Il programma è nella cartella **`ArchivioFoto`**. Tutte le versioni: https://github.com/Vincio84n/consuelnza/releases/tag/archiviofoto

**Con Git**, in alternativa: `git clone https://github.com/Vincio84n/consuelnza.git`

## 2. Installa Python (una volta sola)
Serve **Python 3.10 o successivo**.

### Windows
1. Scarica Python da https://www.python.org/downloads/
2. Avvia l'installer e **spunta "Add python.exe to PATH"** in basso, poi *Install Now*.
3. Controlla: apri *Prompt dei comandi* e scrivi `py --version` (deve rispondere `Python 3.x`).

### macOS
1. Scarica Python da https://www.python.org/downloads/ e installa il pacchetto `.pkg`.
2. Controlla: apri *Terminale* e scrivi `python3 --version`.

## 3. Installa ArchivioFoto
### Windows
1. Apri la cartella `ArchivioFoto` ed esegui con doppio clic **`installa-windows.bat`**.
2. Se compare *"Windows ha protetto il PC"*: **Ulteriori informazioni → Esegui comunque**.
3. Attendi il messaggio *Installato*.

### macOS
1. Nella cartella `ArchivioFoto`: **tasto destro su `installa-mac.command` → Apri → Apri**. Serve solo la prima volta, perché lo script non è firmato.
2. Attendi il messaggio *Installato*.

Lo script crea l'ambiente isolato `.venv` dentro la cartella del programma: non tocca il resto del sistema. Per disinstallare basta cancellare la cartella.

## 4. Apri il terminale nella cartella giusta
- **Windows**: doppio clic su **`avvia-windows.bat`**: si apre un terminale dove il comando `archivio` funziona già. In alternativa, in Esplora file apri la cartella `ArchivioFoto`, clicca sulla barra dell'indirizzo, scrivi `cmd` e premi Invio.
- **macOS**: tasto destro sulla cartella `ArchivioFoto` → *Servizi* → *Nuovo Terminale nella cartella*.

Verifica l'installazione:
```bat
:: Windows
.venv\Scripts\archivio --version
```
```bash
# macOS
.venv/bin/archivio --version
```

Per non scrivere ogni volta il percorso, attiva l'ambiente: `.venv\Scripts\activate` (Windows) o `source .venv/bin/activate` (macOS). Da quel momento basta scrivere `archivio`.

## 5. Configura la chiave API NVIDIA (per la lettura AI e l'assistente)
1. Accedi a https://build.nvidia.com e crea una API key (inizia con `nvapi-`).
2. **Windows**: `setx NVIDIA_API_KEY "nvapi-LA-TUA-CHIAVE"`, poi **chiudi e riapri** il terminale.
3. **macOS**: `echo 'export NVIDIA_API_KEY=nvapi-LA-TUA-CHIAVE' >> ~/.zshrc`, poi chiudi e riapri il Terminale.

Senza chiave tutto il resto funziona: analisi tecnica, volti, revisione, guida e ricerca negli articoli.

## 6. Crea l'archivio e fai la prova
```bash
archivio init D:\Archivio          # macOS: archivio init ~/Archivio
cd D:\Archivio
archivio verifica --rete           # controlla installazione, chiave e connessione
archivio revisione                 # apre la webapp nel browser, con tutorial e guida
```
Alla prima apertura parte un **tutorial** guidato. Il pulsante **? Guida** (o il tasto `/`) apre la ricerca negli articoli e l'assistente.

## 7. Aggiornare
- **ZIP**: scarica il nuovo ZIP dagli stessi link, sostituisci la cartella del programma ed esegui di nuovo lo script di installazione. L'archivio delle foto è in un'altra cartella e non viene toccato.
- **Git**: `git pull`, poi di nuovo lo script di installazione.

Cosa è cambiato tra una versione e l'altra: [CHANGELOG.md](CHANGELOG.md), oppure `archivio versione --log`.

## Problemi frequenti
| Sintomo | Soluzione |
|---|---|
| `py` o `python3` non trovato | Reinstalla Python spuntando *Add to PATH* (Windows) |
| `archivio` non trovato | Usa `.venv\Scripts\archivio` / `.venv/bin/archivio`, oppure attiva l'ambiente (punto 4) |
| *Nessun archivio trovato* | Entra nella cartella dell'archivio con `cd` o creala con `archivio init` |
| Errore HTTP 401 | Chiave API errata, oppure terminale non riaperto dopo `setx` |
| Il browser non si apre | Apri a mano l'indirizzo che compare nel terminale (`http://127.0.0.1:8765/`) |
| Porta già in uso | `archivio revisione --porta 8800` |
| File RAW non letti | `.venv\Scripts\pip install rawpy` (Windows) / `.venv/bin/pip install rawpy` (macOS) |
| Mac: "impossibile aprire, sviluppatore non identificato" | Tasto destro → Apri, invece del doppio clic |

Ogni errore del programma resta registrato: `archivio note` oppure la pagina **Note e allarmi** della webapp.
