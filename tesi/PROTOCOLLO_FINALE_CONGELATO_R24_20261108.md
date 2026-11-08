# FarmaQuery — Protocollo sperimentale finale (congelamento r24)

**Data di preparazione:** 8 novembre 2026  
**Stato:** protocollo e questionario predisposti; **gold ancora da validare**; **nessuna nuova esecuzione LLM effettuata** per il blocco finale.

## 1. Oggetto e decisione di congelamento

La tesi valuta comparativamente due **pipeline** di interrogazione di dati regolatori farmaceutici: la baseline **Text-to-SQL** e il **TAG automatico** realizzato in FarmaQuery. L'obiettivo è misurare benefici, limiti, correttezza delle citazioni, costo e prestazioni; **non** ottenere risposte perfette o continuare a modificare TAG in funzione dei test.

- **Codice di riferimento dei motori:** commit `0d81dd516e8e4e9a6e2151cd1c0478204389aacb`, TAG `2026-11-08-r24-errore-lotti-diagnosticabile`.
- **Database:** `risultati/tesi_statico_20261102.sqlite.gz`, snapshot datato 2 novembre 2026.
- **SHA-256 del file SQLite decompresso:** `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742` (da `risultati/tesi_statico_20261102.json`).
- **SHA-256 dello snapshot sorgente:** `bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`; **non** confondere i due hash.
- **Manifest dei conteggi:** 2.357 record EMA; 160.314 confezioni AIFA; 380 note regionali; 942 pagine; 60 atti GU. Le 28 relazioni documentate/controllate non rappresentano una revisione completa delle 380 note.
- **Documentazione aggiunta dopo il congelamento:** non cambia l'identità del codice r24. In ogni risultato riportare **commit del motore**, SHA SQLite, data, modello/provider e impostazioni.

I test di regressione su bug non autorizzano a modificare il motore per migliorare il benchmark. Se si rende indispensabile un intervento, descrivere separatamente l'esperimento originale e il nuovo protocollo; non mescolare i risultati.

## 2. Separazione fra sviluppo e valutazione

Le 12 domande iniziali e i blocchi pilota già usati, compresi i 20 quesiti del confronto storico, sono **dati di sviluppo**, non un holdout indipendente. I loro risultati possono apparire nel capitolo sui test preliminari, con avvertenza esplicita.

Il blocco finale è `tesi/HOLDOUT_FINALE_20_R24_DA_VALIDARE_20261108.csv`: **20 formulazioni nuove** (4 per categoria). Prima dell'esecuzione:
1. verificare ogni domanda rispetto allo snapshot e alle pagine pertinenti; eliminare domande non validabili **prima** di leggere le uscite dei motori;
2. compilare `risposta_gold`, `fonti_gold`, `note_revisore`; per liste, `elementi_gold` separati da `|`;
3. per assenze documentali, controllare denominazioni alternative, principi attivi e le fonti pertinenti; **non** dedurre che un fatto non sia mai accaduto;
4. fissare il CSV gold e registrarne SHA-256; evitare correzioni retroattive.

Le categorie sono: **DIRETTE (4), RELAZIONALI (4), SEMANTICHE (4), TEMPORALI (4), ASSENZA_DOCUMENTALE (4)**. Le domande richiedono la risposta riferita al **corpus datato**, non la situazione normativa/operativa corrente.

### Stato di preparazione del gold

La versione iniziale `HOLDOUT_FINALE_20_R24_DA_VALIDARE_20261108.csv` conserva tutti i gold vuoti per tracciabilità. La copia di lavoro `HOLDOUT_FINALE_20_R24_GOLD_PARZIALE_20261108.csv` contiene le prime otto risposte controllate direttamente sui record EMA, AIFA e sul titolo/anno dei PDF. **Non** sono state ancora eseguite chiamate LLM sui quesiti finali.

| Categoria | Candidati | Gold controllati | Ancora da verificare |
|---|---:|---:|---:|
| Dirette | 4 | 4 | 0 |
| Relazionali | 4 | 4 | 0 |
| Semantiche | 4 | 0 | 4 |
| Temporali | 4 | 0 | 4 |
| Assenza documentale | 4 | 0 | 4 |
| **Totale** | **20** | **8** | **12** |

Il controllo automatico `tesi.valida_gold.inspect`, effettuato sullo stesso SQLite decompresso, ha confermato **8 record validati, 12 da verificare, zero errori strutturali**. Questo controllo dimostra che le citazioni esistono, non attribuisce un giudizio clinico alle note e non produce accuracy per i modelli. Le 12 domande rimanenti richiedono revisione documentale indipendente.

## 3. Condizioni identiche per i motori

- Stesso SQLite statico e schema, **sola lettura**.
- Identica domanda, in italiano, inviata a tutti i sistemi senza la risposta gold.
- Stesso modello LLM effettivamente disponibile, stessa configurazione di generazione dove applicabile, stessa infrastruttura; registrare la versione reale usata.
- Un'esecuzione per ogni coppia domanda/metodo, senza selezionare la risposta migliore dopo ripetizioni. Il runner alterna l'ordine dei metodi per limitare il bias temporale.
- **Confronto principale:** Text-to-SQL vs TAG automatico r24. Se presente la pipeline TAG manuale del runner, riportarla in una colonna esplorativa distinta, evitando di sostituire il confronto principale.
- Registrare gli errori, i timeout e i `RateLimitError` come esiti osservati. Le risposte parziali non diventano corrette solo perché le citazioni presenti superano i controlli.

**Nota sul confronto:** la baseline Text-to-SQL e il TAG r24 sono **pipeline applicative** con differenti numeri di passaggi. Le misure non dimostrano una superiorità universale della famiglia TAG in astratto.

