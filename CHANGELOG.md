# Changelog

Tutte le modifiche rilevanti a Scrinium sono documentate in questo file.
Formato: data più recente in alto. Le versioni seguono [Semantic Versioning](https://semver.org/lang/it/).

---

## v1.2.3 — 9 maggio 2026

### Fix: installer in stallo se Scrinium era già in esecuzione

Aggiornando da una versione precedente, l'installer poteva
restare bloccato sulla schermata "Copia di Scrinium.exe..." con la
progress bar che oscilla all'infinito. La causa era una
sovrascrittura tentata di ``Scrinium.exe`` mentre il file era ancora
in uso: tipicamente l'app in tray con autostart, oppure una task
headless del Task Scheduler ancora in stato ``Running``. Su Windows
un eseguibile in uso è lockato dal sistema e ``shutil.copy2`` va in
stallo.

L'installer adesso:

- chiude proattivamente le istanze attive di ``Scrinium.exe`` via
  ``taskkill`` (gentile, poi forzato) prima della copia;
- se il target risulta ancora lockato, rinomina il vecchio file in
  ``Scrinium.exe.old-<pid>`` (consentito anche su file in uso) e
  scrive il nuovo al suo posto;
- ritenta fino a tre volte con breve attesa, gestendo l'eventuale
  scansione antivirus dell'eseguibile appena scritto.

---

## v1.2.2 — 7 maggio 2026

### Fix: l'installer mostrava una versione sbagliata

Il wizard di ``Scrinium-Setup.exe`` aveva una costante di versione
hardcoded in ``installer_app/setup.py`` (rimasta a "1.1.3"), che era
disallineata da quella reale del package. L'utente vedeva
"Installazione Scrinium 1.1.3" anche installando la 1.2.1, e la voce
"App installate" di Windows registrava la versione sbagliata.

L'installer ora **legge la versione a runtime** da
``scrinium/__init__.py``, che è l'unica fonte di verità per la
versione: il file viene incluso nel bundle PyInstaller via
``--add-data scrinium/__init__.py;scrinium``. Niente più costante da
ricordare di aggiornare a ogni release.

Nessun cambiamento funzionale al motore di backup o allo scheduler.

---

## v1.2.1 — 7 maggio 2026

### Critico: copie incomplete dichiarate "success"

In tutte le versioni precedenti il motore di backup poteva produrre
backup parziali e dichiararli "success" nel report. La causa era
``os.walk`` chiamato senza ``onerror``: ogni errore di traversata
(``PermissionError`` su una sottocartella, file in lock esclusivo —
PST di Outlook aperto, file Office in uso —, placeholder cloud non
materializzato, drive di rete con timeout, junction point rotti)
veniva ingoiato silenziosamente. I file che si trovavano *dentro* la
sottocartella problematica sparivano dalla scansione e di conseguenza
dal backup, **senza essere conteggiati come falliti**. Il run finiva
con ``files_failed=0`` → ``status=success`` → log ottimistico, ma in
destinazione mancavano interi rami della sorgente.

In questa release:

- ``os.walk`` ora usa una callback ``onerror`` che logga il path non
  esaminato e lo registra come fallimento del run. Anche un solo
  errore di traversata impedisce lo status "success".
- Le ``stat()`` fallite durante la scansione vengono parimenti
  registrate come failure invece di degradare silenziosamente la
  dimensione a zero.
- **Verifica strutturale** dopo la fase di copia: per ogni file
  rilevato in scansione viene controllato che il corrispondente file
  in destinazione esista e abbia dimensione coerente. I mancanti o
  con dimensioni anomale vengono aggiunti a ``failures``. È un
  controllo rapido (no hash) che chiude il cerchio: se per qualunque
  motivo un file scansionato non è arrivato in destinazione, lo status
  finale sarà "partial" o "failed", mai "success".

> Raccomandato: dopo l'aggiornamento, lanciare manualmente ogni
> profilo schedulato e confrontare il nuovo report con la
> destinazione. Eventuali errori di scansione che prima erano
> silenziosi adesso sono visibili nel campo "Fallimenti".

### GUI: tabella aggiornata in tempo reale

La tabella dei profili adesso ricarica ``profiles.json`` da disco
ogni 15 s e prima di ogni salvataggio/eliminazione. Le esecuzioni
headless del Task Scheduler aggiornano il file da fuori della GUI:
prima la GUI, una volta caricata in memoria, lo ignorava. Sintomi
risolti:

- "Le schedulazioni sembrano non scattare" → in realtà scattavano,
  ma la tabella mostrava il ``last_run`` del momento in cui avevi
  aperto l'app.
- Salvare/cancellare un profilo dalla GUI sovrascriveva
  ``profiles.json`` con la versione in memoria, perdendo i
  ``last_run`` aggiornati dalle task headless di quella giornata.
  Adesso la GUI ricarica dal disco prima di scrivere.

### Cap di retry per file in modalità non-cloud

Aggiunto un budget di 5 minuti totali di sleep di backoff per file
nelle modalità non-cloud. Senza cap, un backoff esponenziale
(2 s, 4 s, 8 s, 16 s, …) su un file lockato (PST aperto, file Office
in uso) poteva tenere la task del Task Scheduler in stato ``Running``
per ore, posticipando di fatto i run successivi. La modalità cloud
mantiene attese più lunghe perché lì sono intenzionali per consentire
alla cache cloud di smaltirsi.

---

## v1.2.0 — 26 aprile 2026

### Schedulazione affidata al Task Scheduler di Windows

Le versioni precedenti usavano APScheduler dentro il processo Scrinium:
funzionava solo se l'app era aperta e responsiva, e il PC sveglio
all'orario del cron. In pratica, con il portatile in sleep notturno i
trigger venivano persi; al risveglio la finestra in tray risultava
spesso congelata e andava killata, e fino al successivo riavvio
manuale dell'app non partiva nessun backup.

Da questa release, su Windows la schedulazione di default è delegata
al **Task Scheduler** di sistema:

- Per ogni profilo con `schedule_cron` impostato, Scrinium registra una
  task `\Scrinium\<id>` con `WakeToRun=true` e `StartWhenAvailable=true`:
  Windows **sveglia il PC dallo sleep** all'orario previsto, esegue il
  backup, e se la macchina era spenta recupera la run appena torna
  disponibile.
- Le task invocano `Scrinium.exe --run-profile <id>`, una nuova modalità
  **headless** del programma: nessuna GUI, esecuzione del singolo
  profilo, salvataggio dell'esito su `profiles.json`, exit code mappato
  sullo stato del backup. Funziona anche se l'utente non ha mai aperto
  Scrinium dopo il login.
- Il sync delle task è automatico al boot, a ogni salvataggio o
  cancellazione di profilo, e al cambio di modalità nelle Preferenze.
  Le orfane vengono ripulite.

I cron supportati come trigger nativi del Task Scheduler sono i pattern
realmente esprimibili come `CalendarTrigger`: `M H * * *` (giornaliero),
`M H * * D` (settimanale), `M H D * *` (mensile), `M * * * *` (orario).

La vecchia modalità APScheduler in-app resta disponibile come **fallback
legacy** selezionabile dalla nuova sezione *Modalità di schedulazione*
del dialog Preferenze, per chi preferisce non registrare task nel
sistema.

---

## v1.1.3 — 19 aprile 2026

### Opt-out dal power throttling di Windows 10/11

Su Windows 10, Scrinium lasciato in tray per qualche minuto (anche
con un backup cloud attivo) veniva **sospeso silenziosamente** dal
sistema operativo e poi terminato al primo hover sull'icona della
tray. Il log diagnostico (v1.1.2) ha confermato il pattern: zero
`Tray heartbeat` nei 3-5 minuti di tray, `faulthandler.log` vuoto,
nessun `aboutToQuit` — sintomi tipici di un processo congelato da
EcoQoS e poi ucciso per "unresponsiveness".

Il wake-lock introdotto in v1.1.1 (`SetThreadExecutionState`)
impediva lo sleep del *sistema* ma non la sospensione del *singolo
processo*: Windows 10 usa un meccanismo diverso, il *power
throttling* (EcoQoS), gestito tramite `SetProcessInformation`.
Questa release:

- **Disattiva EcoQoS all'avvio del processo** tramite
  `SetProcessInformation(ProcessPowerThrottling)` con state mask a
  zero: comunica a Windows "questo processo non deve essere
  rallentato né sospeso, neanche quando è senza finestre visibili".
- **Wake lock di sistema reso persistente** per l'intera vita del
  processo (non più solo durante il backup). Lo scheduler continua
  a girare anche con la macchina apparentemente inattiva.
- **Heartbeat della tray portato da 30 s a 10 s**, con primo battito
  sparato immediatamente all'inizializzazione della tray. In caso di
  futuro problema, il log ha granularità tripla per capire quando il
  processo si è davvero fermato.

Il codice del wake-lock è stato rimosso da `BackupEngine` (dove era
condizionato alla singola sessione di backup) e centralizzato in
`__main__.py`.

---

## v1.1.2 — 19 aprile 2026

### Diagnostica dei crash silenti in tray

Alcuni utenti segnalano che Scrinium, lasciato in tray durante un
backup su cartella cloud (Google Drive / OneDrive), sparisce dopo
qualche minuto senza alcuna traccia nel log: nessun *aboutToQuit*,
nessuna icona, nessun errore visibile. Essendo l'eseguibile compilato
in modalità *windowed* (senza console), qualsiasi eccezione Python
non catturata oppure un crash nativo di PyQt viene perso nel nulla.

Questa release aggiunge tre strumenti per catturare la causa alla
prossima occorrenza, senza cambiare il comportamento funzionale
dell'applicazione:

- **Eccezioni Python non catturate**: un `sys.excepthook` installato
  all'avvio scrive nel log (`%APPDATA%\Scrinium\scrinium.log`)
  qualsiasi eccezione non gestita, sia sul thread principale sia sui
  thread secondari (incluso il worker del backup). Livello `CRITICAL`.
- **Crash nativi (segfault, abort C, PyQt)**: `faulthandler` abilitato
  su file dedicato `%APPDATA%\Scrinium\faulthandler.log`. Se il
  processo muore per un errore di memoria o un abort della libreria
  Qt, il file conserva il traceback C di tutti i thread al momento
  del crash.
- **Heartbeat della tray più verboso**: il battito ogni 30 secondi
  ora è a livello `INFO` (prima era `DEBUG`, quindi invisibile nei log
  di produzione) e include anche lo stato del dialog di backup.
  Permette di stabilire con precisione *quando* il processo si è
  fermato rispetto all'ultimo segno di vita.

### Worker di backup resiliente alle eccezioni

Il `BackupWorker` (il `QThread` che fa girare il motore) avvolge ora
`engine.run()` in un `try/except BaseException`: un'eccezione nel
worker non trascina più tutto il processo ma viene loggata e il
`RunDialog` riceve un report fallito, così la GUI non resta appesa.

---

## v1.1.1 — 19 aprile 2026

### Fix — Scrinium non viene più sospeso/terminato quando sta in tray

Su Windows 10/11, un'applicazione senza finestre visibili e senza
"lavoro percepibile" può essere messa in *modern standby* e
successivamente terminata dal sistema operativo (politica di *Process
Lifecycle Management*). Sintomo tipico: dopo qualche minuto con
Scrinium minimizzato nella tray durante un backup, l'icona sparisce e
il processo è terminato.

Due correzioni per rimuovere il problema:

- **Wake lock durante il backup**: il motore chiama
  ``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)``
  all'avvio del run e lo rilascia al termine. Dice al sistema "sto
  lavorando, non sospendermi". Non impedisce lo spegnimento dello
  schermo (solo la sospensione del processo).
