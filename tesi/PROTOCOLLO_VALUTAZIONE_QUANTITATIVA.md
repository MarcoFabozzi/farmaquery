# FarmaQuery — protocollo per il confronto quantitativo

**Stato (3 novembre 2026):** sviluppo dei motori, **non** benchmark finale. Le 12 domande originali e i loro output sono esclusivamente casi di sviluppo e regressione. I dati e le domande del test indipendente non devono essere usati per modificare prompt, recupero, soglie o codice.

## Pipeline implementate

- **Text-to-SQL (baseline):** domanda -> LLM genera una SELECT -> validazione read-only -> SQLite -> sintesi LLM delle righe (solo se disponibili) -> risposta con riferimenti. Una SELECT e nessun retry applicativo.
- **TAG:** domanda -> recupero SQL da EMA/AIFA/note/strutture; per categoria+centro si interrogano **tutte le note con menzione del centro** e si recuperano medicinale, indicazione candidata, PDF e pagine -> preselezione testuale ad alto richiamo (senza top-N prima della query) -> filtro semantico LOTUS -> LLM sintetizza le righe e, ove necessario, il testo delle pagine originali -> revisione dei candidati omessi solo se supportati da citazioni -> risposta e fonti.
- **Intersezioni di centri:** l'operazione sugli abbinamenti revisionati `nota_centro_documentato` è SQL; il testo delle note serve per verificare significato e limiti della relazione. La tabella revisionata copre soltanto una parte del corpus, non tutti i centri autorizzati della Regione.
- Lo snapshot è datato: non dedurre classificazioni/indicazioni *vigenti* o attività reale da semplici menzioni dei PDF.

## Dataset e separazione corretta

- **Sviluppo:** 12 domande già usate, comprese 6 e 7. Nessuna misura su queste 12 sarà presentata come risultato di generalizzazione.
- **Holdout proposto:** `tesi/holdout_20_da_validare.csv`, 20 domande nuove (5 per categoria), tutte nello stato `DA_VERIFICARE`. Sono **proposte**, non una ground truth certificata.
- Prima di eseguire il test, un revisore controlla risposte di riferimento e pagine originali, inserisce `risposta_gold`, `fonti_gold`, `note_revisore` e imposta `VALIDATO`. Per domande a elenco compila `elementi_gold` separando i valori con `|`. Le domande non validabili vanno scartate **prima** di lanciare i motori.
- Validazione strutturale: `python -m tesi.valida_gold --benchmark <gold.csv> --db <snapshot.sqlite>`. Il controllo delle pagine esistenti **non** sostituisce la revisione semantica.
- **Congelamento prima del test:** salva SHA-256 SQLite, commit Git del codice, modello/versione provider e protocollo di valutazione. Niente correzioni dopo aver letto gli output holdout. Eventuali modifiche imporranno un nuovo test indipendente.
- Esegui entrambe le pipeline sullo **stesso snapshot** e **modello**. Conserva output grezzi, query SQL, fonti, orari, tempi, invii LLM e eventuali errori (anche quando non vi è risposta). I test falliti si contano nel denominatore, non si eliminano.
- I valori `valutazione_risposta`, `valutazione_citazioni`, `valutazione_astensione` e le citazioni pertinenti sono annotazioni del revisore, **non** punteggi LLM autoassegnati.

## Metriche

| Metrica | Definizione e limite |
|---|---|
| Accuracy | Risposte interamente corrette / risposte valutate (giudizio 0/1 del revisore); esplicitare anche copertura e denominatore |
| Precision, recall, F1 micro | Sulle risposte a elenco: confronto tra `elementi_gold` e `elementi_predetti` annotati; normalizzazione formale, non matching semantico automatico |
| Citazioni corrette | Due possibilità: giudizio binario per risposta e rapporto `citazioni_corrette_n / citazioni_verificate_n` per riferimenti controllati |
| Astensione | Per le domande di assenza documentale, giudizio separato 0/1: riconosce il limite dello snapshot senza inventare fatti |
| Tempo medio | Secondi effettivamente misurati da inizio a fine chiamata, inclusi eventuali errori; distinguere tempo GUI e backend |
| LLM invii medi | `chiamate_llm_effettive`: richieste LiteLLM dirette più i messaggi LOTUS non cached passati a batch_completion (con `num_retries=0`); conteggio non disponibile = NULL, mai sostituito dalla stima |
| Costo/token/errori | Costo osservato se disponibile, token consumati e quota di errori tecnici; i campi mancanti restano NULL |

Le callback globali LiteLLM non vengono cambiate, per evitare interferenze tra sessioni Streamlit. La misura per LOTUS conta i messaggi inviati al suo batch nel processo (non eventuali ritentativi invisibili dentro librerie/proxy/provider). Se la versione LOTUS non consente l'osservazione, il risultato segnala `conteggio_llm_completo=false`.

## Produzione della tabella richiesta dal relatore

Il file `tesi/risultati_holdout_template.csv` contiene le colonne da compilare dopo l'esecuzione e dopo la revisione. `elementi_predetti` contiene le entità dichiarate nella risposta (se l'elenco è vuoto **scrivi `[]`**, mentre il campo vuoto indica non valutato).

```bash
python -m tesi.valuta_confronto \
  --benchmark tesi/holdout_20_validato.csv \
  --risultati tesi/risultati_holdout_compilati.csv \
  --manifest risultati/tesi_statico_20261102.json \
  --out risultati/confronto_quantitativo.json \
  --tabella-csv risultati/confronto_per_categoria.csv
```

La tabella ha **righe = categorie** e **colonne = accuratezza, precision, recall, F1, citazioni, astensione, tempo, chiamate LLM, costo ed errori** per Text-to-SQL e TAG. Se mancano annotazioni o esecuzioni, **non esiste ancora alcun punteggio finale**. Un campione di 5 domande per categoria è preliminare; nel capitolo sperimentale dichiarare dimensione e limiti del campione.
