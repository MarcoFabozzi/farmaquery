# Audit di aderenza alle indicazioni del relatore — FarmaQuery
_Data: 3 novembre 2026; codice esaminato: main commit 9b1cf22cfd564da45bee192417b7e74705868427._

## Obiettivo concordato
Progettare e valutare un assistente conversazionale per dati regolatori farmaceutici. **TAG con LOTUS è il metodo proposto**; **Text-to-SQL è la baseline**, non un motore da far fallire artificiosamente. Database SQLite, fonti EMA/AIFA/GU/Campania e interfaccia Streamlit sono l'infrastruttura. I risultati devono essere ancorati alle fonti e alle date, senza indicazioni cliniche e senza inferire la situazione vigente da una nota storica.

Il criterio NON è "CSV/JSON contro PDF": entrambi interrogano lo stesso SQLite, comprensivo del testo estratto dai PDF. Text-to-SQL traduce il quesito in SELECT su colonne, poi sintetizza le righe; TAG combina recupero tabellare, filtro semantico LOTUS sul testo e generazione della risposta.

## Verifica del codice già presente

| Obiettivo | Evidenza concreta | Stato |
| --- | --- | --- |
| Unico database dei due metodi | `chatbot_farmaquery.py:answer_question`; `tesi/esegui_benchmark.py:execute` | Realizzato |
| SELECT e lettura sicure | `tesi/pilota_tag_vs_sql.py:validate_sql`, `read_only` | Realizzato; verificare i log degli errori |
| TAG usa davvero LOTUS | `tesi/tag_budget.py:sem_filter_controlled` invoca `DataFrame.sem_filter`; `tesi/pilota_tag_vs_sql.py:tag` lo integra | Realizzato |
| Recupero note per pagina e rimandi | `tesi/recupero_regionale.py`, `tesi/contesto_integrale.py` | Realizzato, completezza da misurare |
| Stesso LLM e snapshot per run riproducibile | `tesi/esegui_benchmark.py` passa lo stesso `model` e verifica SHA SQLite | Realizzato nel runner, NON ancora attestato per le prove manuali Streamlit |
| Benchmark con gold documentali | `tesi/benchmark_regolatorio_30.csv` | **8 VALIDATO, 22 DA_VERIFICARE** |

### Distinzione metodologica fondamentale

Il TAG attuale usa un **recupero preliminare deterministico** delle righe/pagine, poi un `sem_filter` LOTUS su gruppi di evidenze e infine un LLM per la sintesi. Nelle domande su note nominate, `contesto_integrale` può però sostituire il contesto selezionato da LOTUS con il testo completo della nota. La chiamata LOTUS viene eseguita, ma in quei casi il suo filtro **non determina necessariamente l'insieme di pagine consegnate alla risposta**. La maggiore copertura documentale non va dunque attribuita automaticamente all'operatore semantico.

La letteratura TAG descrive sintesi della query, esecuzione su database e generazione grounded; LOTUS estende la manipolazione dei DataFrame con operatori semantici come filter/join. In tesi descrivere l'implementazione effettiva, non attribuire a FarmaQuery `sem_join` o `sem_map` se non sono invocati nel percorso misurato.

Riferimenti scientifici: Biswal et al., «Text2SQL is Not Enough: Unifying AI and Databases with TAG», https://arxiv.org/abs/2408.14717 ; Patel et al., «Semantic Operators: A Declarative Model for Rich, AI-based Analytics Over Text Data», https://arxiv.org/abs/2407.11418 .

## Copertura del benchmark attuale

`tesi/benchmark_regolatorio_30.csv`: 4 CONTROLLO (tutti da verificare), 7 INTERPRETAZIONE (5 validati), 7 MULTIFONTE (nessuno validato), 5 TEMPORALE (1 validato), 4 NEGATIVA (nessuna validata), 3 RIMANDI (2 validati). Totale: **30 domande, 8 gold validati, 22 da verificare**.

