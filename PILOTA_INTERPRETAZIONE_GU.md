# Pilota: interpretazione dei provvedimenti della Gazzetta Ufficiale

Questo modulo sperimentale NON cambia il database pubblico e NON viene avviato dalla dashboard o da GitHub Actions.

## Scopo

Estrarre fino a 15 provvedimenti già archiviati con evidenze AIC, verificare integrità del testo e degli allegati, chiedere a un LLM una **proposta** di interpretazione e scartare citazioni inventate. Ogni evidenza resta in stato `DA_REVISIONARE_MANUALMENTE`. Non equivale a certificare la classe vigente.

## Avvio senza chiamate API

```powershell
python analisi_provvedimenti_llm.py --limit 12
```

L'output è una lista di atti per il pilota, senza interpretazioni LLM.

## Avvio con Gemini (solo quando si vuole provare l'API)

Configurare una chiave Gemini in variabile d'ambiente locale, senza inserirla nei file o in Git:

```powershell
$env:GEMINI_API_KEY = Read-Host "Inserisci GEMINI_API_KEY"
python analisi_provvedimenti_llm.py --provider gemini --limit 12
Remove-Item Env:GEMINI_API_KEY
```

Il modello predefinito è `gemini-3.5-flash-lite`, modificabile con `--model`. L'esecuzione richiede accesso Internet e può comportare costi/limiti API. I provvedimenti sono fonti pubbliche, ma si deve comunque verificare quali dati siano opportuni da inviare al provider.

Se il modello restituisce un errore HTTP, la nuova versione dello script indica `ERRORE_API` e `http_status`, senza esporre la chiave. Se usi uno ZIP scaricato prima della correzione, prova `--model gemini-3.5-flash-lite` oppure scarica la versione aggiornata del modulo.

L'output predefinito è `risultati/analisi_provvedimenti_pilota.local.json`, un rapporto **locale**. Non aggiungerlo al repository. Il prompt può usare estratti parziali di documenti lunghi: il rapporto segnala il limite.

## Test

```powershell
python -m unittest -v tests.test_analisi_provvedimenti_llm
```

## Limiti del pilota

* La validazione automatica accerta la presenza letterale della citazione e del codice AIC, NON la correttezza giuridica dell'interpretazione.
* Le informazioni AIFA e i collegamenti EMA sono riportati soltanto quando già documentati nel database; non vengono create associazioni nuove.
* Nessuna conclusione di vigenza: possono esistere atti successivi, rettifiche o limitazioni non acquisite dalla pipeline.
* Verificare manualmente almeno 10–15 documenti, annotando citazioni, tipo di atto, classe, errori, omissioni e corrispondenze AIC.
* Soltanto dopo il collaudo progettare il collegamento conversazionale, con revisione umana e avvertenze esplicite.

La versione pubblica di FarmaQuery non è modificata dal prototipo.
