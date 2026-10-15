"""Portable JSON ledger protocol v1, authenticated Supabase REST and safe sync.
SQLite stays usable offline. A conditional revision update prevents lost writes.
"""
import base64
import hashlib
import json
import socket
import sqlite3
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROJECT_URL = 'https://dgbooupbrxznjngpkxle.supabase.co'
PUBLISHABLE_KEY = 'sb_publishable_6SDe2FZvohe6Qav6cBUclw_Bgr6GcZP'
TABLES = ('lots', 'items', 'sales', 'expenses', 'photos', 'shipments')


class CloudError(ValueError):
    pass


class Conflict(CloudError):
    pass


def snapshot(store):
    tables = {}
    with store.db:
        for table in TABLES:
            key = 'sale_id' if table == 'shipments' else 'id'
            rows = store.rows(f'SELECT * FROM {table} ORDER BY {key}')
            if table == 'photos':
                for row in rows:
                    row['data'] = base64.b64encode(row['data']).decode('ascii')
            tables[table] = rows
    return dict(format=1, tables=tables)


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


def empty(payload):
    return not any(payload['tables'].values())


def apply_snapshot(store, payload):
    if not isinstance(payload, dict) or payload.get('format') != 1:
        raise CloudError('Formato cloud non supportato. Aggiorna VintDesk.')
    tables = payload.get('tables')
    if not isinstance(tables, dict) or set(tables) != set(TABLES):
        raise CloudError('Dati cloud incompleti: copia locale conservata.')
    decoded = {}
    try:
        for table in TABLES:
            fields = {r[1] for r in store.db.execute(f'PRAGMA table_info({table})')}
            if not isinstance(tables[table], list):
                raise ValueError()
            decoded[table] = []
            for row in tables[table]:
                if not isinstance(row, dict) or set(row) != fields:
                    raise ValueError()
                row = dict(row)
                if table == 'photos':
                    row['data'] = base64.b64decode(row['data'], validate=True)
                decoded[table].append(row)
    except (ValueError, TypeError) as exc:
        raise CloudError('Dati cloud non validi: copia locale conservata.') from exc
    safety = store.path.parent / ('prima-cloud-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    store.backup(safety)
    try:
        with store.db:
            for table in reversed(TABLES):
                store.db.execute(f'DELETE FROM {table}')
            for table in TABLES:
                for row in decoded[table]:
                    columns = ','.join('"' + col + '"' for col in row)
                    marks = ','.join('?' for _ in row)
                    store.db.execute(f'INSERT INTO {table} ({columns}) VALUES ({marks})', tuple(row.values()))
            if store.db.execute('PRAGMA foreign_key_check').fetchone():
                raise CloudError('Riferimenti cloud non validi.')
    except sqlite3.Error as exc:
        raise CloudError('Dati cloud incompatibili: copia locale conservata.') from exc
    return safety


def read_baseline(store, account):
    store.db.execute('CREATE TABLE IF NOT EXISTS cloud_baselines (account TEXT PRIMARY KEY, revision INTEGER NOT NULL, digest TEXT NOT NULL)')
    row = store.db.execute('SELECT revision,digest FROM cloud_baselines WHERE account=?', (account,)).fetchone()
    return dict(row) if row else None


def save_baseline(store, account, revision, fingerprint):
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO cloud_baselines VALUES (?,?,?)',
                         (account, revision, fingerprint))


class Supabase:
    def __init__(self, url, key=PUBLISHABLE_KEY):
        url = url.strip().rstrip('/')
        parts = urlparse(url)
        if (parts.scheme != 'https' or not parts.hostname or
                not parts.hostname.endswith('.supabase.co') or parts.path or
                parts.query or parts.fragment or parts.username or parts.password or parts.port):
            raise CloudError('Inserisci il Project URL: https://ID-PROGETTO.supabase.co')
        self.url, self.key = url, key.strip()
        self.token = self.refresh_token = self.user_id = None

    @property
    def account(self):
        return self.url + '/' + self.user_id

    def request(self, path, method='GET', body=None, retry=True):
        headers = {'apikey': self.key, 'Content-Type': 'application/json',
                   'Prefer': 'return=representation'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        data = None if body is None else json.dumps(body).encode('utf-8')
        req = Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=25) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            if exc.code == 401 and retry and self.refresh_token and path.startswith('/rest/'):
                session = self.request('/auth/v1/token?grant_type=refresh_token', 'POST',
                                       {'refresh_token': self.refresh_token}, retry=False)
                self.set_session(session)
                return self.request(path, method, body, retry=False)
            if exc.code == 409:
                raise Conflict('Un altro dispositivo ha aggiornato il cloud. Sincronizza di nuovo.') from None
            if exc.code in (400, 401, 403, 422) and path.startswith('/auth/'):
                raise CloudError('Accesso non riuscito. Controlla email, password e conferma email.') from None
            if exc.code in (401, 403):
                raise CloudError('Accesso scaduto o non consentito. Accedi di nuovo e verifica le policy Supabase.') from None
            if exc.code == 404:
                raise CloudError('Tabella cloud assente: esegui supabase/schema.sql nel SQL Editor.') from None
            raise CloudError(f'Supabase ha risposto con errore {exc.code}. Dati locali conservati.') from None
        except (URLError, TimeoutError, socket.timeout, OSError, json.JSONDecodeError):
            raise CloudError('Cloud non raggiungibile. Dati salvati sul PC; riprova quando sei online.') from None

    def set_session(self, session):
        self.token = session['access_token']
        self.refresh_token = session['refresh_token']
        self.user_id = session['user']['id']

    def login(self, email, password):
        self.set_session(self.request('/auth/v1/token?grant_type=password', 'POST',
                                      {'email': email.strip(), 'password': password}))

    def signup(self, email, password):
        return self.request('/auth/v1/signup', 'POST', {'email': email.strip(), 'password': password})

    def exchange(self, local, baseline, pull=False):
        """No SQLite/UI access here: this method can run in a worker thread."""
        path = '/rest/v1/vintdesk_ledgers?user_id=eq.' + self.user_id
        rows = self.request(path + '&select=revision,payload')
        fingerprint = digest(local)
        if not rows:
            if pull:
                raise CloudError('Non ci sono ancora dati cloud da scaricare.')
            if baseline:
                raise Conflict('Il registro cloud è stato rimosso. Nessun dato è stato sovrascritto.')
            rows = self.request('/rest/v1/vintdesk_ledgers', 'POST',
                                {'user_id': self.user_id, 'payload': local})
            return ('push', rows[0]['revision'], local)
        remote = rows[0]
        remote_digest = digest(remote['payload'])
        if fingerprint == remote_digest:
            return ('same', remote['revision'], local)
        if pull:
            return ('pull', remote['revision'], remote['payload'])
        if baseline is None:
            if empty(local):
                return ('pull', remote['revision'], remote['payload'])
            raise Conflict('PC e cloud contengono dati diversi. Crea un backup; usa Scarica cloud per adottare la copia cloud. Nessuna fusione automatica.')
        if fingerprint == baseline['digest']:
            return ('pull', remote['revision'], remote['payload'])
        if remote['revision'] != baseline['revision']:
            raise Conflict('Dati modificati sia sul PC sia su un altro dispositivo. Crea un backup e confronta le copie prima di usare Scarica cloud.')
        rows = self.request(path + '&revision=eq.' + str(baseline['revision']), 'PATCH', {'payload': local})
        if not rows:
            raise Conflict('Modifiche contemporanee da un altro dispositivo. Sincronizza di nuovo.')
        return ('push', rows[0]['revision'], local)