## 4. Rubrica prima di vedere gli output

Per ogni metodo/domanda, un revisore controlla:
- `valutazione_risposta=1`: risposta interamente coerente con il gold, senza omissioni richieste, associazioni inventate o condizioni scambiate fra indicazioni; `0` altrimenti;
- `valutazione_citazioni=1`: fonti puntuali, con PDF e pagina o ID EMA/AIC/GU corretti e pertinenti; `0` se citazioni errate, insufficienti o assenti quando dovute;
- per risposte a elenco: `elementi_predetti` e `elementi_gold` secondo regole esplicite di normalizzazione; su questi calcolare **precision, recall, F1 micro**; un elemento non presente nel gold non è automaticamente falso prima del controllo indipendente;
- per domande di assenza: `valutazione_astensione=1` soltanto se il sistema dichiara il limite del corpus senza trasformarlo in un divieto o un conteggio pari a zero;
- errore tecnico o mancata risposta: includere nel denominatore dell'accuratezza come non corretto e nel tasso d'errore, senza eliminarlo dalle misure di tempo/costo disponibili.

**Non creare automaticamente punteggi di correttezza con un altro LLM.** Conservare motivazione e citazioni del revisore. Se la verifica di una domanda non è conclusa, segnarla come non valutata, mai come corretta per default.

## 5. Metriche richieste

Per metodo e categoria:
- **accuratezza delle risposte** = numero di risposte interamente corrette / numero totale di domande gold valutate; includere errori e astensioni improprie nel denominatore;
- **precision / recall / F1 micro** sulle sole domande a elenco il cui gold è definito, con numeri `TP, FP, FN`;
- **correttezza citazioni** come giudizio per risposta e, se disponibile, numero di citazioni corrette / citazioni effettivamente esaminate;
- **tempo medio in secondi** (inclusi esiti tecnici), **chiamate LLM effettive medie**, quota degli errori tecnici, astensioni corrette, token e costo se misurabili;
- sempre specificare **N** per ogni metrica; mai sostituire i dati mancanti con `0`.

Le chiamate dirette e quelle LOTUS vanno distinte. Le richieste non osservabili lato provider devono essere indicate come limite del conteggio.

## 6. Procedura riproducibile

Il file `.gz` va decompresso in uno SQLite locale senza modificare il contenuto:

```bash
python -c "import gzip,pathlib; p=pathlib.Path('risultati/tesi_statico_20261102.sqlite.gz'); pathlib.Path('risultati/tesi_statico_20261102.sqlite').write_bytes(gzip.decompress(p.read_bytes()))"
```

Dopo la validazione semantica e la compilazione dei campi gold, copiare il CSV **validato** in un percorso distinto; non cambiare `DA_VERIFICARE` senza revisione.

```bash
python -m tesi.valida_gold --benchmark tesi/HOLDOUT_FINALE_20_R24_VALIDATO.csv --db risultati/tesi_statico_20261102.sqlite
```

Il comando controlla la struttura e l'esistenza delle pagine, **non** l'effettiva autorizzazione clinica. Soltanto quando **tutti** i 20 gold sono validati eseguire:

```bash
python -m tesi.esegui_holdout \
  --benchmark tesi/HOLDOUT_FINALE_20_R24_VALIDATO.csv \
  --db risultati/tesi_statico_20261102.sqlite \
  --manifest risultati/tesi_statico_20261102.json \
  --model MODELLO_EFFETTIVAMENTE_CONFIGURATO \
  --commit 0d81dd516e8e4e9a6e2151cd1c0478204389aacb \
  --out risultati/holdout_finale_r24_risposte_grezze.csv
```

I tre metodi registrati dal runner sono `Text-to-SQL`, `TAG`, `TAG automatico`, benché i due primi del confronto principale siano Text-to-SQL e TAG automatico. Il file di output non viene sovrascritto per impedire rerun non dichiarati.

Dopo aver annotato **manualmente** valutazioni e citazioni negli output:

```bash
python -m tesi.valuta_confronto \
  --benchmark tesi/HOLDOUT_FINALE_20_R24_VALIDATO.csv \
  --risultati risultati/holdout_finale_r24_annotato.csv \
  --manifest risultati/tesi_statico_20261102.json \
  --out risultati/holdout_finale_r24_metriche.json \
  --tabella-csv risultati/holdout_finale_r24_per_categoria.csv
```

## 7. Prove r24 già osservate: SOLO sviluppo

Una prova sulla domanda dei medicinali neuromuscolari presso AOU Federico II ha mostrato **161 documenti nella prima fase, 15 nella seconda, 11 associazioni accettate su 11 proposte, 3/5 lotti finali completati, 17 invii LLM, 16,7 s**; il quarto lotto si è interrotto con **QUOTA/RateLimitError**. Queste metriche descrivono un **esempio diagnostico dello sviluppo**, non un risultato finale di accuratezza. Il rapporto di 11/11 misura unicamente le coppie proposte e accettate dal controllo interno, non la copertura del gold.

Fra le principali fonti d'errore da analizzare: mancata selezione iniziale delle note, associazioni indicazione-centro su pagine differenti, riferimenti a medicinali in note di altri prodotti, OCR e denominazioni variabili, imprecisione dell'LLM, limiti di quota, differenza fra centri regionali designati e attività prescrittiva reale.

## 8. Conclusione metodologica

L'esperimento intende misurare **quali domande vengono risolte meglio da ciascuna pipeline, a quale costo e con quale tracciabilità**, mantenendo gli errori osservabili. È valido anche se TAG non risponde correttamente a tutte le domande; non è invece valido attribuirgli risposte corrette senza fonti, scegliere solo i tentativi riusciti o modificare il metodo dopo aver visto le domande finali.
