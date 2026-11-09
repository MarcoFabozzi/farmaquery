# FarmaQuery — correzioni generali SQL v2 prima del test finale

## Stato

Questa modifica è proposta **dopo** il collaudo delle 20 domande del 9 novembre 2026.
Le risposte originali sono conservate come risultato della versione
`autocorrezione-v1` e **non** vanno sostituite retroattivamente.
Il nuovo motore dichiara `versione_text_to_sql=autocorrezione-v2-controlli`.

Resta la stessa impostazione SQL-first: una SELECT generata dal modello,
validazione in sola lettura, fino a due correzioni **solo per errori SQL**.
Nessuna ricerca semantica alternativa, LOTUS, TAG o database aggiuntivo.
Il database statico non cambia.

## Tre controlli generali introdotti

1. **Domande su quantitativi operativi reali.** Una domanda che chiede il
   numero di pazienti effettivamente trattati, somministrazioni effettuate o
   ricavi prodotti non può ricevere come risposta un `COUNT(*)` delle tabelle
   anagrafiche/regolatorie dello snapshot. Il sistema restituisce
   `DATO_OPERATIVO_NON_VERIFICABILE`; questo non significa che il fatto
   non sia accaduto. Le domande ordinarie su conteggi di confezioni e note
   rimangono valutabili.
2. **SELECT non probanti.** Sono riconosciute query senza tabelle,
   condizioni letterali sempre false e `LIMIT 0`. Lo stato
   `SQL_NON_PROBANTE` evita di considerarle normali esiti di ricerca.
   Non vengono effettuate ulteriori richieste LLM.
3. **Contraddizione grossolana nella sintesi.** Se le righe contengono
   dati ma la sintesi ne nega globalmente l'esistenza, la risposta
   contraddittoria viene sostituita da un avviso prudente con gli eventuali
   identificativi recuperati. Stato `SINTESI_INCOERENTE`. Il testo integrale
   originale viene conservato in `risposta_originale_llm`.

I controlli **non attestano che una risposta sia corretta** e non sostituiscono
la verifica delle Gold. La sintesi su righe non pertinenti può ancora fallire;
questa limitazione deve restare misurabile.

## Diagnostica e riproducibilità

L'esportazione JSON/CSV conserva `versione_text_to_sql`,
`motivo_controllo_sql` e `risposta_originale_llm` dove applicabili,
oltre a query, tentativi, correzioni, latenza e invii LLM.
Le anomalie vengono registrate e non nascoste nell'analisi finale.

I test offline si trovano in
`tesi/tests/test_sql_controlli_v2.py`.
Verificano falsi zeri, SELECT artificialmente vuote, negazioni globali,
conteggi normali e assenza di ritentativi per SELECT valide senza righe.

## Prima del test finale

- Verificare le CI offline sulla PR, senza spendere quote Gemini.
- Validare il questionario finale e le Gold sui documenti originali.
- Fissare commit dei due motori, SHA-256 del DB SQLite decompresso,
  modello realmente utilizzato e parametri.
- Registrare il collaudo 20 come **sviluppo**, non holdout indipendente.
- Non modificare più le pipeline dopo aver visto le risposte del test finale:
  ulteriori interventi richiedono una versione e un esperimento distinti.

Per riferimento, hash SQLite congelato:
`f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`.
