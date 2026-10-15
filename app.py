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

from core import SALE_STATES, STOCK_STATES, SHIPMENT_STATES, MAX_PHOTOS, Store, cents, data_dir, iso_date, money, prepare_photo

from cloud_ui import CloudController

import ui_kit as ui
from ui_kit import BG, SURFACE_1 as SURFACE, SURFACE_2, SURFACE_3, ROW_ALT, INK, MUTED, ACCENT, ACCENT_INK, NEGATIVE, POSITIVE, WARNING
from ui_kit import SMALL, BODY, LEAD, HEAD, DISPLAY


def background_of(widget):
    try:
        return widget.cget('background')
    except tk.TclError:
        style = widget.cget('style') or widget.winfo_class()
        return ttk.Style(widget).lookup(style, 'background') or BG


def make_button(parent, text, command, primary=False, danger=False):
    """Primary actions take the tag shape; secondary actions are flat tone steps; destructive ones are red."""
    bg = background_of(parent)
    if primary:
        return ui.TagButton(parent, text, command, bg=bg)
    return ui.flat_button(parent, text, command, bg=SURFACE_3 if bg == SURFACE else SURFACE_2, danger=danger)


def it_date(value):
    return f'{value[8:10]}/{value[5:7]}/{value[:4]}' if value and len(value) == 10 else (value or '—')


def short_money(value):
    return money(value).replace(',00 €', ' €')


