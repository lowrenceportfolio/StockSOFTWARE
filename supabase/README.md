# VintDesk: database condiviso

Project URL e chiave pubblica sono già configurati in cloud.py. Nessuna chiave segreta è necessaria nell'app.

## Attivazione (una volta sola)

1. Applicare schema.sql al progetto Supabase dgbooupbrxznjngpkxle dal SQL Editor o tramite integrazione Supabase autorizzata.
2. In VintDesk aprire Dati e backup → Account cloud → Crea account. Confermare l'email se richiesto; quindi Accedi e sincronizza.
3. Usare lo stesso account su tutti i dispositivi. L'account dell'app è distinto dall'account amministratore del pannello Supabase.

Password e token restano in memoria; occorre accedere a ogni avvio. URL ed email vengono salvati accanto al database in un file .cloud.json.

## Funzionamento

SQLite resta la copia di lavoro offline. Dopo il login viene sincronizzato l'intero registro (box, capi, vendite, spese, spedizioni, foto), dopo le modifiche effettuate nell'interfaccia e ogni 30 secondi mentre l'app è aperta. Prima di cambiare dispositivo controllare che compaia “Sincronizzato”. Le finestre di modifica aperte rinviano i download. Chiudere l'app prima della sincronizzazione conserva i dati solo sul PC fino al prossimo accesso.

Un dispositivo vuoto scarica il registro cloud. Al primo collegamento, se PC e cloud contengono dati diversi, la sincronizzazione si ferma: nessuna fusione o sovrascrittura automatica. Lo stesso avviene se entrambi cambiano dopo l'ultima sincronizzazione. Creare un backup e confrontare le copie; “Scarica cloud” adotta la copia remota dopo conferma e backup preventivo prima-cloud-*.sqlite3. Le modifiche locali da conservare devono poi essere reinserite. I backup preventivi non vengono eliminati automaticamente.

Una rete assente o un errore mantiene intatto il database locale; il controllo periodico riprova. I conflitti sospendono il controllo automatico fino a un'azione manuale. Lo stato cloud è visibile anche nella barra laterale. I backup locali restano indipendenti dal cloud.

## Contratto per la futura versione mobile

La versione desktop Tkinter non funziona sul telefono: l'interfaccia mobile resta da sviluppare. Il database e il formato di scambio sono predisposti per condividerne i dati.

Tabella public.vintdesk_ledgers: una riga per utente Supabase Auth, protetta da RLS. Campi user_id, revision, payload JSONB, updated_at. Il payload ha format=1 e tables con lots/items/sales/expenses/photos/shipments; i nomi dei campi corrispondono a SQLite. Prezzi e costi sono centesimi interi, date ISO, photos.data è Base64 JPEG. ID numerici e relazioni vanno preservati.

Il client mobile deve autenticarsi tramite Supabase Auth, leggere solo la riga dell'utente, conservare revisione e impronta della copia sincronizzata, e aggiornare il payload filtrando sia user_id sia la revisione letta. Zero righe aggiornate significa conflitto. Il trigger incrementa atomicamente la revisione. Mai fare upsert incondizionati o sostituire il registro con un sottoinsieme di tabelle. La chiave pubblica va nell'header apikey; Authorization contiene il JWT dell'utente, non la chiave pubblica.

Questa implementazione scambia l'intero registro, foto incluse: adatta a un archivio personale contenuto. Per archivi fotografici grandi serviranno Storage privato e sincronizzazione incrementale; non è una sincronizzazione in tempo reale né una fusione automatica di modifiche offline.

## Verifiche

python -m unittest discover -s tests -v

I test locali simulano la rete e verificano conflitti, aggiornamenti condizionati, recupero dopo risposte perse, foto, rollback e isolamento delle baseline. La verifica live di policy, account e upload/download richiede schema applicato e un account dell'app.

Riferimenti: https://supabase.com/docs/guides/getting-started/api-keys e https://supabase.com/docs/guides/database/postgres/row-level-security
