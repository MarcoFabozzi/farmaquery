# Bozza per la tesi — Materiali, architettura e metodo sperimentale

> **Bozza di scrittura tecnica, 8 novembre 2026.** Da adattare alla numerazione e alla bibliografia definitiva. I risultati del nuovo holdout non sono ancora disponibili. Questo testo non costituisce una validazione clinica o giuridica delle fonti.

## 1. Obiettivo del lavoro

L'interrogazione di informazioni regolatorie sui medicinali presenta una difficoltà specifica: i dati utili a rispondere a una domanda possono essere distribuiti fra tabelle strutturate e documenti testuali. I record relativi alle autorizzazioni europee, alle confezioni e alla loro classificazione italiana possono essere rappresentati in uno schema relazionale; le note regionali, invece, descrivono frequentemente condizioni di prescrizione, elenchi di strutture, aggiornamenti e richiami a provvedimenti precedenti in un linguaggio non completamente standardizzato.

Questo lavoro progetta e valuta **FarmaQuery**, un assistente conversazionale in lingua italiana per l'interrogazione di un corpus regolatorio farmaceutico. L'obiettivo sperimentale è il confronto fra una pipeline basata su **Text-to-SQL** e una pipeline di **Table-Augmented Generation (TAG)** che combina il recupero di informazioni tabellari con operazioni semantiche e controllo delle evidenze documentali.

Non si assume che uno dei due approcci debba essere corretto in ogni situazione. Il confronto intende identificare le categorie di domande in cui ciascuna soluzione risulta più affidabile, gli errori commessi e il costo operativo espresso in tempo e chiamate al modello linguistico.

## 2. Costruzione e congelamento del corpus

Le fonti considerate nel progetto comprendono dati dell'**Agenzia europea per i medicinali (EMA)**, della **Agenzia Italiana del Farmaco (AIFA)**, della **Gazzetta Ufficiale** e delle note pubblicate dalla **Regione Campania**. L'insieme è stato organizzato in un database SQLite utilizzato in sola lettura durante gli esperimenti.

Per garantire la riproducibilità è stata fissata una fotografia dei dati al **2 novembre 2026**, identificata da un'impronta SHA-256. La copia sperimentale contiene 2.357 record EMA, 160.314 confezioni AIFA, 380 note regionali, 942 testi di pagina e 60 atti della Gazzetta Ufficiale. I conteggi corrispondono al manifesto associato allo snapshot e descrivono il materiale **disponibile nel database**, non necessariamente la totalità delle informazioni regolatorie pubblicate.

Le note regionali sono state associate ai testi delle singole pagine, conservando l'identificativo del documento, il percorso interno all'archivio e il numero di pagina. Questa granularità consente al sistema di recuperare una determinata sezione e di produrre una citazione più precisa del semplice nome del file. Per documenti acquisiti tramite riconoscimento ottico dei caratteri (OCR), il testo può presentare errori di trascrizione, soprattutto nelle tabelle con più colonne e nelle denominazioni delle strutture ospedaliere.

Una distinzione centrale riguarda la **qualità dei collegamenti**: la co-occorrenza del nome di un medicinale e di un ospedale nello stesso PDF non dimostra, da sola, che quella struttura sia autorizzata alla prescrizione per una determinata indicazione. Allo stesso modo, la presenza di un centro in un registro AIFA non prova automaticamente la sua designazione nella singola nota regionale. Per questo la valutazione richiede, dove pertinenti, l'indicazione clinica, la tabella dei centri e il corretto rapporto fra le due.

Il database contiene anche relazioni di riconciliazione manuale, ma esse coprono soltanto una parte delle note. Tali collegamenti non devono essere interpretati come un censimento completo di tutte le autorizzazioni regionali.

## 3. Pipeline Text-to-SQL

La prima soluzione costituisce la **baseline**. A partire da una domanda in italiano e dallo schema disponibile, il modello linguistico produce una query SQL. Prima dell'esecuzione la query viene sottoposta a controlli sintattici e di sicurezza, che ne limitano l'ambito alle interrogazioni di sola lettura. La query validata viene applicata al database e i record ottenuti costituiscono la base informativa per la generazione della risposta.

L'approccio è particolarmente naturale per richieste relative a singoli campi, conteggi, identificativi di autorizzazione, AIC o join fra tabelle. La qualità finale, tuttavia, dipende dalla correttezza della SQL generata, dalla rappresentazione relazionale delle informazioni e dalla corrispondenza fra il lessico della domanda e i dati indicizzati. Una domanda che richiede di interpretare l'effetto di un rimando testuale o di associare un reparto a una specifica indicazione può non essere interamente risolvibile tramite la sola struttura tabellare.

