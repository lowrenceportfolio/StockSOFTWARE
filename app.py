"""VintDesk desktop entry point."""
import argparse
import io
import logging
import os
import sys
import tempfile
import tkinter as tk
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse
from PIL import Image, ImageTk

from core import SALE_STATES, STOCK_STATES, SHIPMENT_STATES, MAX_PHOTOS, Store, data_dir, money, prepare_photo

BG = '#f3f5f8'
INK = '#182535'
MUTED = '#69788a'
ACCENT = '#087f8c'
NAV = '#142735'

class PhotoEditor(ttk.Frame):
    def __init__(self, parent, store, ident=None):
        super().__init__(parent,style='White.TFrame',padding=12)
        self.store, self.ident = store, ident
        self.existing = store.photos(ident) if ident else []
        self.paths, self.removed = [], []
        ttk.Label(self,text=f'Carica fino a {MAX_PHOTOS} foto · JPG, PNG o WebP · 20 MB per foto',style='WhiteMuted.TLabel').pack(anchor='w',pady=(0,10))
        actions = ttk.Frame(self,style='White.TFrame')
        actions.pack(fill='x')
        ttk.Button(actions,text='Carica foto dal PC',command=self.choose,style='Accent.TButton').pack(side='left')
        ttk.Button(actions,text='Rimuovi selezionata',command=self.remove).pack(side='left',padx=8)
        ttk.Button(actions,text='Ingrandisci',command=self.enlarge).pack(side='left')
        content = ttk.Frame(self,style='White.TFrame')
        content.pack(fill='both',expand=True,pady=14)
        self.list = tk.Listbox(content,width=23,height=8,exportselection=False,font=('Segoe UI',10),bd=0,highlightthickness=1)
        self.list.pack(side='left',fill='y',padx=(0,15))
        self.list.bind('<<ListboxSelect>>',lambda _:self.show_selected())
        self.preview = ttk.Label(content,text='Nessuna foto caricata',style='WhiteMuted.TLabel',anchor='center')
        self.preview.pack(fill='both',expand=True)
        self.count = tk.StringVar()
        ttk.Label(self,textvariable=self.count,style='WhiteMuted.TLabel').pack(anchor='w')
        ttk.Label(self,text='Le modifiche alle foto vengono applicate quando premi Salva.\nLe foto sono conservate nel database e incluse nel backup.',style='WhiteMuted.TLabel',wraplength=540).pack(anchor='w',pady=(10,0))
        self.refresh()

    def entries(self):
        return [('stored',p['id'],p['name']) for p in self.existing if p['id'] not in self.removed] + [('new',i,Path(p).name) for i,p in enumerate(self.paths)]

    def refresh(self):
        self.list.delete(0,'end')
        for kind,ident,name in self.entries():
            self.list.insert('end',name+(' · nuova' if kind=='new' else ''))
        self.count.set(f'{len(self.entries())} / {MAX_PHOTOS} foto')
        if self.entries():
            self.list.selection_set(0)
        self.show_selected()

    def choose(self):
        paths = filedialog.askopenfilenames(parent=self.winfo_toplevel(),title='Carica foto del capo',filetypes=[('Foto','*.jpg *.jpeg *.png *.webp'),('Tutti i file','*.*')])
        if paths:
            try:
                self.add_paths(paths)
            except (ValueError,OSError) as exc:
                messagebox.showerror('Foto non caricata',str(exc),parent=self.winfo_toplevel())

    def add_paths(self, paths):
        if len(self.entries())+len(paths)>MAX_PHOTOS:
            raise ValueError(f'Massimo {MAX_PHOTOS} foto per capo.')
        for path in paths:
            prepare_photo(path)
        self.paths.extend(str(p) for p in paths)
        self.refresh()

    def selected_bytes(self):
        selected = self.list.curselection()
        if not selected:
            return None
        kind,ident,_ = self.entries()[selected[0]]
        return self.store.photo_data(ident) if kind=='stored' else prepare_photo(self.paths[ident])[1]

    def show_selected(self):
        try:
            data = self.selected_bytes()
            if not data:
                self.preview.configure(image='',text='Nessuna foto caricata')
                self.image_ref = None
                return
            with Image.open(io.BytesIO(data)) as image:
                image.thumbnail((290,220),Image.Resampling.LANCZOS)
                self.image_ref = ImageTk.PhotoImage(image,master=self)
            self.preview.configure(image=self.image_ref,text='')
        except (ValueError,OSError) as exc:
            self.preview.configure(image='',text=str(exc))

    def remove(self):
        selected = self.list.curselection()
        if selected:
            kind,ident,_ = self.entries()[selected[0]]
            self.removed.append(ident) if kind=='stored' else self.paths.pop(ident)
            self.refresh()

    def enlarge(self):
        data = self.selected_bytes()
        if data:
            dialog = tk.Toplevel(self)
            dialog.title('Foto del capo')
            dialog.transient(self.winfo_toplevel())
            with Image.open(io.BytesIO(data)) as image:
                image.thumbnail((min(900,self.winfo_screenwidth()-100),min(650,self.winfo_screenheight()-150)),Image.Resampling.LANCZOS)
                dialog.image_ref = ImageTk.PhotoImage(image,master=dialog)
            ttk.Label(dialog,image=dialog.image_ref).pack(padx=12,pady=12)
            dialog.bind('<Escape>',lambda _:dialog.destroy())

