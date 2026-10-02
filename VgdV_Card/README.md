# VgdV Card

App Android per uso interno: scansiona un biglietto da visita e lo salva in rubrica, con gruppi e note.

## Flusso
1. **Scansione**: ML Kit Document Scanner, con ritaglio automatico e fino a 2 pagine (fronte/retro), oppure import dalla galleria.
2. **OCR on-device**: ML Kit Text Recognition. La foto non lascia mai il telefono.
3. **Analisi** del solo testo, con uno di questi motori:
   - Google Gemini (default `gemini-2.5-flash`)
   - NVIDIA / qualsiasi API OpenAI-compatibile (default `meta/llama-3.3-70b-instruct`)
   - Offline: parser a regole, usato anche come fallback automatico se l'LLM fallisce
4. **Revisione**: campi modificabili, tipo di ogni numero (Cellulare/Lavoro/Fax…), gruppi della rubrica suggeriti dall'LLM, controllo duplicati per telefono/email.
5. **Note**: data + evento/luogo, nota libera (anche dettata a voce), profilo sintetico generato dall'AI.
6. **Salvataggio** nella rubrica dell'account Google scelto (necessario per i gruppi).

## Installazione
Ogni push compila l'APK tramite GitHub Actions: apri **Actions → Build APK → ultimo run → Artifacts → VgdV-Card-apk**.
Scarica `app-release.apk` (firmato con chiave debug, adatto all'uso interno) e installalo consentendo le "origini sconosciute".

## Configurazione
Impostazioni (icona ⚙):
- chiave API Gemini da https://aistudio.google.com/apikey, oppure chiave NVIDIA da https://build.nvidia.com
- account di destinazione e formato del nome

Le chiavi sono salvate cifrate con Android Keystore.

## Build locale
Android Studio (JDK 17), quindi `cd VgdV_Card && ./gradlew assembleDebug` (oppure apri la cartella `VgdV_Card` in Android Studio).