- **Heartbeat della tray**: ogni 30 secondi Scrinium verifica che la
  propria icona nella barra di sistema sia visibile e, in caso di
  problemi (es. ``WM_TASKBARCREATED`` dopo un restart di Explorer), la
  ri-mostra automaticamente.

### Diagnostica estesa

Ogni evento tray (click, show/hide), ogni richiesta di uscita e
``QApplication.aboutToQuit`` vengono ora tracciati in
``%APPDATA%\Scrinium\scrinium.log``, completi di stack trace dove
rilevanti. In caso di problema futuro, il log dice esattamente *chi*
ha richiesto la chiusura dell'applicazione.

---

## v1.1.0 — 18 aprile 2026

### Avvio automatico con Windows

Nuova voce **File → Preferenze...** con la casella "Avvia Scrinium
automaticamente all'accensione di Windows". Quando attiva:

- Al login di Windows, Scrinium parte in background direttamente nella
  barra di sistema (nessuna finestra mostrata).
- Le schedulazioni automatiche girano senza che l'utente debba ricordarsi
  di aprire l'applicazione.
- Implementata tramite `HKCU\...\Run` + flag `--startup`: nessun privilegio
  di amministratore richiesto; la preferenza è salvata nel profilo utente
  corrente.

### Compressione dei backup (formato .gz)

