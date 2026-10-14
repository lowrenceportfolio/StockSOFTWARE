"""VintDesk: local stock and sales ledger. All amounts are integer euro cents."""
import csv
import io
import os
import sqlite3
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageOps, UnidentifiedImageError

STOCK_STATES = ('Da pubblicare', 'In vendita', 'Riservato', 'Archiviato')
SALE_STATES = ('In attesa', 'Spedita', 'Completata')
SHIPMENT_STATES = ('Da preparare', 'Pronta', 'Spedita', 'Consegnata', 'Problema', 'Annullata')
MAX_PHOTOS = 12
CSV_FIELDS = ('sku', 'titolo', 'marca', 'taglia', 'categoria', 'condizione',
              'costo', 'prezzo_annuncio', 'posizione', 'data_acquisto', 'url', 'note')

def cents(value):
    try:
        n = Decimal(str(value).strip().replace(',', '.'))
        if not n.is_finite() or n < 0 or n > Decimal('1000000'):
            raise ValueError('Importo tra 0 e 1.000.000 € richiesto.')
        if n != n.quantize(Decimal('0.01')):
            raise ValueError('Usa al massimo due cifre decimali.')
        return int(n * 100)
    except InvalidOperation as exc:
        raise ValueError('Importo non valido.') from exc

def money(value):
    return f'{value / 100:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.') + ' €'

def iso_date(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError('La data deve essere AAAA-MM-GG.') from exc

def optional_date(value):
    return iso_date(value) if str(value or '').strip() else ''

def prepare_photo(path):
    path = Path(path)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('Ogni foto deve pesare al massimo 20 MB.')
    try:
        with Image.open(path) as image:
            if image.width * image.height > 50_000_000:
                raise ValueError('Foto troppo grande: massimo 50 megapixel.')
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=90, optimize=True)
            return path.name, output.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError(f'Foto non leggibile: {path.name}. Usa JPG, PNG o WebP.') from exc

def data_dir():
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'VintDesk'
    root.mkdir(parents=True, exist_ok=True)
    return root

