# Valutazione manuale Q09 RYBREVANT (03/11/2026)

Domanda: «Quali condizioni EGFR e quali associazioni terapeutiche distingue la nota regionale RYBREVANT 0403588/2026 per le nuove indicazioni?»

Gold di riferimento: `tesi/benchmark_regolatorio_8_validati.csv`, Q09, PDF `RYBREVANT Prot.N.0403588-2026.pdf`, pagine 1–3. Tre nuove indicazioni: ex20 prima linea con carboplatino/pemetrexed solo EV; del19/L858R dopo EGFR-TKI con carboplatino/pemetrexed solo EV; del19/L858R prima linea con lazertinib EV/SC.

## TAG, risposta riportata
- EMA (Indicazioni terapeutiche): carcinoma polmonare non a piccole cellule avanzato con mutazioni da inserzione nell'esone 20 dell'EGFR, prima linea (PDF p.2).
- Associazioni terapeutiche: carboplatino e pemetrexed (PDF p.2).

5,4 secondi; TAG verifica-integrale-v2; fonte non_recuperato; revisione LLM no; evidenze 12; LOTUS 3; chiamate LLM stimate 4.

Valutazione provvisoria: 1/3 indicazioni (prima combinazione senza esplicitare EV), 0/1 completezza rigorosa. Le altre due indicazioni del19/L858R sono omesse. La disponibilità del testo integrale è segnalata come non_recuperato, pur in presenza di riferimento al PDF.

## Text-to-SQL, risposta riportata
«Informazione non documentata nello snapshot consultato.»

Query generata:
```sql
SELECT p.nota_id, p.numero_pagina, p.testo, n.farmaco_candidato, n.indicazione_candidata, n.archivio_url FROM pagine AS p JOIN note AS n ON p.nota_id = n.id WHERE n.protocollo_candidato LIKE '%0403588/2026%' AND (p.testo LIKE '%EGFR%' OR p.testo LIKE '%associazione%') LIMIT 80
```
1,0 secondi; una query generata; interfaccia dichiara modello e snapshot invariati.

Valutazione: 0/3 indicazioni, 0/1 completezza rigorosa, nessuna citazione utile. Possibile filtro restrittivo su `protocollo_candidato` oppure sui termini per pagina. Il formato di `protocollo_candidato` **non è noto**, dunque non attribuire il fallimento alla differenza slash/trattino del nome file. Servono conteggi diagnostici sullo SQLite realmente interrogato.

Comparazione: TAG 5,4 s, Text-to-SQL 1,0 s. Entrambi incompleti secondo rubrica binaria.

Confronto manuale esplorativo, non una misurazione del runner sullo snapshot congelato. Non cambiare i motori o i gold nel corso delle prove.

Domanda successiva Q21: «Quale nota del 2023 è richiamata dalla nota AMVUTTRA 0634617/2026 e come cambiano i canali di rendicontazione ambulatoriale e domiciliare?»