Nuova casella **"Comprimi i file in destinazione (formato .gz)"** nell'editor
del profilo. Quando attiva:

- Ogni file è salvato come `<nome>.gz` in destinazione (gzip standard).
- La compressione è applicata in streaming durante la scrittura — nessuna
  copia intermedia né memoria RAM richiesta oltre al chunk da 1 MiB.
- La **verifica d'integrità SHA-256** confronta il contenuto DECOMPRESSO
  del `.gz` con quello del sorgente: l'integrità è garantita anche con
  compressione attiva.
- **Incrementale e mirror** continuano a funzionare: il confronto
  `dimensione + data` usa solo l'mtime (che viene propagato dal sorgente
  al `.gz`); il confronto `hash` apre il `.gz` al volo.
- Livello di compressione: 6 (default gzip, bilanciato tra velocità e
  rapporto di compressione).

### Fix: la tray non causa più la chiusura prematura dell'app

**Bug critico risolto.** Quando sia la main window sia la finestra di
backup erano nascoste nella tray (es. durante un backup lungo
minimizzato), Qt considerava "finita" l'applicazione al primo ciclo di
eventi e chiamava `quit()`, interrompendo il worker del backup.
Aggiunto `QApplication.setQuitOnLastWindowClosed(False)`: ora Scrinium
resta attivo finché non si chiede esplicitamente *Esci* dal menu File o
dalla tray.

