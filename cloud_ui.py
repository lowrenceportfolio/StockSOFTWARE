"""Tk adapter. All SQLite and widget work stays on the UI thread."""
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from cloud import (PROJECT_URL, Supabase, CloudError, Conflict, snapshot, digest, apply_snapshot,
                   read_baseline, save_baseline)


class CloudController:
    def __init__(self, app):
        self.app = app
        self.client = None
        self.busy = False
        self.paused = False
        self.results = queue.Queue()
        self.status = tk.StringVar(app, 'Cloud scollegato: dati salvati sul PC.')
        self.settings_path = app.store.path.with_suffix('.cloud.json')
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.settings = {}
        self.poll_id = self.app.after(100, self.poll)
        self.tick_id = self.app.after(30000, self.tick)
        self.app.bind('<Destroy>', self.stop, add='+')

    def stop(self, event):
        if event.widget is self.app:
            self.app.after_cancel(self.poll_id)
            self.app.after_cancel(self.tick_id)

    def run(self, work, done, manual=True):
        if self.busy:
            return
        self.busy = True
        def worker():
            try:
                self.results.put((done, work(), None, manual))
            except Exception as exc:
                self.results.put((done, None, exc, manual))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            done, result, error, manual = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            try:
                if error:
                    raise error
                done(result)
            except Exception as exc:
                self.paused = isinstance(exc, Conflict)
                text = str(exc) if isinstance(exc, (CloudError, OSError)) else 'Operazione cloud non riuscita. Dati locali conservati.'
                self.status.set(text)
                if manual:
                    messagebox.showerror('Sincronizzazione', text, parent=self.app)
        self.poll_id = self.app.after(100, self.poll)

    def tick(self):
        if self.client and not self.paused:
            self.sync(manual=False)
        self.tick_id = self.app.after(30000, self.tick)

    def has_form(self):
        return any(isinstance(child, tk.Toplevel) for child in self.app.winfo_children())

    def sync(self, manual=True, pull=False):
        if self.busy:
            if manual:
                self.status.set('Operazione cloud in corso…')
            return
        if not self.client:
            if manual:
                self.configure()
            return
        if self.has_form():
            return
        if pull and not messagebox.askyesno('Scarica cloud',
                'Sostituire i dati sul PC con la copia cloud? Le modifiche locali non inviate verranno rimosse. Prima viene creato un backup completo.', parent=self.app):
            return
        local = snapshot(self.app.store)
        before = digest(local)
        baseline = read_baseline(self.app.store, self.client.account)
        client = self.client
        self.paused = False
        self.status.set('Sincronizzazione in corso…')
        def done(result):
            action, revision, payload = result
            if action == 'pull':
                if self.has_form() or digest(snapshot(self.app.store)) != before:
                    self.status.set('Nuove modifiche locali: download rinviato alla prossima sincronizzazione.')
                    return
                apply_snapshot(self.app.store, payload)
                self.app.thumbs.clear()
                self.app.show(self.app.page)
            save_baseline(self.app.store, client.account, revision, digest(payload))
            self.status.set(('Sincronizzato' if digest(snapshot(self.app.store)) == digest(payload) else 'Modifiche locali in attesa') + ' · ' + self.settings.get('email', '') + ' · controllo ogni 30 secondi')
        self.run(lambda: client.exchange(local, baseline, pull=pull), done, manual)

    def disconnect(self):
        if self.busy:
            self.status.set('Attendi il completamento della sincronizzazione.')
            return
        self.client = None
        self.status.set('Cloud scollegato: dati salvati sul PC.')

    def configure(self):
        if self.busy:
            return
        dialog = tk.Toplevel(self.app)
        dialog.title('Account Supabase')
        dialog.transient(self.app)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Usa lo stesso account su PC e telefono.').grid(row=0, column=0, columnspan=2, pady=(0, 14))
        values = {}
        for n, (key, label, value) in enumerate((
                ('url', 'Project URL', self.settings.get('url', PROJECT_URL)),
                ('email', 'Email', self.settings.get('email', '')),
                ('password', 'Password', '')), 1):
            ttk.Label(frame, text=label).grid(row=n, column=0, sticky='w', padx=(0, 16), pady=8)
            values[key] = tk.StringVar(value=value)
            ttk.Entry(frame, textvariable=values[key], width=48,
                      show='*' if key == 'password' else '').grid(row=n, column=1, pady=8)
        ttk.Label(frame, text='Password e sessione restano solo in memoria. Accedi a ogni avvio.').grid(row=4, column=0, columnspan=2, pady=12)
        def connect(signup=False):
            if self.busy:
                return
            try:
                client = Supabase(values['url'].get())
                email, password = values['email'].get().strip(), values['password'].get()
                if not email or not password:
                    raise CloudError('Inserisci email e password.')
            except CloudError as exc:
                messagebox.showerror('Account', str(exc), parent=dialog)
                return
            def done(_):
                if signup:
                    messagebox.showinfo('Account creato', 'Controlla la tua email per confermare l’account, poi premi Accedi.', parent=dialog if dialog.winfo_exists() else self.app)
                    self.status.set('Account creato: conferma email e accedi.')
                    return
                self.settings = {'url': client.url, 'email': email}
                self.settings_path.write_text(json.dumps(self.settings), encoding='utf-8')
                self.client = client
                self.paused = False
                if dialog.winfo_exists():
                    dialog.destroy()
                self.sync()
            self.status.set('Connessione a Supabase…')
            self.run(lambda: client.signup(email, password) if signup else client.login(email, password), done)
        ttk.Button(frame, text='Crea account', command=lambda: connect(True)).grid(row=5, column=0, pady=8)
        ttk.Button(frame, text='Accedi e sincronizza', command=connect).grid(row=5, column=1, sticky='e', pady=8)
