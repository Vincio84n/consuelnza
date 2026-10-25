# Installazione di ArchivioFoto

## Download
| Sistema | File | Serve Python? |
|---|---|---|
| **Windows 10/11** | [ArchivioFoto-Windows.zip](https://github.com/Vincio84n/consuelnza/releases/download/archiviofoto/ArchivioFoto-Windows.zip) | No |
| **macOS Apple Silicon** (M1, M2, M3, M4) | [ArchivioFoto-macOS.zip](https://github.com/Vincio84n/consuelnza/releases/download/archiviofoto/ArchivioFoto-macOS.zip) | No |
| Mac Intel, Linux, uso da terminale | [ArchivioFoto-sorgenti.zip](https://github.com/Vincio84n/consuelnza/releases/download/archiviofoto/ArchivioFoto-sorgenti.zip) | Sì, 3.10+ |

Tutte le versioni e le novità: https://github.com/Vincio84n/consuelnza/releases/tag/archiviofoto

## Windows
1. Scarica **ArchivioFoto-Windows.zip** ed estrailo: tasto destro → *Estrai tutto…*, ad esempio in `C:\ArchivioFoto`. Non avviarlo dall'interno dello ZIP.
2. Apri la cartella `ArchivioFoto` e fai doppio clic su **ArchivioFoto.exe**.
3. Se compare *"Windows ha protetto il PC"*: **Ulteriori informazioni → Esegui comunque**. Succede perché il programma non è firmato digitalmente.
4. Si apre una finestra nera: è il motore del programma e **deve restare aperta**. Al primo avvio compare la finestra per **scegliere la cartella dell'archivio**: scegline una vuota per crearne uno nuovo.
5. Si apre il browser con la webapp e parte il tutorial.

Per comodità: tasto destro su `ArchivioFoto.exe` → *Mostra altre opzioni* → *Crea collegamento*, poi sposta il collegamento sul Desktop.

## macOS
1. Scarica **ArchivioFoto-macOS.zip** e aprilo: compare **ArchivioFoto.app**. Trascinala in **Applicazioni**.
2. Primo avvio: **tasto destro → Apri → Apri**.
3. Se macOS non lo permette (macOS 15 e successivi): *Impostazioni di Sistema → Privacy e sicurezza*, in fondo **Apri comunque**, poi conferma.
4. Scegli la cartella dell'archivio. Si apre il browser con la webapp.

Il programma resta attivo in background: per chiuderlo usa il pulsante **Esci** nella webapp. Se qualcosa non parte, il file `~/Library/Application Support/ArchivioFoto/ultimo-avvio.log` contiene i messaggi.

## Prima configurazione (5 minuti, dalla webapp)
1. **Impostazioni → Chiave API**: crea una chiave su https://build.nvidia.com (inizia con `nvapi-`), incollala e premi *Salva chiave*. Viene salvata nel **portachiavi del sistema** (Gestione credenziali di Windows, Portachiavi di macOS), mai nei file.
2. **Impostazioni → Motori AI**: *Carica elenco modelli*, scegli i modelli e premi **Prova visione** e **Prova testo**.
3. **Istruzioni**: descrivi l'archivio (chi, dove, quando) e le parole da usare nei tag.
4. **Lavori → Importa rullino**: sei pronto.

Tutte le scelte finiscono nei file **CONFIGURAZIONE.md** e **ISTRUZIONI.md** della cartella dell'archivio, e ogni operazione nel **REGISTRO.md**.

## Aggiornare
La webapp avvisa quando su GitHub c'è una versione nuova. Scarica lo ZIP e sostituisci la cartella del programma (Windows) o l'app (macOS). **L'archivio non viene toccato**: foto, dati, configurazione, istruzioni e registro stanno nella cartella dell'archivio.

## Versione da sorgenti (Mac Intel, Linux, uso avanzato)
1. Installa Python 3.10+ da https://www.python.org/downloads/ (su Windows spunta *Add python.exe to PATH*).
2. Estrai **ArchivioFoto-sorgenti.zip**.
3. Esegui `installa-windows.bat` (Windows) oppure `installa-mac.command` (macOS: tasto destro → Apri).
4. Avvia con `avvia-windows.bat`, oppure da terminale: `.venv/bin/archivio app` (macOS/Linux) o `.venv\Scripts\archivio app` (Windows).

In alternativa con Git: `git clone https://github.com/Vincio84n/consuelnza.git`

## Uso da terminale
Lo stesso eseguibile funziona anche da riga di comando: `ArchivioFoto.exe --help` (Windows), oppure `/Applications/ArchivioFoto.app/Contents/MacOS/ArchivioFoto --help` (macOS). Comandi utili: `config`, `chiave`, `motori`, `istruzioni`, `registro`, `aggiorna`.

## Problemi frequenti
| Sintomo | Soluzione |
|---|---|
| "Windows ha protetto il PC" | Ulteriori informazioni → Esegui comunque |
| macOS: "impossibile aprire" o "app danneggiata" | Privacy e sicurezza → Apri comunque |
| Il browser non si apre | Apri a mano `http://127.0.0.1:8765/` |
| Porta occupata | Il programma prova da solo le porte successive (8766, 8767…) |
| Chiave rifiutata (HTTP 401) | Ricreala su build.nvidia.com e salvala di nuovo in Impostazioni |
| "Configurazione non valida" | Apri Impostazioni: indica la riga e il valore da correggere |
| Voglio cambiare archivio | Avvia con `ArchivioFoto app --scegli` oppure dal terminale `ArchivioFoto app <cartella>` |
| Antivirus blocca l'exe | Falso positivo frequente con i programmi non firmati: aggiungi un'eccezione per la cartella |

Ogni errore resta registrato nella pagina **Note** e nel file **REGISTRO.md**.