Per valutare correttamente la baseline si conservano tanto le risposte riuscite quanto i fallimenti nella generazione o nella validazione della query. Una risposta assente o una SQL non eseguibile non viene esclusa dal conteggio sperimentale.

## 4. Pipeline TAG automatica

La seconda soluzione integra il recupero relazionale con una selezione semantica dei contenuti. In FarmaQuery, TAG non coincide con una semplice ricerca per parola chiave: la pipeline costruisce candidati dal database, li organizza in record contestualizzati e utilizza un operatore semantico di **LOTUS** (`sem_filter`) per valutare la pertinenza rispetto alla domanda.

Nella versione sperimentale **r24**, il primo passaggio genera e valida una SELECT per individuare le righe o i documenti potenzialmente pertinenti. A partire dai documenti regionali, il sistema conserva l'associazione con il testo estratto e la pagina di origine. Per alcune domande, una SELECT iniziale può essere troppo restrittiva: ad esempio, un filtro letterale sul termine «neuromuscolare» non identifica necessariamente una nota che descrive una specifica patologia senza utilizzare quel termine.

Per questo l'implementazione comprende un **recupero documentale alternativo in due fasi**, applicato soltanto quando un piano documentale verificabile lo consente. Nella prima fase vengono ricercate le note che menzionano la struttura di interesse; i documenti così individuati sono classificati semanticamente per la categoria clinica richiesta. Nella seconda fase gli identificativi selezionati sono recuperati nuovamente tramite una SELECT deterministica, quindi vengono sottoposti al controllo semantico LOTUS e alla verifica delle associazioni fra medicinale, indicazione e struttura.

La verifica finale elabora gruppi di documenti per limitare le omissioni che possono verificarsi quando molti PDF sono forniti allo stesso prompt. Ogni associazione proposta viene confrontata con il documento e le pagine citate: le coppie non supportate vengono respinte; i riferimenti verificati nei lotti completati possono essere mantenuti anche se un lotto successivo fallisce. Il sistema distingue quindi fra **risposta completa, risposta parziale, astensione ed errore tecnico**. Un risultato parziale non viene considerato esaustivo.

Questi controlli migliorano la tracciabilità e consentono di studiare gli errori, ma **non certificano automaticamente la correttezza normativa**. Una verifica programmatica può confermare la presenza di un nome e di un'indicazione in una pagina, mentre la qualificazione giuridica del rapporto fra strutture e prescrivibilità richiede comunque l'interpretazione documentale.

## 5. Protocollo comparativo e quesiti

La progettazione dei motori si è svolta utilizzando un insieme preliminare di domande, con cui sono stati individuati e corretti problemi di recupero, classificazione, completezza e formattazione. Questi casi sono **test di sviluppo**: non verranno utilizzati per dichiarare la capacità di generalizzazione dei sistemi.

Dopo il congelamento del codice r24 viene predisposto un ulteriore blocco di **20 domande candidate**, articolate in cinque categorie di quattro quesiti ciascuna:

1. **Dirette:** interrogazioni di campi o conteggi immediatamente individuabili nelle tabelle.
2. **Relazionali:** elenco e collegamento di confezioni, identificativi, anni e documenti.
3. **Semantiche:** interpretazione del contenuto di una nota e della relazione fra indicazione e prescrizione.
4. **Temporali:** confronto fra note successive, distinguendo modifiche espressamente dichiarate da semplici richiami.
5. **Assenza documentale:** richieste di attività o risultati operativi che potrebbero non essere contenuti nelle fonti; il sistema deve riconoscere l'eventuale mancanza di evidenze senza inventare informazioni.

Le domande sono sottoposte a **validazione manuale preventiva**. Il revisore prepara, per ciascuna, una risposta di riferimento, le citazioni puntuali e, nel caso delle enumerazioni, la lista degli elementi attesi. I sistemi non ricevono mai le risposte gold. Se un quesito non risulta verificabile nello snapshot, viene scartato **prima** dell'esperimento.

Ciascuna domanda validata viene poi somministrata alle pipeline utilizzando lo **stesso modello**, lo **stesso snapshot** e una configurazione confrontabile. Le risposte sono raccolte senza scegliere il tentativo migliore, registrando le query generate, le fonti, il tempo, il numero di chiamate e gli eventuali errori. La rotazione dell'ordine di esecuzione limita possibili distorsioni legate al momento in cui una pipeline interroga il provider.

