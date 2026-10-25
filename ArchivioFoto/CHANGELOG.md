# Registro delle versioni

Formato: [Keep a Changelog](https://keepachangelog.com/it/1.1.0/). Numerazione [SemVer](https://semver.org/lang/it/).
La versione in uso si vede con `archivio versione` (o `archivio versione --log` per questo registro), nell'interfaccia di revisione e nel campo `versione_tool` di ogni scheda JSON.

## [0.5.0] - 2026-10-25
### Aggiunto
- **Chiave API in CHIAVE.md**: in alternativa al portachiavi, la chiave si può salvare in un file Markdown nella cartella dell'archivio (`archivio chiave imposta --file`, oppure *Dove salvarla* in Impostazioni). Il file è escluso da Git e dagli ZIP di rilascio; `verifica` ricorda che contiene la chiave in chiaro.
- **Motore selezionato sempre per primo**: `nvidia/nemotron-3-ultra-550b-a55b` è il motore predefinito sia per le foto sia per l'assistente. `nvidia/nemotron-nano-12b-v2-vl` è la riserva di visione: subentra se il motore selezionato non legge un'immagine, e dopo due foto di fila viene usata direttamente per il resto della lettura, con una nota.

### Corretto
- `motori elenca` mostra tutti i ruoli quando un modello ne copre più di uno.

## [0.4.1] - 2026-10-25
### Modificato
- Modello di testo predefinito (assistente della guida): `nvidia/nemotron-3-ultra-550b-a55b`. Gli archivi esistenti mantengono il valore scritto in CONFIGURAZIONE.md: per cambiarlo usa `archivio motori usa testo nvidia/nemotron-3-ultra-550b-a55b` o la pagina Impostazioni.

## [0.4.0] - 2026-10-25
### Aggiunto
- **CONFIGURAZIONE.md**: tutte le scelte del programma in un file Markdown leggibile, modificabile a mano, dalla webapp (*Impostazioni*) o con `archivio config imposta`. Ogni valore viene controllato: un errore indica la riga e blocca i comandi invece di essere ignorato. La versione della configurazione aumenta a ogni modifica.
- **Motori NVIDIA**: tre ruoli (visione, testo, riserva automatica). `archivio motori elenca` legge i modelli disponibili dall'API; `motori prova` fa una chiamata reale e misura tempi ed esito; `motori usa` cambia il modello. Gli stessi pulsanti sono nella pagina Impostazioni.
- **Chiave API nel portachiavi del sistema** (Windows e macOS): `archivio chiave imposta|stato|rimuovi`, oppure dalla webapp. Non viene mai scritta nei file né nel registro; se la si scrive in CONFIGURAZIONE.md viene rifiutata.
- **ISTRUZIONI.md**: contesto dell'archivio e regole passati all'AI, vocabolario controllato dei tag (i sinonimi vengono uniformati) e tag vietati. Ogni lettura AI registra la versione delle istruzioni; `archivio ai --obsolete` rilegge le foto lette con istruzioni vecchie.
- **REGISTRO.md**: diario in sola aggiunta di ogni operazione (comando, dettagli, esito, versione del programma) e di ogni modifica a configurazione, istruzioni e chiave.
- **Aggiornamenti**: `archivio aggiorna` e avviso nella webapp quando su GitHub c'è una versione nuova.
- **Eseguibile autonomo** per Windows (`ArchivioFoto.exe`) e macOS Apple Silicon (`ArchivioFoto.app`): non serve installare Python. Al primo avvio chiede la cartella dell'archivio e la ricorda.
- **Pagina Lavori**: importazione (con *Sfoglia…*), analisi, lettura AI, volti, XMP, viste, verifica e doppioni dalla webapp, con avanzamento in tempo reale. Pulsante **Esci**.
- Pagine **Impostazioni**, **Istruzioni** e **Registro**; nuovi articoli della guida.
- **Sicurezza della webapp**: token di sessione su tutte le richieste che modificano dati e blocco degli host non locali.

### Modificato
- `archivio.json` sostituito da CONFIGURAZIONE.md, con migrazione automatica.
- La lettura AI si ferma dopo `errori_consecutivi_max` errori di fila (configurabile).
- "Cosa fare adesso" segnala anche chiave mancante, configurazione non valida e foto con istruzioni vecchie.

## [0.3.0] - 2026-10-25
### Aggiunto
- **Guida integrata nella webapp**: 20 articoli (primi passi, installazione, ogni comando, note e allarmi, backup, risoluzione problemi), con pagina indice `/guida`.
- **Suggerimenti a comparsa** (ⓘ) su campi, dati e allarmi, attivabili e disattivabili dal pulsante *Suggerimenti*. La scelta viene ricordata.
- **Tutorial guidato** per ogni pagina (rullini, rullino, note, guida): evidenzia gli elementi e li spiega passo per passo. Parte da solo alla prima visita, si può disattivare e riavviare dal pulsante *Tutorial*.
- **Motore di ricerca e assistente** (pulsante *? Guida* o tasto `/`): ricerca istantanea negli articoli, anche offline. *Chiedi* invia la domanda al modello AI (`ai.modello_testo`, default Nemotron 3 Super) insieme agli articoli pertinenti e allo stato dell'archivio. La conversazione resta tra una pagina e l'altra e cita gli articoli usati.
- **Cosa fare adesso**: riquadro nella pagina iniziale con i prossimi passi calcolati sullo stato reale dell'archivio, ciascuno con il comando da eseguire e il link all'articolo della guida.
- Istruzioni di installazione passo per passo (`INSTALLAZIONE.md`) e README principale del repository.

### Modificato
- La grafica della webapp è ora in file separati (`archiviofoto/web/`), con tema chiaro e scuro automatico e layout adatto al telefono.

## [0.2.0] - 2026-10-25
### Aggiunto
- **Note e allarmi** (`archivio note`, pagina "Note e allarmi" nella revisione): registro unico di errori, avvisi, problemi di qualità e note manuali, con stato aperto/chiuso e conteggio delle ripetizioni. Ogni errore di un comando viene registrato in automatico.
- **Allarmi di qualità** durante `analizza`: sotto/sovraesposizione, foto mossa o morbida, luci bruciate, negativo non invertito, risoluzione bassa.
- **`verifica`**: controlla Python, dipendenze, chiave API (`--rete` prova la chiamata), spazio su disco, master mancanti o modificabili, file senza scheda dati, integrità hash (`--hash`).
- **Riconoscimento volti** in locale (OpenCV YuNet + SFace): `volti rileva | raggruppa | elenco | anteprima | nomina`. I nomi si propagano a tutte le foto del gruppo e finiscono in XMP, viste e ricerca.
- **Interfaccia di revisione** nel browser (`archivio revisione`): griglia per rullino, correzione dei campi, "applica a tutto il rullino", spunta "verificata".
- **Somiglianza visiva**: impronta dHash + colore calcolata in `analizza`; comandi `simili` e `doppioni`.
- **Windows e macOS**: pacchetto installabile (`pip install .` crea il comando `archivio`), script `installa-windows.bat` e `installa-mac.command`, nomi file compatibili con Windows, gestione della sola lettura e dei link sui dischi che non li supportano, CSV compatibile con Excel.
- Test automatici e CI su Windows, macOS e Linux.
- Registro delle versioni (questo file) e comando `versione`.

### Modificato
- Il codice è ora il pacchetto `archiviofoto/`; `python archivio.py` continua a funzionare senza installazione.
- `ai` si ferma dopo 3 errori consecutivi, invece di consumare richieste su tutto l'archivio.

## [0.1.0] - 2026-10-25
### Aggiunto
- Prima versione: `init`, `ingest` con ID immutabili e verifica hash, `analizza`, `ai` (API OpenAI-compatibile, default NVIDIA), `annota` da CSV, `imposta`, `viste`, `xmp`, `cerca`, `esporta`, `stato`.
