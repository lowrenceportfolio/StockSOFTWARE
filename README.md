# VintDesk

Gestionale desktop personale per stock e vendite Vinted. Interfaccia italiana,
database SQLite locale e sincronizzazione facoltativa con Supabase. L’installer include Python e Pillow;
per avviare i sorgenti occorre installare le dipendenze di requirements.txt.

**Versione 1.3.0:** accesso Supabase, sincronizzazione del registro e delle foto, protezione dei conflitti e backup prima dei download. Configurazione e limiti in [supabase/README.md](supabase/README.md). La futura interfaccia mobile potrà usare lo stesso account e lo stesso database.

**Versione 1.2.0:** panoramica operativa (cosa fare oggi, margine medio, ROI,
giorni alla vendita, marche più redditizie), stock con età dei capi, duplicazione
e cambio stato multiplo, ricerca e filtri nelle vendite, scorciatoie da tastiera,
interfaccia nitida su schermi ad alta risoluzione e backup automatico giornaliero.
La versione 1.1 ha introdotto foto, modifica completa e spedizioni; i dati si
migrano senza interventi. I test automatici sono 58.

## Cosa fa

- Stock per capo, con fino a 12 foto: SKU, titolo, marca, taglia, categoria, condizione, costo,
  prezzo annuncio, posizione fisica, data acquisto, link e note.
- Box: crea automaticamente tutti i capi e ripartisce il prezzo totale,
  spedizione inclusa, conservando ogni centesimo.
- Vendite: In attesa, Spedita, Completata; una sola vendita attiva per capo.
- Resi completi e annullamenti: ripristinano lo stock mantenendo lo storico.
- Dashboard: stock a costo, vendite completate, incassi, utile, saldo di cassa,
  andamento degli incassi mensili e capi acquistati da almeno 30 giorni.
- Modifica completa di capi, box, vendite e spese, con ricalcolo dei margini.
- Spedizioni: corriere, codice/link tracking, scadenza, date, stato e note.
- Spese generali, importazione capi CSV, export stock e vendite.
- Backup completo e ripristino con copia di sicurezza preventiva.

**Inserimento manuale o CSV.** Non accede al tuo account Vinted, non scarica
vendite o annunci e non pubblica automaticamente. Il link del capo si apre nel
browser. I dati del negozio non vengono inviati a GitHub.

## Scaricare il software

