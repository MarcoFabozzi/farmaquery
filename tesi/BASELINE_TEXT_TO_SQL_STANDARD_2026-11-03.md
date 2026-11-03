# Text-to-SQL standard — baseline definitiva della tesi

**Data:** 3 novembre 2026  
**Decisione metodologica:** usare come baseline **solo Text-to-SQL essenziale**, non una versione potenziata con recupero semantico.

## Funzionamento effettivo

1. L'utente invia una domanda in italiano.
2. L'LLM riceve **soltanto domanda e schema SQLite** e genera **una sola SELECT SQLite**.
3. Il validatore controlla la SELECT e la connessione al database è in **sola lettura**.
4. La SELECT viene eseguita **una sola volta**; al massimo 80 righe e un budget testuale fisso sono condivisi con la sintesi del risultato.
5. Se sono presenti righe, lo **stesso modello LLM** produce una risposta in italiano basandosi **esclusivamente** sul risultato SQL, con identificativi di citazione quando selezionati.
6. Se la SELECT restituisce **zero righe**, il motore non richiama di nuovo l'LLM: segnala «La query SQL generata non ha restituito risultati nello snapshot consultato», senza spacciare lo zero per prova di assenza documentale.
7. Se la SELECT è malformata, vietata o non eseguibile, l'esito è **errore tecnico**; il motore non la corregge.

**La generazione della risposta in lingua naturale a partire dalle righe SQL non è un operatore TAG**: resta una sintesi del risultato recuperato. Non viene effettuato alcun ulteriore accesso al database per la sintesi.

## Cosa NON fa il Text-to-SQL standard

- Nessuna espansione delle categorie implicite (per esempio «neuromuscolare» → «miastenia»).
- Nessun recupero ausiliario o automatico dei PDF, né ricerca delle note candidate fuori dalla query generata.
- Nessuna seconda SELECT su zero righe, su limiti di copertura, su errori di sintassi o su eccezioni SQLite.
- Nessuna correzione automatica delle risposte o revisione di completezza.
- Nessun operatore LOTUS e nessun prompt che incorpori i gold del benchmark.

Il motore può comunque **leggere un testo contenuto nella colonna `pagine.testo` se è la SELECT stessa a recuperarlo**. Non è vietato, per non creare una baseline artificiosamente incapace. Non è invece autorizzato a usare recuperi semantici aggiuntivi né ulteriori query su quel testo.

## Confronto con TAG

| Aspetto | Text-to-SQL standard | TAG con LOTUS |
| --- | --- | --- |
| Database | Stesso SQLite congelato | Stesso SQLite congelato |
| Modello | Stesso modello LLM | Stesso modello LLM |
| Recupero | Singola SELECT generata | Recupero candidati + filtro semantico LOTUS |
| Categoria implicita | Nessuna espansione automatica | Valutazione semantica del testo |
| Rimandi nei PDF | Solo se la SELECT li seleziona | Recupero documentale e verifica dei rimandi candidati |
| Zero righe | Nessun secondo tentativo | Indagine sulle evidenze con pipeline TAG |

**Nota sulla correttezza del confronto:** i vantaggi osservati sono quelli delle **due implementazioni concrete**, non dimostrano che qualsiasi sistema Text-to-SQL non possa analizzare testi. TAG usa anche strategie di recupero integrale che vanno descritte separatamente dall'effetto di LOTUS.

## Versionamento e risultati

- Il codice prima di questa semplificazione rimane nella cronologia Git e **non è esposto come terzo motore in FarmaQuery**.
- Le prove manuali delle otto domande Q05/Q06/Q07/Q08/Q09/Q21/Q28/Q29 e la loro rubrica rimangono **baseline storica di sviluppo della versione avanzata**, non risultati della nuova baseline standard.
- Qualsiasi nuovo confronto deve riportare commit, SHA-256 dello snapshot, versione e parametri del modello, domanda, SQL, risposta, fonti, tempi e errori. **Non mescolare i risultati di versioni diverse**.
- I 30 quesiti principali includono gold ancora non validati: eseguire il confronto conclusivo soltanto quando il gold è stato approvato e il set di test è congelato.

Questo intervento **non cambia TAG, le sorgenti, lo snapshot e nessuna risposta gold**.
