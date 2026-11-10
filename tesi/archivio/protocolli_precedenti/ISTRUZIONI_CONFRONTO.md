# FarmaQuery — Avvio del confronto TAG vs Text-to-SQL

Questo modulo **non modifica la dashboard** e non richiede di implementare altre
funzioni per verificare le domande. Le domande e le risposte gold vengono
scelte e verificate manualmente, prima del giudizio finale sui risultati.

## 1. Ambiente
LOTUS 1.2.4 richiede Python 3.10–3.12: usa **Python 3.12** per gli
esperimenti, anche se il progetto Streamlit principale usa Python 3.15.

PowerShell (Windows):
```powershell
py -3.12 -m venv .venv-tesi
.\.venv-tesi\Scripts\Activate.ps1
python -m pip install -r tesi/requirements-esperimenti.txt
```
Le librerie sperimentali restano separate da quelle dell'app online.

## 2. Database congelato
Da GitHub Actions, esecuzione `41436480339` (oppure un nuovo snapshot
quando tutte le fonti sono aggiornate), scarica `tesi-snapshot-fonti-online`
e metti questi file nella cartella `dist_tesi`:
- `esperimento_online.sqlite`
- `manifest_fonti_online.json`

Il programma verifica il **SHA-256**: rifiuta database e manifesto diversi.
Lo stesso snapshot viene usato da TAG e Text-to-SQL.

## 3. File delle domande
Prepara `dist_tesi/domande.csv` in UTF-8, con un record per domanda.
Il CSV può contenere tutte le 40 domande, anche prima della verifica
delle risposte gold. Esempio:

```csv
id;categoria;domanda
Q01;AIFA;In quale classe è la confezione JIVI da 1000 UI?
Q02;EMA;Per quali pazienti è autorizzato WEGOVY nell'Unione europea?
Q03;Regione;Quali ospedali della Campania possono prescrivere DUVYZAT?
```

Non copiare questi esempi se non sono nel tuo benchmark: sostituiscili
con le domande e le formulazioni effettivamente scelte.

## 4. Prima la simulazione (senza spesa)
```powershell
python -m tesi.esegui_benchmark --db dist_tesi/esperimento_online.sqlite `
  --manifest dist_tesi/manifest_fonti_online.json `
  --domande dist_tesi/domande.csv --max-domande 2
```
La simulazione elenca le domande e controlla le fonti, **non chiama LLM**.

## 5. Test reale limitato
Dopo aver scelto un modello LiteLLM supportato anche da LOTUS e ottenuto
l'accesso API relativo (non condividere la chiave nel codice né su GitHub):
```powershell
$env:GEMINI_API_KEY="INSERISCI_LA_TUA_CHIAVE"
python -m tesi.esegui_benchmark --db dist_tesi/esperimento_online.sqlite `
  --manifest dist_tesi/manifest_fonti_online.json `
  --domande dist_tesi/domande.csv --model gemini/gemini-3.5-flash-lite `
  --max-domande 2 --conferma-chiamate `
  --out dist_tesi/risposte_confronto.csv
```
Sono consentiti anche altri modelli LiteLLM; **usare lo stesso identico
modello per entrambi gli approcci**. Il valore di esempio qui non equivale
a una garanzia di disponibilità o di gratuità.

Solo dopo un test corretto è opportuno estendere `--max-domande` a 40
e aggiungere `--riprendi`, mantenendo invariati modello e snapshot.
Il runner non inventa mai giudizi sulle risposte e registra tempi,
testo, SQL, fonti, token e costi quando forniti dall'API.

## 6. Valutazione dopo la tua revisione delle risposte
Per il giudizio sperimentale, il file gold CSV contiene:
`id;categoria;domanda;risposta_gold;fonti_gold;stato_validazione;note_revisore`.
`stato_validazione=VALIDATO` solo dopo la verifica delle fonti.

Nel CSV delle risposte dei due metodi compilare manualmente
`valutazione_risposta` e `valutazione_citazioni` con 1/0.
Poi:
```powershell
python -m tesi.valuta_confronto `
  --benchmark dist_tesi/domande_gold.csv `
  --risultati dist_tesi/risposte_confronto.csv `
  --manifest dist_tesi/manifest_fonti_online.json `
  --out dist_tesi/metriche_confronto.json
```
Se il gold non è pronto, **non viene calcolata accuratezza**.

## Metodo, limiti e trasparenza
- TAG usa `DataFrame.sem_filter` di LOTUS sulle righe EMA, AIFA e regionali
  recuperate deterministicamente; la sintesi cita i record trattenuti.
- Text-to-SQL genera una singola `SELECT` SQLite controllata da SQLGlot
  ed eseguita su file di sola lettura.
- Le citazioni della parte regionale indicano file PDF e pagina; AIFA e EMA
  indicano AIC/EMA ID e le fonti disponibili nel dataset.
- La classe C NON è dedotta ufficialmente dall'assenza nelle liste A/H;
  la presenza negli elenchi dei registri non basta a dimostrare
  l'autorizzazione regionale alla prescrizione.
- Il costo dipende dall'LLM e dalla documentazione prezzi del provider.
  I token/costi sem_filter LOTUS sono letti dalle statistiche `physical_usage`.
  Se la stima del prezzo non è disponibile, segnare il dato come mancante.
- Le chiamate LOTUS possono essere numerose (sem_filter per riga). Partire
  da **due domande** per verificare quote e qualità, poi ampliare.
- La selezione preliminare delle righe TAG e la libertà SQL di generare
  query differenti sono limiti metodologici da dichiarare in tesi;
  il benchmark misura due pipeline e non una proprietà assoluta del modello.
