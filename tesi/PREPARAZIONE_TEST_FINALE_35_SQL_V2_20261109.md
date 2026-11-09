# FarmaQuery — esecuzione del confronto finale a 35 domande (Text-to-SQL v2 vs TAG automatico)

**Stato 09/11/2026: infrastruttura preparata, benchmark NON ancora avviato con v2.**

## File di riferimento

- Domande originali senza risposte Gold: `tesi/QUESTIONARIO_FINALE_35_20261109.csv` (35 ID, Q01–Q35, formulazioni immutate).
- Gold candidate originali: `tesi/FarmaQuery_Gold_35_20261109.json` (34 indicati come `VERIFICATO_SU_SNAPSHOT`, Q11 `DA_CONFERMARE_ESAUSTIVITA`).
- Scheda di approvazione: `tesi/GOLD_35_REVISIONE_DA_VALIDARE_20261109.csv`, dove i campi operativi `risposta_gold`, `fonti_gold`, `note_revisore` ed `elementi_gold` sono lasciati vuoti per impedire una promozione automatica. Le proposte e le verifiche storiche restano nelle colonne separate.
- Protocollo originario del pilota 20 e finale 35: `tesi/PROTOCOLLO_PILOTA_20_E_FINALE_35_20261109.md`.

Il test finale usa **solo due motori**: `Text-to-SQL con auto-correzione` (versione `autocorrezione-v2-controlli`) e `TAG automatico` (r24). Il runner `tesi/esegui_holdout.py` e il valutatore `tesi/valuta_confronto.py` ora distinguono il confronto finale dal test storico a tre metodi.

## Snapshot e provenienza

- SQLite statico: `risultati/tesi_statico_20261102.sqlite.gz`.
- SHA-256 del file SQLite **decompresso**: `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`.
- Manifesto: `risultati/tesi_statico_20261102.json`.
- Versione Text-to-SQL v2 introdotta dal commit `b430c78a049153927270fef603ca45b1072d6d9f`.
- Runner e valutatore finale a due motori introdotti dal commit `c9a4c27e5850f69af36a85e6812387401c2e852a`.
- Test riferiti al DB statico introdotti dal commit `132cae5472ffea0580d41eb1c91440051a2b3f7c`.

**Prima dell'esecuzione annotare il commit corrente completo di main**, il modello LLM *effettivamente in uso*, i parametri, la data e le eventuali quote API.

## Blocchi di validazione ancora necessari

1. Q11: controllare **visivamente** `note 2025 - 18.12.2025/RYSTIGGO.pdf`, pagina **3**, per verificare se AOU Federico II compare nell'elenco dei centri e se l'elenco dei quattro medicinali precedentemente attestati è esaustivo. Il testo della tabella non è leggibile nella copia OCR. Non aggiungere RYSTIGGO né dichiarare 4/4 corretto senza questa verifica.
2. Per le altre Gold, conservare il controllo precedente sullo snapshot e **formalizzare la revisione** delle pagine OCR/documenti originali, dei riferimenti EMA/AIFA e delle informazioni negative. Una fonte esterna non contenuta nello SQLite non va spacciata come citazione dello snapshot.
3. Compilare i campi `risposta_gold`, `fonti_gold` (formati previsti da `valida_gold.py`), `note_revisore`, `elementi_gold` e impostare `stato_validazione=VALIDATO` soltanto dopo la verifica.

## Comandi una volta approvate tutte le Gold

Decomprimere lo SQLite una sola volta, senza modificarlo:

```bash
python -c "import gzip,pathlib; p=pathlib.Path('risultati/tesi_statico_20261102.sqlite.gz'); pathlib.Path('risultati/tesi_statico_20261102.sqlite').write_bytes(gzip.decompress(p.read_bytes()))"
```

Salvare le Gold approvate in una **copia distinta**: `tesi/GOLD_35_VALIDATO_20261109.csv`.

```bash
python -m tesi.valida_gold \
  --benchmark tesi/GOLD_35_VALIDATO_20261109.csv \
  --db risultati/tesi_statico_20261102.sqlite

python -m tesi.esegui_holdout \
  --benchmark tesi/GOLD_35_VALIDATO_20261109.csv \
  --db risultati/tesi_statico_20261102.sqlite \
  --manifest risultati/tesi_statico_20261102.json \
  --model MODELLO_EFFETTIVO \
  --commit COMMIT_GIT_CONGELATO \
  --out risultati/holdout_35_sql_v2_tag_auto_grezzi.csv
```

Il runner produce **70 record** (35×2) senza inviare le Gold agli LLM e rifiuta sovrascritture. Conservare risposte integrali, SQL originali/finali, tempi, token, costo se noto, chiamate effettive, diagnostica ed errori. Annotare manualmente gli esiti e solo successivamente eseguire `tesi.valuta_confronto`.

## Interpretazione della prova

- Le 20 domande pilota della v1 e le loro risposte non vengono modificate.
- Le 35 domande erano già state usate nel confronto storico. Il confronto con v2 è una **nuova valutazione sulle stesse domande**, non un holdout completamente indipendente.
- Senza revisione Gold e risposte originali nuove non ci sono nuove percentuali da pubblicare.
- Non modificare prompt, TAG o soglie dopo aver letto i risultati definitivi. Se necessario, creare una nuova versione sperimentale separata.
