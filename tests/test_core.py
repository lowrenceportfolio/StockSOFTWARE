import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core import Store, cents, iso_date

class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root/'test.sqlite3')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def item(self, **extra):
        data = dict(title='Felpa Nike',cost='7',asking='15',bought_on='2026-10-14')
        data.update(extra)
        return self.store.add_item(data)

    def sale(self, ident, status='Completata'):
        return self.store.record_sale(ident,'2026-10-14','15','0.5','1',status)


class LedgerTests(StoreCase):
    def test_box_allocation_is_exact(self):
        self.store.add_lot('Box 3','Fornitore','2026-10-14','100',3)
        items = self.store.items()
        self.assertEqual(sorted(r['cost'] for r in items),[3333,3333,3334])
        self.assertEqual(sum(r['cost'] for r in items),10000)
        self.assertEqual(self.store.metrics()['cash'],-10000)

    def test_profit_vs_cash(self):
        a,b = self.item(),self.item()
        self.sale(a)
        self.store.add_expense('2026-10-14','Buste','2')
        m = self.store.metrics()
        self.assertEqual(m['profit'],450)  # 15 - 7 - 0.5 - 1 - 2
        self.assertEqual(m['cash'],-250)   # 13.5 - 14 - 2
        self.assertEqual(m['stock_value'],700)
        self.assertEqual(m['stock_count'],1)

    def test_pending_and_cancelled_sale(self):
        ident = self.item()
        sale = self.sale(ident,'In attesa')
        self.assertEqual(self.store.metrics()['revenue'],0)
        self.assertEqual(self.store.item(ident)['status'],'Riservato')
        self.store.set_sale_status(sale,'Spedita')
        self.assertEqual(self.store.metrics()['revenue'],0)
        self.store.set_sale_status(sale,'Completata')
        self.assertEqual(self.store.metrics()['revenue'],1500)
        self.store.set_sale_status(sale,'Annullata')
        self.assertEqual(self.store.metrics()['revenue'],0)
        self.assertEqual(self.store.item(ident)['status'],'In vendita')
        self.assertEqual(self.store.metrics()['cash'],-700)
        with self.assertRaises(ValueError):
            self.store.set_sale_status(sale,'Completata')
        self.sale(ident)
        self.assertEqual(len(self.store.sales()),2)

    def test_duplicate_sale_blocked_and_cost_correction_supported(self):
        ident = self.item()
        self.sale(ident)
        with self.assertRaises(ValueError):
            self.sale(ident)
        self.store.update_item(ident,dict(title='Changed',cost='50',status='In vendita'))
        self.assertEqual(self.store.sales()[0]['cost_snapshot'],5000)
        self.assertEqual(self.store.item(ident)['status'],'Venduto')

    def test_box_cost_correction_updates_total(self):
        self.store.add_lot('Box','Test','2026-10-14','100',10)
        ident = self.store.items()[0]['id']
        self.store.update_item(ident,dict(title='Nome vero',cost='10'))
        self.store.update_item(ident,dict(title='Nome vero',cost='9'))
        self.assertEqual(self.store.lots()[0]['total'],9900)

    def write_csv(self, rows):
        path = self.root/'import.csv'
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=list(rows[0]),delimiter=';')
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_import_duplicate_rolls_back_entire_batch(self):
        self.item(sku='EXISTS')
        path = self.write_csv([{'sku':'NEW','titolo':'Prima','costo':'1'},{'sku':'EXISTS','titolo':'Seconda','costo':'2'}])
        with self.assertRaises(ValueError):
            self.store.import_csv(path)
        self.assertEqual(len(self.store.items()),1)

    def test_import_invalid_row_rolls_back(self):
        path = self.write_csv([{'titolo':'Prima','costo':'1'},{'titolo':'Seconda','costo':'nan'}])
        with self.assertRaises(ValueError):
            self.store.import_csv(path)
        self.assertEqual(len(self.store.items()),0)

    def test_import_comma_decimal_and_export(self):
        path = self.write_csv([{'sku':'TEST','titolo':'=1+1','costo':'7,50','prezzo_annuncio':'15,20'}])
        self.assertEqual(self.store.import_csv(path),1)
        self.assertEqual(self.store.items()[0]['cost'],750)
        output = self.root/'export.csv'
        self.store.export_csv(output)
        self.assertIn("'=1+1",output.read_text(encoding='utf-8-sig'))

    def test_restore_preserves_snapshot_and_creates_safety(self):
        ident = self.item()
        self.sale(ident)
        before = self.store.metrics()
        backup = self.root/'backup.sqlite3'
        self.store.backup(backup)
        self.item()
        safety = self.store.restore(backup)
        self.assertTrue(safety.exists())
        self.assertEqual(self.store.metrics(),before)
        old = Store(safety)
        self.assertEqual(len(old.items()),2)
        old.close()

    def test_reject_unrelated_database_without_changes(self):
        self.item()
        other = self.root/'wrong.sqlite3'
        db = sqlite3.connect(other)
        db.execute('CREATE TABLE nonsense (id INTEGER)')
        db.close()
        with self.assertRaises(ValueError):
            self.store.restore(other)
        self.assertEqual(len(self.store.items()),1)

    def test_validation_and_literal_search(self):
        for value in ('-1','0.001','NaN','Infinity','abc'):
            with self.assertRaises(ValueError):
                cents(value)
        self.assertEqual(cents('7,25'),725)
        self.item(title='100% cotone')
        self.item(title='Felpa')
        self.assertEqual(len(self.store.items('%')),1)
        with self.assertRaises(ValueError):
            self.store.add_lot('Box','','2026-10-14','100','2.5')
        with self.assertRaises(ValueError):
            self.item(bought_on='2026-02-31')

    def test_box_receipts_are_net(self):
        self.store.add_lot('Box','','2026-10-14','100',10)
        self.sale(self.store.items()[0]['id'])
        lot = self.store.lots()[0]
        self.assertEqual(lot['remaining'],9)
        self.assertEqual(lot['receipts'],1350)

    def test_sale_edit_correction_and_reopen_persistence(self):
        ident = self.item()
        sale = self.sale(ident)
        self.store.set_sale_status(sale,'Annullata')
        self.store.record_sale(ident,'2026-10-14','20','0','0','Completata')
        self.store.close()
        self.store = Store(self.root/'test.sqlite3')
        self.assertEqual(self.store.metrics()['profit'],1300)
        self.assertEqual(self.store.metrics()['sold_count'],1)

    def test_second_connection_cannot_sell_same_item_twice(self):
        ident = self.item()
        other = Store(self.store.path)
        try:
            self.sale(ident)
            with self.assertRaises(ValueError):
                other.record_sale(ident,'2026-10-14','30','0','0','Completata')
        finally:
            other.close()