Repository del progetto: [StockSOFTWARE](https://github.com/lowrenceportfolio/StockSOFTWARE).

Apri [GitHub Actions](https://github.com/lowrenceportfolio/StockSOFTWARE/actions),
seleziona l’ultima build riuscita e scarica l’artefatto **VintDesk-Windows-Installer**.
Estrai lo ZIP e avvia `VintDesk-Setup-1.3.0.exe` sul PC Windows.
Non devi installare Python. Chiudi l’app prima di aggiornare: il setup installa
la nuova versione nella stessa cartella e conserva il tuo database.

Ogni push su `main` compila e verifica il software. Gli artefatti sono disponibili
per 30 giorni: conserva una copia del setup. Il workflow usa `contents: read`.

La repo contiene il software. Stock e vendite restano sul PC e, quando attivi la sincronizzazione, vengono copiati nel tuo progetto Supabase insieme alle foto. I backup rimangono locali.

## Installazione e dati

Destinazione: Windows 10/11 a 64 bit. Il setup installa l'app per il tuo utente,
senza richiedere Python sul PC e senza richiedere privilegi amministrativi.
L'installer è autonomo: contiene i file necessari, non è un downloader.

Il database è in `%LOCALAPPDATA%\VintDesk\vintdesk.sqlite3`. La cartella contiene
anche `errors.log` e le copie create prima di un ripristino. Aggiornamento e
disinstallazione mantengono questa cartella. Il database non è cifrato.
Usa **Dati e backup → Backup completo** per copiarlo su un altro dispositivo.

## Primo utilizzo

1. Apri **Box acquistati → Nuovo box**.
2. Inserisci nome, fornitore, numero di capi e costo totale con spedizione.
3. In **Stock**, modifica i capi generati: nome, marca, taglia, prezzo, posizione.
4. Quando pubblichi su Vinted, imposta **In vendita** e inserisci il link.
5. Seleziona il capo e scegli **Registra vendita**.
6. Inserisci il prezzo del capo, esclusi costi pagati direttamente dal compratore.
   Inserisci commissioni e spedizione soltanto se sono a tuo carico.
7. In **Vendite**, marca **Completata** dopo aver ricevuto il denaro.

## Foto durante l’inserimento

Apri **Stock → Aggiungi capo**. Nella stessa schermata, la scheda
**Foto · carica dal PC** permette di scegliere una o più immagini con
**Carica foto dal PC**. Premi **Salva** per registrare dati e foto insieme.
Puoi aggiungere o rimuovere foto anche modificando un capo già salvato.
Chiudere con Annulla non applica le modifiche alle immagini.

JPG, PNG e WebP; massimo 12 foto per capo, 20 MB e 50 megapixel per file.
Le immagini vengono orientate e salvate come JPEG con lato massimo 2000 pixel.
Sono memorizzate nel database: puoi spostare gli originali senza perdere le
foto e un backup completo include tutte le immagini. Il CSV non include foto.

## Correggere i dati

- **Stock → Modifica:** cambia tutti i dati e le foto, anche dopo una vendita.
  Lo stato di un capo con vendita attiva è determinato dalla vendita.
- Correggere il costo di un capo aggiorna il totale del box e il costo usato
  per calcolare il margine della vendita attiva. Le vendite annullate mantengono
  il loro storico, finché non le modifichi esplicitamente.
- **Vendite → Modifica vendita:** cambia capo associato, date, prezzo,
  commissioni, spedizione, compratore, note e stato, senza annullare prima.
  Una vendita annullata può essere riattivata solo se il capo è libero.
- **Box acquistati → Modifica box:** correggi nome, fornitore, data, quantità
  e totale. Cambiare quantità o totale ridistribuisce il costo tra tutti i capi
  e aggiorna il margine delle vendite attive, incluse quelle completate.
  La riduzione della quantità rimuove solo gli ultimi capi ancora vuoti.
- **Spese → Modifica spesa:** correggi data, descrizione e importo.
- Un capo può essere Archiviato: esce dallo stock operativo, conservando il
  costo negli acquisti e il saldo di cassa. Archiviare non registra una perdita.
- I pulsanti Elimina servono a rimuovere inserimenti errati. L’eliminazione
  richiede conferma. Capi e box con storico vendite non sono eliminabili;
  per rimuoverli devi prima eliminare esplicitamente le vendite errate.
  Per i resi usa Annulla / reso, così conservi lo storico.

## Spedizioni

Ogni vendita crea una spedizione nella sezione **Spedizioni**. Seleziona una
riga e **Gestisci spedizione** per inserire corriere, codice e link tracking,
scadenza, data di spedizione/consegna, stato e note.

- Filtri: Da spedire, Tutte, Spedita, Consegnata, Problema e Scadute.
- Le scadenze superate sono evidenziate e segnalate nella panoramica.
- **Apri tracking** apre il link che hai inserito; **Copia codice** copia il codice.
- Gli stati sono aggiornati manualmente: non interroga i corrieri.
- Segnare Spedita aggiorna una vendita In attesa a Spedita. Consegnata non
  registra automaticamente un incasso: completa la vendita quando ricevi i soldi.
- Annullare una vendita annulla anche la spedizione. Le vecchie vendite
  vengono inizializzate con lo stato spedizione derivato dalla vendita;
  le date non conosciute rimangono vuote.

## Novità della 1.2

- **Panoramica:** blocco "Da fare" con pulsanti diretti (spedizioni da inviare o scadute,
  capi da pubblicare, capi fermi da 30 giorni), grafico incassi/utile per mese e indicatori
  di resa: margine medio, ROI sul costo, giorni medi tra acquisto e vendita, percentuale venduta.
- **Stock:** colonna Giorni (età del capo, in rosso se in vendita da 30 giorni o più),
  selezione multipla con **Segna in vendita** e **Archivia**, **Duplica** per capi simili,
  pareggio e margine atteso nel dettaglio.
- **Vendite:** ricerca, filtro per stato, margine percentuale e totale dei risultati visibili.
- **Tastiera:** Ctrl+1…7 cambia pagina, Ctrl+N nuovo capo, Ctrl+F cerca, F5 aggiorna,
  Invio apre la riga selezionata; i controlli hanno un contorno di focus visibile.
- **Nuovo aspetto:** tema scuro con un solo accento teal; la forma del cartellino del prezzo
  è il pulsante principale, il riquadro dell'utile, la cornice della foto e l'indicatore di stato
  nelle miniature dello stock. Cursore "Quanto vuoi guadagnare" in panoramica: calcola quanti capi
  vendere al tuo margine medio reale. Date accettate anche come 14/10/2026.
- **Backup automatico:** alla chiusura, al massimo uno ogni 20 ore, in
  `%LOCALAPPDATA%\VintDesk\backup-automatici` (ultime 7 copie). Restano sul PC: copiale altrove.

## Contabilità

Tutti gli importi vengono memorizzati come centesimi interi. Gli importi
immessi accettano il punto oppure la virgola, senza separatore delle migliaia;
le date usano `AAAA-MM-GG`.

- **Margine di una vendita** = prezzo − costo del capo − commissioni − spedizione.
- **Utile netto** = somma dei margini delle vendite completate − spese generali.
- **Saldo di cassa** = incassi delle vendite completate al netto di commissioni
  e spedizioni − costo di tutti i capi acquistati − spese generali.
- **Recupero del box** = incassi netti completati del box − costo iniziale del box.

Esempio: box da 10 capi a 100 €, due venduti a 15 € senza altre spese.
Incassi: 30 €. Utile: 10 €. Saldo di cassa e recupero box: −70 €.
Stock residuo: 8 capi, valore a costo 80 €.

Le vendite in attesa o spedite non generano ricavi nei totali. Anche i relativi
costi della vendita entrano nei totali solo alla conclusione. In un reso completo
vengono stornati ricavi e costi associati alla vendita: eventuali spese trattenute
o non rimborsate vanno registrate separatamente in **Spese**. Resi parziali e
pagamenti frazionati non sono gestiti in questa versione.

I numeri rappresentano il tuo registro operativo: non includono tasse e
contributi e non costituiscono un documento contabile fiscale.

## CSV

Salva il modello da **Dati e backup → CSV e importazione**, oppure usa
`examples/modello-stock.csv`. Modifica o elimina la riga di esempio prima di
importarlo. Sono obbligatorie solo le colonne `titolo` e `costo`; le altre sono
facoltative. Importazione UTF-8, separatori punto e virgola, virgola o tab.
Se uno SKU è vuoto ne viene generato uno nuovo. Gli SKU già presenti bloccano
tutta l'importazione, senza inserimenti parziali. Limite: 10.000 righe per file.

L'importazione aggiunge nuovi capi: non aggiorna quelli già presenti e non
ricostruisce vendite o box dagli export. Il backup SQLite conserva tutto lo
storico. Gli export CSV proteggono i campi testuali che potrebbero essere
interpretati come formule da un foglio di calcolo.

## Sviluppo e compilazione locale

Con Python 3.12 e Tkinter:

```bash
python -m pip install -r requirements.txt
python app.py
python -m unittest discover -s tests -v
python app.py --database test-ui.sqlite3 --smoke-test
```

`--smoke-test` apre tutte le schermate e termina, senza usare i dati personali
se specifichi un database di test.

Per compilare su Windows, installa Python 3.12 e Inno Setup 6, poi:

```powershell
.\build-windows.ps1
```

Risultato: `output\VintDesk-Setup-1.1.0.exe`.
La compilazione Windows deve avvenire su Windows: PyInstaller non genera
eseguibili Windows da una normale compilazione Linux.

## Design

Riferimenti e regole sono in `.taste-skill/`: `direction.json` (direzione estratta), `mock/*.html`
e `mock/ref-*.png` (i riferimenti visivi da cui è tradotta l'interfaccia Tkinter). Token e
componenti stanno in `ui_kit.py`. Il carattere Pilcrow Rounded (Indian Type Foundry, Free Font
License) è incluso nell'installer ma non nel repository: `build-windows.ps1` lo scarica da
Fontshare in `assets/fonts/`. Senza font l'app usa Segoe UI.

## Struttura

- `app.py`: interfaccia desktop e avvio.
- `ui_kit.py`: colori, tipografia e componenti a forma di cartellino.
- `core.py`: database, contabilità, CSV e backup.
- `tests/test_core.py`: verifiche dei flussi e dei conteggi.
- `tests/test_upgrade.py`: foto, modifiche, spedizioni e migrazione dei dati.
- `tests/test_ui.py`: verifica del percorso utente nell'interfaccia.
- `installer/vintdesk.iss`: installazione per utente e collegamenti.
- `build-windows.ps1`: compilazione locale e creazione setup.
- `.github/workflows/build-windows.yml`: compilazione e verifica su GitHub.

Non caricare nel repository database, backup o CSV con dati personali.
Il progetto include una `.gitignore` che esclude database, log e risultati
di compilazione. Il programma è indipendente da Vinted.