## 6. Metriche e analisi dei risultati

La principale misura di correttezza è la proporzione di risposte **interamente conformi** alla risposta di riferimento:

\[
\mathrm{Accuracy}=\frac{N_{\mathrm{risposte\ interamente\ corrette}}}{N_{\mathrm{quesiti\ valutati}}}.
\]

Per le domande che richiedono più elementi, è utile distinguere una risposta esatta da una risposta incompleta. A partire dagli elementi attesi e da quelli riportati si calcolano:

\[
\mathrm{Precision}=\frac{TP}{TP+FP},\qquad
\mathrm{Recall}=\frac{TP}{TP+FN},\qquad
F_1=2\,\frac{\mathrm{Precision}\cdot\mathrm{Recall}}{\mathrm{Precision}+\mathrm{Recall}}.
\]

Le misure micro aggregano i conteggi di veri positivi, falsi positivi e falsi negativi sulle sole domande a elenco valutabili. La sola presenza di alcune citazioni corrette non basta a considerare completa una lista richiesta come esaustiva.

Accanto alla correttezza vengono valutati la precisione dei riferimenti (PDF e pagina, identificativo EMA o AIC), il comportamento di astensione, il **tempo medio**, il **numero medio di chiamate LLM** e, quando disponibile, il consumo di token e il costo. Le interruzioni per quota o indisponibilità del provider costituiscono risultati tecnici osservati: devono essere contabilizzate e discusse, non eliminate.

I risultati saranno presentati prima in forma complessiva e poi mediante una tabella **categoria × metodo × metrica**. In questo modo sarà possibile verificare, ad esempio, se il maggiore costo computazionale dell'elaborazione semantica corrisponde a una migliore copertura delle domande documentali, senza generalizzare indebitamente da un unico quesito.

**Tabella da compilare soltanto dopo l'esperimento**

| Categoria | N gold verificati | Accuracy Text-to-SQL | Accuracy TAG r24 | Tempo medio T2S (s) | Tempo medio TAG (s) | Chiamate medie T2S | Chiamate medie TAG |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dirette | — | — | — | — | — | — | — |
| Relazionali | — | — | — | — | — | — | — |
| Semantiche | — | — | — | — | — | — | — |
| Temporali | — | — | — | — | — | — | — |
| Assenza documentale | — | — | — | — | — | — | — |
| Totale | — | — | — | — | — | — | — |

*Il trattino indica che il risultato non è stato ancora misurato; non rappresenta uno zero.*

## 7. Limiti dello studio

La valutazione è riferita a un corpus e a una versione del codice definiti. Non implica che il database esaurisca tutte le disposizioni disponibili o che una classificazione storica descriva la situazione attuale. I testi acquisiti tramite OCR possono contenere nomi e tabelle incompleti; i documenti che descrivono più medicinali o più indicazioni possono produrre errori di attribuzione; le risposte dei modelli linguistici possono variare fra esecuzioni. Inoltre le due pipeline utilizzano un diverso numero di chiamate LLM, rendendo necessario discutere insieme accuratezza e costo.

Il campione finale di 20 quesiti permette un confronto esplorativo e riproducibile sullo snapshot scelto, ma non consente di affermare una superiorità generale di uno dei due paradigmi in ogni dominio regolatorio. Il contributo del lavoro consiste nella realizzazione delle pipeline, nella costruzione di un riferimento verificabile e nella **valutazione trasparente dei compromessi** fra interrogazione strutturata e selezione semantica.

## 8. Segnaposto per il capitolo successivo

Da completare solo dopo la validazione indipendente del gold e la raccolta degli output:

- numerosità effettiva dei quesiti valutabili e motivazione degli eventuali scarti;
- identificativi, versioni e impostazioni del modello LLM;
- tabella delle prestazioni per categoria con denominatori;
- esempi ragionati di una risposta corretta, una risposta parziale, una risposta errata e un'astensione;
- analisi degli errori su OCR, relazioni indicazione-centro, filtri lessicali, limiti di quota e citazioni;
- conclusioni riferite esclusivamente alle osservazioni registrate.

**Materiali da citare in tesi:** documentazione EMA/AIFA/Regione Campania, documentazione SQLite e LOTUS, letteratura scientifica su Text-to-SQL e TAG. I riferimenti bibliografici precisi vanno inseriti e verificati prima della consegna.