---

## v1.0.7 — 18 aprile 2026

### Modalità cloud per destinazioni Google Drive / OneDrive / iCloud

Nuova casella **"Modalità cloud"** nell'editor profilo, pensata per backup
su cartelle sincronizzate con un servizio cloud.

- **Pausa di 1 secondo tra un file e l'altro**, per dare al client cloud il
  tempo di smaltire la coda di upload e liberare la cache locale.
- Sull'errore `[Errno 28] No space left on device` (tipico quando il disco
  locale saturato dalla cache del client cloud respinge nuove scritture),
  il retry passa dal backoff standard 2–4–8 s a una pausa iniziale di
  **120 secondi**, raddoppiata ad ogni tentativo fino a un tetto di 15
  minuti. Così Scrinium aspetta che la coda cloud si svuoti invece di
  abbandonare il file.
- I tentativi massimi per file salgono a 6 (da 3).

Nessun effetto quando la casella non è spuntata: i profili esistenti
mantengono il comportamento precedente.

### Minimize diretto nella tray

Cliccando il pulsante "minimizza" nella barra del titolo della main
window, Scrinium non va più nella taskbar ma direttamente nella barra
di sistema (tray), liberando completamente la barra delle applicazioni.
Lo scheduler continua a girare. Per riaprirla: click sull'icona
Scrinium nella tray.

---

## v1.0.5 — 18 aprile 2026

### Custodia affidabile, anche dopo un'interruzione

Prima, se durante un backup l'utente premeva *Annulla* oppure chiudeva
l'app in emergenza, il file `scrinium-backup.log.txt` nella cartella di
destinazione non veniva aggiornato: niente traccia dei file già copiati.

- **Log sempre scritto al termine**, anche su interruzione. Nuovo stato
  `INTERROTTO DALL'UTENTE` nel report quando si preme *Annulla*.
- **Checkpoint automatico ogni 30 secondi**, salvato in
  `scrinium-backup.in-corso.log.txt`. Se l'applicazione viene killata
  brutalmente (taskkill /F, crash, blackout), in destinazione resta
  comunque un report parziale leggibile con il numero di file già
  copiati, byte trasferiti, primi 10 errori. Il checkpoint viene rimosso
  automaticamente al termine regolare del run.
- Entrambi i file di log sono protetti dal cleanup della modalità
  *Mirror*: non vengono mai cancellati come 'file estranei'.

---

## v1.0.4 — 18 aprile 2026

### Finestra di backup minimizzabile e nascondibile nella tray

Durante un backup in corso, la finestra di avanzamento (prima un
semplice dialog sprovvisto del pulsante "_") diventa completamente
gestibile:

- pulsante **minimizza** nella barra del titolo;
- pulsante esplicito **"Minimizza"** nel pannello comandi;
- pulsante **"Nella tray"** che nasconde la finestra di backup e la main
  window portando Scrinium nella barra di sistema; il backup continua in
  background senza interruzioni;
