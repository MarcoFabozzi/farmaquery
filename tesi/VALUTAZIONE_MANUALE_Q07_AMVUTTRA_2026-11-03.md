# Confronto manuale esplorativo — Q07 AMVUTTRA (3 novembre 2026)

**Domanda identica per TAG e Text-to-SQL:** «Quali sono esattamente i sei centri per ATTR-CM e i tre per polineuropatia ereditaria indicati nella nota AMVUTTRA 2026?»

**Gold validato:** `tesi/benchmark_regolatorio_8_validati.csv`, Q07. Nota `note-regionali-2026 22.09.2026/07-2026/AMVUTTRA Prot.N.0634617-2026.pdf`: pagina 2, tabella ATTR-CM (6 strutture); pagina 3, tabella neuropatia ereditaria (3 strutture). La terza tabella della nota non costituisce un terzo elenco per queste indicazioni.

## TAG — output dell'app riportato nella conversazione
> I sei centri per ATTR-CM (Tab. 1, pag. 2) e i tre per polineuropatia ereditaria (Tab. 2, pag. 3) indicati nella nota AMVUTTRA 2026 sono:
>
> **Centri ATTR-CM (Tab. 1, pag. 2):**
> 1. AO Ospedali dei Colli, Napoli – U.O. Malattie Genetiche e Rare Cardiovascolari
> 2. AOU S. Giovanni di Dio e Ruggi D'Aragona, Salerno – Clinica Cardiologica
> 3. AORN S. Giuseppe Moscati, Avellino – U.O.C. Cardiologia e UTIC
> 4. AO Sant'Anna e San Sebastiano, Caserta – Cardiologia Clinica a direzione universitaria
> 5. AOU Federico II, Napoli – U.O.C. Cardiologia, Emodinamica e UTIC e U.O.C. Geriatria e Fibrosi Cistica dell'Adulto
> 6. AORN A. Cardarelli, Napoli – U.O.C. Medicina 2
>
> **Centri per polineuropatia ereditaria (Tab. 2, pag. 3):**
> 1. AOU Federico II, Napoli – DAI Testa Collo - U.O.C. di Neurologia e Centro per epilessia
> 2. AOU Università degli Studi della Campania "Luigi Vanvitelli", Napoli – UOC di Neurologia II
> 3. AO Ospedali dei Colli, Napoli – U.O. Malattie Genetiche e Rare Cardiovascolari
>
> Fonti: *AMVUTTRA Prot.N.0634617-2026.pdf*, pag. 2 e pag. 3.

**Metadati visualizzati:** 5,3 s; TAG verifica-integrale-v2; fonte integrale; AIC 0; revisione LLM no; selezione raggruppata; evidenze 14; elementi LOTUS 3; chiamate LLM stimate (non misurate) 4.

**Valutazione sulla rubrica del gold:** 6/6 centri ATTR-CM + 3/3 neuropatia ereditaria, senza mescolare le due indicazioni. Le pagine sono pertinenti. Valutazione provvisoria della risposta **1/1** e citazioni **1/1**, limitatamente ai nomi/associazioni richiesti e al riferimento già validato. Le denominazioni dettagliate delle singole U.O. non sono state tutte riesaminate nel PDF originario durante questa conversazione.

## Text-to-SQL — output dell'app riportato nella conversazione
> Informazione non documentata nello snapshot consultato.

**SQL generato (una query):**
```sql
SELECT c.nota_id, c.numero_pagina, c.menzione, c.stato, n.nome_file, n.archivio_url
FROM centri_candidati AS c
JOIN note AS n ON c.nota_id = n.id
WHERE n.nome_file LIKE '%AMVUTTRA%'
  AND n.anno = 2026
  AND (c.menzione LIKE '%ATTR-CM%' OR c.menzione LIKE '%polineuropatia%'
       OR c.stato LIKE '%ATTR-CM%' OR c.stato LIKE '%polineuropatia%')
LIMIT 80
```

**Metadati visualizzati:** 1,1 s; query generate 1; modello e snapshot dichiarati invariati dall'interfaccia.

**Valutazione sulla rubrica:** 0/6 + 0/3 centri; nessuna citazione documentale. Valutazione della risposta **0/1** e citazioni **0/1**, poiché dichiara «non documentata» un'informazione presente nelle tabelle originali.

**Diagnosi SQL (ipotesi da distinguere dal fatto):** lo snapshot sperimentale definisce `centri_candidati(menzione,stato)`, riempiendo i due campi dal database regionale `testo_candidato` e `stato`. La query restringe il recupero di righe candidate chiedendo che nei campi `menzione` o `stato` compaiano le parole ATTR-CM/polineuropatia. Questo criterio non garantisce il recupero di una tabella la cui patologia è nell'intestazione di pagina o in un altro paragrafo, mentre la menzione del centro è su riga differente. Inoltre manca la `JOIN pagine` per consultare l'intero testo delle tabelle. Le condizioni possono quindi produrre un falso negativo di recupero. Per identificare la condizione effettivamente escludente occorre una SELECT diagnostica e confrontare i conteggi, che **non è stata eseguita**. Non attribuire con certezza la causa al filtro senza tale verifica.

## Comparazione
| Indicatore | TAG | Text-to-SQL |
|---|---:|---:|
| ATTR-CM, strutture | 6/6 | 0/6 |
| Neuropatia ereditaria, strutture | 3/3 | 0/3 |
| Associazione delle due indicazioni | Corretta | Non prodotta |
| Documento e pagine | p. 2–3 | Nessuna citazione |
| Completezza binaria secondo gold | 1/1 | 0/1 |
| Tempo visualizzato | 5,3 s | 1,1 s |

**Limiti sperimentali:** risultati raccolti manualmente dalla chat Streamlit e non dal runner sullo snapshot immutabile del 2 novembre 2026. Mancano l'hash preciso dello SQLite realmente interrogato dall'app, il commit del codice e la versione completa di modello/prompt. Non includere direttamente nel report quantitativo sullo snapshot congelato. I motori e il gold non sono stati modificati sulla base di questa prova.

**Passo successivo:** Q08 KEYTRUDA, prima TAG poi Text-to-SQL.
