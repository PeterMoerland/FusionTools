@echo off
rem Dubbelklikbare start van install.ps1, zodat er geen PowerShell-commando
rem overgetypt hoeft te worden. Dubbelklikken op een .ps1 opent in Windows de
rem editor en niet de uitvoering; vandaar dit bestand ernaast.
rem
rem pushd zet een tijdelijke letter op een netwerkpad. Zonder dat begint cmd in
rem de Windows-map met een waarschuwing, want cmd kan niet in een UNC-pad staan.

setlocal
pushd "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set FOUTCODE=%ERRORLEVEL%

popd

echo.
if %FOUTCODE% neq 0 (
    echo De installatie is niet gelukt. Lees de melding hierboven.
) else (
    echo Klaar. Je kunt dit venster sluiten en Fusion starten.
)

echo.
pause
endlocal
