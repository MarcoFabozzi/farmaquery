# Valutazione manuale esplorativa — Q05 PLUVICTO (3 novembre 2026)

**Quesito:** Secondo la nota regionale PLUVICTO del 18/04/2025, quali sono tutte le cinque strutture di Medicina Nucleare individuate e quali requisiti aggiuntivi sono richiesti?

**Riferimento gold:** `tesi/benchmark_regolatorio_8_validati.csv`, Q05, nota `note 2025 - 18.12.2025/PLUVICTO.pdf`, pagine 1–2; data della nota 18/04/2025.

**Importante:** questo confronto proviene da interrogazioni **manuali dell'app Streamlit** fornite nella conversazione, non dal runner sullo SQLite congelato del 02/11/2026. L'interfaccia Text-to-SQL dichiara «modello e snapshot invariati», ma qui non sono stati acquisiti hash SQL, commit dei motori né log tecnici completi. Questi due risultati vanno **tenuti separati** dal calcolo formale di accuratezza sul benchmark immutabile.

## TAG — trascrizione fornita
> Le cinque strutture di Medicina Nucleare individuate sono (PLUVICTO.pdf, p. 1 e p. 2):
>
> - AOU FEDERICO II
> - AORN COLLI
> - AORN CARDARELLI
> - ASL NA 1 CENTRO - PO OSPEDALE DEL MARE
> - IRCCS-PASCALE
>
> I requisiti e le condizioni esplicite richieste (oltre all'autorizzazione alla detenzione) comprendono l'autorizzazione alla prescrizione/somministrazione e l'abilitazione al Registro AIFA PLUVICTO (PLUVICTO.pdf, p. 2).

**Tempo mostrato:** 5,5 s.  
**Dettagli mostrati:** `TAG verifica-integrale-v2`, fonte integrale, 21 evidenze, 3 elementi LOTUS, 5 chiamate LLM stimate (non misurate), revisione LLM sì.

**Annotazione:** 5/5 strutture corrette. Registro AIFA documentato e pagine pertinenti. La risposta dice «autorizzazione alla detenzione» senza specificare che si tratta di **Lutezio-177**, dettaglio previsto esplicitamente nella risposta gold. Per il criterio binario di completezza integrale della Q05: **0/1**, risposta **parzialmente corretta**, non da considerare pienamente validata. Citazioni alla nota e alle pagine 1–2 presenti; verificare separatamente le citazioni se la rubrica richiede tutte le specifiche puntuali.

## Text-to-SQL — trascrizione fornita
> Informazione non documentata nello snapshot consultato.

**Query SQL mostrata:**
```sql
SELECT p.nota_id, p.numero_pagina, c.menzione, c.stato, n.nome_file, n.archivio_url, p.testo
FROM pagine AS p
JOIN note AS n ON p.nota_id = n.id
JOIN centri_candidati AS c ON p.nota_id = c.nota_id AND p.numero_pagina = c.numero_pagina
WHERE (n.nome_file LIKE '%PLUVICTO%' OR n.farmaco_candidato LIKE '%PLUVICTO%')
  AND n.data_candidata = '2025-04-18'
LIMIT 80
```

**Tempo mostrato:** 1,1 s.  
**Dettagli mostrati:** Text-to-SQL; query generate 1; «modello e snapshot invariati».

**Annotazione:** 0/5 strutture, requisiti assenti, nessuna citazione di prova; dichiarazione di assenza **non supportata** dal riferimento gold. Valutazione binaria di completezza: **0/1**. Possibili meccanismi di errore: INNER JOIN su `centri_candidati` e uguaglianza esatta su `data_candidata`, entrambi potenzialmente escludenti. Senza eseguire separatamente la query e verificare la cardinalità dei filtri non è possibile attribuire con certezza la causa al JOIN o alla data. Non dedurre che lo snapshot sia privo del documento sulla base della sola query senza righe.

## Confronto e limiti metodologici

| Indicatore | TAG | Text-to-SQL |
| --- | ---: | ---: |
| Centri esatti recuperati | 5/5 | 0/5 |
| Requisito detenzione Lutezio-177 specificato | No (detenzione generica) | No |
| Registro AIFA indicato | Sì | No |
| Citazione PDF e pagina | Sì | No |
| Completezza integrale stretta | 0/1 | 0/1 |
| Tempo mostrato | 5,5 s | 1,1 s |

Questo non permette di attribuire punteggi scientifici generalizzabili ai due metodi. Da esaminare su nuove domande e sullo stesso snapshot congelato, mantenendo output originali e criteri di voto predefiniti.

**Prossima domanda del lotto:** Q06 DUVYZAT. Per una prova manuale raccogliere entrambe le risposte con latenza e diagnostica, senza correzioni intermedie.
