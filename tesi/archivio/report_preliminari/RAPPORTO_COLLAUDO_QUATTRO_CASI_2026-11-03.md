# Rapporto di collaudo reale — FarmaQuery, 3 novembre 2026

**Workflow:** https://github.com/MarcoFabozzi/farmaquery/actions/runs/41637885874  
**Sorgenti congelate:** 2 novembre 2026  
**SHA-256 SQLite:** `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`  
**Modello:** `gemini/gemini-3.5-flash-lite` (identico per TAG e Text-to-SQL).  
**Metodo SQL:** una sola SELECT, nessuna correzione o seconda query.  
**Metodo TAG:** LOTUS e recupero semantico sulle stesse tabelle.  

## Precollaudo documentale

Preflight **OK** su SQLite reale: integrità, 380 note, 942 pagine, 28 relazioni nota–centro, cinque centri PLUVICTO, due rimandi CAMZYOS, 60 atti e 516 segmenti GU, compreso `23A02767`. Le 28 relazioni non sono tutti i centri del corpus; 23 di esse risultano controllate sul testo estratto, non visualmente su tutti i PDF.

## Otto interrogazioni reali

| Caso | Text-to-SQL | TAG | Fonte di riferimento |
| --- | --- | --- | --- |
| S1 PLUVICTO: centri e requisiti | Nessuna riga SQL | 5 centri, Lutezio-177 e registro AIFA | PLUVICTO.pdf p. 1–2 |
| S2 Neuromuscolari presso Federico II | Nessuna riga SQL | 7 medicinali nominati: ULTOMIRIS, SOLIRIS, EVRYSDI, AGAMREE, ZILBRYSQ, VYVGART, DUVYZAT | PDF regionali con pagine; elenco dichiarato non esaustivo |
| S3 CAMZYOS: rimandi | Nessuna riga SQL | Nota 0624981/2025 annullata e sostituita (p. 1), nota PG/2024/0503681 solo richiamata (p. 2) | CAMZYOS Prot.N.0641382-2025.pdf |
| S4 PLUVICTO: date di attivazione dei centri | Nessuna riga SQL | Assenza di documentazione nella nota | PLUVICTO.pdf p. 1–2 |

**Risultato tecnico:** 8 interrogazioni effettuate sul modello, **0 errori tecnici**.

| Caso | Tempo SQL | Tempo TAG |
| --- | ---: | ---: |
| S1 | 3,538 s | 16,621 s |
| S2 | 0,919 s | 14,449 s |
| S3 | 1,113 s | 5,443 s |
| S4 | 0,945 s | 2,703 s |
| **Totale** | **6,515 s** | **39,216 s** |

Costi API indicativi riportati: SQL 0,0025369 USD; TAG 0,0157442 USD (somma delle quattro domande per metodo).

## Valutazione scientifica

- Queste quattro domande sono un **set di sviluppo/dimostrazione**, dopo la correzione del prompt sulla miastenia; non costituiscono test indipendente sufficiente a dimostrare superiorità statistica.
- **TAG** produce risposte utilizzabili e citazioni alle pagine per S1–S4; per S2 la completezza di tutte le possibili associazioni non è dimostrata.
- **Text-to-SQL** genera query SQLite eseguibili ma ottiene zero righe nei quattro casi. La stringa di assenza si riferisce alle **righe della query**, non all'assenza della fonte dal database.
- Lo snapshot è storico. L'abilitazione del centro oggi non è attestata automaticamente dalle note archiviate e dal file AIFA.
- La prova è backend GitHub Actions con API Gemini reale; **non rappresenta un test visivo dell'interfaccia Streamlit Cloud**.
- Il benchmark dei 30 quesiti deve essere eseguito separatamente con gold verificati e lo stesso snapshot/versione dei motori, senza riciclare gli otto esperimenti di sviluppo.

Il codice di collaudo è `tesi/collaudo_finale.py`; risposte grezze, costi e fonti sono nell'artifact `farmaquery-collaudo-finale` della run linkata sopra.
