# FarmaQuery — consolidamento del pilota a 20 domande (06/11/2026)

> **Stato: sviluppo/pilota, non benchmark indipendente.** Le domande D01–D05, R01–R05, S01–S05 e A01–A05 sono gia' state usate per correggere i motori. Non riutilizzarle per la valutazione finale di generalizzazione.

## Provenienza e perimetro

- Snapshot: `risultati/tesi_statico_20261102.sqlite.gz`, SHA-256 del SQLite decompresso: `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`.
- Fonti dell'audit storico conservate nei pacchetti `FarmaQuery_Confronto_Percentuale_20261104.zip` e `FarmaQuery_Pacchetto_Completo_Pilota_04_11_2026.zip`: `valutazione_graduale_20_domande.csv`, `rubrica_elementi_20.csv`, `metriche_per_categoria_graduali.csv`, `Confronto_20_punteggi_e_gold.csv`. I pacchetti originali sono stati analizzati il 6 novembre.
- 85 elementi della rubrica, alcuni con credito frazionario.
- Livello di verifica del gold storico: 9 domande su record SQLite; 6 su testo estratto da pagine, PDF visuali ancora da controllare; 5 assenze documentali da confermare. Output completi storici non archiviati sistematicamente: alcuni giudizi fanno riferimento a sintesi non verbatim.

## Risultati del confronto storico (Text-to-SQL vs TAG manuale)

| Categoria | N | T2S completamente corrette | TAG completamente corrette | T2S copertura media | TAG copertura media | T2S s | TAG s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dirette | 5 | 5 | 5 | 100,0% | 100,0% | 1,60 | 2,26 |
| Relazionali | 5 | 4 | 4 | 80,0% | 88,6% | 2,02 | 4,58 |
| Semantiche | 5 | 0 | 3 | 20,5% | 93,8% | 1,66 | 8,38 |
| Assenza documentale | 5 | 3 | 2 | 60,0% | 70,0% | 1,30 | 1,88 |
| **Totale** | **20** | **12 (60%)** | **14 (70%)** | **65,1%** | **88,1%** | **1,65** | **4,28** |

- Invii LLM medi: 1,70 T2S e 3,90 TAG manuale.
- F1 *medio per domanda, secondo rubrica graduale*: 66,5% T2S e 91,8% TAG manuale. **Non** e' F1 micro convenzionale di tutti gli elenchi.
- I tempi TAG manuale includono in alcuni casi risposte selezionate dopo retry; confrontabilita' temporale limitata.

## TAG automatico — ultime prove di sviluppo (revisioni r2–r7)

| Categoria | N risposte ottenute | Tempo medio | Invii LLM medi |
|---|---:|---:|---:|
| Dirette | 5 | 3,22 s | 3 |
| Relazionali | 5 | 3,68 s | 3 |
| Semantiche | 5 | 6,00 s | 3 |
| Assenza documentale | 5 | 3,04 s | 3 |
| **Totale** | **20** | **3,99 s** | **3** |

Questi valori si riferiscono alle **ultime prove disponibili**, non a un'unica esecuzione su codice congelato. Non assegnare un'accuratezza del 100%: tutte le 20 risposte sono state prodotte, ma non ancora giudicate formalmente su un gold approvato. R03 presenta una formulazione impropria della data di riferimento A/H come scadenza; R04 menziona sette note ma ne descrive in modo completo soltanto quattro. Le risposte semantiche richiedono verifica PDF.

## Prossimo esperimento indipendente

Esiste gia' un archivio di 20 quesiti nuovi `Nuovo_test_indipendente_20_CANDIDATI_NON_ESEGUITI.csv` nel pacchetto del 4 novembre: quattro quesiti in ciascuna delle cinque categorie (diretta, relazionale, semantica, categoria implicita, assenza documentale). **Tutti sono candidati non validati e non devono essere usati per ulteriore tuning.**

La pipeline formale e' composta da:

1. Validazione manuale preventiva del gold e del PDF, con `tesi.valida_gold`.
2. Congelamento di snapshot, hash, commit, modello, prompt, dipendenze e rubriche.
3. `tesi.esegui_holdout`: una sola esecuzione per domanda e ciascuno dei tre motori; alternanza ciclica dell'ordine; conserva SQL, evidenze, tempi, invii LLM, errori e revisione.
4. Annotazione manuale successiva del CSV, senza leggere al modello le risposte gold.
5. `tesi.valuta_confronto`: report per categoria dei tre motori. Campi non valutati rimangono NULL.

**Non sono state avviate esecuzioni Gemini sui nuovi quesiti durante questo consolidamento.**
