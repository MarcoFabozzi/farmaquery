# FarmaQuery — due fasi di verifica: 20 domande e confronto finale

Protocollo di lavoro approvato il 9 novembre 2026. La grafica dell'app è identica nei due test; le informazioni tecniche restano nei JSON, senza comparire negli screenshot.

## Fase 1 — Collaudo preliminare del solo Text-to-SQL con auto-correzione

**Questionario originale:** `tesi/holdout_20_da_validare.csv` — 20 domande (5+5+5+5). Usare le formulazioni esatte, senza variarle.

**Motore nel sito:** scegliere «Text-to-SQL». L'interfaccia ora collega questo nome esclusivamente a `sql_autocorrezione.sql_autocorrezione`: una SELECT iniziale; fino a **due** riscritture esclusivamente in caso di errore SQL; nessun retry se la SELECT funziona ma restituisce zero righe. LOTUS non è usato.

**Database:** copia statica del 2 novembre 2026. SHA-256 SQLite decompresso: `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`. Questa copia non deve cambiare per confrontare i motori.

**Obiettivo:** esaminare se la correzione riduce gli errori SQL rispetto alla baseline storica, non dichiarare accuratezza definitiva (i Gold del CSV risultano ancora `DA_VERIFICARE`).

### Domande dirette

- **D01** — Qual è il principio attivo del medicinale BEYONTTRA?
- **D02** — Quali sono lo stato autorizzativo EMA e la data di decisione UE per MYALEPTA nello snapshot?
- **D03** — Qual è il principio attivo del medicinale VABYSMO?
- **D04** — Qual è la data della decisione UE riportata da EMA per ELREXFIO?
- **D05** — Quale principio attivo viene indicato nel database EMA per ALHEMO?

### Domande relazionali

- **R01** — Quali AIC e classi risultano per le confezioni del medicinale BRUKINSA nello snapshot AIFA?
- **R02** — Quante confezioni di NINLARO risultano nel database AIFA? Indica per ciascuna AIC e descrizione.
- **R03** — Per LUMYKRAS collega la data di decisione UE EMA alle confezioni AIFA e alle relative classi, citando le due fonti.
- **R04** — Quali note regionali della Campania menzionano KEYTRUDA? Indica anno e identificativo del documento.
- **R05** — Quali confezioni di KAFTRIO sono presenti nello snapshot e quali classi A/H riportano?

### Domande semantiche

- **S01** — Nella nota regionale BEYONTTRA, come vengono individuati i centri già abilitati per il trattamento e quali condizioni sono dichiarate? Cita le pagine.
- **S02** — Nella nota regionale ALHEMO, quali indicazioni e quali strutture sono esplicitamente collegate? Riporta le pagine a supporto.
- **S03** — Nelle note regionali TRODELVY del 2022 e 2025, quali differenze sono effettivamente documentate sulle indicazioni o sui centri? Distingui cambiamenti e semplici richiami.
- **S04** — Confrontando le note regionali RYBREVANT del 2023 e 2026, quali aggiornamenti delle indicazioni o dei centri sono espressamente dichiarati?
- **S05** — Nella nota regionale VABYSMO quali condizioni di prescrizione e quali presidi sono indicati? Riporta il riferimento alla pagina.

### Informazioni non documentate

- **A01** — In quale data ciascun centro regionale individuato per BEYONTTRA ha iniziato effettivamente a prescrivere il medicinale?
- **A02** — Quanti pazienti sono stati realmente trattati con ALHEMO al Santobono nel 2026?
- **A03** — Quante somministrazioni di MYALEPTA sono state effettuate negli ospedali campani nel 2025?
- **A04** — Quale fatturato trimestrale è stato prodotto da RYBREVANT in ciascun ospedale della Campania nel 2026?
- **A05** — Qual è la data esatta della prima somministrazione effettiva di TRODELVY per ogni centro campano?

## Raccolta delle risposte del collaudo

1. Eseguire tutte le 20 domande sul motore Text-to-SQL, senza cambiare prompt, modello o database.
2. Registrare successi, query corrette, query non correggibili, risposte parziali e astensioni; **non** confondere «SELECT senza righe» con «assenza documentale dimostrata».
3. Aprire «Esporta le risposte integrali per la tesi» e scaricare il JSON **prima di cliccare «Nuova conversazione»**. Rinominare il file, ad esempio `pilot_20_sql_auto_risposte_integrali.json`.
4. Conservare tutti gli errori, le SELECT originali e corrette, il numero di tentativi, i token, i tempi e le fonti recuperate (presenti nel JSON). Un errore del provider/quota non conta come risposta valutabile.
5. Annotare versione del codice, modello effettivo e parametri; non usare i risultati di questo collaudo per modificare il TAG prima del confronto finale.

## Fase 2 — Test finale comparativo

- Utilizzare il questionario finale **immutato di 35 domande** e la **stessa** copia statica del database per i due motori.
- Eseguire le domande sia con Text-to-SQL con auto-correzione sia con TAG automatico, annotando che il Text-to-SQL *storico* a una SELECT costituisce una terza baseline precedente e non viene rieseguito come metodo pubblico.
- Prima di calcolare l'accuratezza, **chiudere la Gold Q11 (RYSTIGGO)** e verificare tutte le altre risposte attese aperte.
- Valutare **testo completo** di ogni risposta: correttezza piena, copertura, errori di omissione, Precision/Recall/F1 sugli elenchi, **astensione corretta sì/no**, e correttezza del documento e della pagina citati.
- Verificare in particolare gli eventuali falsi positivi: Precision=100% nei risultati preliminari deve essere confermata sulle risposte integrali.
- Misurare tempo medio, numero di chiamate LLM, correzioni SQL e fallimenti.
- Esportare **due** serie di risposte integrali, una per motore, e conservarle per le appendici della tesi.
- Fare screenshot con la grafica pulita: domanda, risposta, fonti; nascondere query SQL, log di controllo, numero chiamate, codici errore e dettagli di pipeline. Gli errori reali, se presenti nella risposta, non vanno mascherati.
- Registrare esplicitamente le versioni dell'app: il confronto precedente (12% vs 47%) resta un risultato storico riferito al vecchio motore standard, non va etichettato come risultato del nuovo motore.

## Interfaccia e tracciabilità

Il menu mostra soltanto **Text-to-SQL** e **TAG**. L'etichetta Text-to-SQL corrisponde al motore con auto-correzione. Le informazioni tecniche sono nascoste per impostazione predefinita: per visualizzarle durante il collaudo, attivare «Mostra dettagli tecnici» nel chatbot. Per gli screenshot finali lasciare questa opzione disattivata. La diagnostica resta sempre nell'esportazione JSON. La diagnostica resta sempre nell'esportazione JSON.

Il limite di richieste per sessione è aumentato per agevolare il collaudo; le **quote effettive del provider LLM** restano indipendenti, quindi eventuali messaggi QUOTA vanno documentati e ritentati separatamente.

## Attenzione ai risultati della tesi

Il collaudo su 20 domande viene usato per verificare il funzionamento e identificare guasti. La valutazione finale deve riferirsi solo al protocollo congelato, ai Gold verificati e alle risposte complete. Gli screenshot sono materiale illustrativo e non sostituiscono i dati di misura.
