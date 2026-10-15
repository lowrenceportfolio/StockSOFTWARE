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
- Stato iniziale della build: schema non ancora applicato. Configurazione server completata nella verifica live riportata sotto; login e sincronizzazione end-to-end dal desktop con account reale restano da eseguire.
- Interfaccia mobile non inclusa; contratto dati documentato in supabase/README.md.


## Verifica Supabase live — 15 ottobre 2026

Stato: schema applicato e regole di accesso verificate sul progetto `dgbooupbrxznjngpkxle` (`vendino`). Sorgenti controllati: commit `08148de`.

- Applicato `supabase/schema.sql` con migrazione `vintdesk_ledger_initial`.
- Applicata migrazione `vintdesk_ledger_least_privilege`: revocati i privilegi predefiniti a PUBLIC, anon e authenticated; ad authenticated concessi soltanto SELECT, INSERT e UPDATE. Corretto anche lo schema nel repository per riprodurre questa configurazione.
- RLS attiva su `public.vintdesk_ledgers`; policy `own_ledger` con `auth.uid() = user_id` sia in USING sia in WITH CHECK. Il trigger è SECURITY INVOKER con search_path vuoto.
- Test live in transazione con due identità temporanee e ruolo PostgreSQL authenticated: inserimento e lettura del proprio registro; registro altrui invisibile e non aggiornabile; inserimento per altro utente e cambio proprietario negati; DELETE negato.
- Trigger verificato: revisione iniziale forzata a 1, incremento a 2 anche se il client propone 999; aggiornamento con revisione obsoleta modifica zero righe.
- Ruolo anon: lettura negata. Verifica HTTP con la chiave pubblica del desktop: REST restituisce 401 / 42501 (permission denied), non più tabella assente.
- Fixtures SQL completamente annullate con ROLLBACK: nessun account o registro di prova lasciato nel progetto; nessun dato personale usato.
- Security Advisor dopo le modifiche: nessuna segnalazione.
- Rieseguiti i 15 test locali di `tests/test_cloud.py`: tutti superati. Questi test simulano la rete.
- Le foto sono incluse nel payload JSONB; questa versione non richiede bucket Storage né relative policy.

Limite della verifica: i test SQL esercitano realmente RLS con ruoli e identità simulate, ma non sono un login Supabase Auth. Non eseguiti creazione/conferma account e upload/download end-to-end dal desktop con una sessione reale. Per il primo utilizzo: Dati e backup → Account cloud → Crea account, confermare l’email se richiesto, quindi Accedi e sincronizza. Lo stesso account condivide il registro tra dispositivi.

La precedente verifica bloccata per schema mancante è superata dalla pubblicazione dei sorgenti e dalle verifiche sopra.