class Form(tk.Toplevel):
    def __init__(self, parent, title, fields, on_save, subtitle='', photos=False, photo_item_id=None):
        super().__init__(parent)
        self.title(title)
        self.configure(bg='white')
        self.resizable(False, False)
        self.transient(parent)
        self.on_save = on_save
        self.variables = {}
        frame = ttk.Frame(self, style='White.TFrame', padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=title, style='DialogTitle.TLabel').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,8))
        if subtitle:
            ttk.Label(frame, text=subtitle, style='WhiteMuted.TLabel', wraplength=560).grid(row=1, column=0,columnspan=2,sticky='w',pady=(0,14))
        self.photo_editor = None
        if photos:
            tabs = ttk.Notebook(frame)
            tabs.grid(row=2,column=0,columnspan=3,sticky='nsew')
            field_frame = ttk.Frame(tabs,style='White.TFrame',padding=8)
            tabs.add(field_frame,text='Dati del capo')
            self.photo_editor = PhotoEditor(tabs,parent.store,photo_item_id)
            tabs.add(self.photo_editor,text='Foto · carica dal PC')
        else:
            field_frame = ttk.Frame(frame,style='White.TFrame')
            field_frame.grid(row=2,column=0,columnspan=3,sticky='nsew')
        canvas = tk.Canvas(field_frame,bg='white',highlightthickness=0,width=575,
                           height=min(len(fields)*43,max(160,self.winfo_screenheight()-360)))
        canvas.grid(row=0,column=0,sticky='ew')
        inner = ttk.Frame(canvas,style='White.TFrame')
        canvas.create_window((0,0),window=inner,anchor='nw')
        inner.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
        scrollbar = ttk.Scrollbar(field_frame,orient='vertical',command=canvas.yview)
        scrollbar.grid(row=0,column=1,sticky='ns')
        canvas.configure(yscrollcommand=scrollbar.set)
        def scroll(event):
            canvas.yview_scroll(-1 if event.delta>0 or getattr(event,'num',0)==4 else 1,'units')
        canvas.bind('<MouseWheel>',scroll)
        canvas.bind('<Button-4>',scroll)
        canvas.bind('<Button-5>',scroll)
        for n, field in enumerate(fields):
            key, label, value, choices = field
            ttk.Label(inner, text=label, style='White.TLabel').grid(row=n, column=0, sticky='w',padx=(0,24),pady=5)
            var = tk.StringVar(value=str(value))
            self.variables[key] = var
            widget = ttk.Combobox(inner,textvariable=var,values=choices,state='readonly',width=36) if choices else ttk.Entry(inner,textvariable=var,width=39)
            widget.grid(row=n,column=1,sticky='ew',pady=5)
            widget.bind('<MouseWheel>',scroll)
            if n == 0:
                widget.focus_set()
        self.error = tk.StringVar()
        ttk.Label(frame,textvariable=self.error,foreground='#b42318',style='White.TLabel',wraplength=560).grid(row=3,column=0,columnspan=2,pady=8,sticky='w')
        buttons = ttk.Frame(frame,style='White.TFrame')
        buttons.grid(row=4,column=0,columnspan=2,sticky='e')
        ttk.Button(buttons,text='Annulla',command=self.destroy).pack(side='left',padx=8)
        ttk.Button(buttons,text='Salva',style='Accent.TButton',command=self.submit).pack(side='left')
        self.bind('<Escape>',lambda _:self.destroy())
        self.bind('<Return>',lambda _:self.submit())
        self.update_idletasks()
        x = parent.winfo_rootx() + max(0,(parent.winfo_width()-self.winfo_width())//2)
        y = parent.winfo_rooty() + max(0,(parent.winfo_height()-self.winfo_height())//2)
        self.geometry(f'+{x}+{y}')
        self.grab_set()

    def submit(self):
        try:
            data = {k:v.get() for k,v in self.variables.items()}
            if self.photo_editor:
                data['photo_paths'] = self.photo_editor.paths
                data['remove_photo_ids'] = self.photo_editor.removed
            self.on_save(data)
        except (ValueError, OSError) as exc:
            self.error.set(str(exc))
            return
        except Exception:
            logging.exception('Salvataggio fallito')
            self.error.set('Salvataggio non riuscito. I dettagli sono nel registro errori.')
            return
        self.destroy()

class App(tk.Tk):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.title('VintDesk — Stock e vendite')
        if sys.platform == 'win32':
            assets = Path(getattr(sys,'_MEIPASS',Path(__file__).parent)) / 'assets'
            self.iconbitmap(str(assets/'vintdesk.ico'))
        self.geometry(f'{min(1240,self.winfo_screenwidth()-60)}x{min(800,self.winfo_screenheight()-80)}')
        self.minsize(1060,650)
        self.configure(bg=BG)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.style()
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(0,weight=1)
        nav = tk.Frame(self,bg=NAV,width=206)
        nav.grid(row=0,column=0,sticky='ns')
        nav.pack_propagate(False)
        tk.Label(nav,text='VintDesk',font=('Segoe UI',23,'bold'),fg='white',bg=NAV).pack(anchor='w',padx=24,pady=(32,0))
        tk.Label(nav,text='IL TUO MAGAZZINO',font=('Segoe UI',9),fg='#8da8b6',bg=NAV).pack(anchor='w',padx=25,pady=(6,30))
        self.nav_buttons = {}
        for page,label in [('dashboard','Panoramica'),('stock','Stock'),('sales','Vendite'),('shipments','Spedizioni'),('lots','Box acquistati'),('expenses','Spese'),('data','Dati e backup')]:
            button = tk.Button(nav,text=label,anchor='w',font=('Segoe UI',11),bg=NAV,fg='#c3d1db',activebackground='#234756',activeforeground='white',relief='flat',bd=0,padx=24,pady=10,command=lambda p=page:self.show(p))
            button.pack(fill='x',padx=10,pady=2)
            self.nav_buttons[page] = button
        tk.Label(nav,text='VintDesk 1.1\nDati salvati sul PC',justify='left',font=('Segoe UI',9),fg='#8da8b6',bg=NAV).pack(side='bottom',anchor='w',padx=22,pady=22)
        self.body = ttk.Frame(self,padding=28)
        self.body.grid(row=0,column=1,sticky='nsew')
        self.page = 'dashboard'
        self.search = tk.StringVar()
        self.stock_filter = tk.StringVar(value='Tutti')
        self.shipment_filter = tk.StringVar(value='Da spedire')
        self.notice = tk.StringVar(value='Pronto. I dati vengono salvati automaticamente sul PC.')
        footer = ttk.Label(self,textvariable=self.notice,padding=(16,9),style='Footer.TLabel')
        footer.grid(row=1,column=0,columnspan=2,sticky='ew')
        self.show('dashboard')

    def style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.',font=('Segoe UI',10),background=BG,foreground=INK)
        s.configure('TFrame',background=BG)
        s.configure('White.TFrame',background='white')
        s.configure('TLabel',background=BG,foreground=INK)
        s.configure('Title.TLabel',font=('Segoe UI',24,'bold'))
        s.configure('Subtitle.TLabel',foreground=MUTED)
        s.configure('White.TLabel',background='white')
        s.configure('WhiteMuted.TLabel',background='white',foreground=MUTED)
        s.configure('DialogTitle.TLabel',font=('Segoe UI',18,'bold'),background='white')
        s.configure('Footer.TLabel',background='#e7edf1',foreground=MUTED,font=('Segoe UI',9))
        s.configure('TButton',padding=(13,9),background='white',borderwidth=1)
        s.map('TButton',background=[('active','#e5eef1')])
        s.configure('Accent.TButton',background=ACCENT,foreground='white',borderwidth=0)
        s.map('Accent.TButton',background=[('active','#066571')],foreground=[('active','white')])
        s.configure('TEntry',padding=7,fieldbackground='white')
        s.configure('TCombobox',padding=6,fieldbackground='white')
        s.configure('Treeview',background='white',fieldbackground='white',rowheight=36,borderwidth=0)
        s.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),background='#e9eff3',padding=10,relief='flat')
        s.map('Treeview',background=[('selected','#d3eef0')],foreground=[('selected',INK)])

    def close(self):
        self.store.close()
        self.destroy()

    def report_callback_exception(self, exc, val, tb):
        logging.error('Errore interfaccia',exc_info=(exc,val,tb))
        messagebox.showerror('Errore',str(val),parent=self)

    def heading(self, title, subtitle, buttons=()):
        frame = ttk.Frame(self.body)
        frame.pack(fill='x',pady=(0,22))
        text = ttk.Frame(frame)
        text.pack(side='left',fill='x',expand=True)
        ttk.Label(text,text=title,style='Title.TLabel').pack(anchor='w')
        ttk.Label(text,text=subtitle,style='Subtitle.TLabel',wraplength=600).pack(anchor='w',pady=(6,0))
        for label,action,accent in buttons:
            ttk.Button(frame,text=label,command=action,style='Accent.TButton' if accent else 'TButton').pack(side='right',padx=(8,0))

    def show(self, page):
        self.page = page
        for child in self.body.winfo_children():
            child.destroy()
        for key,button in self.nav_buttons.items():
            button.configure(bg='#234756' if key==page else NAV,fg='white' if key==page else '#c3d1db')
        getattr(self, 'page_' + page)()

    def changed(self, message):
        self.show(self.page)
        self.notice.set(message)

    def table(self, columns):
        frame = ttk.Frame(self.body)
        frame.pack(fill='both',expand=True,pady=(12,0))
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        tree = ttk.Treeview(frame,columns=[c[0] for c in columns],show='headings',selectmode='browse',height=6)
        for key,label,width in columns:
            tree.heading(key,text=label,command=lambda k=key:self.sort_tree(tree,k,False))
            tree.column(key,width=width,minwidth=65,stretch=key in ('title','description','name'))
        tree.grid(row=0,column=0,sticky='nsew')
        bar = ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
        bar.grid(row=0,column=1,sticky='ns')
        hbar = ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
        hbar.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=bar.set,xscrollcommand=hbar.set)
        tree.tag_configure('negative',foreground='#b42318')
        tree.tag_configure('muted',foreground=MUTED)
        return tree

    @staticmethod
    def sort_tree(tree, key, descending):
        def parse(value):
            try:
                return (0,float(value.replace(' €','').replace('.','').replace(',','.')))
            except ValueError:
                return (1,value.lower())
        for i,ident in enumerate(sorted(tree.get_children(),key=lambda ident:parse(tree.set(ident,key)),reverse=descending)):
            tree.move(ident,'',i)
        tree.heading(key,command=lambda:App.sort_tree(tree,key,not descending))

    def selected(self, tree):
        selection = tree.selection()
        if not selection:
            messagebox.showinfo('Seleziona una riga','Seleziona prima una riga della tabella.',parent=self)
            return None
        return int(selection[0])

    def page_dashboard(self):
        self.heading('Il tuo negozio, a colpo d’occhio','Stock, vendite completate e denaro investito.',
                     [('Aggiungi capo',self.item_form,True)])
        m = self.store.metrics()
        cards = ttk.Frame(self.body)
        cards.pack(fill='x')
        stats = [('CAPI IN STOCK',str(m['stock_count']),f"Valore a costo: {money(m['stock_value'])}"),
                 ('VENDITE COMPLETATE',str(m['sold_count']),f"{m['pending']} vendite da completare"),
                 ('INCASSI LORDI',money(m['revenue']),'Solo vendite completate'),
                 ('UTILE NETTO',money(m['profit']),'Ricavi − costo capi − spese')]
        for i,(label,value,help_text) in enumerate(stats):
            cards.columnconfigure(i,weight=1,uniform='cards')
            card = tk.Frame(cards,bg='white',padx=16,pady=20)
            card.grid(row=0,column=i,sticky='nsew',padx=(0,10 if i<3 else 0))
            tk.Label(card,text=label,bg='white',fg=MUTED,font=('Segoe UI',9)).pack(anchor='w')
            tk.Label(card,text=value,bg='white',fg=ACCENT if i==3 and m['profit']>=0 else '#b42318' if i==3 else INK,font=('Segoe UI',24,'bold')).pack(anchor='w',pady=8)
            tk.Label(card,text=help_text,bg='white',fg=MUTED,font=('Segoe UI',9),wraplength=190,justify='left').pack(anchor='w')
        ttk.Label(self.body,text=f"Saldo di cassa: {money(m['cash'])}    •    Spese generali: {money(m['expenses'])}",font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(22,5))
        ttk.Label(self.body,text='Saldo = incassi al netto di commissioni e spedizioni − tutti gli acquisti − spese generali.\nL’utile considera il costo dei soli capi venduti. Le vendite in attesa non generano incassi.',style='Subtitle.TLabel').pack(anchor='w')
        chart = tk.Canvas(self.body,bg='white',height=180,highlightthickness=0)
        chart.pack(fill='x',pady=(20,16))
        def draw(_=None):
            chart.delete('all')
            chart.create_text(20,22,text='INCASSI PER MESE',anchor='w',fill=INK,font=('Segoe UI',11,'bold'))
            values = self.store.monthly()
            if not values:
                chart.create_text(20,100,text='Registra la prima vendita completata per vedere l’andamento.',anchor='w',fill=MUTED,font=('Segoe UI',11))
                return
            width = max(chart.winfo_width()-60,300)
            step = width / len(values)
            maximum = max(max(r['revenue'] for r in values),1)
            for i,row in enumerate(values):
                x = 30 + step*i
                h = row['revenue']/maximum*95
                chart.create_rectangle(x,155-h,x+step*.6,155,fill=ACCENT,outline='')
                chart.create_text(x+step*.3,145-h,text=money(row['revenue']),fill=INK,font=('Segoe UI',9))
                chart.create_text(x+step*.3,172,text=row['month'],fill=MUTED,font=('Segoe UI',9))
        chart.bind('<Configure>',draw)
        alerts = []
        stale = (date.today()-timedelta(days=30)).isoformat()
        stale_count = self.store.db.execute("SELECT COUNT(*) FROM items WHERE status='In vendita' AND bought_on<=?",(stale,)).fetchone()[0]
        drafts = self.store.db.execute("SELECT COUNT(*) FROM items WHERE status='Da pubblicare'").fetchone()[0]
        if drafts:
            alerts.append(f'{drafts} capi da fotografare e pubblicare')
        if stale_count:
            alerts.append(f'{stale_count} capi acquistati da almeno 30 giorni e ancora in vendita')
        if m['pending']:
            alerts.append(f"{m['pending']} vendite in attesa o spedite: verifica prima di completarle")
        if m['overdue']:
            alerts.append(f"{m['overdue']} spedizioni oltre la scadenza: controlla Spedizioni")
        ttk.Label(self.body,text='DA TENERE D’OCCHIO',font=('Segoe UI',10,'bold')).pack(anchor='w')
        ttk.Label(self.body,text='\n'.join('• '+a for a in alerts) or 'Nessuna attività in sospeso.',foreground=MUTED).pack(anchor='w',pady=8)
        if not m['stock_count'] and not m['sold_count']:
            ttk.Button(self.body,text='Registra il tuo primo box',command=self.lot_form,style='Accent.TButton').pack(anchor='w')

    def page_stock(self):
        self.heading('Stock','Un capo per riga. Cerca anche per SKU, marca e posizione.',
          [('Aggiungi capo',self.item_form,True),('Nuovo box',self.lot_form,False)])
        controls = ttk.Frame(self.body)
        controls.pack(fill='x')
        entry = ttk.Entry(controls,textvariable=self.search,width=27)
        entry.pack(side='left',padx=(0,8))
        entry.bind('<KeyRelease>',lambda _:self.refresh_stock())
        combo = ttk.Combobox(controls,textvariable=self.stock_filter,values=('Tutti',*STOCK_STATES,'Venduto'),state='readonly',width=16)
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>',lambda _:self.refresh_stock())
        ttk.Button(controls,text='Elimina capo',command=self.delete_selected_item).pack(side='right')
        actions = ttk.Frame(self.body)
        actions.pack(fill='x',pady=(10,0))
        controls = actions
        ttk.Button(controls,text='Registra vendita',command=self.sale_form,style='Accent.TButton').pack(side='right')
        ttk.Button(controls,text='Modifica',command=self.edit_selected).pack(side='right',padx=8)
        ttk.Button(controls,text='Apri annuncio',command=self.open_listing).pack(side='right')
        self.stock_tree = self.table([('sku','SKU',120),('title','Capo',210),('photos','Foto',65),('brand','Marca',95),('size','Taglia',65),('cost','Costo',85),('asking','Prezzo',85),('status','Stato',105),('location','Posizione',90)])
        self.stock_tree.bind('<Double-1>',lambda _:self.edit_selected())
        self.stock_tree.bind('<<TreeviewSelect>>',lambda _:self.stock_detail())
        detail = ttk.Frame(self.body,style='White.TFrame',padding=10)
        detail.pack(fill='x',pady=(10,0))
        self.stock_preview = ttk.Label(detail,style='WhiteMuted.TLabel',text='Seleziona un capo per vedere la foto',width=25)
        self.stock_preview.pack(side='left',padx=(0,18))
        self.stock_info = ttk.Label(detail,style='WhiteMuted.TLabel',wraplength=650)
        self.stock_info.pack(side='left',anchor='n')
        self.refresh_stock()

    def stock_detail(self):
        selection = self.stock_tree.selection()
        self.stock_image_ref = None
        if not selection:
            self.stock_preview.configure(image='',text='Seleziona un capo')
            self.stock_info.configure(text='')
            return
        item = self.store.item(int(selection[0]))
        photos = self.store.photos(item['id'])
        if photos:
            with Image.open(io.BytesIO(self.store.photo_data(photos[0]['id']))) as image:
                image.thumbnail((130,110),Image.Resampling.LANCZOS)
                self.stock_image_ref = ImageTk.PhotoImage(image,master=self)
            self.stock_preview.configure(image=self.stock_image_ref,text='')
        else:
            self.stock_preview.configure(image='',text='Nessuna foto\nCaricala nella scheda del capo')
        self.stock_info.configure(text=f"{item['title']}\nSKU: {item['sku']} · Posizione: {item['location'] or '—'} · {len(photos)} foto\n{item['notes']}")

    def refresh_stock(self):
        tree = self.stock_tree
        tree.delete(*tree.get_children())
        items = self.store.items(self.search.get(),self.stock_filter.get())
        for r in items:
            tree.insert('','end',iid=r['id'],values=(r['sku'],r['title'],r['photo_count'],r['brand'],r['size'],money(r['cost']),money(r['asking']),r['status'],r['location']),tags=('muted',) if r['status'] in ('Venduto','Archiviato') else ())
        self.notice.set(f'{len(items)} capi visualizzati. Doppio clic per modificare.')

    def item_form(self, ident=None):
        r = self.store.item(ident) if ident else {}
        active = self.store.active_sale(ident) if ident else None
        fields = [('title','Nome capo',r.get('title',''),None),('brand','Marca',r.get('brand',''),None),
          ('size','Taglia',r.get('size',''),None),('category','Categoria',r.get('category',''),None),
          ('condition','Condizione',r.get('condition','Buone'),('Nuovo con cartellino','Nuovo senza cartellino','Ottime','Buone','Discrete','Da riparare')),
          ('cost','Costo di acquisto (€)',f"{r.get('cost',0)/100:.2f}",None),
          ('asking','Prezzo annuncio (€)',f"{r.get('asking',0)/100:.2f}",None),
          ('status','Stato',r.get('status','Da pubblicare'),(r['status'],) if active else STOCK_STATES),
          ('location','Posizione / scatola',r.get('location',''),None),
          ('bought_on','Data acquisto (AAAA-MM-GG)',r.get('bought_on',date.today()),None),
          ('sku','SKU (vuoto = automatico)',r.get('sku',''),None),
          ('url','Link annuncio',r.get('url',''),None),('notes','Note',r.get('notes',''),None)]
        def save(data):
            self.store.update_item(ident,data) if ident else self.store.add_item(data)
            self.changed('Capo salvato.')
        Form(self,'Modifica capo' if ident else 'Nuovo capo',fields,save,
             'Carica le immagini nella scheda Foto. Se correggi il costo, box e margine della vendita attiva vengono aggiornati.',photos=True,photo_item_id=ident)

    def confirm_change(self, title, text, callback, notice):
        if messagebox.askyesno(title,text,parent=self):
            try:
                callback()
                self.changed(notice)
            except ValueError as exc:
                messagebox.showerror(title,str(exc),parent=self)

    def delete_selected_item(self):
        ident = self.selected(self.stock_tree)
        if ident:
            self.confirm_change('Elimina capo','Eliminare il capo e le sue foto? È possibile soltanto senza storico vendite. Il costo viene rimosso dagli acquisti.',lambda:self.store.delete_item(ident),'Capo eliminato.')

    def edit_selected(self):
        ident = self.selected(self.stock_tree)
        if ident:
            self.item_form(ident)

    def open_listing(self):
        ident = self.selected(self.stock_tree)
        if not ident:
            return
        url = self.store.item(ident)['url']
        parsed = urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc:
            messagebox.showinfo('Link mancante','Inserisci un link http o https valido nella scheda del capo.',parent=self)
            return
        webbrowser.open(url)

    def lot_form(self, ident=None):
        r = self.store.lot(ident) if ident else {}
        fields = [('name','Nome box',r.get('name','Box prova vintage'),None),('supplier','Fornitore',r.get('supplier',''),None),
          ('quantity','Numero di capi',r.get('quantity','10'),None),('total','Costo totale, spedizione inclusa (€)',f"{r.get('total',10000)/100:.2f}",None),
          ('bought_on','Data acquisto (AAAA-MM-GG)',r.get('bought_on',date.today()),None)]
        def save(data):
            self.store.update_lot(ident,**data) if ident else self.store.add_lot(**data)
            self.changed('Box salvato. I capi e i margini sono aggiornati.')
        Form(self,'Modifica box' if ident else 'Nuovo box',fields,save,'Cambiare totale o quantità ripartisce nuovamente il costo su tutti i capi. Puoi ridurre la quantità solo se i capi rimossi sono ancora vuoti.')

    def sale_form(self):
        ident = self.selected(self.stock_tree)
        if not ident:
            return
        item = self.store.item(ident)
        if self.store.active_sale(ident):
            messagebox.showinfo('Vendita già presente','Questo capo ha già una vendita. Gestiscila dalla sezione Vendite.',parent=self)
            return
        fields = [('sold_on','Data vendita (AAAA-MM-GG)',date.today(),None),('price','Prezzo pagato per il capo (€)',f"{item['asking']/100:.2f}",None),
          ('fees','Commissioni a tuo carico (€)','0.00',None),('shipping','Spedizione a tuo carico (€)','0.00',None),
          ('status','Stato vendita','In attesa',SALE_STATES),('buyer','Compratore (facoltativo)','',None),('notes','Note','',None)]
        def save(data):
            self.store.record_sale(ident,**data)
            self.changed('Vendita registrata. Gli incassi sono conteggiati quando la vendita è Completata.')
        Form(self,'Registra vendita',fields,save,item['title']+' · costo '+money(item['cost'])+'. Inserisci solo le spese che paghi tu.')

    def page_sales(self):
        self.heading('Vendite','Gli incassi e l’utile entrano nei totali solo con lo stato Completata.')
        controls = ttk.Frame(self.body)
        controls.pack(fill='x')
        ttk.Button(controls,text='Modifica vendita',command=self.update_sale,style='Accent.TButton').pack(side='left')
        ttk.Button(controls,text='Annulla / reso',command=self.cancel_sale).pack(side='left',padx=8)
        ttk.Button(controls,text='Elimina',command=self.delete_selected_sale).pack(side='left')
        ttk.Button(controls,text='Esporta CSV',command=lambda:self.export('sales')).pack(side='right')
        self.sales_tree = self.table([('title','Capo',230),('sold_on','Data',100),('price','Vendita',95),('cost','Costo capo',95),('charges','Spese',85),('profit','Margine',100),('status','Stato',110),('buyer','Compratore',100)])
        for r in self.store.sales():
            self.sales_tree.insert('','end',iid=r['id'],values=(r['title'],r['sold_on'],money(r['price']),money(r['cost_snapshot']),money(r['fees']+r['shipping']),money(r['profit']),r['status'],r['buyer']),tags=('muted',) if r['status']=='Annullata' else ('negative',) if r['profit']<0 else ())
        self.sales_tree.bind('<Double-1>',lambda _:self.update_sale())
        ttk.Label(self.body,text='Il margine per vendita esclude le spese generali. Un reso completo riporta il capo In vendita; eventuali costi non rimborsati vanno registrati in Spese.',style='Subtitle.TLabel',wraplength=880).pack(anchor='w',pady=10)

    def update_sale(self):
        ident = self.selected(self.sales_tree)
        if not ident:
            return
        r = self.store.sale(ident)
        choices = {}
        for item in self.store.items():
            if item['id']==r['item_id'] or not self.store.active_sale(item['id']):
                choices[f"{item['sku']} · {item['title']}"] = item['id']
        current = next(label for label,item_id in choices.items() if item_id==r['item_id'])
        def save(data):
            data['item_id'] = choices[data.pop('item')]
            self.store.update_sale(ident,**data)
            self.changed('Vendita aggiornata. Incassi, margini e stock ricalcolati.')
        fields = [('item','Capo',current,tuple(choices)),('sold_on','Data vendita (AAAA-MM-GG)',r['sold_on'],None),
          ('price','Prezzo del capo (€)',f"{r['price']/100:.2f}",None),('fees','Commissioni (€)',f"{r['fees']/100:.2f}",None),
          ('shipping','Spedizione a tuo carico (€)',f"{r['shipping']/100:.2f}",None),('status','Stato vendita',r['status'],(*SALE_STATES,'Annullata')),
          ('buyer','Compratore',r['buyer'],None),('notes','Note',r['notes'],None)]
        Form(self,'Modifica vendita',fields,save,'Puoi correggere tutti i dati senza annullare la vendita. Una vendita annullata può essere riattivata solo se il capo non ha un’altra vendita attiva.')

    def delete_selected_sale(self):
        ident = self.selected(self.sales_tree)
        if ident:
            self.confirm_change('Elimina vendita','Eliminare questa vendita e la relativa spedizione dallo storico? Per un reso usa Annulla / reso.',lambda:self.store.delete_sale(ident),'Vendita eliminata.')

    def cancel_sale(self):
        ident = self.selected(self.sales_tree)
        if ident and messagebox.askyesno('Annulla vendita / reso','Confermi l’annullamento completo? Gli incassi saranno rimossi e il capo tornerà In vendita. Lo storico rimane.',parent=self):
            try:
                self.store.set_sale_status(ident,'Annullata')
                self.changed('Vendita annullata; capo di nuovo disponibile.')
            except ValueError as exc:
                messagebox.showerror('Impossibile annullare',str(exc),parent=self)

    def page_lots(self):
        self.heading('Box acquistati','Il recupero di cassa confronta gli incassi netti del box con tutto il costo iniziale.',
                     [('Nuovo box',self.lot_form,True)])
        controls = ttk.Frame(self.body)
        controls.pack(fill='x')
        ttk.Button(controls,text='Modifica box',command=self.edit_selected_lot,style='Accent.TButton').pack(side='left')
        ttk.Button(controls,text='Elimina box',command=self.delete_selected_lot).pack(side='left',padx=8)
        tree = self.lots_tree = self.table([('name','Box',230),('supplier','Fornitore',150),('bought_on','Acquistato',105),('quantity','Capi',65),('remaining','Rimasti',75),('total','Investito',110),('receipts','Incassi netti',110),('recovery','Recupero cassa',120)])
        tree.bind('<Double-1>',lambda _:self.edit_selected_lot())
        for r in self.store.lots():
            delta = r['receipts']-r['total']
            tree.insert('','end',iid=r['id'],values=(r['name'],r['supplier'],r['bought_on'],r['quantity'],r['remaining'],money(r['total']),money(r['receipts']),money(delta)),tags=('negative',) if delta<0 else ())
        ttk.Label(self.body,text='Un recupero negativo significa che non hai ancora recuperato tutto il costo del box. Non coincide con l’utile dei capi già venduti.',style='Subtitle.TLabel',wraplength=880).pack(anchor='w',pady=12)

    def edit_selected_lot(self):
        ident = self.selected(self.lots_tree)
        if ident:
            self.lot_form(ident)

    def delete_selected_lot(self):
        ident = self.selected(self.lots_tree)
        if ident:
            self.confirm_change('Elimina box','Eliminare il box, tutti i suoi capi e tutte le foto? È possibile solo se non contiene vendite registrate.',lambda:self.store.delete_lot(ident),'Box eliminato.')

    def page_expenses(self):
        self.heading('Spese generali','Imballaggi, pulizia e altri costi. Non reinserire i costi già presenti nei capi o nelle vendite.',
                     [('Aggiungi spesa',self.expense_form,True)])
        controls = ttk.Frame(self.body)
        controls.pack(fill='x')
        ttk.Button(controls,text='Modifica spesa',command=self.edit_selected_expense,style='Accent.TButton').pack(side='left')
        ttk.Button(controls,text='Elimina spesa',command=self.delete_expense).pack(side='left',padx=8)
        self.expense_tree = self.table([('spent_on','Data',110),('description','Descrizione',500),('amount','Importo',120)])
        for r in self.store.rows('SELECT * FROM expenses ORDER BY spent_on DESC,id DESC'):
            self.expense_tree.insert('','end',iid=r['id'],values=(r['spent_on'],r['description'],money(r['amount'])))
        self.expense_tree.bind('<Double-1>',lambda _:self.edit_selected_expense())

    def expense_form(self, ident=None):
        r = self.store.expense(ident) if ident else {}
        def save(data):
            self.store.update_expense(ident,**data) if ident else self.store.add_expense(**data)
            self.changed('Spesa salvata.')
        Form(self,'Modifica spesa' if ident else 'Nuova spesa',[('spent_on','Data (AAAA-MM-GG)',r.get('spent_on',date.today()),None),('description','Descrizione',r.get('description',''),None),('amount','Importo (€)',f"{r.get('amount',0)/100:.2f}",None)],save)

    def edit_selected_expense(self):
        ident = self.selected(self.expense_tree)
        if ident:
            self.expense_form(ident)

    def page_shipments(self):
        self.heading('Spedizioni','Corriere, tracking e scadenze. Lo stato di consegna si aggiorna manualmente.')
        controls = ttk.Frame(self.body)
        controls.pack(fill='x')
        combo = ttk.Combobox(controls,textvariable=self.shipment_filter,state='readonly',width=17,
            values=('Da spedire','Tutte','Spedita','Consegnata','Problema','Scadute'))
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>',lambda _:self.refresh_shipments())
        ttk.Button(controls,text='Gestisci spedizione',command=self.shipment_form,style='Accent.TButton').pack(side='left',padx=10)
        ttk.Button(controls,text='Apri tracking',command=self.open_tracking).pack(side='right')
        ttk.Button(controls,text='Copia codice',command=self.copy_tracking).pack(side='right',padx=8)
        self.shipments_tree = self.table([('title','Capo',210),('location','Posizione',95),('carrier','Corriere',105),('tracking','Tracking',150),('ship_by','Scadenza',100),('status','Spedizione',110),('sale_status','Vendita',110)])
        self.shipments_tree.bind('<Double-1>',lambda _:self.shipment_form())
        self.refresh_shipments()
        ttk.Label(self.body,text='Rosso = scadenza superata. Consegnata non significa pagamento ricevuto: completa la vendita quando hai incassato.',style='Subtitle.TLabel',wraplength=880).pack(anchor='w',pady=10)

    def refresh_shipments(self):
        self.shipments_tree.delete(*self.shipments_tree.get_children())
        for r in self.store.shipments(self.shipment_filter.get()):
            self.shipments_tree.insert('','end',iid=r['sale_id'],values=(r['title'],r['location'],r['carrier'],r['tracking'],r['ship_by'] or '—',r['status'],r['sale_status']),tags=('negative',) if r['overdue'] else ())

    def shipment_form(self):
        ident = self.selected(self.shipments_tree)
        if not ident:
            return
        r = self.store.shipment(ident)
        fields = [('carrier','Corriere',r['carrier'],None),('tracking','Codice tracking',r['tracking'],None),
            ('tracking_url','Link tracking',r['tracking_url'],None),('ship_by','Spedire entro (AAAA-MM-GG)',r['ship_by'],None),
            ('shipped_on','Data spedizione (AAAA-MM-GG)',r['shipped_on'],None),('delivered_on','Data consegna (AAAA-MM-GG)',r['delivered_on'],None),
            ('status','Stato spedizione',r['status'],SHIPMENT_STATES[:-1]),('notes','Note',r['notes'],None)]
        def save(data):
            self.store.update_shipment(ident,**data)
            self.changed('Spedizione aggiornata.')
        Form(self,'Gestisci spedizione',fields,save,'Le date sono facoltative finché non segni Spedita o Consegnata. Il tracking si apre nel browser.')

    def open_tracking(self):
        ident = self.selected(self.shipments_tree)
        if ident:
            url = self.store.shipment(ident)['tracking_url']
            if url and urlparse(url).scheme in ('http','https') and urlparse(url).netloc:
                webbrowser.open(url)
            else:
                messagebox.showinfo('Tracking','Inserisci il link tracking nella scheda della spedizione.',parent=self)

    def copy_tracking(self):
        ident = self.selected(self.shipments_tree)
        if ident:
            self.clipboard_clear()
            self.clipboard_append(self.store.shipment(ident)['tracking'])
            self.notice.set('Codice tracking copiato.')

    def delete_expense(self):
        ident = self.selected(self.expense_tree)
        if ident and messagebox.askyesno('Elimina spesa','Vuoi eliminare questa spesa?',parent=self):
            self.store.delete_expense(ident)
            self.changed('Spesa eliminata.')

    def page_data(self):
        self.heading('I tuoi dati','Il database rimane sul tuo PC. Il repository contiene soltanto il software.')
        sections = [
          ('Backup completo','Salva un file con stock, foto, box, vendite, spedizioni e spese. Copialo anche su un altro dispositivo.', [('Crea backup',self.backup),('Ripristina backup',self.restore)]),
          ('CSV e importazione','Importa nuovi capi dal modello CSV. Gli SKU duplicati bloccano tutta l’importazione.\nGli export servono per consultazione; il backup SQLite conserva lo storico completo.', [('Importa capi CSV',self.import_csv),('Esporta stock',lambda:self.export('stock')),('Esporta vendite',lambda:self.export('sales')),('Salva modello CSV',self.csv_template)]),
          ('Posizione database',str(self.store.path), [('Apri cartella dati',self.open_data)]),
          ('Come iniziare','1. Registra il box o un capo.\n2. Compila nome, marca, taglia e posizione nello stock.\n3. Quando pubblichi su Vinted, seleziona In vendita e incolla il link.\n4. Registra la vendita; segnala Completata quando ricevi il denaro.\n5. Controlla utile, saldo di cassa e recupero dei box.', []),
        ]
        tabs = ttk.Notebook(self.body)
        tabs.pack(fill='both',expand=True)
        for title,description,actions in sections:
            card = ttk.Frame(tabs,style='White.TFrame',padding=24)
            tabs.add(card,text=title)
            ttk.Label(card,text=title,style='DialogTitle.TLabel',font=('Segoe UI',13,'bold')).pack(anchor='w')
            ttk.Label(card,text=description,style='WhiteMuted.TLabel',wraplength=850).pack(anchor='w',pady=8)
            row = ttk.Frame(card,style='White.TFrame')
            row.pack(anchor='w')
            for label,callback in actions:
                ttk.Button(row,text=label,command=callback).pack(side='left',padx=(0,8))

    def csv_template(self):
        from core import CSV_FIELDS
        import csv
        path = filedialog.asksaveasfilename(parent=self,defaultextension='.csv',initialfile='modello-stock.csv',filetypes=[('CSV','*.csv')])
        if path:
            with open(path,'w',encoding='utf-8-sig',newline='') as f:
                writer = csv.writer(f,delimiter=';')
                writer.writerow(CSV_FIELDS)
                writer.writerow(['VD-ESEMPIO-1','Felpa vintage','Nike','L','Felpe','Buone','7.00','15.00','Scatola A',date.today().isoformat(),'','Riga di esempio: modifica o rimuovi prima di importare'])
            self.notice.set('Modello CSV salvato.')

    def export(self, kind):
        path = filedialog.asksaveasfilename(parent=self,defaultextension='.csv',initialfile=f'{kind}-{date.today()}.csv',filetypes=[('CSV','*.csv')])
        if path:
            self.store.export_csv(path,kind)
            self.notice.set('Esportazione salvata.')

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self,filetypes=[('CSV','*.csv')])
        if path:
            try:
                count = self.store.import_csv(path)
                self.changed(f'Importati {count} capi.')
            except (ValueError,OSError,UnicodeError) as exc:
                messagebox.showerror('Importazione non riuscita',str(exc),parent=self)

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self,defaultextension='.sqlite3',initialfile=f'vintdesk-backup-{datetime.now():%Y%m%d-%H%M%S}.sqlite3',filetypes=[('Backup VintDesk','*.sqlite3')])
        if path:
            self.store.backup(path)
            self.notice.set('Backup completo salvato.')

    def restore(self):
        path = filedialog.askopenfilename(parent=self,filetypes=[('Backup VintDesk','*.sqlite3')])
        if path and messagebox.askyesno('Ripristina backup','Sostituire i dati attuali con questo backup? Prima verrà creata una copia di sicurezza dei dati attuali.',parent=self):
            try:
                safety = self.store.restore(path)
                self.changed('Ripristino completato. Copia di sicurezza: '+safety.name)
            except Exception as exc:
                messagebox.showerror('Ripristino non riuscito',str(exc),parent=self)

    def open_data(self):
        if sys.platform == 'win32':
            os.startfile(self.store.path.parent)
        else:
            webbrowser.open(self.store.path.parent.resolve().as_uri())

