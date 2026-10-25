@echo off
rem Apre un terminale pronto all'uso: il comando "archivio" funziona senza percorsi.
cd /d "%~dp0"
if not exist .venv\Scripts\archivio.exe (echo Prima esegui installa-windows.bat & pause & exit /b 1)
start "ArchivioFoto" cmd /k "call .venv\Scripts\activate.bat && archivio --version && echo. && echo Scrivi: archivio --help   oppure   archivio init C:\Archivio"
