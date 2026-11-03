# Demo FarmaQuery per il relatore — quattro tipologie di quesiti

Questa traccia segue **solo** le richieste del relatore. FarmaQuery è un **prototipo universitario**, non un servizio di prescrizione o verifica operativa. Non richiede un sito industriale, infrastruttura documentale completa o UI complessa. Nessuna risposta è preimpostata nel chatbot: le domande vanno inviate davvero ai due motori.

## Citazioni e visualizzazione fonti

La demo visualizza per ogni evidenza disponibile:
- **Nome del documento e pagina** per le note regionali (es. `PLUVICTO.pdf — pagina 2`);
- **passaggio del testo realmente recuperato** nel pannello «Passaggi del testo consultato»;
- **link alla fonte ufficiale** (PDF se disponibile direttamente, archivio ZIP se il PDF è interno);
- **anteprima su richiesta della pagina originale del PDF**: il pulsante «Visualizza la pagina del PDF originale» scarica lo ZIP ufficiale e visualizza **solo la pagina citata**. L'anteprima viene caricata soltanto se il PDF è disponibile e identificabile nello ZIP. In caso contrario restano nome, pagina e testo estratto.

Se la fonte ha un **URL diretto PDF**, il link include `#page=N` dove il browser lo supporta. Se punta a uno **ZIP**, non inventiamo un PDF web inesistente: il pulsante estrae il file PDF nominato dalla fonte e mostra la pagina nell'app attraverso un visualizzatore opzionale. Il pulsante richiede una connessione allo ZIP regionale; non è garantito su ogni documento. L'evidenziazione di una frase **dentro il PDF originale** non è implementata; il relatore la considera facoltativa («se ci riesci»). Non scambiare l'estratto testuale con un'evidenziazione del documento.

## Quattro casi da mostrare

| Caso del relatore | Domanda da inviare | Cosa verificare nella risposta |
| --- | --- | --- |
| Semplice: centro/indicazione | «Secondo la nota regionale PLUVICTO del 18/04/2025, quali sono tutte le cinque strutture di Medicina Nucleare individuate e quali requisiti aggiuntivi sono richiesti?» | Cinque strutture, detenzione Lutezio-177, registro AIFA; nome del PDF e p. 1–2; distingue nota storica da operatività vigente. Gold Q05 già validato |
| TAG: categoria implicita | «Quali farmaci citati nelle note campane per patologie neuromuscolari prevedono la prescrizione presso il Federico II? Riporta farmaco, patologia, indicazione, pagina e centro.» | Comprensione della categoria non presente come colonna; per ogni abbinamento devono esserci **sia indicazione sia centro** documentati. P03 **DA_VERIFICARE**, quindi non promettere elenco esaustivo |
| Rimando tra note | «In relazione all'EGPA, quale nota precedente è richiamata da FASENRA 0520736/2026 e in che senso vengono sostituiti e aggiornati i centri per mepolizumab?» | Mostrare nota citante e nota richiamata quando presente; non trasformare la sostituzione di **centri** in abrogazione della nota. Gold Q28 validato; il PDF storico può non essere nello ZIP del corpus |
| Nessuna risposta nei dati | «Qual è la data di effettiva attivazione del trattamento PLUVICTO per ciascuno dei cinque centri campani, secondo lo snapshot?» | Se le date non sono nel corpus, astensione circoscritta allo snapshot, senza inventare un divieto o una data. Q24 **DA_VERIFICARE**, richiede ricerca documentale completa |

**Punto scientifico:** Text-to-SQL e TAG leggono lo **stesso SQLite**, che contiene dati EMA/AIFA e testo estratto dei PDF. La domanda semantica serve a mostrare il possibile contributo dell'operatore LOTUS, non a far fallire artificiosamente Text-to-SQL.

## Valutazione concreta di ciascun caso

Per entrambi i motori conservare: domanda esatta, risposta non modificata, SQL generato (solo Text-to-SQL), citazioni mostrate, durata, modello e versione dello snapshot. Accanto alla risposta annotare `OK`, `PARZIALE`, `NON DOCUMENTATO` oppure `ERRORE TECNICO` e descrivere in cosa differisce dalla fonte verificata. **Non attribuire 1/1 ai gold da verificare.**

Le otto domande già usate per ottimizzare i motori restano **set di sviluppo**, non misura finale indipendente. Non cambiare nuovamente Text-to-SQL o TAG durante il confronto finale.

## Checklist prima di mostrare la demo

1. Aprire il chatbot e selezionare il metodo desiderato.
2. Inviare una domanda alla volta e verificare che la risposta sia generata dall'LLM, non precaricata.
3. Aprire «Fonti consultate»: controllare documento, pagina e tipo di collegamento. Se la fonte è nello ZIP, provare «Visualizza la pagina del PDF originale» (il PDF deve essere scaricabile).
4. Aprire «Passaggi del testo consultato»: controllare che il passo provenga dalla stessa pagina e che non contenga una conclusione inventata.
5. Per rimandi distinguere il riferimento testuale dal reale recupero della nota precedente.
6. Per l'assenza di dati non trasformare il mancato recupero di una query in un fatto normativo.

**Ambito:** questa preparazione riguarda soltanto la presentazione delle fonti e la prova guidata della demo. Non tocca il motore TAG, la baseline Text-to-SQL o il benchmark.
