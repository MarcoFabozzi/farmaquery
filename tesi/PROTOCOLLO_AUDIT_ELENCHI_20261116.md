# FarmaQuery – protocollo e audit retrospettivo del 16/11/2026
I due motori hanno risposto alle stesse 35 domande usando lo SQLite congelato il 02/11/2026. Lo snapshot e le 70 risposte originali non sono stati modificati. Si misurano separatamente l'accuratezza completa (0/1) e le metriche di recupero su 16 domande con almeno due entità o tuple omogenee: Q01, Q08, Q11–Q20, Q24, Q31, Q34 e Q35. Q32 e Q33 richiedono attributi eterogenei di un singolo medicinale, quindi rimangono nell'accuratezza completa ma non nei conteggi sulle liste.

## Regole
TP: tupla affermata dal motore e coerente con tutti i vincoli obbligatori della domanda, inclusi indicazione e centro quando richiesti. FP: tupla affermata come appartenente all'insieme ma estranea alla Gold; in Q24 TAG include per errore Ruggi d'Aragona nella lista polineuropatia. FN: tupla Gold non recuperata o non provata. Menzioni negate, soggetti indicati come non ancora autorizzati, citazioni contestuali e duplicati identici non producono ulteriori predizioni positive. Alias di denominazione sono normalizzati. La Precision è n.d. quando non sono prodotte tuple positive; Recall e F1 valgono zero se la Gold non è vuota. Si calcolano micro Precision/Recall/F1 dalle somme di TP/FP/FN e Recall macro come media dei Recall per domanda, includendo le domande senza predizioni.

Q31 misura nove associazioni AIC–classe; Q34 due medicinali collegati a Federico II; Q35 cinque centri PLUVICTO. Altri attributi necessari alla risposta completa sono valutati nel giudizio binario, non trasformati in tuple aggiuntive di questi elenchi. Le unità sono contate per domanda, perciò alcuni elementi ricorrono in quesiti differenti.

## Gold rettificate e provenienza
Originali inalterati: `tesi/GOLD_35_VALIDATO_SOLO_DATABASE_20261109.csv` e `tesi/FarmaQuery_Gold_35_20261109.json`. Rettifica retrospettiva: `tesi/GOLD_35_REVISIONE_DOCUMENTALE_20261116.csv` e `tesi/FarmaQuery_Gold_35_REVISIONE_DOCUMENTALE_20261116.json`. Q11 passa da 4 a 5: il PDF originale RYSTIGGO (PG/2025/0307935, p. 3) elenca AOU Federico II; la relazione non era stata correttamente conservata nella trasformazione testuale dello snapshot, ma non è omessa nella fonte. Q14 passa da 6 a 8: si includono le due associazioni relative alla nota KAFTRIO+KALYDECO 2022, già menzionate nella Gold discorsiva originale. Queste revisioni sono state compiute conoscendo le risposte prodotte e non costituiscono un benchmark indipendente.

## Risultati
16 domande e 73 unità Gold. Text-to-SQL: TP=22, FP=0, FN=51, Precision micro 100,0%, Recall micro 30,1%, F1 micro 46,3%, Recall macro 22,2%. TAG: TP=47, FP=1, FN=26, Precision micro 97,9%, Recall micro 64,4%, F1 micro 77,7%, Recall macro 58,8%. Accuratezza completa sulle 35 domande: Text-to-SQL 10/35 e TAG 20/35; astensione 5/5 per entrambi; accuratezza sulle 30 rispondibili Text-to-SQL 5/30, TAG 15/30.

## Fallimenti SQL
TAG: Q08 ParseError (validazione); Q21 OperationalError (esecuzione: colonna inesistente); Q31 ValueError (validazione); Q34 OperationalError (esecuzione: colonna inesistente). Text-to-SQL: Q22, dopo autocorrezione. Gli output registrati non contengono le SQL integrali in questa sintesi: non si possono attribuire con certezza a singole colonne o costrutti. TAG dispone di normalizzazioni e percorsi alternativi, non di autocorrezione generale equivalente alle due riscritture di Text-to-SQL.

## Limiti e tracciabilità
La valutazione e la scelta delle Gold sono a cura dell'autore di FarmaQuery; il ricalcolo è retrospettivo e non cieco. Il manifesto `risultati/tesi_statico_20261102.json` registra 160314 confezioni AIFA e 60 atti GU nello snapshot congelato; l'origine causale di conteggi alternativi (160015 e 63) non è attestata dal manifesto. Ulteriori verifiche non effettuate non vengono dichiarate come svolte.

Tabella numerica: `tesi/AUDIT_ELENCHI_16_DOMANDE_20261116.csv`.
