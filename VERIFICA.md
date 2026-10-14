# Verifica della prima versione

Verifica eseguita il 14 ottobre 2026 sui sorgenti Python.

- 14 test del database e della contabilità: superati.
- 2 test dell'interfaccia Tkinter con display virtuale: superati.
- Percorso verificato: nuovo box → modifica capo → vendita in attesa →
  completamento → utile e saldo aggiornati.
- Tutte le sei schermate aperte con database di prova.
- Ispezionate le schermate a risoluzione 1366×768; modulo capo scorrevole,
  pulsanti di salvataggio visibili e sezioni backup/CSV organizzate in schede.
- Compilazione dei moduli Python: superata.

## Verifica Windows

Esecuzione riuscita: [GitHub Actions 38546127005](https://github.com/lowrenceportfolio/StockSOFTWARE/actions/runs/38546127005).
Commit sorgenti: `ab43cd159d00aeb740e366c09af86b3761083cf0`.

- Tutti i 16 test: superati su Windows.
- Build PyInstaller e compilazione Inno Setup: superate.
- Apertura di tutte le schermate dai sorgenti: superata.
- Avvio e apertura di tutte le schermate dell'eseguibile: superati.
- Installazione senza interazione: superata.
- Avvio dell'app installata: superato.
- Disinstallazione: superata.

Installer: `VintDesk-Setup-1.0.0.exe`, disponibile negli artefatti della build GitHub Actions.
I test sono automatici sul runner Windows; non sostituiscono una prova sul PC
dell'utilizzatore. I dati reali non sono stati usati nei test.
