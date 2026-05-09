@echo off
REM Costruisce Scrinium-Setup.exe (installer autocontenuto, include Scrinium.exe).
REM Prerequisito: aver gia' prodotto dist\Scrinium.exe (eseguire prima build.bat).

setlocal
cd /d "%~dp0"

if not exist "dist\Scrinium.exe" (
    echo.
    echo ERRORE: dist\Scrinium.exe non trovato.
    echo Eseguire prima build.bat per produrre l'eseguibile principale.
    echo.
    exit /b 1
)

echo === Installazione PyInstaller ===
python -m pip install pyinstaller >nul 2>&1

echo === Pulizia build precedenti installer ===
if exist build\Scrinium-Setup rmdir /s /q build\Scrinium-Setup
if exist Scrinium-Setup.spec del /q Scrinium-Setup.spec
if exist dist\Scrinium-Setup.exe del /q dist\Scrinium-Setup.exe

echo === Build Scrinium-Setup.exe (include Scrinium.exe al suo interno) ===
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name Scrinium-Setup ^
    --add-data "dist\Scrinium.exe;." ^
    --add-data "scrinium\__init__.py;scrinium" ^
    installer_app\setup.py || goto :err

echo.
echo === Installer pronto ===
echo   %cd%\dist\Scrinium-Setup.exe
echo.
echo Doppio click per installare. L'installazione avviene in
echo   %%LOCALAPPDATA%%\Programs\Scrinium
echo senza richiedere diritti di amministratore.
exit /b 0

:err
echo.
echo *** BUILD INSTALLER FALLITA ***
exit /b 1
