# Sperimentazione TAG vs Text-to-SQL — FarmaQuery

## Obiettivo di ricerca
Confrontare **Table-Augmented Generation (TAG)** tramite gli operatori semantici di **LOTUS** e **Text-to-SQL**, su domande regolatorie in italiano relative ai medicinali, alle note della Regione Campania, alle indicazioni e ai centri prescrittori.

Il successo della dashboard pubblica non costituisce la valutazione scientifica. L’esperimento resta **separato** dall'aggiornamento automatico online.

## Fonti: ultime versioni ufficiali online, congelate per ogni esperimento

**Scelta aggiornata:** i file AIFA A/H del **31 maggio 2026 non sono vincolanti**. Erano stati inviati soltanto come ripiego durante l'indisponibilità del sito AIFA. Utilizziamo le **ultime versioni effettivamente acquisite e verificate dai workflow automatici** di FarmaQuery. La data dell'ultimo elenco pubblicato può essere precedente alla data di acquisizione.

Fonti incluse:
- **EMA**: catalogo JSON ufficiale e data/hash dell'ultima acquisizione riuscita.
- **AIFA**: anagrafica nazionale, principi attivi, liste A/H con la **data di riferimento più recente recuperata**; non dedurre la classe C ufficiale dall'assenza nelle liste A/H.
- **Regione Campania**: raccolte ZIP ufficiali 2022–2026 indicizzate mediante testo/OCR, con citazione a nome PDF e pagina.
- **AIFA strutture registri**: CSV ufficiale più recente disponibile nel progetto, limitato alla Campania.

**Distinzione essenziale**: FarmaQuery online mantiene gli aggiornamenti automatici; l'esperimento scatta quando selezioniamo una versione del repository GitHub e genera un **nuovo snapshot immutabile** con le fonti disponibili in quel commit. Tutti i metodi usano lo **stesso file SQLite sperimentale**, e il suo manifesto registra date e SHA-256. Gli esperimenti successivi su dati aggiornati saranno una nuova serie, non una modifica silenziosa dei test precedenti.

Per creare lo snapshot, dopo un aggiornamento riuscito delle fonti:
```bash
python tesi/prepara_snapshot_online.py \
  --output risultati/esperimento_online.sqlite \
  --manifest risultati/esperimento_online_manifest.json
```
Oppure eseguire il workflow GitHub Actions **Crea snapshot online per la tesi**: pubblica i due file come artifact scaricabile (senza modificare il database pubblico). Il database ha tabelle `note`, `pagine`, `pagine_fts`, `strutture_registri`, `centri_candidati`, `rimandi_candidati`, `aifa_confezioni`, `ema_medicinali`, `fonti_snapshot`.

Gli allegati originariamente forniti dal relatore (`Note_regionali_PDF 1(1).zip` e `Strutture_registri_regioni_2026-09-14.csv`) rimangono **materiale storico di riferimento**, ma non sostituiscono più le versioni ufficiali più aggiornate. Il loro hash è conservato in `risultati/snapshot_relatore_meta.json` per provenienza.

Il gold pilota di OLUMIANT è verificato sul PDF del materiale iniziale: **prima di usarlo nello snapshot online occorre confermare la presenza della stessa nota, la sua pagina e l'eventuale esistenza di note successive**. Non utilizzare automaticamente una risposta storica per dichiarare la situazione vigente.

Per le note regionali le pagine scansionate richiedono OCR. Una menzione di un centro nel documento o la presenza nel registro AIFA non equivale a prescrivibilità verificata.

## Struttura dati minima
- `note`: documento, anno, filename, hash, farmaco candidato, protocollo/data/determina da controllare.
- `pagine`: **una riga per (documento, pagina)** e testo estratto, metodo testo/OCR.
- `strutture_registri`: medicinale, patologia, indicazione, struttura, data dell'elenco AIFA.
- `centri_candidati` e `rimandi_candidati`: **solo candidati**, non un'approvazione regionale conclusiva.
- `riconciliazioni_candidate`: corrispondenze da revisionare fra nota e denominazione AIFA.

Evitare di assumere equivalenza tra **centro abilitato al registro AIFA** e **centro prescrittore autorizzato dalla specifica nota regionale**; verificare indicazione e periodo di efficacia.

## Selezione dei quesiti e raccolta delle evidenze

Il comando `python tesi/crea_benchmark_documentato.py` viene eseguito
dal workflow **Crea snapshot online per la tesi** sullo stesso SQLite
immutabile, utilizzando il suo manifesto SHA-256.

Produce tre file:
- `benchmark_36_da_validare.csv`: 9 domande per categoria, risposta e
  citazioni **vuote** finché non avviene il controllo umano.
- `evidenze_da_controllare.jsonl`: prima selezione delle pagine candidate,
  testo OCR, metodo di estrazione, percorso PDF e archivio istituzionale.
- `rapporto_benchmark.json`: hash dello snapshot, commit e distribuzione
  delle categorie.

Ogni domanda è `DA_VERIFICARE`. Un revisore deve controllare
il PDF ufficiale e compilare `risposta_gold`, `fonti_gold`,
`stato_validazione=VALIDATO`, con le osservazioni sul periodo di
efficacia, il contesto clinico e i rimandi. Un negativo deve essere
controllato anche per sinonimi, denominazioni alternative e principi
attivi. **L'assenza da un risultato di ricerca non dimostra un divieto
di prescrizione.**

