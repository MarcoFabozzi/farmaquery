# FarmaQuery — rapporto del collaudo reale dei due motori

**Data:** 3 novembre 2026.  
**Fonte primaria dell'esperimento:** [GitHub Actions, run 41637885874](https://github.com/MarcoFabozzi/farmaquery/actions/runs/41637885874), artifact `farmaquery-collaudo-finale`, file `collaudo_live.json`.  
**Modello effettivamente utilizzato:** `gemini/gemini-3.5-flash-lite`.  
**SHA-256 dello SQLite:** `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`.  
**Snapshot delle fonti originali:** `bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53` (2 novembre 2026).

Entrambi i metodi hanno utilizzato **lo stesso SQLite** (quello pubblicato in `risultati/tesi_statico_20261102.sqlite.gz` e attestato da `risultati/tesi_statico_20261102.json`). La nuova baseline Text-to-SQL esegue **una sola SELECT** e non usa retry; TAG mantiene l'operatore semantico LOTUS e il recupero delle pagine.

## Risultati grezzi

L'esecuzione ha prodotto **otto interrogazioni, quattro per metodo, zero errori tecnici**. Gli stati qui riportati sono quelli dei motori, **non punteggi di accuratezza gold**.

| Caso | Text-to-SQL standard | TAG | Tempi SQL / TAG |
| --- | --- | --- | --- |
| S1 — PLUVICTO, centri e requisiti | `NESSUNA_EVIDENZA`, 0 citazioni | `OK`: cinque centri, requisito di Lutezio-177, compilazione registro AIFA; fonti PLUVICTO p. 1–2 | 3,538 s / 16,621 s |
| S2 — categoria neuromuscolare, Federico II | `NESSUNA_EVIDENZA`, 0 citazioni | `OK`: elenca ULTOMIRIS, SOLIRIS, EVRYSDI, AGAMREE, ZILBRYSQ, VYVGART, DUVYZAT; 19 citazioni; avviso di non esaustività | 0,919 s / 14,449 s |
| S3 — due rapporti CAMZYOS | `NESSUNA_EVIDENZA`, 0 citazioni | `OK`: annulla/sostituisce 0624981/2025 (p. 1); richiama PG/2024/0503681 (p. 2); tre citazioni | 1,113 s / 5,443 s |
| S4 — date di attivazione dei centri PLUVICTO | `NESSUNA_EVIDENZA`, 0 citazioni | `OK`: dichiara che le date non sono documentate nella nota consultata; p. 1–2 | 0,945 s / 2,703 s |

## Qualità delle risposte: revisione documentale

- **S1:** la risposta TAG coincide con i cinque centri riportati nella pagina 2 del PDF PLUVICTO e riporta il requisito relativo alla detenzione del Lutezio-177 e alla piattaforma AIFA.
- **S2:** l'elenco TAG è interessante e include categorie cliniche non codificate in una colonna; **le sette corrispondenze non sono tutte qui dichiarate gold**, quindi non attribuire un punteggio di completezza o esaustività prima del controllo puntuale dei documenti.
- **S3:** le distinzioni tra sostituzione e semplice richiamo corrispondono alle frasi citate nello snapshot CAMZYOS, alle rispettive pagine.
- **S4:** l'astensione TAG è opportunamente circoscritta alla **nota PLUVICTO**; non equivale a dimostrazione dell'assenza di attivazione reale o in altri documenti.

## Interpretazione per la tesi

Nelle **quattro domande di dimostrazione**, TAG ha fornito una risposta documentata con fonti in tutti i casi, mentre la baseline Text-to-SQL non ha restituito righe. **Non sono quattro prove indipendenti di superiorità statistica**: sono esempi selezionati dal set di sviluppo, e le risposte S2 richiedono ulteriori verifiche manuali.

Il risultato mostra una differenza di **copertura documentale nel prototipo implementato**, non prova che un Text-to-SQL standard non possa in generale leggere testo da SQLite. La baseline ha fallito in tre casi con filtri SQL letterali o su metadati candidati non uniformi; per scelta metodologica non vengono generate seconde query riparative.

TAG ha impiegato più tempo per tutti e quattro i casi, coerentemente con il recupero semantico e i maggiori token elaborati. Questo deve essere descritto come costo del metodo, non nascosto.

## Distinzione fra collaudo e benchmark definitivo

Questo rapporto riguarda **il collaudo reale della demo**, non il benchmark dei 30 quesiti con gold indipendenti. L'esperimento conclusivo richiede convalida delle risposte gold mancanti, congelamento del set di domande, verifica delle citazioni e misura delle metriche su più esempi e, preferibilmente, ripetizioni.

**Non sono stati precompilati output del chatbot e non è stata alterata la baseline per favorire TAG.**
