"""VintDesk: local stock and sales ledger. All amounts are integer euro cents."""
import csv
import os
import sqlite3
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

STOCK_STATES = ('Da pubblicare', 'In vendita', 'Riservato')
SALE_STATES = ('In attesa', 'Spedita', 'Completata')
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
        if version > 1:
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
        PRAGMA user_version=1;
        ''')

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
        if status not in STOCK_STATES:
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
        try:
            with self.db:
                return self.db.execute('''INSERT INTO items
                (sku,title,brand,size,category,condition,cost,asking,location,bought_on,url,notes,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', values).lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError('SKU già esistente oppure dati non validi.') from exc

    def update_item(self, ident, data):
        values = self._item_values(data)
        try:
            with self.db:
                old = self.item(ident)
                if self.active_sale(ident):
                    raise ValueError('Prima annulla la vendita per modificare questo capo.')
                if old['lot_id'] and values[6] != old['cost']:
                    raise ValueError('Il costo dei capi di un box è ripartito automaticamente e non è modificabile.')
                self.db.execute('''UPDATE items SET sku=?,title=?,brand=?,size=?,category=?,condition=?,
                cost=?,asking=?,location=?,bought_on=?,url=?,notes=?,status=? WHERE id=?''', (*values, ident))
        except sqlite3.IntegrityError as exc:
            raise ValueError('SKU già esistente oppure dati non validi.') from exc

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

    def items(self, search='', status='Tutti'):
        sql, params = 'SELECT items.*, lots.name AS lot_name FROM items LEFT JOIN lots ON lots.id=items.lot_id WHERE 1=1', []
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

    def lots(self):
        return self.rows('''SELECT lots.*,COUNT(items.id) AS total_items,
          SUM(CASE WHEN items.status!='Venduto' THEN 1 ELSE 0 END) AS remaining,
          COALESCE((SELECT SUM(price-fees-shipping) FROM sales
            JOIN items i ON i.id=sales.item_id WHERE i.lot_id=lots.id AND sales.status='Completata'),0) AS receipts
          FROM lots LEFT JOIN items ON items.lot_id=lots.id GROUP BY lots.id ORDER BY lots.id DESC''')

    def metrics(self):
        stock = self.db.execute("SELECT COUNT(*),COALESCE(SUM(cost),0) FROM items WHERE status!='Venduto'").fetchone()
        sales = self.db.execute("SELECT COUNT(*),COALESCE(SUM(price),0),COALESCE(SUM(price-fees-shipping-cost_snapshot),0),COALESCE(SUM(price-fees-shipping),0) FROM sales WHERE status='Completata'").fetchone()
        expenses = self.db.execute('SELECT COALESCE(SUM(amount),0) FROM expenses').fetchone()[0]
        purchases = self.db.execute('SELECT COALESCE(SUM(cost),0) FROM items').fetchone()[0]
        pending = self.db.execute("SELECT COUNT(*) FROM sales WHERE status IN ('In attesa','Spedita')").fetchone()[0]
        return dict(stock_count=stock[0], stock_value=stock[1], sold_count=sales[0], revenue=sales[1],
                    profit=sales[2]-expenses, cash=sales[3]-purchases-expenses, expenses=expenses, pending=pending)

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
            if source.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('Versione backup non supportata.')
            expected = {
                'items': {'id','sku','title','brand','size','category','condition','cost','asking','location','bought_on','url','notes','status','lot_id'},
                'sales': {'id','item_id','sold_on','price','fees','shipping','status','buyer','notes','cost_snapshot'},
                'lots': {'id','name','supplier','bought_on','total','quantity'},
                'expenses': {'id','spent_on','description','amount'},
            }
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
        return safety
