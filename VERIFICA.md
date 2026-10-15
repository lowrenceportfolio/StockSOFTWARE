# Verifica VintDesk 1.2.0

Locale, 14 ottobre 2026, Windows 11:
- 41 test superati (core, aggiornamento dati, interfaccia grafica).
- Build PyInstaller e Inno Setup locale riuscita: `output/VintDesk-Setup-1.2.0.exe`.
- Smoke test dell'eseguibile compilato superato; font incluso nel pacchetto.
- Confronto visivo fra i riferimenti `.taste-skill/mock/ref-*.png` e gli screenshot Tkinter.
Non eseguiti per la 1.2.0: installazione/disinstallazione automatiche e build su GitHub Actions.

---

## Verifica della versione precedente (1.1.0)

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


## Verifica integrazione Supabase 1.3.0 (15 ottobre 2026)

- 58 test locali superati: 15 test del protocollo cloud e 2 nuovi test desktop, oltre ai 41 esistenti.
- PyInstaller: compilazione riuscita; eseguibile verificato con --smoke-test e database isolato build/cloud-smoke.sqlite3 (exit 0).
- Inno Setup: output/VintDesk-Setup-1.3.0.exe generato. Installer non installato sulla copia personale dell'utente.
- Project URL e chiave pubblica: richiesta REST ricevuta da Supabase; tabella assente (PGRST205).
- In attesa di accesso amministrativo tramite integrazione Supabase per applicare supabase/schema.sql. Nessuna migrazione live eseguita, nessun dato utente caricato, nessun test autenticato end-to-end eseguito.
- Interfaccia mobile non inclusa; contratto dati documentato in supabase/README.md.


## Verifica Supabase — 15 ottobre 2026

Stato: configurazione bloccata per sorgente SQL mancante.

- Progetto `dgbooupbrxznjngpkxle` (`vendino`): ACTIVE_HEALTHY, PostgreSQL 17.
- Lo schema `public` non contiene tabelle al momento del controllo.
- Security Advisor: nessuna segnalazione. Questo risultato su uno schema vuoto non dimostra la sicurezza dell’integrazione VintDesk.
- Nel repository `lowrenceportfolio/StockSOFTWARE`, unico ramo remoto `main`, non esistono `supabase/schema.sql` né riferimenti a Supabase nei sorgenti controllati.
- Nessuna modifica eseguita sul database. Applicazione dello schema e test di isolamento degli utenti/RLS non eseguiti: occorre la versione aggiornata del progetto che contiene l’integrazione desktop e il relativo SQL.

Per completare: rendere disponibile `supabase/schema.sql`, confrontarlo con le chiamate del client, applicarlo e verificare autorizzazioni, isolamento tra utenti e accessi Storage previsti. I precedenti test Windows non costituiscono una verifica Supabase.


Nota di pubblicazione: questo aggiornamento aggiunge i sorgenti cloud e supabase/schema.sql mancanti al momento della verifica precedente. Lo schema deve ancora essere applicato e verificato sul progetto Supabase.
