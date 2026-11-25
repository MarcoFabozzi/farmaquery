# Screenshot delle risposte di FarmaQuery

Questa cartella raccoglie gli **screenshot delle risposte originali** dei due motori, **Text-to-SQL** e **TAG**, a supporto della tesi *Interrogazione in linguaggio naturale di basi di dati: dal Text-to-SQL alla Table-Augmented Generation*.

## Organizzazione

- [benchmark_35/](benchmark_35/): risposte del benchmark regolatorio, **Q01–Q35**.
- [test_sql_15/](test_sql_15/): risposte del test separato di generazione SQL, **Q36–Q50**.

## Convenzione per i file

Salvare ciascuno screenshot con il numero della domanda e il motore:

- `Q01_Text-to-SQL.png`
- `Q01_TAG.png`
- `Q13_TAG_01.png`, `Q13_TAG_02.png` per risposte che richiedono più immagini.
- `Q40_Text-to-SQL.png`, `Q40_TAG.png` nella cartella del test SQL.

Conservare l'ordine cronologico delle immagini quando una risposta occupa più schermate. Preferire PNG per il testo, oppure JPG ad alta leggibilità. Non modificare né ricostruire le risposte raffigurate.

## Criteri di pubblicazione

- Gli screenshot sono **evidenza visiva**, non sostituiscono i JSON delle esecuzioni, le risposte integrali in formato testuale o le query Gold.
- Pubblicare soltanto screenshot delle **esecuzioni selezionate per la valutazione**. I tentativi esclusi o di errore, se conservati, vanno identificati esplicitamente.
- Prima del caricamento, controllare la leggibilità di testo, fonti e dati tecnici ed eliminare eventuali chiavi API, token di accesso, credenziali o altre informazioni riservate.
- Non introdurre numeri, valutazioni o interpretazioni nelle immagini che non appartenevano alle risposte originali.
- Gli esperimenti si riferiscono allo snapshot congelato del **2 novembre 2026**: non confondere gli screenshot con risposte della dashboard aggiornata in seguito.

Le cartelle sono inizialmente vuote: gli screenshot saranno caricati separatamente.
