# Modalità TAG a consumo ridotto — protocollo tecnico

## Obiettivo
FarmaQuery mantiene **Text-to-SQL invariato** e la stessa fotografia SQLite per entrambi i metodi. Il TAG continua a utilizzare l'operatore semantico **LOTUS `DataFrame.sem_filter`**, ma ora supporta due granularità di selezione:

- `FARMAQUERY_TAG_SELECTION_MODE=raggruppata` (**predefinita**): le evidenze recuperate vengono organizzate in massimo tre gruppi prima della valutazione LOTUS. Ogni gruppo contiene più estratti, con tipo e chiave originale. Se un gruppo è selezionato, le evidenze vengono espanse senza inventare fonti. Una domanda TAG valuta quindi al massimo **tre elementi** in `sem_filter`, oltre alla chiamata di sintesi.
- `FARMAQUERY_TAG_SELECTION_MODE=righe`: per controllo sperimentale utilizza il precedente filtro per singola riga. Può richiedere più chiamate al provider.

Questa ottimizzazione cambia la granularità della decisione semantica: **non è garantito che le risposte siano identiche** nelle due modalità. Non sostituire il test di accuratezza con i test tecnici.

## Misure e limiti delle stime
Il motore restituisce `modalita_selezione`, `righe_recuperate`, `righe_sem_filter`, `righe_selezionate_lotus`, `chiamate_semantiche_stimate` e `chiamate_llm_stimate`. Le due ultime sono **stime fondate sul numero di elementi valutati**, NON conteggi confermati dall'API Gemini. LOTUS può eseguire operazioni interne o retry; usare la console del provider per verificare i consumi reali.

Restano riportati token e costo **solo se restituiti dalle librerie/provider**. Non dichiarare costo totale preciso quando uno dei due componenti non espone il valore.

Confrontare le stesse domande e lo stesso snapshot nelle due modalità su un piccolo insieme pilota prima di fissare la modalità del benchmark definitivo. Registrare la modalità usata, non cambiare configurazione a metà di un esperimento.

## Rate limit e ripresa
Un errore HTTP 429 o `RateLimitError` è classificato `QUOTA`: **non è una risposta errata del TAG**. Il runner interrompe la sequenza dopo aver salvato l'errore (senza usare un'ulteriore chiamata al metodo successivo). Il limite può essere al minuto, ai token o giornaliero: l'app non tenta di indovinarlo.

In caso di limite API: controllare quota e modello su Google AI Studio e riprendere con `--riprendi`, sullo stesso snapshot e nella stessa modalità TAG. I tentativi QUOTA/ERRORE restano nello storico CSV e sono ritentati alla ripresa: per la valutazione considerare soltanto i risultati riusciti, ignorando le righe dei tentativi falliti. Il codice impedisce di mescolare nello stesso CSV modalità TAG differenti. Gli errori sono classificati senza registrare il testo grezzo delle eccezioni, che potrebbe contenere informazioni riservate.

## Timeout della selezione LOTUS

Una risposta TAG comprende **due fasi distinte**: `sem_filter` (selezione)
e la chiamata finale di sintesi. A seguito di un errore `ServiceUnavailableError`
durante *selezione TAG* a circa 29,6 secondi, la selezione passa a LiteLLM
`timeout=90` e `num_retries=0` tramite `sem_filter(..., **model_kwargs)`.
Per domande sulle categorie implicite la simultaneità `max_batch_size`
scende da 4 a 2. La sintesi delle categorie mantiene il suo timeout autonomo
di 90 secondi.

**Un errore HTTP 503 non è necessariamente un timeout:** può essere restituito
dal provider anche prima dei 90 secondi. È registrato come `SERVIZIO` e non
deve essere valutato come errore semantico del TAG. Nessun fallimento di
selezione viene sostituito artificialmente da un risultato documentale, e
non sono abilitati retry automatici che consumino ulteriore quota.

## Richiamo dei documenti nei quesiti a elenco

Per le domande su **categorie implicite** (per esempio «quali medicinali
neuromuscolari al Federico II?»), il sistema ricerca tutti i documenti
candidati che contengono una patologia pertinente e la struttura richiesta
in una delle pagine della stessa nota. Il recupero non si ferma più ai
primi 8 documenti ordinati per frequenza testuale.

In questi quesiti LOTUS continua a eseguire **sem_filter** per selezionare
e prioritizzare gruppi di documenti, ma la non selezione di un gruppo **non
costituisce una prova che i suoi medicinali non siano pertinenti**.
Per preservare il richiamo, i documenti candidati non selezionati arrivano
comunque alla sintesi come *candidati da verificare*, non come risultati
positivi. Questa è una scelta esplicita del protocollo sperimentale e ne
cambia la granularità della selezione rispetto alle domande nominative.

Le citazioni sono associate alle singole pagine; le finestre di testo
sono centrate su patologia e centro, non sull'intestazione OCR.
I limiti di contesto sono dichiarati e la lista non viene presentata
come esaustiva senza una verifica documentale completa.

Il test sullo snapshot reale controlla che i documenti DUVYZAT e ULTOMIRIS,
già individuati nelle evidenze normative di controllo, **raggiungano il
payload finale**. Il codice di produzione non contiene liste predefinite di
farmaci corretti né attribuisce automaticamente centri autorizzati.
La correttezza delle associazioni rimane oggetto della revisione gold.

## Stato
I test automatici verificano conservazione delle evidenze, tracciabilità dei gruppi, classificazione quota e arresto del runner. **Non eseguono chiamate a Gemini** e non dimostrano la correttezza clinico-regolatoria delle risposte.
