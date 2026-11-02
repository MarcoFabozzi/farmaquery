# Le 35 domande scelte per la tesi

Questa lista è stata definita direttamente dall'autrice del progetto il 2 novembre
2026: **35 domande in totale**, non più l'insieme provvisorio di 36
domande generate automaticamente o il precedente PDF con 40 esempi.

Il CSV `tesi/domande_utente_35.csv` è **la fonte dei quesiti della
sperimentazione**. I riferimenti `Q01`…`Q35` restano stabili per confrontare
le risposte del chatbot. Le colonne `risposta_gold` e `fonti_gold` sono
lasciate vuote fino alla validazione manuale.

| Fonte principale | Domande |
|---|---:|
| AIFA | 13 |
| EMA | 9 |
| Regione Campania | 9 |
| Incrocio di più fonti | 4 |
| **Totale** | **35** |

Tre piccole modifiche di chiarezza rispetto al messaggio originale:
- Q03: domanda sulle *formulazioni autorizzate* per bambini sotto 6 anni
  invece di chiedere «il formato più adatto», che richiederebbe anamnesi,
  peso, posologia e scheda tecnica. I dati attualmente raccolti non
  necessariamente contengono l'intero RCP: **non inventare una scelta**.
- Q07: il riferimento implicito viene esplicitato: «confezioni di Eutirox».
- Q08: corretto il refuso «claase»; Q25: formulato come domanda completa.

Le domande Q04 e Q06 chiedono una classe riferita al medicinale senza
specificare l'AIC: occorre indicare la classe delle confezioni pertinenti,
evitando di attribuire automaticamente a tutte le confezioni la stessa.
Anche l'assenza delle A/H non giustifica la classificazione ufficiale C.

Q21 (CEVEDALO) testa la capacità di **non inventare** un prescrittore
autorizzato quando le fonti nello snapshot non sono sufficienti.

## Come provarle nel sito

1. Apri FarmaQuery → **Chatbot**.
2. Scegli il metodo dal menu: **Text-to-SQL** oppure **TAG**.
3. Espandi **Le 35 domande della tesi (facoltativo)** e seleziona Q01,
   oppure digita la domanda liberamente nella chat.
4. Ripeti la stessa domanda con l'altro metodo.
5. Alla fine seleziona **Scarica le risposte delle prove (CSV)** per
   ottenere le uscite, i riferimenti e i tempi dei due motori.

L'accesso alle API richiede un provider e il suo secret su Streamlit Cloud,
non nel repository. Il limite della chat demo resta 12 domande per sessione.
Il download è **manuale**, perché la chat non archivia su GitHub i dati
della sessione.

## Valutazione

Le risposte raccolte dai due motori non sono automaticamente corrette.
L'autrice verifica fonti e contenuto e assegna a ciascuna risposta
un giudizio manuale 0/1. La statistica va riferita all'esatto snapshot
dei dati e al modello realmente utilizzato: non confrontare prove
raccolte su snapshot diversi senza separare le serie.