class PhotoEditor(ttk.Frame):
    def __init__(self, parent, store, ident=None):
        super().__init__(parent,style='White.TFrame',padding=12)
        self.store, self.ident = store, ident
        self.existing = store.photos(ident) if ident else []
        self.paths, self.removed = [], []
        ttk.Label(self,text=f'Carica fino a {MAX_PHOTOS} foto · JPG, PNG o WebP · 20 MB per foto',style='WhiteMuted.TLabel').pack(anchor='w',pady=(0,10))
        actions = ttk.Frame(self,style='White.TFrame')
        actions.pack(fill='x')
        make_button(actions,'Carica foto dal PC',self.choose,primary=True).pack(side='left')
        self.remove_button = make_button(actions,'Rimuovi selezionata',self.remove,danger=True)
        self.remove_button.pack(side='left',padx=8)
        self.enlarge_button = make_button(actions,'Ingrandisci',self.enlarge)
        self.enlarge_button.pack(side='left')
        content = ttk.Frame(self,style='White.TFrame')
        content.pack(fill='both',expand=True,pady=14)
        self.list = tk.Listbox(content,width=23,height=8,exportselection=False,font=ui.font(BODY),bd=0,highlightthickness=0,
                               bg=SURFACE_2,fg=INK,selectbackground=SURFACE_3,selectforeground=INK,activestyle='none')
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
        for button in (self.remove_button,self.enlarge_button):
            ui.set_enabled(button,bool(self.list.curselection()))
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
    def __init__(self, parent, title, fields, on_save, subtitle='', photos=False, photo_item_id=None, save_label='Salva'):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        self.on_save = on_save
        self.variables, self.widgets, self.labels, self.hints = {}, [], {}, {}
        self.invalid = None
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
        canvas = self.canvas = tk.Canvas(field_frame,bg=SURFACE,highlightthickness=0,width=ui.px(575),
                           height=min(len(fields)*ui.px(46),max(160,self.winfo_screenheight()-360)))
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
            if '(AAAA-MM-GG)' in label:
                label, value = label.replace('(AAAA-MM-GG)','(GG/MM/AAAA)'), it_date(str(value)) if value else ''
            caption = ttk.Label(inner, text=label, style='White.TLabel', cursor='hand2')
            caption.grid(row=n*2, column=0, sticky='w',padx=(0,24),pady=5)
            var = tk.StringVar(value=str(value))
            self.variables[key] = var
            widget = ttk.Combobox(inner,textvariable=var,values=choices,state='readonly',width=36) if choices else ttk.Entry(inner,textvariable=var,width=39)
            widget.grid(row=n*2,column=1,sticky='ew',pady=5)
            # The error for a field sits right under it and goes away as soon as the field is edited.
            hint = ttk.Label(inner,style='FieldError.TLabel',wraplength=ui.px(330))
            hint.grid(row=n*2+1,column=1,sticky='w',pady=(0,ui.px(6)))
            hint.grid_remove()
            self.hints[key] = hint
            var.trace_add('write',lambda *_,k=key:self.clear_invalid(k))
            self.widgets.append(widget)
            self.labels[key] = label
            caption.bind('<Button-1>',lambda _,w=widget:w.focus_set())
            widget.bind('<MouseWheel>',scroll)
            if n == 0:
                widget.focus_set()
        self.error = tk.StringVar()
        ttk.Label(frame,textvariable=self.error,foreground=NEGATIVE,style='White.TLabel',wraplength=560).grid(row=3,column=0,columnspan=2,pady=8,sticky='w')
        buttons = ttk.Frame(frame,style='White.TFrame')
        buttons.grid(row=4,column=0,columnspan=2,sticky='e')
        make_button(buttons,'Annulla',self.cancel).pack(side='left',padx=8)
        make_button(buttons,save_label,self.submit,primary=True).pack(side='left')
        self.bind('<Escape>',lambda _:self.cancel())
        self.protocol('WM_DELETE_WINDOW',self.cancel)
        self.initial = {k:v.get() for k,v in self.variables.items()}
        self.bind('<Return>',lambda _:self.submit())
        self.update_idletasks()
        x = parent.winfo_rootx() + max(0,(parent.winfo_width()-self.winfo_width())//2)
        y = parent.winfo_rooty() + max(0,(parent.winfo_height()-self.winfo_height())//2)
        self.geometry(f'+{x}+{y}')
        self.grab_set()

    def dirty(self):
        photos = self.photo_editor and (self.photo_editor.paths or self.photo_editor.removed)
        return bool(photos) or any(v.get() != self.initial[k] for k,v in self.variables.items())

    def cancel(self):
        if self.dirty() and not messagebox.askyesno('Modifiche non salvate','Chiudere senza salvare le modifiche?',parent=self):
            return
        self.destroy()

    def focus_field(self, message):
        """Porta il cursore sul campo da correggere: una data o un importo non validi, poi il campo nominato nell'errore."""
        def invalid(key):
            label, value = self.labels[key], self.variables[key].get()
            try:
                if 'GG/MM' in label and value.strip():
                    iso_date(value)
                elif '€' in label:
                    cents(value)
            except ValueError:
                return True
            return False
        target = next((k for k in self.variables if invalid(k)),None)
        text = message.lower()
        for word,key in (('nome del capo','title'),('nome del box','name'),('descrizione','description'),('link tracking','tracking_url'),('numero di capi','quantity'),('sku','sku')):
            if not target and word in text and key in self.variables:
                target = key
        keys = list(self.variables)
        widget = self.widgets[keys.index(target)] if target else (self.widgets[0] if self.widgets else None)
        if target:
            self.mark_invalid(target,message)
        if widget:
            widget.focus_set()

    def mark_invalid(self, key, message):
        """Red border and the message under the field; the summary next to Salva stays as well."""
        self.clear_invalid(self.invalid)
        widget = self.widgets[list(self.variables).index(key)]
        widget.configure(style='Invalid.'+widget.winfo_class())
        self.hints[key].configure(text=message)
        self.hints[key].grid()
        self.invalid = key
        self.update_idletasks()
        inner = widget.master
        self.canvas.yview_moveto(max(widget.winfo_y()-ui.px(20),0)/max(inner.winfo_height(),1))

    def clear_invalid(self, key):
        if key is None or key != self.invalid:
            return
        widget = self.widgets[list(self.variables).index(key)]
        widget.configure(style=widget.winfo_class())
        self.hints[key].grid_remove()
        self.invalid = None
        self.error.set('')

    def submit(self):
        try:
            data = {k:v.get() for k,v in self.variables.items()}
            if self.photo_editor:
                data['photo_paths'] = self.photo_editor.paths
                data['remove_photo_ids'] = self.photo_editor.removed
            self.on_save(data)
        except (ValueError, OSError) as exc:
            self.focus_field(str(exc))
            self.error.set(f'Controlla il campo «{self.labels[self.invalid]}».' if self.invalid else str(exc))
            return
        except Exception:
            logging.exception('Salvataggio fallito')
            self.error.set('Salvataggio non riuscito. I dettagli sono nel registro errori.')
            return
        self.destroy()

class App(tk.Tk):
    def __init__(self, store):
        ui.load_private_fonts()
        super().__init__()
        ui.init(self)
        self.store = store
        self.thumbs = {}
        self.title('VintDesk — Stock e vendite')
        if sys.platform == 'win32':
            assets = Path(getattr(sys,'_MEIPASS',Path(__file__).parent)) / 'assets'
            self.iconbitmap(str(assets/'vintdesk.ico'))
        self.geometry(f'{min(ui.px(1280),self.winfo_screenwidth()-60)}x{min(ui.px(820),self.winfo_screenheight()-80)}')
        self.minsize(ui.px(1080),ui.px(680))
        self.configure(bg=BG)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.style()
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(0,weight=1)
        nav = tk.Frame(self,bg=SURFACE,width=ui.px(220))
        nav.grid(row=0,column=0,rowspan=2,sticky='ns')
        nav.pack_propagate(False)
        mark = tk.Frame(nav,bg=SURFACE)
        mark.pack(anchor='w',padx=ui.px(28),pady=(ui.px(28),ui.px(34)))
        tk.Label(mark,text='vint',font=ui.font(30,'bold'),fg=INK,bg=SURFACE,bd=0,padx=0).pack(side='left')
        tk.Label(mark,text='desk',font=ui.font(30,'bold'),fg=ACCENT,bg=SURFACE,bd=0,padx=0).pack(side='left')
        self.nav_buttons, self.nav_rows = {}, {}
        pages = [('dashboard','Panoramica'),('stock','Stock'),('sales','Vendite'),('shipments','Spedizioni'),('lots','Box acquistati'),('expenses','Spese'),('data','Dati e backup')]
        for number,(page,label) in enumerate(pages,1):
            row = tk.Frame(nav,bg=SURFACE)
            row.pack(fill='x')
            marker = ui.tag_marker(row,ACCENT,SURFACE_2)
            marker.pack(side='left',padx=(ui.px(28),ui.px(12)))
            button = tk.Button(row,text=label,anchor='w',font=ui.font(16),bg=SURFACE,fg=MUTED,activebackground=SURFACE_2,activeforeground=INK,
                               relief='flat',bd=0,padx=0,pady=ui.px(10),takefocus=True,highlightthickness=ui.px(2),highlightbackground=SURFACE,
                               highlightcolor=ACCENT,cursor='hand2',command=lambda p=page:self.show(p))
            button.pack(side='left',fill='x',expand=True)
            button.bind('<Return>',lambda _,p=page:self.show(p))
            for widget in (row,button,marker):
                widget.bind('<Enter>',lambda _,p=page:self.paint_nav(p,hover=True),add='+')
                widget.bind('<Leave>',lambda _,p=page:self.paint_nav(p),add='+')
            marker.bind('<Button-1>',lambda _,p=page:self.show(p))
            self.nav_buttons[page] = button
            self.nav_rows[page] = (row,marker)
            self.bind(f'<Control-Key-{number}>',lambda _,p=page:self.show(p))
        tk.Label(nav,text='Ctrl+1…7  pagine\nCtrl+N  nuovo capo\nCtrl+F  cerca\nF5  aggiorna',justify='left',font=ui.font(SMALL),fg=MUTED,bg=SURFACE).pack(side='bottom',anchor='w',padx=ui.px(28),pady=ui.px(22))
        self.body = ttk.Frame(self,padding=(ui.px(28),ui.px(24),ui.px(28),0))
        self.body.grid(row=0,column=1,sticky='nsew')
        self.page = 'dashboard'
        self.search = tk.StringVar()
        self.stock_filter = tk.StringVar(value='Tutti')
        self.sales_filter = tk.StringVar(value='Tutte')
        self.shipment_filter = tk.StringVar(value='Da spedire')
        self.goal = tk.IntVar(value=150)
        self.notice = tk.StringVar(value='Pronto. I dati vengono salvati automaticamente sul PC.')
        footer = tk.Frame(self,bg=SURFACE)
        footer.grid(row=1,column=1,sticky='ew')
        self.notice_label = tk.Label(footer,textvariable=self.notice,font=ui.font(SMALL),fg=MUTED,bg=SURFACE,anchor='w')
        self.notice_label.pack(side='left',padx=(ui.px(28),0),pady=ui.px(9))
        # The confirmation tag sits in the gutter, so the text never moves.
        self.notice_marker = ui.tag_marker(footer,POSITIVE,SURFACE,16,9)
        self.notice_marker.place(x=ui.px(6),rely=.5,anchor='w')
        self.notice_after = None
        self.calm_notice()
        self.bind('<Control-n>',lambda _:self.item_form())
        self.bind('<Control-f>',self.focus_search)
        self.bind('<F5>',lambda _:self.show(self.page))
        self.cloud = CloudController(self)
        tk.Label(nav, textvariable=self.cloud.status, justify='left', wraplength=ui.px(170),
                 font=ui.font(SMALL), fg=MUTED, bg=SURFACE).pack(side='bottom', padx=ui.px(24), pady=ui.px(10))
        self.show('dashboard')

    def paint_nav(self, page, hover=False):
        row, marker = self.nav_rows[page]
        active = page == self.page
        bg = SURFACE_2 if active or hover else SURFACE
        for widget in (row,marker):
            widget.configure(bg=bg)
        self.nav_buttons[page].configure(bg=bg,fg=INK if active or hover else MUTED,highlightbackground=bg,
                                         font=ui.font(16,'bold' if active else 'normal'))
        marker.itemconfigure('all',state='normal' if active else 'hidden')

    def focus_search(self, _=None):
        if self.page in ('stock','sales'):
            self.search_entry.focus_set()
            self.search_entry.selection_range(0,'end')
        else:
            self.show('stock')
            self.after(50,self.focus_search)
        return 'break'

    def style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        f = ui.font
        s.configure('.',font=f(BODY),background=BG,foreground=INK,focuscolor=ACCENT,troughcolor=BG,
                    bordercolor=BG,lightcolor=BG,darkcolor=BG,selectbackground=SURFACE_3,selectforeground=INK,insertcolor=INK)
        s.configure('TFrame',background=BG)
        s.configure('White.TFrame',background=SURFACE)
        s.configure('TLabel',background=BG,foreground=INK)
        s.configure('Title.TLabel',font=f(HEAD,'bold'))
        s.configure('Subtitle.TLabel',foreground=MUTED)
        s.configure('White.TLabel',background=SURFACE,foreground=INK)
        s.configure('WhiteMuted.TLabel',background=SURFACE,foreground=MUTED)
        s.configure('DialogTitle.TLabel',font=f(HEAD,'bold'),background=SURFACE)
        s.configure('FieldError.TLabel',background=SURFACE,foreground=NEGATIVE,font=f(SMALL))
        s.configure('TButton',padding=(ui.px(16),ui.px(8)),background=SURFACE_2,foreground=INK,borderwidth=1,bordercolor=SURFACE_2,
                    lightcolor=SURFACE_2,darkcolor=SURFACE_2,relief='flat')
        s.map('TButton',background=[('pressed',SURFACE_3),('active',SURFACE_3)],bordercolor=[('focus',ACCENT)])
        field = dict(fieldbackground=SURFACE_2,foreground=INK,bordercolor=SURFACE_2,lightcolor=SURFACE_2,darkcolor=SURFACE_2,
                     insertcolor=INK,padding=ui.px(8))
        s.configure('TEntry',**field)
        s.map('TEntry',bordercolor=[('focus',ACCENT)],lightcolor=[('focus',ACCENT)])
        s.configure('TCombobox',arrowcolor=INK,background=SURFACE_2,**field)
        s.map('TCombobox',bordercolor=[('focus',ACCENT)],fieldbackground=[('readonly',SURFACE_2)],foreground=[('readonly',INK)],
              background=[('active',SURFACE_3)],selectbackground=[('readonly',SURFACE_2)],selectforeground=[('readonly',INK)])
        invalid = dict(bordercolor=NEGATIVE,lightcolor=NEGATIVE,darkcolor=NEGATIVE)
        s.configure('Invalid.TEntry',**{**field,**invalid})
        s.map('Invalid.TEntry',bordercolor=[('focus',NEGATIVE)],lightcolor=[('focus',NEGATIVE)])
        s.configure('Invalid.TCombobox',arrowcolor=INK,background=SURFACE_2,**{**field,**invalid})
        s.map('Invalid.TCombobox',bordercolor=[('focus',NEGATIVE)],fieldbackground=[('readonly',SURFACE_2)],foreground=[('readonly',INK)],
              selectbackground=[('readonly',SURFACE_2)],selectforeground=[('readonly',INK)])
        self.option_add('*TCombobox*Listbox.background',SURFACE_2)
        self.option_add('*TCombobox*Listbox.foreground',INK)
        self.option_add('*TCombobox*Listbox.selectBackground',SURFACE_3)
        self.option_add('*TCombobox*Listbox.selectForeground',INK)
        self.option_add('*TCombobox*Listbox.font',f(BODY))
        s.configure('Treeview',background=BG,fieldbackground=BG,foreground=INK,rowheight=ui.px(40),borderwidth=0,font=f(BODY))
        s.configure('Stock.Treeview',rowheight=ui.px(48))
        s.configure('Treeview.Heading',font=f(BODY),background=SURFACE,foreground=MUTED,padding=(ui.px(10),ui.px(9)),relief='flat',borderwidth=0)
        s.map('Treeview.Heading',background=[('active',SURFACE_2)],foreground=[('active',INK)])
        s.map('Treeview',background=[('selected',SURFACE_3)],foreground=[('selected',INK)])
        s.configure('Vertical.TScrollbar',background=SURFACE_2,troughcolor=BG,arrowcolor=MUTED,bordercolor=BG,gripcount=0)
        s.configure('Horizontal.TScrollbar',background=SURFACE_2,troughcolor=BG,arrowcolor=MUTED,bordercolor=BG,gripcount=0)
        s.map('TScrollbar',background=[('active',SURFACE_3)])
        s.configure('TNotebook',background=SURFACE,borderwidth=0,tabmargins=0,bordercolor=SURFACE,lightcolor=SURFACE,darkcolor=SURFACE)
        s.configure('TNotebook.Tab',padding=(ui.px(16),ui.px(8)),background=SURFACE,foreground=MUTED,borderwidth=0,bordercolor=SURFACE,lightcolor=SURFACE,darkcolor=SURFACE)
        s.map('TNotebook.Tab',background=[('selected',SURFACE_2)],foreground=[('selected',INK)])

    def confirm(self, message):
        """Conferma un'azione riuscita: segno verde e testo pieno per 4 secondi, poi la riga torna neutra."""
        self.calm_notice()
        self.notice.set(message)
        self.notice_marker.itemconfigure('all',state='normal')
        self.notice_label.configure(fg=INK)
        self.notice_after = self.after(4000,self.calm_notice)

    def calm_notice(self):
        if self.notice_after:
            self.after_cancel(self.notice_after)
            self.notice_after = None
        self.notice_marker.itemconfigure('all',state='hidden')
        self.notice_label.configure(fg=MUTED)

    def close(self):
        if self.cloud.busy:
            messagebox.showinfo('Cloud', 'Attendi il completamento della sincronizzazione prima di chiudere.', parent=self)
            return
        self.calm_notice()
        try:
            self.store.auto_backup()
        except Exception:
            logging.exception('Backup automatico fallito')
        self.store.close()
        self.destroy()

    def report_callback_exception(self, exc, val, tb):
        logging.error('Errore interfaccia',exc_info=(exc,val,tb))
        messagebox.showerror('Errore',str(val),parent=self)

    def button(self, parent, text, command, primary=False):
        return make_button(parent, text, command, primary)

    def heading(self, title, subtitle, buttons=()):
        frame = ttk.Frame(self.body)
        frame.pack(fill='x',pady=(0,ui.px(22)),padx=(0,self.right_gutter))
        text = ttk.Frame(frame)
        text.pack(side='left',fill='x',expand=True)
        ttk.Label(text,text=title.lower(),style='Title.TLabel').pack(anchor='w')
        self.subtitle = ttk.Label(text,text=subtitle,style='Subtitle.TLabel',wraplength=ui.px(640))
        self.subtitle.pack(anchor='w',pady=(ui.px(6),0))
        for label,action,accent in buttons:
            make_button(frame,label,action,primary=accent).pack(side='right',padx=(ui.px(8),0),anchor='n')

    def show(self, page):
        if page != self.page and {page,self.page} & {'stock','sales'}:
            self.search.set('')
        self.page = page
        for child in self.body.winfo_children():
            child.destroy()
        for key in self.nav_buttons:
            self.paint_nav(key)
        bleed = page in ('dashboard','sales')
        self.right_gutter = ui.px(28) if bleed else 0
        self.body.configure(padding=(ui.px(28),ui.px(24),0 if bleed else ui.px(28),0))
        self.calm_notice()
        self.notice.set('Pronto. I dati vengono salvati automaticamente sul PC.')
        getattr(self, 'page_' + page)()
        for tree in self.trees():
            self.stripe(tree)

    def trees(self):
        found, stack = [], [self.body]
        while stack:
            widget = stack.pop()
            if isinstance(widget,ttk.Treeview):
                found.append(widget)
            stack.extend(widget.winfo_children())
        return found

    @staticmethod
    def stripe(tree):
        for i,ident in enumerate(tree.get_children()):
            tags = [t for t in tree.item(ident,'tags') if t != 'odd']
            tree.item(ident,tags=tags+(['odd'] if i % 2 else []))

    def changed(self, message):
        self.show(self.page)
        self.confirm(message)
        if self.cloud.client and not self.cloud.paused:
            self.after(500, lambda: self.cloud.sync(manual=False))

    @staticmethod
    def needs_selection(tree, one=(), many=()):
        """Azioni sulle righe: spente finché la selezione non le rende possibili (one = una riga, many = almeno una)."""
        def sync(_=None):
            count = len(tree.selection())
            for button in one:
                ui.set_enabled(button,count==1)
            for button in many:
                ui.set_enabled(button,count>=1)
        tree.bind('<<TreeviewSelect>>',sync,add='+')
        tree.sync = sync
        sync()

    @staticmethod
    def sync_actions(tree):
        getattr(tree,'sync',lambda:None)()

    def table(self, columns, parent=None, style='Treeview', tree_column=0):
        frame = ttk.Frame(parent or self.body)
        frame.pack(fill='both',expand=True,pady=(ui.px(12),ui.px(20)),padx=(0,self.right_gutter))
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        tree = ttk.Treeview(frame,columns=[c[0] for c in columns],show='tree headings' if tree_column else 'headings',
                            selectmode='browse',height=6,style=style)
        if tree_column:
            tree.column('#0',width=ui.px(tree_column),minwidth=ui.px(tree_column),stretch=False)
        tree.labels = {c[0]:c[1] for c in columns}
        for key,label,width,*anchor in columns:
            tree.heading(key,text=label,anchor=anchor[0] if anchor else 'w',command=lambda k=key:self.sort_tree(tree,k,False))
            tree.column(key,width=ui.px(width),minwidth=ui.px(56),stretch=key in ('title','description','name'),anchor=anchor[0] if anchor else 'w')
        tree.grid(row=0,column=0,sticky='nsew')
        bar = ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
        bar.grid(row=0,column=1,sticky='ns')
        hbar = ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
        hbar.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=bar.set,xscrollcommand=hbar.set)
        tree.tag_configure('odd',background=ROW_ALT)
        tree.tag_configure('negative',foreground=NEGATIVE)
        tree.tag_configure('positive',foreground=POSITIVE)
        tree.tag_configure('warning',foreground=WARNING)
        tree.tag_configure('muted',foreground=MUTED)
        tree.empty = ttk.Label(frame,style='Subtitle.TLabel',background=BG,justify='center')
        return tree

    @staticmethod
    def set_empty(tree, text):
        """Mostra un messaggio guida sopra la tabella vuota; text='' lo nasconde."""
        if text:
            tree.empty.configure(text=text)
            tree.empty.place(in_=tree,relx=0.5,rely=0.45,anchor='center')
        else:
            tree.empty.place_forget()

    @staticmethod
    def sort_tree(tree, key, descending):
        def parse(value):
            if len(value) == 10 and value[2] == '/' and value[5] == '/':
                return (0,float(value[6:]+value[3:5]+value[:2]))
            try:
                return (0,float(value.replace(' €','').replace('%','').replace('−','-').replace('.','').replace(',','.')))
            except ValueError:
                return (1,value.lower())
        for i,ident in enumerate(sorted(tree.get_children(),key=lambda ident:parse(tree.set(ident,key)),reverse=descending)):
            tree.move(ident,'',i)
        App.stripe(tree)
        for column,label in tree.labels.items():
            tree.heading(column,text=label+((' ↓' if descending else ' ↑') if column==key else ''))
        tree.heading(key,command=lambda:App.sort_tree(tree,key,not descending))

    def selected(self, tree):
        selection = tree.selection()
        if not selection:
            messagebox.showinfo('Seleziona una riga','Seleziona prima una riga della tabella.',parent=self)
            return None
        return int(selection[0])

    def page_dashboard(self):
        m, perf = self.store.metrics(), self.store.performance()
        month = date.today().strftime('%Y-%m')
        month_name = ('gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre')[date.today().month-1]
        self.heading('Panoramica',f'{month_name.capitalize()} {date.today().year} · vendite completate e denaro investito.',
                     [('Aggiungi capo',self.item_form,True),('Nuovo box',self.lot_form,False)])
        hero = ttk.Frame(self.body)
        hero.pack(fill='x')
        hero.columnconfigure(0,weight=1)
        figures = ttk.Frame(hero)
        figures.grid(row=0,column=0,sticky='nsew',padx=(0,ui.px(28)))
        stats = [(str(m['stock_count']),f"capi in stock · {money(m['stock_value'])} a costo",INK),
                 (str(m['sold_count']),f"vendite completate · {m['pending']} da chiudere",INK),
                 (short_money(m['revenue']),'incassi lordi',INK),
                 (short_money(m['cash']),'saldo di cassa',NEGATIVE if m['cash']<0 else INK),
                 (short_money(m['expenses']),'spese generali',INK),
                 (f"{perf['avg_days']} gg" if perf['avg_days'] is not None else '—','tempo medio di vendita',INK)]
        for i,(value,label,color) in enumerate(stats):
            figures.columnconfigure(i%3,weight=1,uniform='fig')
            cell = tk.Frame(figures,bg=BG)
            cell.grid(row=i//3,column=i%3,sticky='nw',pady=(ui.px(14),ui.px(10)))
            tk.Label(cell,text=value,font=ui.font(HEAD,'bold'),fg=color,bg=BG).pack(anchor='w')
            tk.Label(cell,text=label,font=ui.font(BODY),fg=MUTED,bg=BG,wraplength=ui.px(180),justify='left').pack(anchor='w',pady=(ui.px(4),0))
        tag = ui.BigTag(hero,money(m['profit']),'Utile netto','Ricavi − costo dei capi venduti − spese generali',bg=BG)
        tag.grid(row=0,column=1,sticky='nsew')
        hero.columnconfigure(1,minsize=ui.px(470))
        if m['profit'] < 0:
            tag.values = (money(m['profit']),'Utile netto · in perdita','Ricavi − costo dei capi venduti − spese generali')

        lower = ttk.Frame(self.body)
        lower.pack(fill='both',expand=True,pady=(ui.px(16),ui.px(20)),padx=(0,ui.px(28)))
        for col,weight in enumerate((105,120,95)):
            lower.columnconfigure(col,weight=weight,uniform='lower')
        lower.rowconfigure(0,weight=1)

        # The live thing: the visitor's own target, worked out from their real average margin.
        goal = tk.Frame(lower,bg=SURFACE,padx=ui.px(24),pady=ui.px(20))
        goal.grid(row=0,column=0,sticky='nsew',padx=(0,ui.px(16)))
        done = sum(r['profit'] for r in self.store.monthly() if r['month']==month)
        tk.Label(goal,text=f'Quanto vuoi guadagnare a {month_name}?',font=ui.font(LEAD,'bold'),fg=INK,bg=SURFACE,wraplength=ui.px(260),justify='left').pack(anchor='w')
        caption = tk.Label(goal,font=ui.font(BODY),fg=MUTED,bg=SURFACE)
        caption.pack(anchor='w',pady=(ui.px(12),ui.px(4)))
        ui.Slider(goal,self.goal,1000,10,SURFACE).pack(fill='x')
        result = tk.Frame(goal,bg=SURFACE)
        result.pack(side='bottom',anchor='w',fill='x')
        how = tk.Label(result,font=ui.font(SMALL),fg=MUTED,bg=SURFACE,wraplength=ui.px(270),justify='left')
        figure_row = tk.Frame(result,bg=SURFACE)
        figure_row.pack(anchor='w')
        need_label = tk.Label(figure_row,font=ui.font(DISPLAY,'bold'),fg=INK,bg=SURFACE)
        need_label.pack(side='left')
        unit = tk.Label(figure_row,font=ui.font(LEAD),fg=INK,bg=SURFACE)
        unit.pack(side='left',anchor='s',pady=(0,ui.px(18)),padx=(ui.px(10),0))
        how.pack(anchor='w',pady=(ui.px(4),0))
        def recompute(*_):
            target = self.goal.get()*100
            caption.configure(text=f'Obiettivo di utile: {short_money(target)}')
            missing = max(target-done,0)
            if not perf['avg_margin'] or perf['avg_margin'] <= 0:
                need_label.configure(text='—')
                unit.configure(text='')
                how.configure(text='Completa qualche vendita con margine positivo: il calcolo usa il tuo margine medio reale.')
                return
            need = -(-missing//perf['avg_margin'])
            need_label.configure(text=str(need))
            unit.configure(text='capo da vendere' if need==1 else 'capi da vendere')
            how.configure(text=(f'Mancano {short_money(missing)} ai {short_money(done)} già fatti questo mese, al tuo margine medio di {money(perf["avg_margin"])} a capo.'
                                if missing else f'Obiettivo raggiunto: questo mese hai già fatto {short_money(done)} di utile.'))
        trace = self.goal.trace_add('write',recompute)
        need_label.bind('<Destroy>',lambda _:self.goal.trace_remove('write',trace))
        recompute()

        chart_panel = tk.Frame(lower,bg=SURFACE,padx=ui.px(24),pady=ui.px(20))
        chart_panel.grid(row=0,column=1,sticky='nsew',padx=(0,ui.px(16)))
        tk.Label(chart_panel,text='Incassi e utile per mese',font=ui.font(LEAD,'bold'),fg=INK,bg=SURFACE).pack(anchor='w')
        legend = tk.Frame(chart_panel,bg=SURFACE)
        legend.pack(anchor='w',pady=(ui.px(4),0))
        for color,label in ((ACCENT,'Incassi'),(INK,'Utile')):
            tk.Frame(legend,bg=color,width=ui.px(10),height=ui.px(10)).pack(side='left',padx=(0,ui.px(6)))
            tk.Label(legend,text=label,font=ui.font(SMALL),fg=MUTED,bg=SURFACE).pack(side='left',padx=(0,ui.px(16)))
        chart = tk.Canvas(chart_panel,bg=SURFACE,highlightthickness=0,height=ui.px(200))
        chart.pack(fill='both',expand=True,pady=(ui.px(14),0))
        months = self.store.monthly()
        names = ('gen','feb','mar','apr','mag','giu','lug','ago','set','ott','nov','dic')
        def draw(_=None):
            chart.delete('all')
            w, h = chart.winfo_width(), chart.winfo_height()
            if not months:
                chart.create_text(0,ui.px(20),text='Registra la prima vendita completata\nper vedere l’andamento.',anchor='nw',fill=MUTED,font=ui.font(BODY))
                return
            base = h-ui.px(40)
            peak = max(max(r['revenue'] for r in months),max(r['profit'] for r in months),1)
            step = w/len(months)
            gap = ui.px(4)
            bar = (step-ui.px(14)-gap)/2
            for i,row in enumerate(months):
                x = step*i
                h1 = row['revenue']/peak*(base-ui.px(6))
                chart.create_rectangle(x,base-h1,x+bar,base,fill=ACCENT,outline='')
                if row['profit'] > 0:
                    chart.create_rectangle(x+bar+gap,base-row['profit']/peak*(base-ui.px(6)),x+bar*2+gap,base,fill=INK,outline='')
                else:
                    chart.create_rectangle(x+bar+gap,base-ui.px(3),x+bar*2+gap,base,fill=NEGATIVE,outline='')
                chart.create_text(x,base+ui.px(8),text=short_money(row['revenue']),anchor='nw',fill=INK,font=ui.font(SMALL,'bold'))
                chart.create_text(x,base+ui.px(24),text=f"{names[int(row['month'][5:])-1]} · {row['sold']}",anchor='nw',fill=MUTED,font=ui.font(SMALL))
        chart.bind('<Configure>',draw)

        todo = tk.Frame(lower,bg=SURFACE,padx=ui.px(24),pady=ui.px(20))
        todo.grid(row=0,column=2,sticky='nsew')
        tk.Label(todo,text='Da fare',font=ui.font(LEAD,'bold'),fg=INK,bg=SURFACE).pack(anchor='w',pady=(0,ui.px(6)))
        stale = self.store.stale_items()
        def plural(n, one, many):
            return f'{n} {one if n==1 else many}'
        actions = []
        if m['overdue']:
            actions.append((plural(m['overdue'],'spedizione scaduta','spedizioni scadute'),'shipments',NEGATIVE))
        if m['to_ship']:
            actions.append((plural(m['to_ship'],'capo da spedire','capi da spedire'),'shipments',ACCENT))
        if m['drafts']:
            actions.append((plural(m['drafts'],'capo da fotografare','capi da fotografare'),'stock',ACCENT))
        if stale:
            actions.append((plural(len(stale),'fermo da 30 giorni: sconta','fermi da 30 giorni: sconta'),'stock',WARNING))
        if m['pending']:
            actions.append((plural(m['pending'],'vendita da completare','vendite da completare'),'sales',ACCENT))
        if not actions:
            tk.Label(todo,text='Tutto in ordine: nessuna attività in sospeso.',font=ui.font(BODY),fg=MUTED,bg=SURFACE,wraplength=ui.px(220),justify='left').pack(anchor='w',pady=ui.px(8))
        for text,page,color in actions[:5]:
            row = tk.Frame(todo,bg=SURFACE,cursor='hand2')
            row.pack(fill='x',pady=ui.px(5))
            ui.tag_marker(row,color,SURFACE,16,9).pack(side='left',padx=(0,ui.px(12)))
            link = tk.Label(row,text=text,font=ui.font(BODY),fg=INK,bg=SURFACE,cursor='hand2',takefocus=True,
                            highlightthickness=ui.px(2),highlightbackground=SURFACE,highlightcolor=ACCENT)
            link.pack(side='left')
            for widget in (row,link):
                widget.bind('<Button-1>',lambda _,p=page:self.show(p))
            link.bind('<Return>',lambda _,p=page:self.show(p))
            link.bind('<Enter>',lambda _,l=link:l.configure(font=ui.font(BODY,'underline')))
            link.bind('<Leave>',lambda _,l=link:l.configure(font=ui.font(BODY)))
        if not m['stock_count'] and not m['sold_count']:
            make_button(todo,'Registra il primo box',self.lot_form,primary=True).pack(anchor='w',pady=(ui.px(12),0))
        resa = tk.Frame(todo,bg=SURFACE)
        resa.pack(side='bottom',fill='x')
        resa.columnconfigure(0,weight=1)
        figures = [('Margine medio',f"{money(perf['avg_margin'])}"+(f" · {perf['margin_pct']:.0f}%" if perf['margin_pct'] is not None else '') if perf['avg_days'] is not None else '—'),
                   ('ROI sul costo',f"{perf['roi_pct']:.0f}%" if perf['roi_pct'] is not None else '—'),
                   ('Venduti sul pubblicato',f"{perf['sell_through']}%" if perf['sell_through'] is not None else '—')]
        brands = self.store.top_brands(1)
        if brands:
            figures.append(('Marca migliore',f"{brands[0]['brand']} · {short_money(brands[0]['profit'])}"))
        for r,(label,value) in enumerate(figures):
            tk.Label(resa,text=label,font=ui.font(SMALL),fg=MUTED,bg=SURFACE).grid(row=r,column=0,sticky='w',pady=ui.px(2))
            tk.Label(resa,text=value,font=ui.font(BODY,'bold'),fg=INK,bg=SURFACE).grid(row=r,column=1,sticky='e',pady=ui.px(2))

    def page_stock(self):
        available = [r for r in self.store.items() if r['status'] not in ('Venduto','Archiviato')]
        self.heading('Stock',f"{len(available)} capi disponibili, {money(sum(r['cost'] for r in available))} a costo. Cerca con Ctrl+F.",
          [('Aggiungi capo',self.item_form,True),('Nuovo box',self.lot_form,False)])
        split = ttk.Frame(self.body)
        split.pack(fill='both',expand=True)
        aside = tk.Frame(split,bg=BG,width=ui.px(280))
        aside.pack(side='left',fill='y',padx=(0,ui.px(24)))
        aside.pack_propagate(False)
        self.stock_photo = tk.Canvas(aside,width=ui.px(280),height=ui.px(350),bg=BG,highlightthickness=0,cursor='hand2')
        self.stock_photo.pack(anchor='nw')
        self.stock_photo.bind('<Double-1>',lambda _:self.edit_selected())
        self.stock_title = tk.Label(aside,font=ui.font(LEAD,'bold'),fg=INK,bg=BG,anchor='w',justify='left',wraplength=ui.px(280))
        self.stock_title.pack(fill='x',pady=(ui.px(16),0))
        self.stock_meta = tk.Label(aside,font=ui.font(BODY),fg=MUTED,bg=BG,anchor='w',justify='left',wraplength=ui.px(280))
        self.stock_meta.pack(fill='x',pady=(ui.px(2),ui.px(12)))
        self.stock_facts = tk.Frame(aside,bg=BG)
        self.stock_facts.pack(fill='x')
        self.stock_facts.columnconfigure(0,weight=1)
        self.stock_preview = self.stock_photo
        right = ttk.Frame(split)
        right.pack(side='left',fill='both',expand=True)
        controls = ttk.Frame(right)
        controls.pack(fill='x')
        self.search_entry = entry = ttk.Entry(controls,textvariable=self.search,width=30)
        entry.pack(side='left',padx=(0,ui.px(8)))
        entry.bind('<KeyRelease>',lambda _:self.refresh_stock())
        ui.placeholder(entry,self.search,'Cerca nome, SKU, marca…')
        combo = ttk.Combobox(controls,textvariable=self.stock_filter,values=('Tutti',*STOCK_STATES,'Venduto'),state='readonly',width=15)
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>',lambda _:self.refresh_stock())
        delete = make_button(controls,'Elimina',self.delete_selected_item,danger=True)
        delete.pack(side='right')
        listing = make_button(controls,'Apri annuncio',self.open_listing)
        listing.pack(side='right',padx=ui.px(8))
        actions = ttk.Frame(right)
        actions.pack(fill='x',pady=(ui.px(10),0))
        duplicate = make_button(actions,'Duplica',self.duplicate_selected)
        duplicate.pack(side='left',padx=(0,ui.px(8)))
        publish = make_button(actions,'Segna in vendita',lambda:self.bulk_status('In vendita'))
        publish.pack(side='left',padx=(0,ui.px(8)))
        archive = make_button(actions,'Archivia',lambda:self.bulk_status('Archiviato'))
        archive.pack(side='left')
        sell = make_button(actions,'Registra vendita',self.sale_form,primary=True)
        sell.pack(side='right')
        edit = make_button(actions,'Modifica',self.edit_selected)
        edit.pack(side='right',padx=ui.px(8))
        self.stock_tree = self.table([('title','Capo',150),('brand','Marca',88),('size','Taglia',56),('cost','Costo',80,'e'),('asking','Prezzo',80,'e'),('age','Giorni',56,'e'),('status','Stato',108),('sku','SKU',110),('location','Posizione',90)],
                                     parent=right,style='Stock.Treeview',tree_column=58)
        self.stock_tree.configure(selectmode='extended')
        self.stock_tree.bind('<Double-1>',lambda _:self.edit_selected())
        self.stock_tree.bind('<Return>',lambda _:self.edit_selected())
        self.stock_tree.bind('<<TreeviewSelect>>',lambda _:self.stock_detail())
        self.needs_selection(self.stock_tree,one=(delete,listing,duplicate,sell,edit),many=(publish,archive))
        self.refresh_stock()
        children = self.stock_tree.get_children()
        if children and not self.stock_tree.selection():
            self.stock_tree.selection_set(children[0])
        self.stock_detail()

    def stock_detail(self):
        selection = self.stock_tree.selection()
        canvas, side, height = self.stock_photo, ui.px(280), ui.px(350)
        canvas.delete('all')
        self.stock_image_ref = None
        for child in self.stock_facts.winfo_children():
            child.destroy()
        def placeholder(text):
            ui.draw_tag(canvas,0,0,side,height,ui.px(46),SURFACE_2,BG)
            canvas.create_text(side/2+ui.px(20),height/2,text=text,fill=MUTED,font=ui.font(BODY),justify='center',width=side-ui.px(80))
        if len(selection) != 1:
            placeholder('Seleziona un capo' if not selection else f'{len(selection)} capi selezionati')
            self.stock_title.configure(text='')
            self.stock_meta.configure(text='Ctrl o Maiusc per selezionarne più di uno.' if not selection else 'Usa Segna in vendita o Archivia per tutti insieme.')
            return
        item = self.store.item(int(selection[0]))
        photos = self.store.photos(item['id'])
        if photos:
            with Image.open(io.BytesIO(self.store.photo_data(photos[0]['id']))) as image:
                image = image.convert('RGB')
                scale = max(side/image.width,height/image.height)
                image = image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
                left, top = (image.width-side)//2, (image.height-side*5//4)//2
                image = image.crop((left,max(top,0),left+side,max(top,0)+height))
                self.stock_image_ref = ImageTk.PhotoImage(ui.mask_tag(image,46/300,BG),master=self)
            canvas.create_image(0,0,image=self.stock_image_ref,anchor='nw')
        else:
            placeholder('Nessuna foto.\nDoppio clic per caricarla.')
        self.stock_title.configure(text=item['title'])
        self.stock_meta.configure(text=' · '.join(v for v in (item['sku'],item['size'] and 'taglia '+item['size'],item['location'],f'{len(photos)} foto') if v))
        facts = [('Costo',money(item['cost']),INK),('Prezzo annuncio',money(item['asking']) if item['asking'] else '—',INK)]
        if item['asking']:
            margin = item['asking']-item['cost']
            facts.append(('Margine atteso',('+' if margin>=0 else '')+money(margin),POSITIVE if margin>=0 else NEGATIVE))
        facts.append(('Pareggio sotto',money(item['cost']),MUTED))
        if item['status'] not in ('Venduto','Archiviato'):
            age = (date.today()-date.fromisoformat(item['bought_on'])).days
            facts.append(('In stock da',f'{age} giorni',WARNING if age>=30 and item['status']=='In vendita' else INK))
        for r,(label,value,color) in enumerate(facts):
            tk.Label(self.stock_facts,text=label,font=ui.font(BODY),fg=MUTED,bg=BG).grid(row=r,column=0,sticky='w',pady=ui.px(1))
            tk.Label(self.stock_facts,text=value,font=ui.font(BODY,'bold'),fg=color,bg=BG).grid(row=r,column=1,sticky='e',pady=ui.px(1))

    def thumb(self, item):
        key = (item['id'],item['photo_id'],item['status'])
        if key not in self.thumbs:
            data = self.store.photo_data(item['photo_id']) if item['photo_id'] else None
            try:
                self.thumbs[key] = ImageTk.PhotoImage(ui.list_thumb(data,item['status']),master=self)
            except (OSError,ValueError):
                self.thumbs[key] = ImageTk.PhotoImage(ui.list_thumb(None,item['status']),master=self)
        return self.thumbs[key]

    def refresh_stock(self):
        tree = self.stock_tree
        chosen = tree.selection()
        tree.delete(*tree.get_children())
        items = self.store.items(self.search.get(),self.stock_filter.get())
        for r in items:
            age = '' if r['age'] is None else str(max(r['age'],0))
            stale = r['status']=='In vendita' and r['age'] is not None and r['age']>=30
            tree.insert('','end',iid=r['id'],image=self.thumb(r),
                        values=(r['title'],r['brand'] or '—',r['size'] or '—',money(r['cost']),money(r['asking']) if r['asking'] else '—',age,r['status'],r['sku'],r['location']),
                        tags=('muted',) if r['status'] in ('Venduto','Archiviato') else ('warning',) if stale else ())
        tree.selection_set([c for c in chosen if tree.exists(c)])
        self.stripe(tree)
        self.sync_actions(tree)
        filtered = bool(self.search.get()) or self.stock_filter.get()!='Tutti'
        self.set_empty(tree,'' if items else ('Nessun capo corrisponde ai filtri.\nCancella la ricerca o scegli Tutti.' if filtered else 'Lo stock è vuoto.\nAggiungi capo (Ctrl+N), Nuovo box, oppure importa un CSV da Dati e backup.'))
        self.calm_notice()
        self.notice.set(f'{len(items)} capi visualizzati. Doppio clic o Invio per modificare; in giallo i capi in vendita da 30 giorni o più.')

    def duplicate_selected(self):
        ident = self.selected(self.stock_tree)
        if ident:
            self.store.duplicate_item(ident)
            self.changed('Capo duplicato: modifica nome, taglia e foto del nuovo capo.')

    def bulk_status(self, status):
        ids = [int(i) for i in self.stock_tree.selection()]
        if not ids:
            messagebox.showinfo('Seleziona una riga','Seleziona uno o più capi (Ctrl o Maiusc per selezionarne più di uno).',parent=self)
            return
        changed = self.store.set_items_status(ids,status)
        skipped = len(ids)-changed
        self.changed(f'{changed} capi impostati su «{status}».'+(f' {skipped} con vendita attiva non modificati: lo stato dipende dalla vendita.' if skipped else ''))

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
        Form(self,'Registra vendita',fields,save,item['title']+' · costo '+money(item['cost'])+f" · sotto {money(item['cost'])} vai in perdita. Inserisci solo le spese che paghi tu.",save_label='Registra vendita')

    def page_sales(self):
        self.heading('Vendite','Incassi e utile contano solo con lo stato Completata.',[('Esporta CSV',lambda:self.export('sales'),False)])
        summary = ttk.Frame(self.body)
        summary.pack(fill='x',pady=(0,ui.px(18)))
        summary.columnconfigure(3,weight=1)
        self.sales_stats = []
        for col in range(3):
            cell = tk.Frame(summary,bg=BG)
            cell.grid(row=0,column=col,sticky='w',padx=(0,ui.px(44)))
            value = tk.Label(cell,font=ui.font(HEAD,'bold'),fg=INK,bg=BG)
            value.pack(anchor='w')
            label = tk.Label(cell,font=ui.font(BODY),fg=MUTED,bg=BG)
            label.pack(anchor='w')
            self.sales_stats.append((value,label))
        self.sales_tag = ui.BigTag(summary,'','',notch=56,height=160,label_first=False)
        self.sales_tag.grid(row=0,column=4,sticky='e')
        self.sales_tag.configure(width=ui.px(400))
        controls = ttk.Frame(self.body)
        controls.pack(fill='x',padx=(0,ui.px(28)))
        self.search_entry = ttk.Entry(controls,textvariable=self.search,width=30)
        self.search_entry.pack(side='left',padx=(0,ui.px(8)))
        self.search_entry.bind('<KeyRelease>',lambda _:self.refresh_sales())
        ui.placeholder(self.search_entry,self.search,'Cerca capo, SKU, compratore…')
        combo = ttk.Combobox(controls,textvariable=self.sales_filter,state='readonly',width=14,values=('Tutte',*SALE_STATES,'Annullata'))
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>',lambda _:self.refresh_sales())
        edit = make_button(controls,'Modifica vendita',self.update_sale,primary=True)
        edit.pack(side='right')
        delete = make_button(controls,'Elimina',self.delete_selected_sale,danger=True)
        delete.pack(side='right',padx=ui.px(8))
        cancel = make_button(controls,'Annulla / reso',self.cancel_sale)
        cancel.pack(side='right')
        self.sales_tree = self.table([('title','Capo',220),('sold_on','Data',100),('price','Vendita',95,'e'),('cost','Costo',90,'e'),('charges','Spese',85,'e'),('profit','Margine',100,'e'),('pct','%',70,'e'),('status','Stato',110),('buyer','Compratore',120)])
        self.sales_tree.bind('<Double-1>',lambda _:self.update_sale())
        self.sales_tree.bind('<Return>',lambda _:self.update_sale())
        self.needs_selection(self.sales_tree,one=(edit,delete,cancel))
        self.refresh_sales()

    def refresh_sales(self):
        tree = self.sales_tree
        chosen = tree.selection()
        tree.delete(*tree.get_children())
        needle, state = self.search.get().strip().lower(), self.sales_filter.get()
        rows = [r for r in self.store.sales() if (state=='Tutte' or r['status']==state)
                and (not needle or needle in r['title'].lower() or needle in r['sku'].lower() or needle in r['buyer'].lower())]
        for r in rows:
            pct = f"{r['profit']*100/r['price']:.0f}%" if r['price'] else '—'
            tree.insert('','end',iid=r['id'],values=(r['title'],it_date(r['sold_on']),money(r['price']),money(r['cost_snapshot']),money(r['fees']+r['shipping']),money(r['profit']),pct,r['status'],r['buyer'] or '—'),
                        tags=('muted',) if r['status']=='Annullata' else ('negative',) if r['profit']<0 else ())
        tree.selection_set([c for c in chosen if tree.exists(c)])
        self.stripe(tree)
        self.sync_actions(tree)
        self.set_empty(tree,'' if rows else 'Nessuna vendita da mostrare.\nRegistrane una da Stock → Registra vendita.')
        done = [r for r in rows if r['status']=='Completata']
        revenue = sum(r['price'] for r in done)
        margin = sum(r['profit'] for r in done)
        values = [(str(len(done)),'completate'),(short_money(revenue),'incassato'),
                  (f"{margin*100/revenue:.0f}%" if revenue else '—','margine medio')]
        for (value_label,label),(value,text) in zip(self.sales_stats,values):
            value_label.configure(text=value)
            label.configure(text=text)
        self.sales_tag.values = (money(margin),'di margine sulle vendite visibili','')
        self.sales_tag.draw()
        self.calm_notice()
        self.notice.set(f'{len(rows)} vendite visualizzate. Doppio clic per modificare. Il margine esclude le spese generali.')

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
        edit = make_button(controls,'Modifica box',self.edit_selected_lot,primary=True)
        edit.pack(side='left')
        delete = make_button(controls,'Elimina box',self.delete_selected_lot,danger=True)
        delete.pack(side='left',padx=8)
        tree = self.lots_tree = self.table([('name','Box',230),('supplier','Fornitore',150),('bought_on','Acquistato',105),('quantity','Capi',65,'e'),('remaining','Rimasti',75,'e'),('total','Investito',110,'e'),('receipts','Incassi netti',110,'e'),('recovery','Recupero cassa',120,'e')])
        tree.bind('<Double-1>',lambda _:self.edit_selected_lot())
        lots = self.store.lots()
        for r in lots:
            delta = r['receipts']-r['total']
            tree.insert('','end',iid=r['id'],values=(r['name'],r['supplier'] or '—',it_date(r['bought_on']),r['quantity'],r['remaining'],money(r['total']),money(r['receipts']),money(delta)),tags=('negative',) if delta<0 else ())
        self.set_empty(tree,'' if lots else 'Nessun box registrato.\nUsa Nuovo box per ripartire il costo di un lotto su tutti i suoi capi.')
        self.needs_selection(tree,one=(edit,delete))
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
        edit = make_button(controls,'Modifica spesa',self.edit_selected_expense,primary=True)
        edit.pack(side='left')
        delete = make_button(controls,'Elimina spesa',self.delete_expense,danger=True)
        delete.pack(side='left',padx=8)
        self.expense_tree = self.table([('spent_on','Data',110),('description','Descrizione',500),('amount','Importo',120,'e')])
        expenses = self.store.rows('SELECT * FROM expenses ORDER BY spent_on DESC,id DESC')
        for r in expenses:
            self.expense_tree.insert('','end',iid=r['id'],values=(it_date(r['spent_on']),r['description'],money(r['amount'])))
        self.expense_tree.bind('<Double-1>',lambda _:self.edit_selected_expense())
        self.set_empty(self.expense_tree,'' if expenses else 'Nessuna spesa generale.\nAggiungi spesa per imballaggi, pulizia e altri costi.')
        self.needs_selection(self.expense_tree,one=(edit,delete))

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
        manage = make_button(controls,'Gestisci spedizione',self.shipment_form,primary=True)
        manage.pack(side='left',padx=10)
        tracking = make_button(controls,'Apri tracking',self.open_tracking)
        tracking.pack(side='right')
        copy = make_button(controls,'Copia codice',self.copy_tracking)
        copy.pack(side='right',padx=8)
        self.shipments_tree = self.table([('title','Capo',210),('location','Posizione',95),('carrier','Corriere',105),('tracking','Tracking',150),('ship_by','Scadenza',100),('status','Spedizione',110),('sale_status','Vendita',110)])
        self.shipments_tree.bind('<Double-1>',lambda _:self.shipment_form())
        self.needs_selection(self.shipments_tree,one=(manage,tracking,copy))
        self.refresh_shipments()
        ttk.Label(self.body,text='Rosso = scadenza superata. Consegnata non significa pagamento ricevuto: completa la vendita quando hai incassato.',style='Subtitle.TLabel',wraplength=880).pack(anchor='w',pady=10)

    def refresh_shipments(self):
        tree = self.shipments_tree
        tree.delete(*tree.get_children())
        rows = self.store.shipments(self.shipment_filter.get())
        for r in rows:
            tree.insert('','end',iid=r['sale_id'],values=(r['title'],r['location'],r['carrier'],r['tracking'],it_date(r['ship_by']),r['status'],r['sale_status']),tags=('negative',) if r['overdue'] else ())
        self.stripe(tree)
        self.sync_actions(tree)
        self.set_empty(tree,'' if rows else 'Nessuna spedizione da preparare.\nOgni vendita registrata crea qui la sua spedizione.' if self.shipment_filter.get()=='Da spedire'
                       else 'Nessuna spedizione con questo filtro.\nScegli Tutte per vederle tutte.')

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
            self.confirm('Codice tracking copiato.')

    def delete_expense(self):
        ident = self.selected(self.expense_tree)
        if ident and messagebox.askyesno('Elimina spesa','Vuoi eliminare questa spesa?',parent=self):
            self.store.delete_expense(ident)
            self.changed('Spesa eliminata.')

    def page_data(self):
        self.heading('I tuoi dati','Database locale e sincronizzazione facoltativa con il tuo account Supabase.')
        sections = [
          ('Backup completo','Salva un file con stock, foto, box, vendite, spedizioni e spese. Copialo anche su un altro dispositivo.', [('Crea backup',self.backup),('Ripristina backup',self.restore)]),
          ('CSV e importazione','Importa nuovi capi dal modello CSV. Gli SKU duplicati bloccano tutta l’importazione.\nGli export servono per consultazione; il backup SQLite conserva lo storico completo.', [('Importa capi CSV',self.import_csv),('Esporta stock',lambda:self.export('stock')),('Esporta vendite',lambda:self.export('sales')),('Salva modello CSV',self.csv_template)]),
          ('Backup automatici',f'VintDesk salva ogni giorno una copia alla chiusura e conserva le ultime {self.store.AUTO_BACKUP_KEEP} in:\n{self.store.path.parent/"backup-automatici"}\nCopiale anche su un altro dispositivo: sono sullo stesso PC dei dati.', [('Apri cartella dati',self.open_data)]),
          ('Sincronizzazione cloud',self.cloud.status.get(), [('Account cloud',self.cloud.configure),('Sincronizza',self.cloud.sync),('Scarica cloud',lambda:self.cloud.sync(pull=True)),('Disconnetti',self.cloud.disconnect)]),
          ('Come iniziare','1. Registra il box o un capo.\n2. Compila nome, marca, taglia e posizione nello stock.\n3. Quando pubblichi su Vinted, seleziona In vendita e incolla il link.\n4. Registra la vendita; segnala Completata quando ricevi il denaro.\n5. Controlla utile, saldo di cassa e recupero dei box.', []),
        ]
        grid = ttk.Frame(self.body)
        grid.pack(fill='both',expand=True,pady=(0,ui.px(20)))
        grid.columnconfigure((0,1),weight=1,uniform='data')
        for n,(title,description,actions) in enumerate(sections):
            card = ttk.Frame(grid,style='White.TFrame',padding=ui.px(24))
            card.grid(row=n//2,column=n%2,sticky='nsew',padx=(0,ui.px(16)) if n%2==0 else 0,pady=(0,ui.px(16)))
            ttk.Label(card,text=title,style='DialogTitle.TLabel',font=ui.font(LEAD,'bold')).pack(anchor='w')
            text = ttk.Label(card,text=description,style='WhiteMuted.TLabel')
            if title == 'Sincronizzazione cloud':
                text.configure(textvariable=self.cloud.status)
            text.pack(anchor='w',fill='x',pady=8)
            text.bind('<Configure>',lambda e,t=text:t.configure(wraplength=e.width-ui.px(4)))
            row = ttk.Frame(card,style='White.TFrame')
            row.pack(anchor='w',pady=(ui.px(4),0))
            for i,(label,callback) in enumerate(actions):
                make_button(row,label,callback,primary=i==0 and title=='Backup completo').grid(row=i//2,column=i%2,sticky='w',padx=(0,ui.px(8)),pady=(0,ui.px(8)))

    def csv_template(self):
        from core import CSV_FIELDS
        import csv
        path = filedialog.asksaveasfilename(parent=self,defaultextension='.csv',initialfile='modello-stock.csv',filetypes=[('CSV','*.csv')])
        if path:
            with open(path,'w',encoding='utf-8-sig',newline='') as f:
                writer = csv.writer(f,delimiter=';')
                writer.writerow(CSV_FIELDS)
                writer.writerow(['VD-ESEMPIO-1','Felpa vintage','Nike','L','Felpe','Buone','7.00','15.00','Scatola A',date.today().isoformat(),'','Riga di esempio: modifica o rimuovi prima di importare'])
            self.confirm('Modello CSV salvato.')

    def export(self, kind):
        path = filedialog.asksaveasfilename(parent=self,defaultextension='.csv',initialfile=f'{kind}-{date.today()}.csv',filetypes=[('CSV','*.csv')])
        if path:
            self.store.export_csv(path,kind)
            self.confirm('Esportazione salvata.')

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
            self.confirm('Backup completo salvato.')

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

def enable_dpi_awareness():
    """Su Windows evita l'interfaccia sfocata sugli schermi con scala 125-200%."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

def main():
    enable_dpi_awareness()
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
