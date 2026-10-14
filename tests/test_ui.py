"""Real Tkinter UI checks. Requires a graphical display (Windows CI or Xvfb)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from app import App, Form
from core import Store

@unittest.skipUnless(sys.platform=='win32' or os.environ.get('DISPLAY'), 'Serve un display grafico')
class DesktopFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'ui.sqlite3')
        self.app = App(self.store)
        self.app.update()

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def dialog(self):
        return next(child for child in self.app.winfo_children() if isinstance(child,Form))

    def test_lot_item_sale_and_completion(self):
        self.app.lot_form()
        form = self.dialog()
        form.variables['name'].set('Box prova')
        form.variables['quantity'].set('10')
        form.variables['total'].set('100')
        form.submit()
        self.app.update()
        self.assertEqual(self.store.metrics()['stock_count'],10)
        self.app.show('stock')
        tree = self.app.stock_tree
        ident = tree.get_children()[0]
        tree.selection_set(ident)
        self.app.edit_selected()
        form = self.dialog()
        form.variables['title'].set('Felpa Nike vintage')
        form.variables['brand'].set('Nike')
        form.variables['asking'].set('15')
        form.variables['status'].set('In vendita')
        form.submit()
        self.app.update()
        self.app.stock_tree.selection_set(ident)
        self.app.sale_form()
        self.dialog().submit()
        self.app.update()
        self.assertEqual(self.store.metrics()['pending'],1)
        self.assertEqual(self.store.metrics()['revenue'],0)
        self.app.show('sales')
        sale_id = self.app.sales_tree.get_children()[0]
        self.app.sales_tree.selection_set(sale_id)
        self.app.update_sale()
        form = self.dialog()
        form.variables['status'].set('Completata')
        form.submit()
        self.app.update()
        self.assertEqual(self.store.metrics()['profit'],500)
        self.assertEqual(self.store.metrics()['cash'],-8500)
        self.assertEqual(self.store.metrics()['stock_count'],9)
        for page in self.app.nav_buttons:
            self.app.show(page)
            self.app.update()

    def test_invalid_form_does_not_save_or_close(self):
        self.app.item_form()
        form = self.dialog()
        form.variables['cost'].set('abc')
        form.submit()
        self.app.update()
        self.assertTrue(form.winfo_exists())
        self.assertTrue(form.error.get())
        self.assertEqual(self.store.metrics()['stock_count'],0)
        form.destroy()

    def test_photo_uploaded_during_item_creation_and_cancel_preserves_it(self):
        path = Path(self.tmp.name)/'foto.png'
        Image.new('RGB',(100,150),'navy').save(path)
        self.app.item_form()
        form = self.dialog()
        form.variables['title'].set('Capo fotografato')
        form.variables['cost'].set('7')
        form.photo_editor.add_paths([path])
        form.submit()
        self.app.update()
        ident = self.store.items()[0]['id']
        self.assertEqual(len(self.store.photos(ident)),1)
        self.app.show('stock')
        self.app.stock_tree.selection_set(str(ident))
        self.app.update()
        self.assertIsNotNone(self.app.stock_image_ref)
        self.app.item_form(ident)
        form = self.dialog()
        form.photo_editor.remove()
        form.destroy()
        self.assertEqual(len(self.store.photos(ident)),1)

    def test_complete_edits_and_shipping_forms(self):
        lot = self.store.add_lot('Box','','2026-08-01','20',2)
        item = self.store.items()[0]['id']
        sale = self.store.record_sale(item,'2026-09-01','20','0','0','In attesa')
        self.app.show('sales')
        self.app.sales_tree.selection_set(str(sale))
        self.app.update_sale()
        form = self.dialog()
        form.variables['price'].set('25')
        form.variables['buyer'].set('Compratore corretto')
        form.submit()
        self.app.update()
        self.assertEqual(self.store.sale(sale)['price'],2500)
        self.app.show('shipments')
        self.app.shipments_tree.selection_set(str(sale))
        self.app.shipment_form()
        form = self.dialog()
        form.variables['carrier'].set('InPost')
        form.variables['tracking'].set('TEST-123')
        form.variables['shipped_on'].set('2026-09-02')
        form.variables['status'].set('Spedita')
        form.submit()
        self.app.update()
        self.assertEqual(self.store.sale(sale)['status'],'Spedita')
        self.assertEqual(self.store.shipment(sale)['tracking'],'TEST-123')
        self.app.show('lots')
        self.app.lots_tree.selection_set(str(lot))
        self.app.edit_selected_lot()
        form = self.dialog()
        form.variables['total'].set('22')
        form.submit()
        self.app.update()
        self.assertEqual(self.store.sale(sale)['cost_snapshot'],1100)
        expense = self.store.add_expense('2026-09-01','Buste','1')
        self.app.show('expenses')
        self.app.expense_tree.selection_set(str(expense))
        self.app.edit_selected_expense()
        form = self.dialog()
        form.variables['amount'].set('2')
        form.submit()
        self.app.update()
        self.assertEqual(self.store.expense(expense)['amount'],200)

if __name__=='__main__':
    unittest.main()