Le domande possono essere rigenerate su uno snapshot successivo, ma
non vanno cambiate dopo aver avviato il confronto sullo snapshot fissato.
La valutazione quantitativa deve riportare separatamente quante domande
hanno effettivamente un gold validato.

## Benchmark: 36 domande, 4 categorie
1. **9 dirette**: verifica di un medicinale/centro in una nota.
2. **9 semantiche**: ricerca di indicazioni e centri per patologia.
3. **9 con rimandi**: note che richiamano, estendono o modificano provvedimenti precedenti.
4. **9 negative**: nessuna evidenza di una nota nel corpus, senza inventare un divieto di prescrizione.

Ogni gold comprende risposta verificata, documento, pagina e criterio di valutazione. I quesiti sono **solo candidati** finché non revisionati manualmente. Per ciascun esperimento conservare gli ID delle domande, timestamp, versione del codice, modello LLM, prompt, output, citazioni, tempo, token e costo.

## Confronto imparziale
- Identico snapshot SQLite, stesse 36 domande, stesso LLM/versione e parametri, stessa disponibilità delle pagine OCR, stessa tassonomia di risposte («sì», «no», «non documentato nel corpus»).
- **Text-to-SQL**: genera SELECT in sola lettura sullo schema relazionale; verificare automaticamente il codice SQL prima di eseguirlo.
- **TAG con LOTUS**: sem_filter/sem_map su DataFrame di pagine e strutture, con predicati in linguaggio naturale; eventuali sem_join solo su coppie candidate e con criteri verificabili. Documentazione: https://lotus-ai.readthedocs.io/en/latest/sem_filter.html e https://lotus-ai.readthedocs.io/en/latest/sem_join.html .
- Non effettuare chiamate LLM quando i gold non sono ancora stati validati oppure quando la chiave/modello non sono stati configurati dall'utente.

## Primo lotto di gold validati sullo snapshot online del 2 novembre 2026

Sono stati verificati **visivamente sui PDF** 5 casi del benchmark:
`DIR-01` (PLUVICTO), `SEM-05` (DUVYZAT), `SEM-09` (HETRONIFLY),
`RIM-06` (FASENRA) e `RIM-08` (CASGEVY). I PDF allegati coincidono
con quelli presenti nello snapshot online per **SHA-256**, non soltanto
per nome. Il JSON `tesi/gold_5_verificati_snapshot_online.json` riporta
risposta, pagine, ancore testuali e limiti della verifica.

La validazione è riferita **esclusivamente al contenuto delle note nelle
date indicate**; non prova da sola che strutture e indicazioni siano
ancora attive nel presente. Per i rimandi a note precedenti viene
specificato se si tratta di una sostituzione dei centri oppure di un
semplice riferimento operativo.

Il workflow **Tesi - verifica cinque gold sullo snapshot online** prende
il benchmark immutabile del run GitHub Actions `41436480339`, verifica
hash dello SQLite, hash di ogni PDF, percorso, pagina e ancore e produce
`benchmark_36_gold_5_validati.csv`: **5 validati, 31 da verificare**.
La verifica del file con `tesi/valida_gold.py` è obbligatoria; non vengono
attribuiti automaticamente punteggi TAG o Text-to-SQL.

## Validazione dei gold e valutazione

Dopo aver annotato `risposta_gold`, `fonti_gold` (formato
`nome/percorso.pdf#p2`, separatore `|` per più citazioni),
`note_revisore` e `stato_validazione=VALIDATO`, verificare i
riferimenti sullo stesso SQLite dello snapshot:

```bash
python -m tesi.valida_gold \
  --benchmark dist_tesi/benchmark_36_da_validare.csv \
  --db dist_tesi/esperimento_online.sqlite \
  --report dist_tesi/verifica_gold.json
```

Il programma controlla che documenti e pagine **esistano** e che il
revisore abbia fornito una motivazione; non pretende di decidere
automaticamente la validità normativa. Le domande ancora
`DA_VERIFICARE` non entrano nelle statistiche.

Per calcolare la correttezza del confronto usare
`python -m tesi.valuta_confronto` con i due output sullo
**stesso hash di snapshot** e con il **medesimo modello LLM**.
Il CSV risultati richiede le annotazioni manuali
`valutazione_risposta` e `valutazione_citazioni` (0/1), oltre
a tempo, token e costo quando disponibili. La metrica di correttezza
è `null` se non esistono giudizi manuali; non usare un semplice
confronto letterale delle risposte aperte come accuracy scientifica.

## Metriche
Risposte corrette sul gold, correttezza delle citazioni (documento + pagina), gestione dei negativi/astensioni, tempo di risposta, token e costo per domanda. Riportare i risultati **per categoria** oltre alla media. Controllare l'effetto dell'OCR sugli errori.

## Ordine operativo
1. Verificare l'ultimo aggiornamento di EMA, AIFA e Regione Campania; creare e archiviare un unico snapshot sperimentale online con manifesto SHA-256.
2. Rivedere protocolli, centri, indicazioni e rimandi.
3. Fissare i 36 gold documentati e i casi negativi.
4. Eseguire gli stessi test con Text-to-SQL e LOTUS.
5. Analizzare errori e scrivere i capitoli «problema e fonti», «architettura», «esperimenti».
