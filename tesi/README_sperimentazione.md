# Sperimentazione TAG vs Text-to-SQL — FarmaQuery

## Obiettivo di ricerca
Confrontare **Table-Augmented Generation (TAG)** tramite gli operatori semantici di **LOTUS** e **Text-to-SQL**, su domande regolatorie in italiano relative ai medicinali, alle note della Regione Campania, alle indicazioni e ai centri prescrittori.

Il successo della dashboard pubblica non costituisce la valutazione scientifica. L’esperimento resta **separato** dall'aggiornamento automatico online.

## Dataset congelato del relatore
Fonti del 02/11/2026:
- `Note_regionali_PDF 1(1).zip` — 209 PDF / 580 pagine; hash SHA-256: `8e444cb36f94ff0b73518ace3003f43eaf847f7e658da9b3913ac1d0e9a308a5`.
- `Strutture_registri_regioni_2026-09-14.csv` — 10.527 righe Campania; hash: `f4b1ec6f3123b441e240080867b37dd4ba19f2b54cd5b37b82fb869bffa155da`.
- Per gli esperimenti sulle classi di rimborsabilità usare **A/H al 31/05/2026** richiesti dal relatore, NON gli A/H del 30/06/2026 aggiornati dalla dashboard. Incorporare i file A/H soltanto dopo averne fissato SHA-256, struttura e data.
- Per le note regionali le pagine scansionate richiedono OCR. Un OCR non verificato va segnalato, non trattato come certezza.

**I file ZIP/CSV non sono inclusi nel repository**: hanno dimensioni elevate e fanno parte del materiale sperimentale fornito. Il loro hash consente di ripetere l'importazione a parità di sorgente.

## Struttura dati minima
- `note`: documento, anno, filename, hash, farmaco candidato, protocollo/data/determina da controllare.
- `pagine`: **una riga per (documento, pagina)** e testo estratto, metodo testo/OCR.
- `strutture_registri`: medicinale, patologia, indicazione, struttura, data dell'elenco AIFA.
- `centri_candidati` e `rimandi_candidati`: **solo candidati**, non un'approvazione regionale conclusiva.
- `riconciliazioni_candidate`: corrispondenze da revisionare fra nota e denominazione AIFA.

Evitare di assumere equivalenza tra **centro abilitato al registro AIFA** e **centro prescrittore autorizzato dalla specifica nota regionale**; verificare indicazione e periodo di efficacia.

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

## Metriche
Risposte corrette sul gold, correttezza delle citazioni (documento + pagina), gestione dei negativi/astensioni, tempo di risposta, token e costo per domanda. Riportare i risultati **per categoria** oltre alla media. Controllare l'effetto dell'OCR sugli errori.

## Ordine operativo
1. Completare OCR e congelare il database dei PDF/strutture.
2. Rivedere protocolli, centri, indicazioni e rimandi.
3. Fissare i 36 gold documentati e i casi negativi.
4. Eseguire gli stessi test con Text-to-SQL e LOTUS.
5. Analizzare errori e scrivere i capitoli «problema e fonti», «architettura», «esperimenti».
