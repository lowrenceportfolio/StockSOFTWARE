# Verifica VintDesk 1.1.0

Verifica locale il 14 ottobre 2026: 33 test superati, inclusi 4 test
nell’interfaccia grafica con display virtuale.

Copertura: caricamento foto durante la creazione, annullamento delle modifiche
alle foto, backup/ripristino delle immagini, migrazione dalla versione 1.0,
correzione di costi e margini, modifica vendite e spese, protezione dello storico,
quantità e prezzo dei box, tracking, scadenze e distinzione fra consegna e incasso.

## Verifica Windows

La build [38555004325](https://github.com/lowrenceportfolio/StockSOFTWARE/actions/runs/38555004325)
del commit `6200a695fd5ce66e876e8a92d7e8920215091b3c` è riuscita.

- Tutti i 33 test: superati su Windows.
- Compilazione PyInstaller e Inno Setup: superate.
- Avvio dei sorgenti con visualizzazione delle foto: superato.
- Avvio dell’eseguibile con anteprima e scheda foto: superato.
- Installazione e avvio dell’app installata, incluse le foto: superati.
- Disinstallazione: superata.

Il workflow conserva `contents: read`. Nessun dato reale dell’utilizzatore
è stato usato nei test. Il setup è `VintDesk-Setup-1.1.0.exe`.
