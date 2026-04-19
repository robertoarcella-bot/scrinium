# Changelog

Tutte le modifiche rilevanti a Scrinium sono documentate in questo file.
Formato: data più recente in alto. Le versioni seguono [Semantic Versioning](https://semver.org/lang/it/).

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
