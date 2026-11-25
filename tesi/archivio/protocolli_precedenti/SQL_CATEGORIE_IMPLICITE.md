# Text-to-SQL e categorie cliniche implicite — protocollo

## Problema osservato nel pilota
Per la domanda sui medicinali neuromuscolari al Federico II, la prima versione Text-to-SQL ha interrogato soltanto strutture_registri filtrando letteralmente per «neuromuscolari». Zero righe della query non implica assenza dell'informazione nello SQLite: nello stesso snapshot sono presenti note regionali pertinenti.

## Modifica metodologica
Per quesiti con categoria implicita il prompt riceve il vocabolario di indizi già condiviso con il recupero TAG, non un elenco di farmaci autorizzati né risposte gold. Il modello è istruito a cercare prove regionali nelle tabelle note e pagine, anche se patologia e centro sono su pagine diverse della stessa nota. La semplice compresenza nel PDF non prova l'autorizzazione.

Se la prima SELECT generata per una categoria implicita restituisce zero righe, il medesimo LLM può produrre UNA seconda SELECT sulla base dello schema, della domanda e della query vuota. Entrambe sono validate SELECT-only, eseguite sul medesimo database e con gli stessi limiti di sicurezza. L'eventuale secondo fallimento è classificato NESSUNA_RIGA_SQL, che non significa assenza documentale.

## Rigore del confronto
I risultati registrano sql_iniziale, sql_tentativi, sql effettivamente eseguita e categoria_implicita_sql. Token e costi includono l'eventuale seconda generazione, quindi non va confrontato il solo tempo di sintesi. La precedente prova con SELECT letterale e risposta vuota resta un risultato storico della vecchia configurazione, da non sovrascrivere.

Lo snapshot, le domande e il modello rimangono gli stessi per TAG e Text-to-SQL. La nuova versione del metodo SQL va identificata nel protocollo, poiché il replan e l'espansione lessicale ne modificano il comportamento. Non è una dimostrazione di maggiore correttezza: risposte e citazioni richiedono verifica dei documenti PDF.

I test offline simulano query vuote e rigenerate, verificano citazioni e contabilizzazione API, senza consumare quota Gemini.