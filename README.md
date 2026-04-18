# Scrinium

*Custodia dei tuoi documenti.*

Dal latino **scrinium**: la cassetta di cuoio e legno in cui i giureconsulti e
i magistrati romani custodivano tavolette cerate, rotoli e documenti.

Software di backup per Windows 10 / 11 con **copia identica**, **copia
incrementale**, **verifica d'integrità SHA-256**, **retry automatico con
backoff esponenziale**, **throttling I/O** e **scheduler integrato** per
eseguire backup automatici a orari definiti.

**Autori:** Avv. Roberto Arcella · Commissione Informatica del Consiglio dell'Ordine degli Avvocati di Napoli

**Data di rilascio:** 18 aprile 2026

---

## Funzionalità

- **Più profili di backup** indipendenti (sorgente → destinazione con regole proprie)
- **Tre modalità chiaramente descritte in GUI**:
  - **Copia completa** – sovrascrive tutto ogni volta
  - **Incrementale** – copia solo i file nuovi o modificati (non cancella nulla)
  - **Mirror** – copia identica 1:1 (cancella in destinazione i file rimossi in sorgente)
- **Due criteri di confronto**: veloce (dimensione + data) o sicuro (hash SHA-256)
- **Verifica post-copia**: ricalcolo dell'hash e, se diverso, ricopia automatica
- **Retry automatico** con backoff esponenziale (file bloccati, errori transienti)
- **Throttling MB/s** configurabile per non saturare disco/rete
- **Pattern di esclusione** (glob: `*.tmp`, `~$*`, `.git`, `Thumbs.db`, ecc.)
- **Pausa / ripresa / annullamento** durante l'esecuzione
- **Schedulazione integrata** (cron) con preset amichevoli
- **Log rotazionale** in `%APPDATA%\Scrinium\scrinium.log`
- **Report dettagliato** dell'ultimo run per profilo

## Requisiti

- Windows 10/11 (x64) — build nativa via PyInstaller
- macOS 12+ — build nativa su Mac tramite `build_mac.sh`
- Per sviluppo / build: Python 3.10+

## Avvio in sviluppo

```cmd
pip install -r requirements.txt
python -m scrinium
```

## Build dell'eseguibile (.exe)

Doppio click su `build.bat` oppure da prompt:

```cmd
build.bat
```

Output: `dist\Scrinium.exe` (singolo file, eseguibile senza installazione).

## Creazione installer

### Windows

Lo script `build_installer.bat` produce **`dist\Scrinium-Setup.exe`**,
un installer autocontenuto (include Scrinium.exe al suo interno) con
wizard in italiano, scorciatoie Desktop/Start e registrazione in
*Impostazioni → App installate*. Nessun software esterno richiesto.

Alternativa professionale (installer più leggero): installare
[Inno Setup](https://jrsoftware.org/isinfo.php), aprire `installer.iss` e
premere **Compile**.

### macOS

Lo script **`build_mac.sh`** (da lanciare su un Mac) produce:
- `dist/Scrinium.app` — bundle applicazione
- `dist/Scrinium.dmg` — immagine disco per distribuzione

L'utente finale apre il DMG e trascina l'icona in *Applicazioni*.

```bash
chmod +x build_mac.sh
./build_mac.sh
```

> PyInstaller non supporta cross-compilation: il build Mac si può
> produrre solo da un Mac.

## Uso tipico

1. Avviare Scrinium
2. **Nuovo profilo** → dare un nome (es. *Fascicoli 2026 → disco esterno*)
3. Scegliere **sorgente** e **destinazione**
4. Selezionare la **modalità** (tipicamente *Incrementale* per uso quotidiano)
5. Lasciare attiva la **verifica hash** per sicurezza massima
6. Facoltativo: impostare una **schedulazione** (es. *ogni giorno alle 22:00*)
7. Salvare. Cliccare **Esegui ora** per il primo backup completo.

## Dove sono i dati

- Profili: `%APPDATA%\Scrinium\profiles.json`
- Log: `%APPDATA%\Scrinium\scrinium.log`

## Note sullo scheduler

Lo scheduler integrato gira dentro l'applicazione: i backup automatici
scattano quando Scrinium è aperto (anche minimizzato). Per una
schedulazione che funzioni anche a Scrinium chiuso, usare il Task
Scheduler di Windows richiamando `Scrinium.exe`.

## Licenza

Software ad uso personale/professionale dell'autore.
