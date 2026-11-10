# Q29 CASGEVY — confronto manuale esplorativo (03/11/2026)

**Domanda identica ai due motori:** «Quale nota del 2024 richiama CASGEVY nel 2025 per SINFONIA, e questo rimando annulla o sostituisce la nota precedente?»

**Gold:** `tesi/benchmark_regolatorio_8_validati.csv`, Q29: la nota CASGEVY 0655032/2025 del 25/11/2025 cita la nota PG/2024/0503681 del 24/10/2024, relativa all'abilitazione sulla piattaforma regionale SINFONIA. È un rimando operativo per SINFONIA Piani Terapeutici 2.0, **non** una dichiarazione di annullamento/sostituzione della nota 2024. Fonte: `note 2025 - 18.12.2025/CASGEVY  Prot.N.0655032-2025.pdf#p3`. L'integrale della nota precedente non è stato confrontato.

## TAG — output originale ricevuto

> La nota del 2024 richiamata nel 2025 per CASGEVY in relazione alla piattaforma SINFONIA è la **Nota PG/2024/0503681 del 24/10/2024** (“Chiarimento del Percorso di abilitazione sulla piattaforma regionale SINFONIA”) (Fonte: `CASGEVY Prot.N.0655032-2025.pdf#p3`).
>
> Il documento **non** specifica se tale rimando annulla o sostituisce la nota precedente, limitandosi a stabilire che, in base ad essa, le prescrizioni dovranno essere implementate sul sistema SINFONIA Piani Terapeutici 2.0 (Fonte: `CASGEVY Prot.N.0655032-2025.pdf#p3`). L'eventuale annullamento o sostituzione non è documentato nel testo.

**Metadati dell'app:** 4,9 s; TAG verifica-integrale-v2; fonte integrale; AIC 0; revisione LLM sì; evidenze 7, elementi LOTUS 3, chiamate LLM stimate 5.

**Valutazione TAG:** protocollo, data, finalità operativa e distinzione da abrogazione corretti: completezza **1/1**; citazione p.3 pertinente; nessuna abrogazione dedotta.

## Text-to-SQL — output originale ricevuto

> Informazione non documentata nello snapshot consultato.

**SQL generato:**
```sql
SELECT n.id AS nota_id, n.nome_file, n.anno, n.farmaco_candidato,
       n.protocollo_candidato, n.data_candidata, n.indicazione_candidata,
       n.archivio_url, p.numero_pagina, p.testo,
       rc.riferimento AS rimando_riferimento, rc.stato AS rimando_stato
FROM note AS n
JOIN pagine AS p ON n.id = p.nota_id
JOIN rimandi_candidati AS rc
  ON p.nota_id = rc.nota_id AND p.numero_pagina = rc.numero_pagina
WHERE n.anno = 2024
  AND (n.farmaco_candidato LIKE '%CASGEVY%' OR p.testo LIKE '%CASGEVY%')
  AND (p.testo LIKE '%2025%' OR rc.riferimento LIKE '%2025%')
  AND (p.testo LIKE '%SINFONIA%' OR n.indicazione_candidata LIKE '%SINFONIA%')
LIMIT 80
```

**Metadati dell'app:** 1,1 s; 1 query generata; l'interfaccia dichiara modello e snapshot invariati.

**Valutazione Text-to-SQL:** **0/1**, nessuna citazione o elemento richiesto. La clausola `n.anno = 2024` esclude la nota CASGEVY del **2025** da cui occorre ricavare il rimando al 2024; l'anno del documento richiamato è stato scambiato con l'anno del documento interrogato. Anche la INNER JOIN con `rimandi_candidati` è potenzialmente restrittiva, ma non abbiamo eseguito SELECT diagnostiche, quindi non attribuiamo altre cause.

## Confronto
| Criterio | TAG | Text-to-SQL |
| --- | ---: | ---: |
| Protocollo e data 2024 | Corretti | Assenti |
| Finalità operativa SINFONIA 2.0 | Corretta | Assente |
| Nessun annullamento/sostituzione dichiarato | Corretto | Assente |
| Completezza rigorosa | 1/1 | 0/1 |
| Latenza mostrata | 4,9 s | 1,1 s |

**Limiti:** prove raccolte manualmente dalla Streamlit online; versione esatta degli LLM, hash dello snapshot live e prompt non accertati. Risposte originali non modificate. Questo non è l'esito della pipeline automatica sullo SQLite congelato del 02/11/2026.
