# Verifica VintDesk 1.1.0

Verifica locale il 14 ottobre 2026: 33 test superati, inclusi 4 test
nell’interfaccia grafica con display virtuale.

Copertura: caricamento foto durante la creazione, annullamento delle modifiche
alle foto, backup/ripristino delle immagini, migrazione dalla versione 1.0,
correzione di costi e margini, modifica vendite e spese, protezione dello storico,
quantità e prezzo dei box, tracking, scadenze e distinzione fra consegna e incasso.

La compilazione e i controlli Windows sono configurati in GitHub Actions:
16 test della prima versione erano già stati superati anche su Windows;
la versione 1.1 deve superare l’intera suite aggiornata prima della consegna.

Il workflow non amplia i permessi GitHub e conserva `contents: read`.
