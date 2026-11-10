# FarmaQuery

**FarmaQuery** è un prototipo di tesi per interrogare in linguaggio naturale una base di dati regolatori farmaceutici, confrontando **Text-to-SQL con auto-correzione** e **Table-Augmented Generation (TAG)**.

App: https://farmaquery.streamlit.app/  
Repository: https://github.com/MarcoFabozzi/farmaquery

> **Uso accademico.** I contenuti non attestano automaticamente la rimborsabilità vigente, non sono consigli medici e non sostituiscono le fonti ufficiali.

## Struttura del repository

| Percorso | Contenuto |
| --- | --- |
| `dashboard_regolatorio.py`, `chatbot_widget.py` | Interfaccia Streamlit e chatbot |
| `chatbot_farmaquery.py`, `tesi/*.py` | Componenti dei motori Text-to-SQL e TAG |
| `*.py` nella radice | Pipeline di acquisizione e qualità dei dati |
| `risultati/` | Database operativo, dati e report di aggiornamento |
| `risultati/tesi_statico_20261102.sqlite.gz` | Copia congelata per il benchmark, **da non modificare** |
| `tesi/` | Benchmark, Gold, protocolli, motori, test e materiali della tesi |
| `tesi/archivio/` | Report preliminari e istruzioni di esperimenti precedenti |
| `tests/`, `tesi/tests/` | Test automatici |
| `.github/workflows/` | GitHub Actions per aggiornamenti e verifiche |
| `docs/` | Documentazione tecnica e storico |

Il materiale **attivo** della sperimentazione è descritto in [tesi/README.md](tesi/README.md). I rapporti delle prove precedenti sono conservati separatamente per non confonderli con i risultati finali.

## Avvio dell'app

Da una installazione Python con le dipendenze di `requirements.txt`:

```bash
pip install -r requirements.txt
streamlit run dashboard_regolatorio.py
```

L'app utilizza `risultati/farmaci_automatico.sqlite` per la dashboard e lo snapshot sperimentale separato per i test della tesi. Le chiavi API devono rimanere in variabili di ambiente o segreti Streamlit, mai nel repository.

## Test

```bash
python -m unittest discover -s tests -t . -v
python -m unittest discover -s tesi/tests -t . -v
```

Per gli esperimenti TAG sono previste dipendenze dedicate in `tesi/requirements-esperimenti.txt`.

## Origine dei dati e riproducibilità

Fonti: **EMA, AIFA, Gazzetta Ufficiale e Regione Campania**. I workflow presenti in `.github/workflows/` gestiscono i tentativi di acquisizione e le verifiche; le date effettive e i risultati vanno letti dai relativi report, non dedotti dalla sola presenza dei workflow.

Il test comparativo finale usa un unico SQLite congelato del **2 novembre 2026**. SHA-256 del file decompresso:

```
f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742
```

Il codice dell'app, le pipeline, il database operativo, le Gold congelate e i workflow **non sono stati spostati** durante il riordino della documentazione.

## Ulteriori documenti

- [Panoramica dei test di tesi](tesi/README.md)
- [Guida chatbot](docs/CHATBOT.md)
- [Nota tecnica sui principi attivi AIFA](docs/FIX_AIFA_PRINCIPI.md)
- [README precedente, conservato per riferimento](docs/README_pre_riordino_20261110.md)
