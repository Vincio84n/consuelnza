@echo off
rem Installa ArchivioFoto in un ambiente Python isolato (.venv) nella cartella del programma.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -m venv .venv || (echo Python 3.10+ non trovato: installalo da https://www.python.org/downloads/ spuntando "Add to PATH" & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[volti]" || (echo Installazione fallita & pause & exit /b 1)
echo.
echo Installato. Apri un terminale in questa cartella e usa:  .venv\Scripts\archivio --help
pause
