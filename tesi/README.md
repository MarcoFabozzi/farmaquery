# Materiali di tesi — FarmaQuery

**Titolo:** Interrogazione in linguaggio naturale di basi di dati: dal Text-to-SQL alla Table-Augmented Generation.

## Esperimento finale (riferimento principale)

Il confronto consiste in **35 domande** sul medesimo database SQLite congelato, distribuite in cinque categorie: 10 semplici, 10 a categoria implicita, 5 multifonte, 5 non documentabili e 5 multiple.

| Materiale | File |
| --- | --- |
| Questionario finale | [QUESTIONARIO_FINALE_35_20261109.csv](QUESTIONARIO_FINALE_35_20261109.csv) |
| Gold validate sullo snapshot | [GOLD_35_VALIDATO_SOLO_DATABASE_20261109.csv](GOLD_35_VALIDATO_SOLO_DATABASE_20261109.csv) |
| Gold strutturate | [FarmaQuery_Gold_35_20261109.json](FarmaQuery_Gold_35_20261109.json) |
| Manifesto di congelamento | [MANIFESTO_CONGELAMENTO_PRETEST_35_SOLO_DATABASE_20261109.json](MANIFESTO_CONGELAMENTO_PRETEST_35_SOLO_DATABASE_20261109.json) |
| Protocollo di test | [PROTOCOLLO_PILOTA_20_E_FINALE_35_20261109.md](PROTOCOLLO_PILOTA_20_E_FINALE_35_20261109.md) |
| Runner / valutazione | [esegui_holdout.py](esegui_holdout.py), [valuta_confronto.py](valuta_confronto.py) |
| Motori | [sql_autocorrezione.py](sql_autocorrezione.py), [tag_automatico.py](tag_automatico.py) |

**Snapshot:** `risultati/tesi_statico_20261102.sqlite.gz` (non sostituire o rigenerare per l'esperimento registrato). SHA-256 del file SQLite decompresso:

```
f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742
```

Modello registrato nelle esportazioni: `gemini/gemini-3.5-flash-lite`. Le specifiche di prompt, versione, parametri e modello vanno ricavate anche dal codice/JSON dell'esecuzione effettiva, non da esempi storici.

**Criterio di valutazione concordato:** conservare tutte le esecuzioni grezze, escludere dal punteggio soltanto i tentativi interrotti da errori esterni (ad es. Gemini 503); contare i fallimenti SQL generati dal motore e le astensioni non giustificate. Per ciascuna domanda valutare risposta **integrale**, completezza, documento e pagina; distinguere precisione/richiamo per le domande a elenco e astensioni corrette. Non scegliere retroattivamente il tentativo migliore fra esecuzioni valide.

Il benchmark 35 domande è stato eseguito sui due motori. Gli score manuali e le metriche devono essere verificati prima della pubblicazione in tesi; eventuali JSON esportati fuori dal repository vanno archiviati senza sovrascrivere le Gold.

## Struttura della tesi e indicazioni del relatore

- Introduzione: percorso EMA → AIFA → Regione e contesto operativo del farmacista ospedaliero
- Capitolo 1: stato dell'arte, Text-to-SQL, RAG/TAG, benchmark e lavori correlati
- Capitolo 2: metodologia e architettura **generale** di FarmaQuery, scelte e motivazioni
- Capitolo 3: tecnologie e ambiente sperimentale, benchmark, metriche e confronto quantitativo/qualitativo
- Conclusioni, bibliografia, appendici (questionario, Gold e risposte integrali)

Il relatore ha richiesto di collocare i dettagli di implementazione, librerie, modello e parametri **nel Capitolo 3**, non nel Capitolo 2, e di citare pagina e documento a supporto delle affermazioni.

## Materiali precedenti

I [report preliminari](archivio/report_preliminari/) e i [protocolli storici](archivio/protocolli_precedenti/) descrivono fasi diverse (anche benchmark da 36 o 40 quesiti). **Non sostituiscono** il protocollo e le Gold delle 35 domande. Il codice dei motori, i test e i dati storici necessari alla riproducibilità restano nei loro percorsi originali.
