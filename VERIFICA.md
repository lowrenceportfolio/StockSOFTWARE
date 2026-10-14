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

**Non ancora eseguito:** compilazione Windows, test dell'eseguibile compilato,
installazione e disinstallazione Windows. Questi controlli sono configurati
nel workflow GitHub incluso. La verifica Windows è documentata dai risultati
di GitHub Actions; i sorgenti non includono un installer già compilato.

Il display di prova Linux non offre i font Segoe UI di Windows, quindi la
resa tipografica effettiva su Windows deve essere controllata dopo la build.
