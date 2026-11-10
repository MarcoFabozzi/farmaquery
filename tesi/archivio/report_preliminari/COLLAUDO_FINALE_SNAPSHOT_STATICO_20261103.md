# FarmaQuery — collaudo finale della demo statica (03/11/2026)

## Obiettivo e confini

Per la prova universitaria utilizziamo **un solo snapshot statico della fotografia del 2 novembre 2026**. Il codice Text-to-SQL standard continua a generare **una sola SELECT**, senza retry. TAG continua a usare LOTUS per il recupero e la valutazione semantica. Entrambi ricevono **la stessa domanda e lo stesso file SQLite** aperto in sola lettura.

La preparazione dello snapshot non è una fase di addestramento e **non inserisce risposte gold nella base di dati**. Le 28 relazioni nota–centro inserite derivano dalla revisione già svolta: 5 con precedente controllo PDF, 23 ricontrollate sui testi estratti. Le altre note continuano a essere disponibili integralmente nelle 942 pagine, ma non sono state tutte consolidate manualmente.

## Provenienza e distribuzione

- Snapshot originario (dati EMA/AIFA/GU/Campania): SHA-256 `bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`.
- Fonte dell'esecuzione: artifact GitHub Actions **`tesi-snapshot-fonti-online`**, workflow run `41436480339`.
- Derivazione congelata per la demo: `tesi/build_frozen_demo.py`.
- Archivio distribuito: `risultati/tesi_statico_20261102.sqlite.gz`.
- Manifesto distribuito: `risultati/tesi_statico_20261102.json`, contenente `sha256_sqlite`. **Usare il valore del manifesto come riferimento unico**, non l'hash di un'altra copia di lavoro.
- Il workflow `tesi-deploy-statico.yml` verifica integrità, 28 relazioni e fonti; al merge su `main` pubblica i file nel repository (se permesso dal token GitHub).
- Il chatbot carica automaticamente questa copia, se entrambi i file sono presenti. La estrae in locale e verifica lo SHA del contenuto prima di farla leggere ai motori. Una coppia incompleta non viene utilizzata.

**La copia locale di revisione v2 e il file costruito dalla pipeline possono avere SHA binari differenti**, pur derivando dalla stessa fotografia e dalle stesse 28 relazioni. Il confronto finale non deve mescolare i loro risultati: per la demo online utilizziamo sempre il file pubblicato col suo manifesto.

## Collaudo di natura documentale

Il comando seguente non usa API e non produce output LLM:

```bash
python tesi/collaudo_statico.py \
  --db /percorso/tesi_statico.sqlite \
  --manifest risultati/tesi_statico_20261102.json \
  --out risultati/collaudo_quattro_casi.json
```

Verifica la presenza dei cinque centri PLUVICTO a p. 2; alcuni esempi neuromuscolari collegati al Federico II (EVRYSDI, AGAMREE, ZILBRYSQ) con fonte p. 2; i due diversi rimandi CAMZYOS (p. 1 e p. 2). Non considera una ricerca SQL senza risultati come prova che un fatto regolatorio non esista.

## Interrogazione finale dei due motori

Le domande dimostrative si trovano in `tesi/demo_finale_quattro_domande.csv`: semplice, categoria implicita, rimando e informazione non documentata. **Non sono gold di benchmark certificati** e vanno tenute distinte dalle 30 domande accademiche.

Per eseguire una prova con Gemini, con la stessa chiave server già configurata:

```bash
python tesi/esegui_benchmark.py \
  --db /percorso/tesi_statico.sqlite \
  --manifest risultati/tesi_statico_20261102.json \
  --domande tesi/demo_finale_quattro_domande.csv \
  --out risultati/risposte_demo.csv \
  --model gemini/gemini-2.5-flash \
  --max-domande 4 --conferma-chiamate
```

La prova registra risposte originali, query SQL, fonti, durata ed errori senza giudicarle automaticamente corrette. Il workflow GitHub tenta questa prova solo se **`GEMINI_API_KEY` è disponibile nei GitHub Actions Secrets**. Altrimenti produce esplicitamente un esito di mancata configurazione, non finge risposte.

**Criteri per dichiarare finita la demo:** snapshot statico effettivamente servito online, entrambi i motori disponibili, risposte prodotte su tutte e quattro le domande senza errori di provider, verifica manuale delle citazioni e delle eventuali astensioni. I controlli CI offline **non sostituiscono** la prova con LLM.

## Benchmark della tesi

Le otto domande di sviluppo non diventano una misura statistica conclusiva. La valutazione definitiva richiede completare le risposte gold ancora `DA_VERIFICARE`, mantenere versione LLM/snapshot bloccate, eseguire TAG e Text-to-SQL standard sullo stesso set, e revisionare risposte e citazioni. Non attribuire superiorità al TAG prima di misurare i risultati.

**Aggiornamento automatico delle fonti e modifiche funzionali estranee alla demo sono esclusi da questa fase.**
