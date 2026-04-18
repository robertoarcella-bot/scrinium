#!/usr/bin/env bash
# Build di Scrinium per macOS.
#
# DEVE ESSERE LANCIATO SU UN MAC. PyInstaller non supporta la compilazione
# cross-platform: un .app macOS può essere prodotto solo da macOS.
#
# Produce:
#   dist/Scrinium.app    (il bundle dell'applicazione)
#   dist/Scrinium.dmg    (l'immagine disco per la distribuzione)
#
# Uso:
#   chmod +x build_mac.sh
#   ./build_mac.sh

set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERRORE: questo script va lanciato su macOS."
    exit 1
fi

echo "=== Verifica Python ==="
PYTHON="${PYTHON:-python3}"
"$PYTHON" --version

echo "=== Installazione dipendenze ==="
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt
"$PYTHON" -m pip install pyinstaller

echo "=== Pulizia build precedenti ==="
rm -rf build dist Scrinium.spec

echo "=== Build Scrinium.app ==="
"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name Scrinium \
    --osx-bundle-identifier it.arcella.scrinium \
    --collect-submodules apscheduler \
    scrinium/__main__.py

APP="dist/Scrinium.app"
if [[ ! -d "$APP" ]]; then
    echo "ERRORE: $APP non prodotto."
    exit 1
fi

echo "=== Creazione DMG di distribuzione ==="
DMG="dist/Scrinium.dmg"
STAGING="dist/dmg-staging"
rm -rf "$STAGING" "$DMG"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
# Scorciatoia alla cartella Applicazioni: quando l'utente apre il DMG
# vede l'icona Scrinium e una freccia ad "Applications": basta trascinare.
ln -s /Applications "$STAGING/Applications"

hdiutil create \
    -volname "Scrinium" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    "$DMG"

rm -rf "$STAGING"

echo ""
echo "=== Build completata ==="
echo "App:        $APP"
echo "Installer:  $DMG"
echo ""
echo "Distribuisci il solo file Scrinium.dmg: l'utente fara' doppio click,"
echo "trascinera' l'icona in Applicazioni, e avra' l'app installata."
echo ""
echo "NOTA sulla firma: l'app non e' firmata con un Apple Developer ID."
echo "Al primo avvio gli utenti dovranno tasto-destro -> Apri, oppure"
echo "autorizzarla da Impostazioni -> Privacy e sicurezza."
