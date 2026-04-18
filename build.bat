@echo off
REM Build Scrinium.exe via PyInstaller (singolo file, finestra grafica, niente console).
REM Uso: doppio click oppure `build.bat` da cmd.

setlocal
cd /d "%~dp0"

echo === Installazione dipendenze ===
python -m pip install --upgrade pip || goto :err
python -m pip install -r requirements.txt || goto :err
python -m pip install pyinstaller || goto :err

echo === Pulizia build precedenti ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist Scrinium.spec del /q Scrinium.spec

echo === Build PyInstaller ===
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name Scrinium ^
    --collect-submodules apscheduler ^
    scrinium\__main__.py || goto :err

echo.
echo === Build completata ===
echo Eseguibile: %cd%\dist\Scrinium.exe
exit /b 0

:err
echo.
echo *** BUILD FALLITA ***
exit /b 1
