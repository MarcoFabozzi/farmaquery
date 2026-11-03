# Confronto manuale esplorativo Q06 — DUVYZAT

**Data:** 3 novembre 2026.
**Domanda identica per i due motori:** «Secondo la nota DUVYZAT del 2026, quali sono tutti i quattro presidi individuati in Campania, per quali pazienti e con quali condizioni di prescrizione?»

**Gold:** `tesi/benchmark_regolatorio_8_validati.csv`, Q06. Documento `note-regionali-2026 22.09.2026/DUVYZAT  Prot.N.0368583-2026.pdf`, pagine 1–2. Risposta gold validata per il documento storico, non per la situazione odierna.

## Output TAG — testo originale ricevuto
- **EMA (Indicazione terapeutica):** trattamento della distrofia muscolare di Duchenne (DMD) in pazienti deambulanti, di età pari o superiore a 6 anni, e con trattamento concomitante con corticosteroidi (*DUVYZAT Prot.N.0368583-2026.pdf#p1*).
- **REGIONE (Presidi, pazienti e condizioni in Campania):**
  - **Pazienti:** pazienti affetti da distrofia muscolare di Duchenne (DMD) (codice esenzione RFG080, gruppo Distrofie Muscolari) (*DUVYZAT Prot.N.0368583-2026.pdf#p2*).
  - **Condizioni di prescrizione:** prescrizione medica limitativa, da rinnovare volta per volta, vendibile al pubblico su prescrizione di centri ospedalieri o di specialisti individuati dalle Regioni (RNRL), erogato in distribuzione diretta (File F Canale D), con implementazione dei piani terapeutici sul sistema SINFONIA - Piani Terapeutici 2.0 previa attivazione del centro, e subordinatamente alla disponibilità effettiva del farmaco presso le farmacie ospedaliere nelle more della gara SO.RE.SA. (*DUVYZAT Prot.N.0368583-2026.pdf#p2*).
  - **I quattro presidi individuati:**
    1. A.O.R.N. Santobono-Pausilipon, Napoli – S.C. Neurologia e Neuroriabilitazione (*DUVYZAT Prot.N.0368583-2026.pdf#p2*).
    2. AOU "San Giovanni di Dio Ruggi d'Aragona", Salerno – Scienze Mediche - Neurologia (*DUVYZAT Prot.N.0368583-2026.pdf#p2*).
    3. Azienda Ospedaliera Universitaria dell'Università degli Studi della Campania "Luigi Vanvitelli" – UOC di I Neurologia e Neurofisiopatologia (*DUVYZAT Prot.N.0368583-2026.pdf#p2*).
    4. Azienda Ospedaliera Universitaria Federico II, Napoli – DAI Testa Collo - U.O.C. di Neurologia e Centro per epilessia (*DUVYZAT Prot.N.0368583-2026.pdf#p2*).

**Metadati visualizzati:** 3,4 s; TAG verifica-integrale-v2; fonte integrale; AIC 0; revisione LLM no; selezione raggruppata; 11 evidenze; 3 elementi LOTUS; 4 chiamate LLM stimate (non misurate).

**Valutazione rispetto al gold:** 4/4 presidi; età, deambulazione, corticosteroidi, RNRL, distribuzione diretta, SINFONIA 2.0 e disponibilità riportati. Omissioni di classe H e menzione esplicita del registro DUVYZAT; attribuzione etichettata «EMA» ma con citazione del PDF regionale. Per criterio di completezza binaria stretta: 0/1; qualitativamente quasi completo. La prova di correttezza delle singole pagine è distinta dalla verifica di copertura.

## Output Text-to-SQL — testo originale ricevuto
> Informazione non documentata nello snapshot consultato.

**Query SQL visualizzata:**
```sql
SELECT c.menzione AS presidio, c.stato AS condizioni_prescrizione,
       p.testo AS dettagli_pazienti, n.id AS nota_id, p.numero_pagina
FROM note AS n
JOIN pagine AS p ON n.id = p.nota_id
JOIN centri_candidati AS c
  ON p.nota_id = c.nota_id AND p.numero_pagina = c.numero_pagina
WHERE n.farmaco_candidato LIKE '%DUVYZAT%'
  AND n.anno = 2026
  AND n.percorso_zip LIKE '%Campania%'
LIMIT 80
```
**Metadati visualizzati:** 1,2 s; 1 query generata; «modello e snapshot invariati».

**Valutazione rispetto al gold:** 0/4 presidi; nessuna condizione recuperata; assenza affermata impropriamente. Per criterio di completezza binaria: 0/1. La condizione `n.percorso_zip LIKE '%Campania%'` **non corrisponde al percorso PDF registrato nel gold** riportato in apertura; questo è un filtro escludente certo per tale percorso. L'INNER JOIN su `centri_candidati` può escludere ulteriori pagine anche se il testo è presente. Non abbiamo eseguito le SELECT diagnostiche, quindi non possiamo attribuire con certezza la cardinalità effettiva di ogni singolo join/filtro nella sessione online.

## Comparazione e limiti
| Criterio | TAG | Text-to-SQL |
| --- | --- | --- |
| Presidi citati correttamente | 4/4 | 0/4 |
| Condizioni di prescrizione | Quasi complete | Nessuna |
| Citazione PDF/pagina | p. 1–2 (fonte riportata, etichetta EMA da correggere) | Nessuna |
| Completezza binaria stretta | 0/1 | 0/1 |
| Latenza visualizzata | 3,4 s | 1,2 s |

**Limite metodologico:** output raccolti dalla chat Streamlit, non dal runner sullo snapshot immutabile del 2 novembre. Non risultano disponibili hash della base dati interrogata nell'app, versione esatta dei prompt o modello. Classificare come confronto manuale esplorativo, non includere direttamente nel calcolo di accuratezza del lotto congelato.

**Passo successivo:** Q07 AMVUTTRA, prima TAG e poi Text-to-SQL con identica formulazione.
