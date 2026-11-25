# Script di manutenzione

I comandi in questa cartella sono avviati dalla **radice del repository** come moduli Python, per mantenere risolvibili gli import dei moduli condivisi e i percorsi di `risultati/`.

```bash
python -m scripts.aggiorna_indipendente --source ema
python -m scripts.aggiorna_indipendente --source aifa
python -m scripts.aggiorna_indipendente --source gazzetta
python -m scripts.aggiorna_automatico --limite 30 --senza-pilota
python -m scripts.regione_campania_etl
python -m scripts.diagnostica_classi
python -m scripts.verifica_ricerca_aifa
```

Gli altri strumenti di controllo sono `scripts.verifica_snapshot`, `scripts.verifica_qualita_base_dati`, `scripts.valida_evidenze_gazzetta`, `scripts.prepara_revisione_collegamenti` e `scripts.qualita_database`.

**Non avviare questi file con** `python scripts/nome.py`: usare `python -m scripts.nome` dalla radice, come nei workflow aggiornati.

I moduli condivisi, richiamati da Streamlit e/o dai processi di aggiornamento (`pipeline.py`, `aifa_componenti.py`, `catalogo_ema.py`, `gazzetta_incrementale.py`, ecc.), restano temporaneamente nella radice per conservare la compatibilità degli import e dei test. Lo snapshot congelato della tesi non viene modificato.