- dimensione minima 520×360, libera ridimensionabilità;
- chiudere con la X durante il backup non interrompe più il processo ma
  lo porta nella tray.

Quando si riapre Scrinium dalla tray, se c'è un backup in corso la sua
finestra viene ripristinata insieme alla main window.

---

## v1.0.3 — 18 aprile 2026

### System tray, GUI veloce con 100k+ file, run concorrenti bloccati

Fix critici emersi con un backup reale da 97 GB / 139 000 file.

- **System tray**: chiudendo la finestra Scrinium resta attivo nella
  barra di sistema e lo scheduler continua. Icona generata a runtime
  (quadrato navy con "S"). Menu tray: *Apri Scrinium*, *Esegui backup*
  (sottomenu con i profili), *Esci*.
- **GUI non congelabile**: prima il motore emetteva un segnale di
  progresso per ogni file processato, saturando la UI con 100 000+
  emissioni. Ora throttling a ~10 Hz per i progressi ordinari (errori e
  cambi di fase restano istantanei).
- **Prevenzione run concorrenti**: due backup dello stesso profilo
  potevano partire in parallelo (scheduler + avvio manuale
  contestuali). Aggiunto `max_instances=1` e `coalesce=True` nello
  scheduler, più un lock per `profile_id` nella main window.
- **Esclusioni built-in sempre attive**: `desktop.ini`, `Thumbs.db`,
  `~$*` (lock di Office), `.DS_Store`, `*.scrinium-part`. Erano la causa
  di centinaia di errori su archivi reali.
- **Log widget alleggerito**: solo milestone ogni 1 000 file, cambi di
  fase ed errori. Niente più 139 000 righe nella finestra.
- Finestra principale con dimensione minima 640×420 e stato forzato
  "normale" all'avvio (evita che Windows ricordi il fullscreen
  precedente).

---

## v1.0.2 — 18 aprile 2026

### Supporto ai path lunghi Windows (oltre i 260 caratteri)

I file archiviati da AlexPro come PEC (nome derivato dall'oggetto della
mail) producevano percorsi oltre il limite storico Windows MAX_PATH
(260 caratteri), causando errori criptici "No such file or directory".
Ora tutte le operazioni del motore su Windows usano il prefisso `\\?\`,
bypassando il limite. Nessuna modifica al registro richiesta, nessun
privilegio amministratore. Testato con percorsi di 460 caratteri.

---

## v1.0.1 — 18 aprile 2026

### UI blu/grigio, credits aggiornati, log .txt in destinazione

- Tema QSS **blu e grigio** (barra menu navy, pulsanti blu, tabelle con
  header evidenziato).
- Menu **Aiuto → Informazioni**: aggiunta **data di rilascio**, autori
  "Avv. Roberto Arcella e Commissione Informatica del Consiglio
  dell'Ordine degli Avvocati di Napoli", rimossa l'email di contatto.
- Al termine di ogni backup viene scritto un report leggibile in
  `scrinium-backup.log.txt` nella cartella di destinazione, in append:
  conserva lo storico di tutti i run.

---

## v1.0.0 — 18 aprile 2026

### Prima release

Scrinium nasce come software libero di backup incrementale per Windows
10/11 e macOS 12+, pensato per avvocati, giuristi e chiunque abbia
necessità di custodire con cura i propri documenti.

- Tre modalità: **copia completa**, **incrementale**, **mirror**.
- Due criteri di confronto: veloce (dimensione + data di modifica) e
  sicuro (hash SHA-256).
- **Verifica d'integrità SHA-256** post-copia con ricopia automatica se
  gli hash non coincidono.
- **Retry automatico** con backoff esponenziale.
- **Throttling** MB/s configurabile.
- **Pattern di esclusione** glob.
- **Pausa / Riprendi / Annulla** durante l'esecuzione.
- **Schedulazione integrata** con preset amichevoli (ogni ora, ogni
  giorno alle 22:00, ogni lunedì alle 08:00, ogni 1° del mese).
- **Più profili** di backup indipendenti, ognuno con regole proprie.
- Distribuito come installer Windows (`Scrinium-Setup.exe`),
  eseguibile portable (`Scrinium.exe`) e immagine disco macOS
  (`Scrinium.dmg`).

---

*Autori: Avv. Roberto Arcella e Commissione Informatica del Consiglio dell'Ordine degli Avvocati di Napoli*
