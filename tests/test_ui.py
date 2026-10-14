"""Real Tkinter UI checks. Requires a graphical display (Windows CI or Xvfb)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

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

if __name__=='__main__':
    unittest.main()
