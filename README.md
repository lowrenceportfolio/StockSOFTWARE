# VintDesk

Gestionale desktop personale per stock e vendite Vinted. Interfaccia italiana,
database SQLite locale, nessun abbonamento e nessuna dipendenza di esecuzione
esterna oltre a Python quando si avvia dai sorgenti.

**Versione 1.0.0:** installer Windows compilato e verificato. Tutti i 16 test,
la verifica dell'eseguibile e i controlli di installazione/disinstallazione
sono stati superati su GitHub Actions.

## Cosa fa

- Stock per capo: SKU, titolo, marca, taglia, categoria, condizione, costo,
  prezzo annuncio, posizione fisica, data acquisto, link e note.
- Box: crea automaticamente tutti i capi e ripartisce il prezzo totale,
  spedizione inclusa, conservando ogni centesimo.
- Vendite: In attesa, Spedita, Completata; una sola vendita attiva per capo.
- Resi completi e annullamenti: ripristinano lo stock mantenendo lo storico.
- Dashboard: stock a costo, vendite completate, incassi, utile, saldo di cassa,
  andamento degli incassi mensili e capi acquistati da almeno 30 giorni.
- Spese generali, importazione capi CSV, export stock e vendite.
- Backup completo e ripristino con copia di sicurezza preventiva.

**Inserimento manuale o CSV.** Non accede al tuo account Vinted, non scarica
vendite o annunci e non pubblica automaticamente. Il link del capo si apre nel
browser. I dati del negozio non vengono inviati a GitHub.

## Scaricare il software

Repository del progetto: [StockSOFTWARE](https://github.com/lowrenceportfolio/StockSOFTWARE).

Apri [la build verificata](https://github.com/lowrenceportfolio/StockSOFTWARE/actions/runs/38546127005)
e scarica l'artefatto **VintDesk-Windows-Installer** in fondo alla pagina.
Estrai lo ZIP e avvia `VintDesk-Setup-1.0.0.exe` sul PC Windows.
Non devi installare Python.

Ogni push su `main` compila e verifica il software. Gli artefatti sono disponibili
per 30 giorni: conserva una copia del setup. La pubblicazione automatica in
Releases non è configurata; il workflow usa soltanto `contents: read`.

La repo contiene il software. Stock, vendite e backup rimangono sul tuo PC.

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

Per correggere il prezzo di una vendita: annullala e registrala di nuovo.
Il costo di un capo da box è bloccato per mantenere coerente il totale.

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

Risultato: `output\VintDesk-Setup-1.0.0.exe`.
La compilazione Windows deve avvenire su Windows: PyInstaller non genera
eseguibili Windows da una normale compilazione Linux.

## Struttura

- `app.py`: interfaccia desktop e avvio.
- `core.py`: database, contabilità, CSV e backup.
- `tests/test_core.py`: verifiche dei flussi e dei conteggi.
- `tests/test_ui.py`: verifica del percorso utente nell'interfaccia.
- `installer/vintdesk.iss`: installazione per utente e collegamenti.
- `build-windows.ps1`: compilazione locale e creazione setup.
- `.github/workflows/build-windows.yml`: compilazione e verifica su GitHub.

Non caricare nel repository database, backup o CSV con dati personali.
Il progetto include una `.gitignore` che esclude database, log e risultati
di compilazione. Il programma è indipendente da Vinted.