class InsightTests(StoreCase):
    def test_performance_and_top_brands(self):
        self.assertEqual(self.store.performance()['avg_days'],None)
        a = self.item(brand='Nike',bought_on='2026-10-04')
        b = self.item(brand='Zara',sku='VD-B',cost='10',bought_on='2026-10-10')
        self.store.record_sale(a,'2026-10-14','20','0','0','Completata')   # margine 13, 10 giorni
        self.store.record_sale(b,'2026-10-14','12','0','0','Completata')   # margine 2, 4 giorni
        perf = self.store.performance()
        self.assertEqual(perf['avg_margin'],750)
        self.assertEqual(perf['avg_days'],7)
        self.assertEqual(perf['roi_pct'],88.2)
        self.assertEqual(perf['sell_through'],100)
        self.assertEqual([r['brand'] for r in self.store.top_brands()],['Nike','Zara'])

    def test_bulk_status_skips_items_with_active_sale(self):
        free, sold = self.item(), self.item(sku='VD-S')
        self.sale(sold,'In attesa')
        self.assertEqual(self.store.set_items_status([free,sold],'In vendita'),1)
        self.assertEqual(self.store.item(free)['status'],'In vendita')
        self.assertEqual(self.store.item(sold)['status'],'Riservato')
        with self.assertRaises(ValueError):
            self.store.set_items_status([free],'Venduto')

    def test_duplicate_keeps_data_but_not_link_status_or_sku(self):
        ident = self.item(brand='Levis',url='https://www.vinted.it/items/1',status='In vendita')
        copy = self.store.item(self.store.duplicate_item(ident))
        self.assertEqual((copy['brand'],copy['cost'],copy['url'],copy['status']),('Levis',700,'','Da pubblicare'))
        self.assertNotEqual(copy['sku'],self.store.item(ident)['sku'])

    def test_stale_items_and_age(self):
        old = self.item(bought_on='2020-01-01',status='In vendita')
        self.item(sku='VD-NEW',status='In vendita')
        self.assertEqual([r['id'] for r in self.store.stale_items()],[old])
        self.assertGreater(self.store.items()[1]['age'],1000)

    def test_auto_backup_rotates_and_is_daily(self):
        self.assertIsNone(self.store.auto_backup())            # vuoto: niente da salvare
        self.item()
        first = self.store.auto_backup()
        self.assertTrue(first.exists())
        self.assertIsNone(self.store.auto_backup())            # già salvato oggi
        folder = first.parent
        for n in range(10):
            (folder/f'auto-2020010{n}-000000.sqlite3').write_bytes(b'x')
        import os, time
        os.utime(first,(time.time()-90000,)*2)
        self.store.auto_backup()
        self.assertLessEqual(len(list(folder.glob('auto-*.sqlite3'))),Store.AUTO_BACKUP_KEEP)

class DateTests(unittest.TestCase):
    def test_italian_and_iso_dates(self):
        self.assertEqual(iso_date('14/10/2026'),'2026-10-14')
        self.assertEqual(iso_date('4.1.2026'),'2026-01-04')
        self.assertEqual(iso_date('2026-10-14'),'2026-10-14')
        for wrong in ('31/02/2026','14/10','ieri'):
            with self.assertRaises(ValueError):
                iso_date(wrong)

if __name__ == '__main__':
    unittest.main()