Le otto domande Q05, Q06, Q07, Q08, Q09, Q21, Q28, Q29 sono state ripetutamente usate per analizzare e correggere TAG/Text-to-SQL. Sono **set di sviluppo e studio pilota**, non test indipendente: i loro punteggi non vanno presentati come misura conclusiva della generalizzazione. La ripetizione post-correzione di Q05 PLUVICTO è un controllo di regressione, non nuova osservazione indipendente.

Manca una **categoria implicita esplicita nel benchmark principale**. Due domande candidate sono già presenti in `tesi/pilota_4_tipi_relatori_da_validare.csv`:
- P03: farmaci per patologie neuromuscolari presso AOU Federico II, con indicazione/patologia/centro/pagina;
- P04: medicinali per malattie autoimmuni presso Cardarelli, con note e pagine.

**P03/P04 sono DA_VERIFICARE**: non promuoverle a test o gold senza controllo integrale delle note e senza verificare la relazione tra categoria, specifica indicazione e centro. Possono servire come casi pilota per affinare la rubrica; un nuovo insieme indipendente deve essere definito e congelato prima di ulteriori modifiche ai motori.

## Procedura da seguire per la valutazione finale

1. **Bloccare la versione del software** tramite SHA di commit e il database tramite hash SHA-256 del manifesto. App online e snapshot sperimentale restano distinti.
2. **Congelare la rubrica**: per ogni quesito annotare risposta gold completa, PDF e pagine, data a cui si riferisce il provvedimento, elementi obbligatori, eventuale assenza documentale verificata e causa di esclusione.
3. **Validare innanzitutto Q01–Q04 (CONTROLLI EMA/AIFA)**: occorrono casi semplici in cui Text-to-SQL possa dimostrare i suoi punti di forza. Non inventare una classificazione C ufficiale per esclusione da A/H.
4. **Validare casi semantici e di rimando**, inclusi P03/P04 o un loro nuovo insieme predefinito: senza questi manca il quesito caratteristico esplicitamente suggerito dal relatore.
5. **Validare i casi negativi Q24–Q27**: ricerca nell'intero corpus e per sinonimi; «non documentato nel corpus» non equivale a «il farmaco non è prescrivibile».
6. **Separare sviluppo e valutazione indipendente**, evitando correzioni basate sulle risposte del test definitivo. Se si modifica il motore dopo aver visto gli esiti, creare una nuova versione e riportarlo.
7. **Eseguire entrambi con stessa domanda, stesso SQLite e stesso modello** usando `tesi/esegui_benchmark.py`. Conservare risposte originali, query SQL, pagine, stati, durata, token, costo se misurabile; errori e interruzioni separati.
8. **Valutare manualmente** completezza rigorosa, copertura dei singoli elementi gold, correttezza delle citazioni, astensione corretta, tempo e fallimenti tecnici. Riportare i risultati per tipo di domanda oltre all'aggregato.
9. **Dichiarare i limiti di comparabilità**: TAG legge talvolta pagine integrali fino al proprio budget, Text-to-SQL può ricevere testi troncati; il numero di chiamate LLM e la quantità di evidenza non sono identici. Gli effetti osservati sono della coppia di *implementazioni*, non necessariamente una proprietà intrinseca della tecnica.
10. **Analizzare qualitativamente gli errori**: identificazione nota, SQL generato, selezione delle pagine, comprensione semantica, completezza, citazioni e rapporti temporali. Un controllo aggiuntivo sul ruolo effettivo di LOTUS può verificare quanto del vantaggio derivi da `sem_filter` anziché dal solo recupero integrale.

## Decisione operativa

**Non integrare nuove correzioni dei motori adesso.** La baseline originale è archiviata; il commit sopra indicato è la versione post-correzione da documentare. La prima attività scientifica è verificare i gold di CONTROLLO e CATEGORIA_IMPLICITA, non chiedere allo stesso modello di rifare all'infinito le domande già usate per ottimizzarlo.

Capitoli da avviare in parallelo: (1) percorso EMA/Commissione europea/AIFA/Regione e problema informativo; (2) Text-to-SQL, RAG come contesto di letteratura, TAG e LOTUS; (3) sistema FarmaQuery; (4) metodologia e risultati riproducibili.
