# FarmaQuery — revisione manuale e connessione allo snapshot statico

**Fotografia sorgente:** 2 novembre 2026. **Nessun aggiornamento o download delle fonti.**

## Database

La copia statica è fornita separatamente come `farmaquery_statico_revisionato_v2.sqlite` e accompagnata da `manifest_statico_revisionato_v2.json`. La versione è identificata dall'hash SHA-256

`5d4174a8a5a40d4d249ab8a0a6ec9d58f2bdb592bc5001697a68c495355921ed`.

La copia deriva dal database originale sperimentale del 02/11/2026 (SHA `bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`) attraverso una prima copia consolidata e una seconda revisione *in locale*. Le tabelle sorgente `note`, `pagine`, `aifa_confezioni`, `ema_medicinali`, `gu_*` non sono modificate.

## Che cosa è stato revisionato

- **28 relazioni nota–centro**, ciascuna con numero di pagina, frammento testuale che nomina il centro e richiamo al paragrafo autorizzativo. **5 PLUVICTO** hanno la precedente verifica gold sul PDF; **23** sono state revisionate sul *testo già estratto* e **non** vanno descritte come verificate visivamente sui PDF.
- Le **tre nuove relazioni** riguardano **EVRYSDI**, **AGAMREE** e **ZILBRYSQ** presso **AOU Federico II**, documentate nelle rispettive note e pagine.
- Tabella `revisione_relazioni_manuale_v2` con i passaggi testuali, metodo ed esito.
- Tabella `revisione_collegamenti_aifa_v2`: **23 riscontri nominali con lo stesso medicinale**, **5 senza abbinamento univoco**. **Nessuno** equivale automaticamente ad attestazione di abilitazione operativa del centro.
- Le altre **3.072 menzioni candidate** restano candidate e non sono state convalidate globalmente.
- Nessuna colonna di classificazione clinica **«neuromuscolare»** è stata precompilata: il riconoscimento è ancora materia del TAG.

## Collegamento dell'identica copia a entrambi i motori

Il file `chatbot_farmaquery.py` ora accetta:

- `FARMAQUERY_STATIC_DB_PATH`: percorso assoluto al file SQLite della copia v2.
- `FARMAQUERY_STATIC_MANIFEST_PATH`: percorso assoluto al manifesto v2.

**I due valori vanno configurati insieme.** La verifica controlla SHA-256, integrità SQLite e tabelle necessarie. In caso di errore, la modalità statica **si ferma** e **non** ricostruisce la base con dati online.

In PowerShell, nella cartella del repository e dopo aver collocato localmente i due file:

```powershell
$env:FARMAQUERY_STATIC_DB_PATH = "C:\percorso\farmaquery_statico_revisionato_v2.sqlite"
$env:FARMAQUERY_STATIC_MANIFEST_PATH = "C:\percorso\manifest_statico_revisionato_v2.json"
streamlit run dashboard_regolatorio.py
```

In questa modalità entrambi i motori sono chiamati da `chatbot_farmaquery.answer_question(...)` **con lo stesso percorso SQLite**, sempre aperto in sola lettura. **Text-to-SQL resta standard** (una sola SELECT); **TAG mantiene LOTUS**. Il solo aggiornamento allo schema SQL espone le tabelle aggiunte, senza attivare retry o filtri semantici per la baseline.

Il runner `tesi/esegui_benchmark.py` supporta già esplicitamente `--db` e `--manifest`. Esempio di anteprima **senza LLM**:

```powershell
python -m tesi.esegui_benchmark --db "C:\percorso\farmaquery_statico_revisionato_v2.sqlite" --manifest "C:\percorso\manifest_statico_revisionato_v2.json" --domande tesi/benchmark_regolatorio_30.csv --max-domande 3
```

**Attenzione:** il file di benchmark principale oggi contiene l'hash dello snapshot **originale**, quindi la modalità di confronto deve utilizzare **un benchmark separato per lo snapshot v2**, con gold rivisti, per poter eseguire realmente le chiamate LLM; il controllo anti-mismatch esistente non va rimosso.

### Limite del deploy

La modifica **abilita** il collegamento alla copia statica, ma **non carica il database binario di ~47 MiB nel repository GitHub / su Streamlit Cloud**. Il sito online continuerà a usare la sua pipeline corrente se i due percorsi statici non sono configurati. Non dichiarare online la modalità statica finché il file binario e il manifesto non sono stati effettivamente messi a disposizione del server.

### Verifiche eseguite

- Verifica SHA-256 dei file v1 e v2, integrità SQLite e chiavi esterne.
- Verifica degli estratti per tutte le 28 relazioni; i 23 casi non verificati visivamente sui PDF restano con la corretta etichetta.
- I test `tests/test_chatbot_farmaquery.py` controllano la selezione statica, il blocco per hash incoerente e il routing a entrambi i motori.

**Nessuna chiamata reale a Gemini è stata effettuata durante questa fase.** I tempi, l'accuratezza e le citazioni di TAG vs Text-to-SQL vanno misurati nella prossima fase, con le stesse domande e lo stesso modello.
