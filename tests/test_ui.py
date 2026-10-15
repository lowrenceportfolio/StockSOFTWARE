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

    def test_cloud_download_is_deferred_if_local_changes_during_request(self):
        from cloud import Supabase, PROJECT_URL, snapshot
        controller = self.app.cloud
        controller.client = Supabase(PROJECT_URL)
        controller.client.user_id = 'test-user'
        remote = snapshot(self.store)
        callbacks = []
        controller.run = lambda work, done, manual=True: callbacks.append(done)
        controller.sync()
        ident = self.store.add_item(dict(title='Modifica durante rete',cost='1',asking='2'))
        callbacks[0](('pull', 1, remote))
        self.assertEqual(self.store.item(ident)['title'], 'Modifica durante rete')
        self.assertIn('rinviato', controller.status.get())

    def test_cloud_settings_display_default_project_without_password_persistence(self):
        import tkinter as tk
        from cloud import PROJECT_URL
        self.app.show('data')
        self.app.cloud.configure()
        dialog = next(child for child in self.app.winfo_children() if isinstance(child, tk.Toplevel))
        entries = [w for w in dialog.winfo_children()[0].winfo_children() if w.winfo_class() == 'TEntry']
        self.assertEqual(entries[0].get(), PROJECT_URL)
        self.assertEqual(entries[2].cget('show'), '*')
        self.assertFalse(self.app.cloud.settings_path.exists())
        dialog.destroy()

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

    def test_dates_in_italian_format_and_error_focus(self):
        self.app.expense_form()
        form = self.dialog()
        self.assertRegex(form.variables['spent_on'].get(),r'^\d\d/\d\d/\d{4}$')
        form.variables['description'].set('Buste')
        form.variables['amount'].set('abc')
        form.submit()
        self.app.update()
        self.assertTrue(form.winfo_exists())
        self.assertIs(form.focus_lastfor(),form.widgets[2])
        form.variables['amount'].set('2,50')
        form.variables['spent_on'].set('01/09/2026')
        form.submit()
        self.app.update()
        self.assertEqual(self.store.rows('SELECT spent_on,amount FROM expenses'),[{'spent_on':'2026-09-01','amount':250}])

    def test_goal_slider_and_cancel_without_changes(self):
        self.app.show('dashboard')
        self.app.goal.set(300)
        self.app.update()
        self.app.item_form()
        form = self.dialog()
        form.cancel()
        self.app.update()
        self.assertFalse(form.winfo_exists())

if __name__=='__main__':
    unittest.main()