def main():
    parser = argparse.ArgumentParser(description='VintDesk — Gestionale locale per rivenditori Vinted')
    parser.add_argument('--database',type=Path,help='Percorso database alternativo (test / sviluppo)')
    parser.add_argument('--smoke-test',action='store_true',help='Apre tutte le schermate e chiude (verifica build)')
    args = parser.parse_args()
    if args.smoke_test and not args.database:
        parser.error('--smoke-test richiede --database con un percorso di prova.')
    logging.basicConfig(filename=data_dir()/'errors.log',level=logging.ERROR,format='%(asctime)s %(levelname)s %(message)s')
    try:
        store = Store(args.database)
        app = App(store)
        if args.smoke_test:
            with tempfile.TemporaryDirectory() as tmp:
                photo = Path(tmp)/'foto-smoke.png'
                Image.new('RGB',(100,150),'navy').save(photo)
                ident = store.add_item(dict(title='Verifica foto installer',cost='0',photo_paths=[photo]))
                for page in app.nav_buttons:
                    app.show(page)
                    app.update()
                app.show('stock')
                app.stock_tree.selection_set(str(ident))
                app.update()
                if app.stock_image_ref is None:
                    raise RuntimeError('Anteprima foto non funzionante nella build.')
                app.item_form(ident)
                dialog = next(c for c in app.winfo_children() if isinstance(c,Form))
                dialog.photo_editor.master.select(dialog.photo_editor)
                app.update()
                if not dialog.photo_editor.image_ref:
                    raise RuntimeError('Scheda foto non funzionante nella build.')
                dialog.destroy()
                store.delete_item(ident)
            app.close()
        else:
            app.mainloop()
    except Exception:
        logging.exception('Avvio fallito')
        if args.smoke_test:
            raise
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror('VintDesk','Avvio non riuscito. Consulta errors.log nella cartella dati. Il database non viene cancellato.')
            root.destroy()
        except Exception:
            raise

if __name__ == '__main__':
    main()
