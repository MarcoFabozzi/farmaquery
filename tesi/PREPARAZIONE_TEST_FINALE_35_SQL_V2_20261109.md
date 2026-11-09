# FarmaQuery — esecuzione del confronto finale a 35 domande (Text-to-SQL v2 vs TAG automatico)

**Stato 09/11/2026: preparazione completata e Gold definite sul solo SQLite congelato; benchmark v2 NON ancora eseguito.**

## File di riferimento

- Domande originali senza risposte Gold: `tesi/QUESTIONARIO_FINALE_35_20261109.csv` (35 ID, Q01–Q35, formulazioni immutate).
- **Gold ufficiali per questo confronto**: `tesi/GOLD_35_VALIDATO_SOLO_DATABASE_20261109.csv`, 35 domande valide **esclusivamente rispetto al contenuto estratto e alle tabelle dello SQLite statico**. Non comprendono informazioni ottenute da PDF esterni, web, linee guida aggiornate o altre fonti non presenti nel DB.
- Gold candidate precedenti, conservate esclusivamente per la storia delle revisioni: `tesi/FarmaQuery_Gold_35_20261109.json`; non usare questo JSON per valutare il nuovo benchmark.
- Scheda preparatoria precedente: `tesi/GOLD_35_REVISIONE_DA_VALIDARE_20261109.csv`, sostituita dal file ufficiale sopra.
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

## Regola Gold definitiva: database soltanto

La risposta Gold deve riflettere **esclusivamente ciò che è ricavabile dal file SQLite congelato**: tabelle `note`, `pagine` (compreso testo OCR imperfetto), `aifa_confezioni`, `ema_medicinali`, `gu_atti`, `gu_documenti`, `gu_segmenti` e le relazioni effettivamente incluse nello snapshot.

**Non aggiornare o correggere i testi OCR sulla base dei PDF originali o di fonti online.** Una discrepanza tra DB e realtà normativa non è un errore della Gold sperimentale: è un limite del corpus e va riportato nella tesi.

**Caso Q11/RYSTIGGO.** Nel DB il testo della pagina 3 della nota RYSTIGGO descrive la MGg ma non estrae l'elenco dei centri; il registro AIFA conservato nello stesso DB contiene un collegamento RYSTIGGO–Federico II. Poiché la domanda chiede i medicinali indicati **nelle note regionali**, questo collegamento AIFA non certifica il centro nella nota. Per il confronto si valutano le quattro associazioni regionali testualmente ricostruibili: VYVGART, SOLIRIS, ULTOMIRIS, ZILBRYSQ. La Gold registra l'incertezza come limite del corpus; non si inserisce un quinto medicinale attribuito per supposizione. Questa decisione è fissata **prima** di leggere gli output del nuovo test.

Audit offline:
- `tesi/tests/test_gold_35_snapshot_audit.py`: 59 citazioni regionali verificate, 0 pagine assenti, 0 omonimie non risolte.
- `tesi/tests/test_gold_35_database_contract.py`: controlla la lista AIFA XEMBIFY, la distinzione SIVEXTRO, i record EMA, l'atto GU 23A02767, la Gold negativa rispetto allo schema, Q11 e i 35 record validati.
- `tesi.valida_gold`: controlla esistenza delle 35 citazioni Gold e coerenza del file ufficiale.
- Validazione esclusivamente relativa allo snapshot, **non un giudizio di conformità normativa attuale**.

## Comandi per il benchmark finale (Gold già predisposte)

Decomprimere lo SQLite una sola volta, senza modificarlo:

```bash
python -c "import gzip,pathlib; p=pathlib.Path('risultati/tesi_statico_20261102.sqlite.gz'); pathlib.Path('risultati/tesi_statico_20261102.sqlite').write_bytes(gzip.decompress(p.read_bytes()))"
```

Usare il file Gold già preparato: `tesi/GOLD_35_VALIDATO_SOLO_DATABASE_20261109.csv`. Non rigenerarlo dopo aver visto gli output.

```bash
python -m tesi.valida_gold \
  --benchmark tesi/GOLD_35_VALIDATO_SOLO_DATABASE_20261109.csv \
  --db risultati/tesi_statico_20261102.sqlite

python -m tesi.esegui_holdout \
  --benchmark tesi/GOLD_35_VALIDATO_SOLO_DATABASE_20261109.csv \
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
- Le Gold sono già definite rispetto allo snapshot; senza le 70 nuove esecuzioni non esistono ancora metriche della v2 da pubblicare.
- Non modificare prompt, TAG o soglie dopo aver letto i risultati definitivi. Se necessario, creare una nuova versione sperimentale separata.
