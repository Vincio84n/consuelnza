# Registro delle versioni

Formato: [Keep a Changelog](https://keepachangelog.com/it/1.1.0/). Numerazione [SemVer](https://semver.org/lang/it/).
La versione in uso si vede con `archivio versione` (o `archivio versione --log` per questo registro), nell'interfaccia di revisione e nel campo `versione_tool` di ogni scheda JSON.

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
