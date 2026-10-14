import io
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from PIL import Image
from core import Store, MAX_PHOTOS

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root/'test.sqlite3')
        self.photo = self.root/'test.png'
        Image.new('RGB',(60,80),'navy').save(self.photo)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def item(self, **extra):
        return self.store.add_item(dict(title='Felpa',cost='10',asking='20',bought_on='2026-08-01',**extra))

    def sale(self, item=None, status='In attesa'):
        return self.store.record_sale(item or self.item(),'2026-09-01','20','1','2',status)

    def test_create_item_with_photo_and_photo_survives_source_removal(self):
        ident = self.item(photo_paths=[self.photo])
        photo = self.store.photos(ident)[0]
        self.photo.unlink()
        with Image.open(io.BytesIO(self.store.photo_data(photo['id']))) as image:
            self.assertEqual(image.size,(60,80))
        self.assertEqual(self.store.items()[0]['photo_count'],1)

    def test_invalid_photo_prevents_partial_item(self):
        broken = self.root/'bad.jpg'
        broken.write_text('not an image')
        with self.assertRaises(ValueError):
            self.item(photo_paths=[self.photo,broken])
        self.assertEqual(self.store.items(),[])

    def test_photo_replacement_and_limit(self):
        ident = self.item(photo_paths=[self.photo])
        photo = self.store.photos(ident)[0]
        self.store.update_item(ident,dict(photo_paths=[self.photo],remove_photo_ids=[photo['id']]))
        self.assertEqual(len(self.store.photos(ident)),1)
        self.assertNotEqual(self.store.photos(ident)[0]['id'],photo['id'])
        with self.assertRaises(ValueError):
            self.store.add_photos(ident,[self.photo]*MAX_PHOTOS)
        self.assertEqual(len(self.store.photos(ident)),1)

    def test_cross_item_photo_removal_is_rejected(self):
        a = self.item(photo_paths=[self.photo])
        b = self.item()
        with self.assertRaises(ValueError):
            self.store.update_item(b,dict(remove_photo_ids=[self.store.photos(a)[0]['id']]))
        self.assertEqual(len(self.store.photos(a)),1)

    def test_photo_and_shipment_in_complete_backup(self):
        ident = self.item(photo_paths=[self.photo])
        sale = self.sale(ident)
        self.store.update_shipment(sale,carrier='InPost',tracking='ABC',ship_by='2026-09-06')
        backup = self.root/'backup.sqlite3'
        self.store.backup(backup)
        self.store.delete_sale(sale)
        self.store.delete_item(ident)
        self.store.restore(backup)
        self.assertEqual(len(self.store.photos(ident)),1)
        self.assertEqual(self.store.shipment(sale)['tracking'],'ABC')

    def test_edit_completed_sale_recalculates_profit_without_new_record(self):
        sale = self.sale(status='Completata')
        self.store.update_sale(sale,'2026-09-02','30','2','3','Completata',buyer='Nome corretto')
        self.assertEqual(self.store.metrics()['revenue'],3000)
        self.assertEqual(self.store.metrics()['profit'],1500)
        self.assertEqual(len(self.store.sales()),1)
        self.assertEqual(self.store.sale(sale)['buyer'],'Nome corretto')

    def test_move_sale_to_other_item_and_duplicate_rejection(self):
        a,b = self.item(),self.item()
        sale = self.sale(a)
        self.store.update_sale(sale,'2026-09-01','20','0','0','Completata',item_id=b)
        self.assertEqual(self.store.item(a)['status'],'In vendita')
        self.assertEqual(self.store.item(b)['status'],'Venduto')
        another = self.sale(a)
        with self.assertRaises(ValueError):
            self.store.update_sale(another,'2026-09-01','30','0','0','In attesa',item_id=b)
        self.assertEqual(self.store.sale(another)['item_id'],a)

    def test_reactivate_cancelled_sale_only_if_item_available(self):
        ident = self.item()
        sale = self.sale(ident)
        self.store.set_sale_status(sale,'Annullata')
        another = self.sale(ident)
        with self.assertRaises(ValueError):
            self.store.update_sale(sale,'2026-09-01','20','0','0','In attesa')
        self.store.delete_sale(another)
        self.store.update_sale(sale,'2026-09-01','20','0','0','In attesa')
        self.assertEqual(self.store.shipment(sale)['status'],'Da preparare')

    def test_lot_total_corrects_costs_of_completed_sales(self):
        lot = self.store.add_lot('Box','','2026-08-01','100',10)
        sale = self.sale(self.store.items()[0]['id'],status='Completata')
        self.store.update_lot(lot,'Box corretto','Fornitore','2026-08-02','110',10)
        self.assertEqual(self.store.sale(sale)['cost_snapshot'],1100)
        self.assertEqual(self.store.metrics()['profit'],600)
        self.assertEqual(sum(r['cost'] for r in self.store.items()),11000)
        self.assertEqual(self.store.lot(lot)['name'],'Box corretto')

    def test_lot_quantity_reduction_protects_photos_and_custom_data(self):
        lot = self.store.add_lot('Box','','2026-08-01','30',3)
        last = self.store.items()[0]['id']
        self.store.add_photos(last,[self.photo])
        with self.assertRaises(ValueError):
            self.store.update_lot(lot,'Box','','2026-08-01','20',2)
        self.assertEqual(len(self.store.items()),3)
        self.store.update_item(last,dict(remove_photo_ids=[self.store.photos(last)[0]['id']]))
        self.store.update_lot(lot,'Box','','2026-08-01','20',2)
        self.assertEqual(len(self.store.items()),2)
        self.store.update_lot(lot,'Box','','2026-08-01','45',4)
        self.assertEqual(len(self.store.items()),4)
        self.assertEqual(sum(r['cost'] for r in self.store.items()),4500)

    def test_deletions_preserve_sales_history_and_recount_lots(self):
        lot = self.store.add_lot('Box','','2026-08-01','30',3)
        ident = self.store.items()[0]['id']
        sale = self.sale(ident)
        with self.assertRaises(ValueError):
            self.store.delete_lot(lot)
        with self.assertRaises(ValueError):
            self.store.delete_item(ident)
        self.store.delete_sale(sale)
        self.assertFalse(self.store.db.execute('SELECT 1 FROM shipments WHERE sale_id=?',(sale,)).fetchone())
        self.store.delete_item(ident)
        self.assertEqual(self.store.lot(lot)['quantity'],2)
        self.assertEqual(self.store.lot(lot)['total'],2000)

    def test_expense_edit_and_archive_preserve_cash(self):
        ident = self.item()
        expense = self.store.add_expense('2026-09-01','Buste','2')
        self.store.update_expense(expense,'2026-09-02','Buste corrette','3')
        self.store.update_item(ident,dict(status='Archiviato'))
        self.assertEqual(self.store.metrics()['stock_count'],0)
        self.assertEqual(self.store.metrics()['cash'],-1300)
        self.assertEqual(self.store.expense(expense)['amount'],300)

    def test_shipping_delivery_does_not_automatically_record_payment(self):
        sale = self.sale()
        self.store.update_shipment(sale,carrier='BRT',tracking='123',tracking_url='https://example.com/track',
            ship_by='2026-09-04',shipped_on='2026-09-03',status='Spedita')
        self.assertEqual(self.store.sale(sale)['status'],'Spedita')
        self.assertEqual(self.store.metrics()['revenue'],0)
        self.store.update_shipment(sale,shipped_on='2026-09-03',delivered_on='2026-09-05',status='Consegnata')
        self.assertEqual(self.store.metrics()['revenue'],0)
        self.store.set_sale_status(sale,'Completata')
        self.assertEqual(self.store.metrics()['revenue'],2000)

    def test_shipping_dates_tracking_and_overdue_validation(self):
        sale = self.sale()
        overdue = (date.today()-timedelta(days=1)).isoformat()
        self.store.update_shipment(sale,ship_by=overdue)
        self.assertEqual(self.store.metrics()['overdue'],1)
        for args in [dict(tracking_url='file:///secret'),dict(status='Spedita'),
                     dict(shipped_on='2026-08-01',status='Spedita'),
                     dict(shipped_on='2026-09-04',delivered_on='2026-09-02',status='Consegnata')]:
            with self.assertRaises(ValueError):
                self.store.update_shipment(sale,**args)
        self.store.update_shipment(sale,shipped_on='2026-09-02',status='Spedita')
        with self.assertRaises(ValueError):
            self.store.update_sale(sale,'2026-09-03','20','0','0','Spedita')
        self.store.set_sale_status(sale,'Annullata')
        self.assertEqual(self.store.shipments(),[])
        self.assertEqual(self.store.metrics()['overdue'],0)

    def test_version_one_migrates_and_can_be_restored(self):
        ident = self.item()
        sale = self.sale(ident)
        legacy = self.root/'legacy.sqlite3'
        self.store.backup(legacy)
        db = sqlite3.connect(legacy)
        db.executescript('DROP TABLE photos; DROP TABLE shipments; PRAGMA user_version=1;')
        db.close()
        migrated = Store(legacy)
        self.assertEqual(migrated.item(ident)['cost'],1000)
        self.assertEqual(migrated.shipment(sale)['status'],'Da preparare')
        self.assertEqual(migrated.db.execute('PRAGMA user_version').fetchone()[0],2)
        self.assertTrue(list(self.root.glob('prima-versione-1.1-*.sqlite3')))
        migrated.close()
        # Recreate v1 and restore it into the v2 store.
        db = sqlite3.connect(legacy)
        db.executescript('DROP TABLE photos; DROP TABLE shipments; PRAGMA user_version=1;')
        db.close()
        self.store.restore(legacy)
        self.assertEqual(self.store.shipment(sale)['status'],'Da preparare')
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0],2)

if __name__=='__main__':
    unittest.main()
