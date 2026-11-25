# Risultati finali della tesi — riferimento documentale (25 novembre 2026)

Questo documento allinea la **documentazione del repository** alla versione della tesi *Interrogazione in linguaggio naturale di basi di dati: dal Text-to-SQL alla Table-Augmented Generation*. Non sostituisce gli archivi delle esecuzioni e non costituisce una nuova esecuzione dei due motori.

## Benchmark regolatorio: 35 domande

Snapshot congelato il **02/11/2026**: 2.357 medicinali EMA, 160.314 confezioni AIFA, 380 note regionali, 942 pagine di note e 60 atti GU. SHA-256 del file SQLite decompresso: `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`.

| Indicatore | Text-to-SQL | TAG |
| --- | ---: | ---: |
| Risposte completamente corrette (35) | 10/35 (28,6%) | 20/35 (57,1%) |
| Risposte corrette sulle 30 rispondibili | 5/30 (16,7%) | 15/30 (50,0%) |
| Astensioni corrette | 5/5 | 5/5 |
| Fallimenti SQL | 1 | 4 |
| Tempo medio | 3,33 s | 8,55 s |
| Tempo mediano | 2,33 s | 6,43 s |
| Chiamate LLM medie | 1,51 | 3,09 |
| TP / FP / FN su 16 domande a elenco | 22 / 0 / 51 | 47 / 1 / 26 |
| Precision micro | 100,0% | 97,9% |
| Recall micro | 30,1% | 64,4% |
| F1 micro | 46,3% | 77,7% |
| F1 macro | 23,2% | 61,6% |
| Almeno un dato utile nelle 30 rispondibili | 7/30 | 21/30 |

Valutazione documentale manuale dell'autore; le metriche sugli elenchi derivano da TP/FP/FN assegnati alle singole risposte. I costi registrati sono parziali perché alcuni fallimenti non presentano importi disponibili. Questi risultati non devono essere presentati come valutazione indipendente.

### Gold Q11 e Q14 — riferimento definitivo della tesi

I file `GOLD_35_VALIDATO_SOLO_DATABASE_20261109.csv`, `FarmaQuery_Gold_35_20261109.json` e gli altri materiali datati 09/11 **sono preservati come documenti storici**, per non perdere la traccia del criterio originario.

- **Q11 — miastenia gravis generalizzata, AOU Federico II**: la Gold definitiva considera **5 medicinali**: VYVGART, SOLIRIS, ULTOMIRIS, ZILBRYSQ e RYSTIGGO. Il collegamento RYSTIGGO–Federico II è stato confermato dalla tabella a **pagina 3 del PDF originale**; non risultava completamente conservato nella trasformazione testuale/OCR dello snapshot. Nelle valutazioni definitive: Text-to-SQL TP/FP/FN = **0/0/5**, TAG = **2/0/3**.
- **Q14 — fasce d'età per terapie della fibrosi cistica, AOU Federico II**: la Gold definitiva contiene **8 associazioni terapia–fascia d'età**, incluse quelle relative a KAFTRIO e KALYDECO **6–<12 anni** nella nota 2022. Nelle valutazioni definitive: Text-to-SQL **0/0/8**, TAG **4/0/4**.
  
Queste integrazioni non hanno modificato domande, risposte prodotte dai motori né snapshot. I riferimenti ai documenti originali e l'effetto delle revisioni sono descritti nel §3.10 della tesi e nell'Appendice A.

## Test separato: 15 interrogazioni SQL

Il test Q36–Q50 non viene sommato al benchmark delle 35 domande.

| Indicatore | Text-to-SQL | TAG |
| --- | ---: | ---: |
| Risposte completamente corrette | 7/15 (46,7%) | 11/15 (73,3%) |
| SQL concluse con successo | 15/15 | 14/15 |
| Execution accuracy riportata nella tesi | 8/15 (53,3%) | 11/15 (73,3%) |
| Tempo medio | 4,88 s | 5,81 s |
| Tempo mediano | 2,77 s | 3,85 s |
| TP / FP / FN (14 elenchi) | 62 / 17 / 56 | 88 / 14 / 30 |
| F1 micro (14 elenchi) | 62,9% | 80,0% |

L'*execution accuracy* è il risultato **dichiarato nella tesi**, non ricalcolato da questo aggiornamento della documentazione. Per la **Q40**, la query Gold originale include `COUNT(*) AS numero_confezioni` per documentare la graduatoria, mentre il giudizio della risposta TAG come completamente corretta riguarda i **cinque medicinali** richiesti nella domanda. Nessun file delle esecuzioni né risultato di benchmark viene qui modificato.

## Disponibilità dei materiali e riproducibilità

- Snapshot: `risultati/tesi_statico_20261102.sqlite.gz`, immutabile per il benchmark.
- Questionario e Gold del 09/11: presenti in `tesi/`, **versioni storiche** per Q11/Q14.
- La presente sintesi documenta i **criteri e i risultati definitivi della tesi**; non va scambiata per una raccolta di risposte integrali o tracce originali.
- Le risposte complete, le SQL finali, i tentativi, i token e i costi vanno pubblicati solo dopo averne verificato l'effettiva disponibilità e aver rimosso eventuali credenziali o dati sensibili.

Le fonti regolatorie acquisite sono fotografie temporali dei dati e non sostituiscono la consultazione degli atti ufficiali aggiornati.