class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_dir() / 'vintdesk.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=5000')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 2:
            self.db.close()
            raise ValueError('Database di una versione più recente: aggiorna VintDesk.')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS lots (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, supplier TEXT NOT NULL DEFAULT '',
          bought_on TEXT NOT NULL, total INTEGER NOT NULL CHECK(total>=0),
          quantity INTEGER NOT NULL CHECK(quantity>0));
        CREATE TABLE IF NOT EXISTS items (
          id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
          brand TEXT NOT NULL DEFAULT '', size TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL DEFAULT '', condition TEXT NOT NULL DEFAULT '',
          cost INTEGER NOT NULL CHECK(cost>=0), asking INTEGER NOT NULL CHECK(asking>=0),
          location TEXT NOT NULL DEFAULT '', bought_on TEXT NOT NULL,
          url TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'Da pubblicare',
          lot_id INTEGER REFERENCES lots(id));
        CREATE TABLE IF NOT EXISTS sales (
          id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id),
          sold_on TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>=0),
          fees INTEGER NOT NULL CHECK(fees>=0), shipping INTEGER NOT NULL CHECK(shipping>=0),
          status TEXT NOT NULL, buyer TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
          cost_snapshot INTEGER NOT NULL CHECK(cost_snapshot>=0));
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_sale ON sales(item_id)
          WHERE status != 'Annullata';
        CREATE TABLE IF NOT EXISTS expenses (
          id INTEGER PRIMARY KEY, spent_on TEXT NOT NULL, description TEXT NOT NULL,
          amount INTEGER NOT NULL CHECK(amount>=0));
        ''')
        self._migrate(version)

    def _migrate(self, version, safety_copy=True):
        if version >= 2:
            return
        if version == 1 and safety_copy:
            self.backup(self.path.parent / ('prima-versione-1.1-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3'))
        try:
            self.db.executescript('''
            BEGIN;
            CREATE TABLE IF NOT EXISTS photos (
              id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
              name TEXT NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS shipments (
              sale_id INTEGER PRIMARY KEY REFERENCES sales(id) ON DELETE CASCADE,
              carrier TEXT NOT NULL DEFAULT '', tracking TEXT NOT NULL DEFAULT '',
              tracking_url TEXT NOT NULL DEFAULT '', ship_by TEXT NOT NULL DEFAULT '',
              shipped_on TEXT NOT NULL DEFAULT '', delivered_on TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'Da preparare', notes TEXT NOT NULL DEFAULT '');
            INSERT OR IGNORE INTO shipments(sale_id,status)
              SELECT id,CASE status WHEN 'Completata' THEN 'Consegnata' WHEN 'Spedita' THEN 'Spedita'
              WHEN 'Annullata' THEN 'Annullata' ELSE 'Da preparare' END FROM sales;
            PRAGMA user_version=2;
            COMMIT;
            ''')
        except Exception:
            self.db.rollback()
            raise

    def close(self):
        self.db.close()

    def rows(self, sql, params=()):
        return [dict(r) for r in self.db.execute(sql, params)]

    def item(self, ident):
        r = self.db.execute('SELECT * FROM items WHERE id=?', (ident,)).fetchone()
        if r is None:
            raise ValueError('Capo non trovato.')
        return dict(r)

    def active_sale(self, ident):
        return self.db.execute("SELECT id FROM sales WHERE item_id=? AND status!='Annullata'", (ident,)).fetchone()

    def _item_values(self, data):
        title = str(data.get('title', '')).strip()
        if not title:
            raise ValueError('Inserisci il nome del capo.')
        status = data.get('status', 'Da pubblicare')
        if status not in (*STOCK_STATES, 'Venduto'):
            raise ValueError('Stato stock non valido.')
        sku = str(data.get('sku') or '').strip() or 'VD-' + uuid.uuid4().hex[:10].upper()
        return (sku, title,
                str(data.get('brand', '')).strip(), str(data.get('size', '')).strip(),
                str(data.get('category', '')).strip(), str(data.get('condition', '')).strip(),
                cents(data.get('cost', '0')), cents(data.get('asking', '0')),
                str(data.get('location', '')).strip(), iso_date(data.get('bought_on', date.today())),
                str(data.get('url', '')).strip(), str(data.get('notes', '')).strip(), status)

    def add_item(self, data):
        values = self._item_values(data)
        if values[-1] == 'Venduto':
            raise ValueError('Registra la vendita per impostare un nuovo capo come venduto.')
        prepared = [prepare_photo(path) for path in data.get('photo_paths', ())]
        if len(prepared) > MAX_PHOTOS:
            raise ValueError(f'Massimo {MAX_PHOTOS} foto per capo.')
        try:
            with self.db:
                ident = self.db.execute('''INSERT INTO items
                (sku,title,brand,size,category,condition,cost,asking,location,bought_on,url,notes,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', values).lastrowid
                self._write_photos(ident, prepared)
                return ident
        except sqlite3.IntegrityError as exc:
            raise ValueError('SKU già esistente oppure dati non validi.') from exc

    def update_item(self, ident, data):
        old = self.item(ident)
        merged = dict(old, cost=f"{old['cost']/100:.2f}", asking=f"{old['asking']/100:.2f}")
        merged.update(data)
        values = list(self._item_values(merged))
        prepared = [prepare_photo(path) for path in data.get('photo_paths', ())]
        remove = list(dict.fromkeys(int(i) for i in data.get('remove_photo_ids', ())))
        try:
            with self.db:
                old = self.item(ident)
                active = self.active_sale(ident)
                if active:
                    sale = self.sale(active['id'])
                    values[-1] = 'Venduto' if sale['status'] == 'Completata' else 'Riservato'
                elif values[-1] == 'Venduto':
                    raise ValueError('Registra una vendita per impostare lo stato Venduto.')
                self._validate_photo_changes(ident, remove, len(prepared))
                self.db.execute('''UPDATE items SET sku=?,title=?,brand=?,size=?,category=?,condition=?,
                cost=?,asking=?,location=?,bought_on=?,url=?,notes=?,status=? WHERE id=?''', (*values, ident))
                self._write_photos(ident, prepared, remove)
                if old['lot_id']:
                    self.db.execute('UPDATE lots SET total=(SELECT SUM(cost) FROM items WHERE lot_id=?) WHERE id=?', (old['lot_id'], old['lot_id']))
                if active:
                    self.db.execute('UPDATE sales SET cost_snapshot=? WHERE id=?', (values[6], active['id']))
        except sqlite3.IntegrityError as exc:
            raise ValueError('SKU già esistente oppure dati non validi.') from exc

    def photos(self, ident):
        return self.rows('SELECT id,name,created_at FROM photos WHERE item_id=? ORDER BY id', (ident,))

    def photo_data(self, ident):
        row = self.db.execute('SELECT data FROM photos WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Foto non trovata.')
        return row['data']

    def _validate_photo_changes(self, ident, remove, added_count):
        current = {p['id'] for p in self.photos(ident)}
        if not set(remove).issubset(current):
            raise ValueError('Foto da rimuovere non appartenente al capo.')
        if len(current)-len(remove)+added_count > MAX_PHOTOS:
            raise ValueError(f'Massimo {MAX_PHOTOS} foto per capo.')

    def _write_photos(self, ident, prepared, remove=()):
        for photo_id in remove:
            self.db.execute('DELETE FROM photos WHERE id=? AND item_id=?', (photo_id, ident))
        for name, binary in prepared:
            self.db.execute('INSERT INTO photos(item_id,name,data,created_at) VALUES(?,?,?,?)',
                (ident, name, binary, datetime.now().isoformat(timespec='seconds')))

    def add_photos(self, ident, paths):
        prepared = [prepare_photo(path) for path in paths]
        with self.db:
            self.item(ident)
            self._validate_photo_changes(ident, (), len(prepared))
            self._write_photos(ident, prepared)

    def delete_item(self, ident):
        with self.db:
            old = self.item(ident)
            if self.db.execute('SELECT 1 FROM sales WHERE item_id=?', (ident,)).fetchone():
                raise ValueError('Il capo ha uno storico vendite. Elimina prima le vendite errate oppure conserva il capo.')
            self.db.execute('DELETE FROM items WHERE id=?', (ident,))
            if old['lot_id']:
                self._recount_lot(old['lot_id'])

    def _recount_lot(self, ident):
        row = self.db.execute('SELECT COUNT(*),COALESCE(SUM(cost),0) FROM items WHERE lot_id=?', (ident,)).fetchone()
        if row[0]:
            self.db.execute('UPDATE lots SET quantity=?,total=? WHERE id=?', (*row, ident))
        else:
            self.db.execute('DELETE FROM lots WHERE id=?', (ident,))

    def add_lot(self, name, supplier, bought_on, total, quantity):
        name = name.strip()
        if not name:
            raise ValueError('Inserisci il nome del box.')
        try:
            qty = int(str(quantity))
        except ValueError as exc:
            raise ValueError('Il numero di capi deve essere intero.') from exc
        if not 1 <= qty <= 1000:
            raise ValueError('Il box deve contenere da 1 a 1.000 capi.')
        total = cents(total)
        bought_on = iso_date(bought_on)
        share, extra = divmod(total, qty)
        with self.db:
            ident = self.db.execute('INSERT INTO lots(name,supplier,bought_on,total,quantity) VALUES(?,?,?,?,?)',
                                    (name, supplier, bought_on, total, qty)).lastrowid
            for i in range(qty):
                self.db.execute('''INSERT INTO items(sku,title,cost,asking,bought_on,lot_id)
                  VALUES(?,?,?,?,?,?)''', (f'BOX-{ident}-{i+1:03}', f'{name} · capo {i+1}',
                                         share + (i < extra), 0, bought_on, ident))
        return ident

    def lot(self, ident):
        row = self.db.execute('SELECT * FROM lots WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Box non trovato.')
        return dict(row)

    def update_lot(self, ident, name, supplier, bought_on, total, quantity):
        old = self.lot(ident)
        name = name.strip()
        if not name:
            raise ValueError('Inserisci il nome del box.')
        try:
            qty = int(str(quantity))
        except ValueError as exc:
            raise ValueError('Il numero di capi deve essere intero.') from exc
        if not 1 <= qty <= 1000:
            raise ValueError('Da 1 a 1.000 capi per box.')
        total, bought_on = cents(total), iso_date(bought_on)
        with self.db:
            items = self.rows('SELECT * FROM items WHERE lot_id=? ORDER BY id', (ident,))
            if qty < len(items):
                removing = items[qty:]
                for item in removing:
                    if (not item['title'].startswith(old['name']+' · capo ') or item['brand'] or item['size']
                        or item['asking'] or item['notes'] or item['url'] or item['location'] or item['category'] or item['condition']
                        or item['status'] != 'Da pubblicare' or self.photos(item['id'])
                        or self.db.execute('SELECT 1 FROM sales WHERE item_id=?', (item['id'],)).fetchone()):
                        raise ValueError('Puoi ridurre la quantità solo rimuovendo gli ultimi capi ancora vuoti. Gestisci i capi già compilati dallo stock.')
                for item in removing:
                    self.db.execute('DELETE FROM items WHERE id=?', (item['id'],))
            if qty > len(items):
                for _ in range(qty-len(items)):
                    sequence = self.db.execute('SELECT COALESCE(MAX(id),0)+1 FROM items').fetchone()[0]
                    self.db.execute('INSERT INTO items(sku,title,cost,asking,bought_on,lot_id) VALUES(?,?,?,?,?,?)',
                        (f'BOX-{ident}-N{sequence}', f'{name} · capo {sequence}', 0, 0, bought_on, ident))
            items = self.rows('SELECT * FROM items WHERE lot_id=? ORDER BY id', (ident,))
            redistribute = total != old['total'] or qty != old['quantity']
            share, extra = divmod(total, qty)
            for i, item in enumerate(items):
                title = f'{name} · capo {i+1}' if item['title'].startswith(old['name']+' · capo ') else item['title']
                cost = share+(i<extra) if redistribute else item['cost']
                self.db.execute('UPDATE items SET title=?,cost=?,bought_on=? WHERE id=?', (title, cost, bought_on, item['id']))
                self.db.execute("UPDATE sales SET cost_snapshot=? WHERE item_id=? AND status!='Annullata'", (cost, item['id']))
            self.db.execute('UPDATE lots SET name=?,supplier=?,bought_on=?,total=?,quantity=? WHERE id=?',
                (name, supplier.strip(), bought_on, total, qty, ident))

    def delete_lot(self, ident):
        with self.db:
            self.lot(ident)
            if self.db.execute('SELECT 1 FROM sales JOIN items ON items.id=sales.item_id WHERE lot_id=?', (ident,)).fetchone():
                raise ValueError('Il box contiene uno storico vendite: non può essere eliminato.')
            self.db.execute('DELETE FROM items WHERE lot_id=?', (ident,))
            self.db.execute('DELETE FROM lots WHERE id=?', (ident,))

    def items(self, search='', status='Tutti'):
        sql, params = 'SELECT items.*, lots.name AS lot_name,(SELECT COUNT(*) FROM photos WHERE item_id=items.id) AS photo_count FROM items LEFT JOIN lots ON lots.id=items.lot_id WHERE 1=1', []
        if search:
            sql += " AND (title LIKE ? ESCAPE '\\' OR sku LIKE ? ESCAPE '\\' OR brand LIKE ? ESCAPE '\\' OR location LIKE ? ESCAPE '\\')"
            literal = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            params.extend(['%' + literal + '%'] * 4)
        if status != 'Tutti':
            sql += ' AND items.status=?'
            params.append(status)
        return self.rows(sql + ' ORDER BY items.id DESC', params)

    def record_sale(self, ident, sold_on, price, fees, shipping, status, buyer='', notes=''):
        if status not in SALE_STATES:
            raise ValueError('Stato vendita non valido.')
        values = (iso_date(sold_on), cents(price), cents(fees), cents(shipping))
        try:
            with self.db:
                item = self.item(ident)
                if self.active_sale(ident):
                    raise ValueError('Esiste già una vendita attiva per questo capo.')
                result = self.db.execute('''INSERT INTO sales
                  (item_id,sold_on,price,fees,shipping,status,buyer,notes,cost_snapshot)
                  VALUES(?,?,?,?,?,?,?,?,?)''', (ident, *values, status, buyer, notes, item['cost'])).lastrowid
                self.db.execute('UPDATE items SET status=? WHERE id=?',
                                ('Venduto' if status == 'Completata' else 'Riservato', ident))
                self.db.execute('INSERT INTO shipments(sale_id,status) VALUES(?,?)',
                    (result, 'Consegnata' if status == 'Completata' else 'Spedita' if status == 'Spedita' else 'Da preparare'))
                return result
        except sqlite3.IntegrityError as exc:
            raise ValueError('Esiste già una vendita attiva per questo capo.') from exc

    def set_sale_status(self, ident, status):
        if status not in (*SALE_STATES, 'Annullata'):
            raise ValueError('Stato vendita non valido.')
        with self.db:
            sale = self.db.execute('SELECT * FROM sales WHERE id=?', (ident,)).fetchone()
            if not sale:
                raise ValueError('Vendita non trovata.')
            if sale['status'] == 'Annullata':
                raise ValueError('Una vendita annullata non può essere riattivata. Registra una nuova vendita.')
            self.db.execute('UPDATE sales SET status=? WHERE id=?', (status, ident))
            self.db.execute('UPDATE items SET status=? WHERE id=?',
                            ('In vendita' if status == 'Annullata' else 'Venduto' if status == 'Completata' else 'Riservato', sale['item_id']))
            if status == 'Annullata':
                self.db.execute("UPDATE shipments SET status='Annullata' WHERE sale_id=?", (ident,))
            elif status == 'Spedita':
                self.db.execute("UPDATE shipments SET status='Spedita' WHERE sale_id=? AND status IN ('Da preparare','Pronta')", (ident,))

    def sale(self, ident):
        row = self.db.execute('SELECT * FROM sales WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Vendita non trovata.')
        return dict(row)

    def update_sale(self, ident, sold_on, price, fees, shipping, status, buyer='', notes='', item_id=None):
        if status not in (*SALE_STATES, 'Annullata'):
            raise ValueError('Stato vendita non valido.')
        values = (iso_date(sold_on), cents(price), cents(fees), cents(shipping))
        try:
            with self.db:
                old = self.sale(ident)
                shipment = self.shipment(ident)
                if shipment['shipped_on'] and values[0] > shipment['shipped_on']:
                    raise ValueError('La data vendita non può essere successiva alla spedizione. Correggi prima le date della spedizione.')
                target = self.item(item_id if item_id is not None else old['item_id'])
                active = self.active_sale(target['id'])
                if status != 'Annullata' and active and active['id'] != ident:
                    raise ValueError('Il capo scelto ha già una vendita attiva.')
                self.db.execute('''UPDATE sales SET item_id=?,sold_on=?,price=?,fees=?,shipping=?,status=?,buyer=?,notes=?,cost_snapshot=? WHERE id=?''',
                    (target['id'], *values, status, buyer, notes, target['cost'], ident))
                if old['status'] != 'Annullata' and old['item_id'] != target['id']:
                    self.db.execute("UPDATE items SET status='In vendita' WHERE id=?", (old['item_id'],))
                if status != 'Annullata':
                    self.db.execute('UPDATE items SET status=? WHERE id=?',
                        ('Venduto' if status == 'Completata' else 'Riservato', target['id']))
                elif old['status'] != 'Annullata':
                    self.db.execute("UPDATE items SET status='In vendita' WHERE id=?", (old['item_id'],))
                if status == 'Annullata':
                    self.db.execute("UPDATE shipments SET status='Annullata' WHERE sale_id=?", (ident,))
                elif old['status'] == 'Annullata':
                    self.db.execute("UPDATE shipments SET status=? WHERE sale_id=?", ('Spedita' if status == 'Spedita' else 'Da preparare', ident))
                elif status == 'Spedita':
                    self.db.execute("UPDATE shipments SET status='Spedita' WHERE sale_id=? AND status IN ('Da preparare','Pronta')", (ident,))
        except sqlite3.IntegrityError as exc:
            raise ValueError('Il capo ha già una vendita attiva.') from exc

    def delete_sale(self, ident):
        with self.db:
            old = self.sale(ident)
            self.db.execute('DELETE FROM sales WHERE id=?', (ident,))
            if old['status'] != 'Annullata':
                self.db.execute("UPDATE items SET status='In vendita' WHERE id=?", (old['item_id'],))

    def shipments(self, filter_state='Tutte'):
        rows = self.rows('''SELECT shipments.*,sales.status AS sale_status,sales.sold_on,sales.buyer,
            items.id AS item_id,items.title,items.sku,items.location FROM shipments
            JOIN sales ON sales.id=shipments.sale_id JOIN items ON items.id=sales.item_id
            WHERE sales.status!='Annullata' ORDER BY CASE WHEN ship_by='' THEN '9999' ELSE ship_by END,sale_id DESC''')
        for row in rows:
            row['overdue'] = bool(row['ship_by'] and row['ship_by'] < date.today().isoformat()
                and not row['shipped_on'] and row['status'] in ('Da preparare','Pronta','Problema'))
        if filter_state == 'Da spedire':
            return [r for r in rows if r['status'] in ('Da preparare','Pronta')]
        if filter_state == 'Scadute':
            return [r for r in rows if r['overdue']]
        return rows if filter_state == 'Tutte' else [r for r in rows if r['status'] == filter_state]

    def shipment(self, ident):
        row = self.db.execute('SELECT * FROM shipments WHERE sale_id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Spedizione non trovata.')
        return dict(row)

    def update_shipment(self, ident, carrier='', tracking='', tracking_url='', ship_by='', shipped_on='', delivered_on='', status='Da preparare', notes=''):
        if status not in SHIPMENT_STATES[:-1]:
            raise ValueError('Stato spedizione non valido.')
        ship_by, shipped_on, delivered_on = map(optional_date, (ship_by, shipped_on, delivered_on))
        if delivered_on and not shipped_on:
            raise ValueError('Inserisci prima la data di spedizione.')
        if delivered_on and delivered_on < shipped_on:
            raise ValueError('La consegna non può precedere la spedizione.')
        tracking_url = tracking_url.strip()
        parsed = urlparse(tracking_url)
        if tracking_url and (parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username):
            raise ValueError('Il link tracking deve essere un URL http o https valido.')
        with self.db:
            sale = self.sale(ident)
            old_shipment = self.shipment(ident)
            if sale['status'] == 'Annullata':
                raise ValueError('La vendita è annullata. Modificala prima di gestire la spedizione.')
            if shipped_on and shipped_on < sale['sold_on']:
                raise ValueError('La spedizione non può precedere la vendita.')
            if status == 'Consegnata' and not delivered_on and old_shipment['status'] != 'Consegnata':
                raise ValueError('Inserisci la data di consegna.')
            if status == 'Spedita' and not shipped_on and old_shipment['status'] != 'Spedita':
                raise ValueError('Inserisci la data di spedizione.')
            if status in ('Da preparare','Pronta') and (shipped_on or delivered_on):
                raise ValueError('Con date di spedizione/consegna usa Spedita, Consegnata o Problema.')
            if delivered_on and status not in ('Consegnata','Problema'):
                raise ValueError('Con data di consegna usa Consegnata o Problema.')
            self.db.execute('''UPDATE shipments SET carrier=?,tracking=?,tracking_url=?,ship_by=?,shipped_on=?,delivered_on=?,status=?,notes=? WHERE sale_id=?''',
                (carrier.strip(), tracking.strip(), tracking_url, ship_by, shipped_on, delivered_on, status, notes.strip(), ident))
            if (shipped_on or status in ('Spedita','Consegnata')) and sale['status'] == 'In attesa':
                self.db.execute("UPDATE sales SET status='Spedita' WHERE id=?", (ident,))

    def sales(self):
        return self.rows('''SELECT sales.*,items.sku,items.title,
          price-fees-shipping-cost_snapshot AS profit FROM sales
          JOIN items ON items.id=sales.item_id ORDER BY sold_on DESC,sales.id DESC''')

    def add_expense(self, spent_on, description, amount):
        if not description.strip():
            raise ValueError('Inserisci una descrizione.')
        with self.db:
            return self.db.execute('INSERT INTO expenses(spent_on,description,amount) VALUES(?,?,?)',
                (iso_date(spent_on), description.strip(), cents(amount))).lastrowid

    def delete_expense(self, ident):
        with self.db:
            self.db.execute('DELETE FROM expenses WHERE id=?', (ident,))

    def expense(self, ident):
        row = self.db.execute('SELECT * FROM expenses WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Spesa non trovata.')
        return dict(row)

    def update_expense(self, ident, spent_on, description, amount):
        if not description.strip():
            raise ValueError('Inserisci una descrizione.')
        with self.db:
            self.expense(ident)
            self.db.execute('UPDATE expenses SET spent_on=?,description=?,amount=? WHERE id=?',
                (iso_date(spent_on), description.strip(), cents(amount), ident))

    def lots(self):
        return self.rows('''SELECT lots.*,COUNT(items.id) AS total_items,
          SUM(CASE WHEN items.status!='Venduto' THEN 1 ELSE 0 END) AS remaining,
          COALESCE((SELECT SUM(price-fees-shipping) FROM sales
            JOIN items i ON i.id=sales.item_id WHERE i.lot_id=lots.id AND sales.status='Completata'),0) AS receipts
          FROM lots LEFT JOIN items ON items.lot_id=lots.id GROUP BY lots.id ORDER BY lots.id DESC''')

    def metrics(self):
        stock = self.db.execute("SELECT COUNT(*),COALESCE(SUM(cost),0) FROM items WHERE status NOT IN ('Venduto','Archiviato')").fetchone()
        sales = self.db.execute("SELECT COUNT(*),COALESCE(SUM(price),0),COALESCE(SUM(price-fees-shipping-cost_snapshot),0),COALESCE(SUM(price-fees-shipping),0) FROM sales WHERE status='Completata'").fetchone()
        expenses = self.db.execute('SELECT COALESCE(SUM(amount),0) FROM expenses').fetchone()[0]
        purchases = self.db.execute('SELECT COALESCE(SUM(cost),0) FROM items').fetchone()[0]
        pending = self.db.execute("SELECT COUNT(*) FROM sales WHERE status IN ('In attesa','Spedita')").fetchone()[0]
        return dict(stock_count=stock[0], stock_value=stock[1], sold_count=sales[0], revenue=sales[1],
                    profit=sales[2]-expenses, cash=sales[3]-purchases-expenses, expenses=expenses, pending=pending,
                    overdue=len(self.shipments('Scadute')))

    def monthly(self):
        return self.rows("""SELECT substr(sold_on,1,7) AS month,SUM(price) AS revenue,
          SUM(price-fees-shipping-cost_snapshot) AS profit FROM sales WHERE status='Completata'
          GROUP BY month ORDER BY month DESC LIMIT 6""")[::-1]

    def export_csv(self, path, kind='stock'):
        if kind == 'stock':
            rows = []
            for item in self.items():
                row = dict(zip(CSV_FIELDS, (item['sku'], item['title'], item['brand'], item['size'], item['category'],
                    item['condition'], f"{item['cost']/100:.2f}", f"{item['asking']/100:.2f}", item['location'],
                    item['bought_on'], item['url'], item['notes'])))
                row['stato'] = item['status']
                row['box'] = item['lot_name'] or ''
                rows.append(row)
            fields = (*CSV_FIELDS, 'stato', 'box')
        elif kind == 'sales':
            rows = self.sales()
            fields = ('id','sku','title','sold_on','status','price','fees','shipping','cost_snapshot','profit','buyer','notes')
            for row in rows:
                for key in ('price','fees','shipping','cost_snapshot','profit'):
                    row[key] = f"{row[key]/100:.2f}"
        else:
            raise ValueError('Tipo esportazione non valido.')
        def spreadsheet_safe(value):
            return "'" + value if isinstance(value, str) and value.lstrip().startswith(('=','+','-','@')) else value
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fields, delimiter=';', extrasaction='ignore')
            writer.writeheader()
            writer.writerows({k: spreadsheet_safe(v) for k,v in row.items()} for row in rows)

    def import_csv(self, path):
        with open(path, encoding='utf-8-sig', newline='') as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=';,\t')
            except csv.Error:
                dialect = csv.excel
                dialect.delimiter = ';'
            reader = csv.DictReader(f, dialect=dialect)
            if not reader.fieldnames or not {'titolo','costo'}.issubset(reader.fieldnames):
                raise ValueError('Il CSV deve contenere almeno titolo e costo. Usa il modello incluso.')
            prepared = []
            for number, row in enumerate(reader, 2):
                state = row.get('stato') or 'Da pubblicare'
                if state not in STOCK_STATES:
                    raise ValueError(f'Riga {number}: stato non importabile; le vendite si registrano separatamente.')
                mapping = dict(zip(('sku','title','brand','size','category','condition','cost','asking','location','bought_on','url','notes'),
                               ((row.get(k) or '') for k in CSV_FIELDS)))
                for k in ('cost','asking'):
                    mapping[k] = mapping[k] or '0'
                mapping['bought_on'] = mapping['bought_on'] or date.today().isoformat()
                mapping['status'] = state
                try:
                    prepared.append(self._item_values(mapping))
                except ValueError as exc:
                    raise ValueError(f'Riga {number}: {exc}') from exc
                if len(prepared) > 10000:
                    raise ValueError('Massimo 10.000 capi per importazione.')
        try:
            with self.db:
                self.db.executemany('''INSERT INTO items
                  (sku,title,brand,size,category,condition,cost,asking,location,bought_on,url,notes,status)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', prepared)
        except sqlite3.IntegrityError as exc:
            raise ValueError('Importazione annullata: SKU duplicato. Nessun capo è stato aggiunto.') from exc
        return len(prepared)

    def backup(self, path):
        if Path(path).resolve() == self.path.resolve():
            raise ValueError('Scegli un file diverso dal database attivo.')
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()

    @staticmethod
    def validate_backup(path):
        source = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup danneggiato.')
            version = source.execute('PRAGMA user_version').fetchone()[0]
            if version not in (1, 2):
                raise ValueError('Versione backup non supportata.')
            expected = {
                'items': {'id','sku','title','brand','size','category','condition','cost','asking','location','bought_on','url','notes','status','lot_id'},
                'sales': {'id','item_id','sold_on','price','fees','shipping','status','buyer','notes','cost_snapshot'},
                'lots': {'id','name','supplier','bought_on','total','quantity'},
                'expenses': {'id','spent_on','description','amount'},
            }
            if version == 2:
                expected['photos'] = {'id','item_id','name','data','created_at'}
                expected['shipments'] = {'sale_id','carrier','tracking','tracking_url','ship_by','shipped_on','delivered_on','status','notes'}
            for table, fields in expected.items():
                actual = {r[1] for r in source.execute(f'PRAGMA table_info({table})')}
                if not fields.issubset(actual):
                    raise ValueError('Questo non è un backup VintDesk valido.')
            if source.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Backup con riferimenti mancanti.')
        finally:
            source.close()

    def restore(self, path):
        if Path(path).resolve() == self.path.resolve():
            raise ValueError('Il file selezionato è già il database attivo.')
        self.validate_backup(path)
        safety = self.path.parent / ('prima-ripristino-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        self.backup(safety)
        source = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            source.backup(self.db)
        finally:
            source.close()
        self._migrate(self.db.execute('PRAGMA user_version').fetchone()[0], safety_copy=False)
        return safety
