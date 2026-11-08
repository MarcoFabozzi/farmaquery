# FarmaQuery — 20 domande e risposte Gold fondate sul database statico

**Riferimento del corpus:** SQLite statico del 02/11/2026, SHA-256 del file decompresso `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`  
**Motori:** nessun quesito del blocco finale è stato ancora somministrato a TAG o Text-to-SQL.  
**Fonte delle risposte:** interrogazioni manualmente revisionate su `ema_medicinali`, `aifa_confezioni`, `note` e `pagine`.  
**Limite:** «Gold» significa risposta corretta **rispetto alle informazioni presenti nel corpus**. Non attesta il quadro regolatorio attuale. Le pagine OCR di alcune note richiedono conferma visiva prima di approvare come Gold definitivo.

## Come leggere questo documento

I quesiti **F01–F08** hanno Gold tabellare già verificato e citazioni esistenti. Per **F09–F20**, le risposte sottostanti sono **proposte di Gold ricostruite dal testo estratto dello snapshot** e non sono state ancora promosse automaticamente allo stato `VALIDATO`. I testi delle note 2022/2023 e alcuni del 2024 derivano da OCR: evitare di affermare una certezza visiva non ancora verificata. Per i casi negativi la risposta corretta è «informazione non documentata nel corpus», non «fatto mai accaduto».

Le risposte complete e le citazioni strutturate sono disponibili anche in `tesi/20_DOMANDE_GOLD_PROPOSTI_DAL_DATABASE_20261108.csv`. Quel file conserva gli 8 Gold confermati nel campo `risposta_gold`; per le altre 12 usa `risposta_gold_proposta_da_testo_sqlite` e `fonti_gold_proposte`, lasciando `risposta_gold` vuoto e `DA_VERIFICARE` per impedire l'esecuzione prematura del benchmark.


## 1. Domande dirette

### F01 — KAYFANDA

**Domanda:** Quale principio attivo è riportato per KAYFANDA nel record EMA dello snapshot?

**Risposta Gold validata:** Nel record EMA EMEA/H/C/006462 il principio attivo di Kayfanda è odevixibat sesquihydrate.

**Fonti nel database:** `EMA:EMEA/H/C/006462`

### F02 — BESREMI

**Domanda:** Quale indicazione terapeutica è registrata nel record EMA di BESREMI nello snapshot?

**Risposta Gold validata:** Il record EMA EMEA/H/C/004128 riporta Besremi in monoterapia per il trattamento della policitemia vera negli adulti senza splenomegalia sintomatica.

**Fonti nel database:** `EMA:EMEA/H/C/004128`

### F03 — VOXZOGO

**Domanda:** Quale data di decisione UE è presente nel record EMA di VOXZOGO nello snapshot? Riporta anche l'identificativo EMA.

**Risposta Gold validata:** Nel record EMA EMEA/H/C/005475 relativo a VOXZOGO, il campo data_decisione_ue dello snapshot vale 2026-06-11. La data è quella del record acquisito e non è presentata come prima autorizzazione storica.

**Fonti nel database:** `EMA:EMEA/H/C/005475`

### F04 — EMGALITY

**Domanda:** Quante confezioni del medicinale EMGALITY risultano nella tabella AIFA dello snapshot?

**Risposta Gold validata:** Nella tabella AIFA dello snapshot risultano 6 confezioni con nome esatto EMGALITY, AIC: 047424015, 047424027, 047424039, 047424041, 047424054 e 047424066.

**Fonti nel database:** `AIFA:047424015` · `AIFA:047424027` · `AIFA:047424039` · `AIFA:047424041` · `AIFA:047424054` · `AIFA:047424066`


## 2. Domande relazionali

### F05 — PROCYSBI

**Domanda:** Quali AIC e descrizioni delle confezioni di PROCYSBI sono riportate nel database AIFA congelato? Elencale tutte.

**Risposta Gold validata:** PROCYSBI: AIC 043041019 — 25 mg, capsule rigide gastroresistenti, flacone da 60 capsule; AIC 043041021 — 75 mg, capsule rigide gastroresistenti, flacone da 250 capsule; AIC 043041033 — 75 mg, granulato gastroresistente, 120 bustine; AIC 043041045 — 300 mg, granulato gastroresistente, 120 bustine. Tutte per uso orale, come da descrizioni AIFA.

**Fonti nel database:** `AIFA:043041019` · `AIFA:043041021` · `AIFA:043041033` · `AIFA:043041045`

### F06 — BIMZELX

**Domanda:** Quali PDF regionali presenti nello snapshot hanno BIMZELX nel titolo? Indica il nome del documento e l'anno dell'archivio di ciascuno.

**Risposta Gold validata:** I PDF del corpus regionale con BIMZELX nel titolo sono due: BIMZELX.pdf nell'archivio 2022 e BIMZELX artite psoriasica.pdf nell'archivio 2024.

**Fonti nel database:** `PTR_Note regionali 2022/BIMZELX.pdf#p1` · `ptr-note-regionali-11.12.24 ore 16.40/BIMZELX artite psoriasica.pdf#p1`

### F07 — EPIDYOLEX

**Domanda:** Quali PDF regionali presenti nello snapshot hanno EPIDYOLEX nel titolo? Riporta per ciascuno nome del file e anno dell'archivio.

**Risposta Gold validata:** I PDF del corpus regionale con EPIDYOLEX nel titolo sono due: Epidyolex sclerosi tuberosa.pdf nell'archivio 2022 ed EPIDYOLEX rara.pdf nell'archivio 2025. L'anno indicato è quello dell'archivio, non la data del protocollo.

**Fonti nel database:** `PTR_Note regionali 2022/Epidyolex sclerosi tuberosa.pdf#p1` · `note 2025 - 18.12.2025/EPIDYOLEX rara.pdf#p1`

### F08 — HEMLIBRA

**Domanda:** Per ciascuna confezione di HEMLIBRA nello snapshot AIFA, quali AIC e classe A/H sono riportate, se documentate?

**Risposta Gold validata:** HEMLIBRA: AIC 046130011 classe A; 046130023 classe A; 046130035 classe A; 046130047 classe A; 046130050 classe A/H non documentata nel relativo campo dello snapshot; 046130062 classe A. Per le cinque classi A valorizzate, la data della lista è 30/06/2026. Non si deduce classe C dall'assenza A/H per la sesta confezione.

**Fonti nel database:** `AIFA:046130011` · `AIFA:046130023` · `AIFA:046130035` · `AIFA:046130047` · `AIFA:046130050` · `AIFA:046130062`


## 3. Interpretazione delle note regionali

### F09 — KAYFANDA

**Domanda:** Nella nota campana KAYFANDA del 2026, quali condizioni di prescrizione e quali strutture o criteri di individuazione dei centri sono esplicitamente riportati? Cita le pagine.

**Risposta Gold proposta e controllata sul testo SQLite:** KAYFANDA (odevixibat) è indicato per il trattamento del prurito colestatico nella sindrome di Alagille (ALGS) dai 6 mesi di età (p.1). Classe H, prescrizione limitativa RRL. La pagina 2 autorizza quattro presidi regionali per la sindrome di Alagille (RN1350): AOU San Giovanni di Dio e Ruggi d'Aragona (Salerno), AORN Santobono-Pausilipon (Napoli), AOU Università della Campania Luigi Vanvitelli (Napoli), AOU Federico II (Napoli). Per Federico II la nota menziona il programma interdipartimentale Malattie del fegato e delle vie biliari. La pagina 3 dispone distribuzione diretta (File F Canale D), gestione dei piani terapeutici su SINFONIA 2.0, comunicazione preventiva dei dati per l'attivazione dei centri e abilitazione dei medici soltanto dopo tale attivazione; la prescrizione è subordinata anche alla disponibilità effettiva del farmaco.

**Fonti nel database:** `note-regionali-2026 22.09.2026/KAYFANDA Prot.N.0162816-2026.pdf#p1` · `note-regionali-2026 22.09.2026/KAYFANDA Prot.N.0162816-2026.pdf#p2` · `note-regionali-2026 22.09.2026/KAYFANDA Prot.N.0162816-2026.pdf#p3`

**Nota di controllo:** TESTO_SQLITE; pagina 2 con quattro strutture; non affermare attivazione operativa attuale.

### F10 — XEMBIFY

**Domanda:** Nella nota regionale XEMBIFY, per quale indicazione sono previste le disposizioni regionali e come vengono individuati i presidi prescrittori? Distingui i centri nominati dai criteri generali e cita le pagine.

**Risposta Gold proposta e controllata sul testo SQLite:** XEMBIFY (immunoglobulina umana normale sottocutanea) è oggetto di disposizioni per terapia sostitutiva in quattro condizioni (p.1): (1) immunodeficienze primarie con produzione di anticorpi compromessa; (2) ipogammaglobulinemia con infezioni batteriche ricorrenti nella leucemia linfocitica cronica quando la profilassi antibiotica non funziona o è controindicata; (3) ipogammaglobulinemia con infezioni batteriche ricorrenti nel mieloma multiplo; (4) ipogammaglobulinemia prima/dopo trapianto allogenico di cellule staminali ematopoietiche. A pagina 2: classe H, prescrizione RNRL da centri ospedalieri o internista, infettivologo, ematologo, immunologo; esclusivo uso sottocutaneo; avvio e monitoraggio da personale sanitario esperto dell'addestramento per la terapia domiciliare; MUP SANIARP. Non sono nominati singoli ospedali: il documento invita SANIARP a renderlo disponibile ai centri già utilizzatori di immunoglobuline sottocutanee per la medesima indicazione.

**Fonti nel database:** `note 2025 - 18.12.2025/XEMBIFY.pdf#p1` · `note 2025 - 18.12.2025/XEMBIFY.pdf#p2`

**Nota di controllo:** TESTO_SQLITE. Per la categoria centro NON sostituire i criteri generali con nomi inventati.

### F11 — DUPIXENT

**Domanda:** Quale indicazione terapeutica e quali istruzioni regionali di prescrizione sono indicate nella nota DUPIXENT del 2026? Collega ogni elemento alla pagina pertinente.

**Risposta Gold proposta e controllata sul testo SQLite:** La nota DUPIXENT (dupilumab) 0368563/2026 riporta due nuove indicazioni (p.1): (1) BPCO non controllata negli adulti con eosinofili ematici aumentati, come mantenimento aggiuntivo insieme a ICS/LABA/LAMA oppure LABA/LAMA se ICS non appropriato; (2) esofagite eosinofila nei bambini di età 1-11 anni e peso >=15 kg non adeguatamente controllati, intolleranti o non candidati alla terapia farmacologica convenzionale. A p.2: classe A/PHT, prescrizione RRL distinta per confezione e specialista; per BPCO registro WEB AIFA e unità/ambulatori già autorizzati alla prescrizione dei farmaci BPCO secondo Nota AIFA 99; per esofagite eosinofila scheda cartacea/piano terapeutico AIFA. A p.3 sono nominati i quattro centri pediatrici per esofagite: AOU Federico II (DAI Materno Infantile), AOU Ruggi d'Aragona (DAI Materno Infantile - Pediatria Generale), AOU Vanvitelli (DAI Materno Infantile), AORN Santobono (S.C. Pediatria 1-2); distribuzione diretta File F Canale D e implementazione dei piani su SINFONIA 2.0 con previa attivazione dei centri.

**Fonti nel database:** `note-regionali-2026 22.09.2026/DUPIXENT  Prot.N.0368563-2026.pdf#p1` · `note-regionali-2026 22.09.2026/DUPIXENT  Prot.N.0368563-2026.pdf#p2` · `note-regionali-2026 22.09.2026/DUPIXENT  Prot.N.0368563-2026.pdf#p3`

**Nota di controllo:** TESTO_SQLITE. La nota distingue nuove indicazioni da altre indicazioni già rimborsate elencate a p.2.

### F12 — ALYFTREK

**Domanda:** Secondo la nota ALIFTREK Prot.N.0259328-2026 relativa ad ALYFTREK, quali pazienti rientrano nell'indicazione e quali disposizioni sui centri o sulla prescrizione sono esplicite? Riporta le pagine.

**Risposta Gold proposta e controllata sul testo SQLite:** Il medicinale è chiamato ALYFTREK nel corpo della nota, mentre il nome del file è ALIFTREK. La p.1 riporta la fibrosi cistica in pazienti di età >=6 anni con almeno una mutazione non di classe I del gene CFTR; principio attivo combinato: deutivacaftor/tezacaftor/vanzacaftor. La p.2 indica classe A/PHT e prescrizione limitativa RRL da centri specializzati per fibrosi cistica. I centri regionali individuati sono entrambi presso AOU Federico II: Centro Pediatrico del Dipartimento Clinico di Pediatria Generale Specialistica e Centro Fibrosi Cistica dell'Adulto, UOC Geriatria del DAI Emergenze Cardiovascolari e Medicina Clinica. Distribuzione diretta File F Canale D; dal ciclo successivo al primo, erogazione tramite ASL di residenza sulla prescrizione del centro regionale; piani SINFONIA 2.0, previa attivazione e disponibilità effettiva del farmaco.

**Fonti nel database:** `note-regionali-2026 22.09.2026/ALIFTREK Prot.N.0259328-2026.pdf#p1` · `note-regionali-2026 22.09.2026/ALIFTREK Prot.N.0259328-2026.pdf#p2`

**Nota di controllo:** TESTO_SQLITE. Correggere il nome del MEDICINALE a ALYFTREK, mantenere ALIFTREK come filename.


## 4. Confronti fra documenti di anni diversi

### F13 — VOXZOGO

**Domanda:** Confrontando le note regionali VOXZOGO del 2022, 2023 e 2025, quali modifiche alle indicazioni o ai centri risultano esplicitamente documentate? Distingui variazioni dichiarate da semplici richiami.

**Risposta Gold proposta e controllata sul testo SQLite:** La nota VOXZOGO del 2022 (pp.1-2) descrive l'acondroplasia in pazienti da 2 anni in su con epifisi non chiuse e conferma genetica; il monitoraggio per innovatività riguarda, nella nota, l'intervallo 5-14 anni. La nota PG/2023/0390549 del 02/08/2023 (pp.1-2) documenta una NUOVA indicazione rimborsata per 2-5 anni e aggiorna il registro per l'intervallo 2-14 anni. La nota 0625081/2025 del 14/11/2025 (pp.1-2) documenta una nuova indicazione per 4 mesi-2 anni e l'aggiornamento del registro. Le tre note indicano presidi di riferimento per acondroplasia/codice RNG050; il confronto delle denominazioni leggibili non documenta una revoca esplicita dei centri precedenti. La nota 2025 p.3 aggiunge la gestione dei piani terapeutici su SINFONIA 2.0, richiamando la nota 2024/0503681 sul percorso di abilitazione. Non confondere fascia di indicazione e fascia di registro/innovatività; non dedurre annullamenti non dichiarati.

**Fonti nel database:** `PTR_Note regionali 2022/VOXZOGO.pdf#p1` · `PTR_Note regionali 2022/VOXZOGO.pdf#p2` · `PTR_NoteRegionali2023_020124/VOXZOGO_nota prot.0390549 del 02.08.2023.pdf#p1` · `PTR_NoteRegionali2023_020124/VOXZOGO_nota prot.0390549 del 02.08.2023.pdf#p2` · `note 2025 - 18.12.2025/VOXZOGO  Prot.N.0625081-2025.pdf#p1` · `note 2025 - 18.12.2025/VOXZOGO  Prot.N.0625081-2025.pdf#p2` · `note 2025 - 18.12.2025/VOXZOGO  Prot.N.0625081-2025.pdf#p3`

**Nota di controllo:** OCR 2022/2023: soglie età leggibili, elenchi ospedalieri formattati male; rilettura visiva consigliata prima di approvare gold finale.

### F14 — ENHERTU

**Domanda:** Fra le note regionali ENHERTU del 2023 e del 2024, quali differenze nelle indicazioni o nelle istruzioni di prescrizione risultano dichiarate dai testi? Cita entrambe.

**Risposta Gold proposta e controllata sul testo SQLite:** ENHERTU 2023 (nota 0370053/2023, pp.1-2): rimborsabilità per carcinoma mammario HER2-positivo non resecabile o metastatico negli adulti con precedenti trattamenti anti-HER2, con condizioni dettagliate sulla progressione; classe H/OSP, registro AIFA e prescrizione tramite oncologie dei GOM mammella della ROC, con elenco di strutture a p.2. ENHERTU 2024 (nota del 19/01/2024, pp.1-3) mantiene come precedente l'indicazione HER2-positivo mammaria e aggiunge due indicazioni rimborsate: (1) carcinoma mammario HER2-low non resecabile o metastatico dopo la chemioterapia prevista; (2) adenocarcinoma gastrico o della giunzione gastroesofagea avanzato HER2-positivo dopo precedente trastuzumab. Prevede registri specifici e associa per HER2-low le oncologie aderenti ai GOM mammella (p.2), per l'indicazione gastrica quelle dei GOM stomaco (p.3); ribadisce classe H/OSP e tracciatura su registri AIFA. Non concludere che un centro omesso da un elenco sia revocato senza un atto esplicito.

**Fonti nel database:** `PTR_NoteRegionali2023_020124/ENHERTU.pdf#p1` · `PTR_NoteRegionali2023_020124/ENHERTU.pdf#p2` · `ptr-note-regionali-11.12.24 ore 16.40/ENHERTU 2024.pdf#p1` · `ptr-note-regionali-11.12.24 ore 16.40/ENHERTU 2024.pdf#p2` · `ptr-note-regionali-11.12.24 ore 16.40/ENHERTU 2024.pdf#p3`

**Nota di controllo:** OCR 2023/2024; pagina 4 del PDF 2024 vuota nello snapshot. Elenchi GOM leggibili ma da controllare visivamente se si trascrivono nomi puntuali.

### F15 — KAFTRIO;KALYDECO

**Domanda:** Come si confrontano le condizioni di utilizzo documentate nella nota KAFTRIO+KALYDECO del 2022 e nella nota KAFTRIO del 2026? Separa indicazioni e prescrizioni e riporta le pagine.

**Risposta Gold proposta e controllata sul testo SQLite:** La nota KAFTRIO+KALYDECO del 20/10/2022 (pp.1-3) tratta l'estensione nella fibrosi cistica di KAFTRIO associato a ivacaftor/KALYDECO nei bambini da 6 a meno di 12 anni con almeno una mutazione F508del; descrive i genotipi previsti dai registri, la classe A/PHT, la prescrizione RRL e i due centri Federico II per fibrosi cistica pediatrica e dell'adulto. La nota KAFTRIO 0259319/2026 del 16/03/2026 (pp.1-2) riporta nuove indicazioni: compresse con ivacaftor dai 6 anni in su se è presente almeno una mutazione CFTR NON di classe I; granulato con ivacaftor da 2 a meno di 6 anni con almeno una mutazione CFTR NON di classe I. Riporta classe A/PHT, i medesimi due centri Federico II, distribuzione diretta File F Canale D e piani SINFONIA 2.0. La nota 2026 dichiara la chiusura dei registri KAFTRIO per le indicazioni precedentemente monitorate: è un fatto distinto dall'eventuale revoca di un'autorizzazione o di un centro, non dichiarata.

**Fonti nel database:** `PTR_Note regionali 2022/KAFTRIO+KALYDECO.pdf#p1` · `PTR_Note regionali 2022/KAFTRIO+KALYDECO.pdf#p2` · `PTR_Note regionali 2022/KAFTRIO+KALYDECO.pdf#p3` · `note-regionali-2026 22.09.2026/KAFTRIO  Prot.N.0259319-2026.pdf#p1` · `note-regionali-2026 22.09.2026/KAFTRIO  Prot.N.0259319-2026.pdf#p2`

**Nota di controllo:** OCR 2022: confrontare visivamente specifiche mutazioni e tabelle; p.4 2022 vuota nello snapshot.

### F16 — LIVMARLI

**Domanda:** Quali aggiornamenti delle indicazioni o dei centri sono espressamente riportati nella nota LIVMARLI del 2025 rispetto a quella del 2023? Indica i documenti e le pagine.

**Risposta Gold proposta e controllata sul testo SQLite:** La nota LIVMARLI 2023 (pp.1-2) concerne il prurito colestatico nella sindrome di Alagille dai 2 mesi di età, classe H e prescrizione RRL; autorizza i presidi di riferimento per ALGS/codice RN1350, con elenco comprendente, tra gli altri, Federico II. La nota LIVMARLI 0625098/2025 (p.1) aggiunge una NUOVA indicazione: colestasi intraepatica familiare progressiva (PFIC) dai 3 mesi, mantenendo esplicitamente come già rimborsata l'indicazione ALGS dai 2 mesi. Per PFIC la p.2 individua con codice RIG010 cinque strutture: AORN Moscati, AORN Santobono-Pausilipon, AOU Ruggi d'Aragona, AOU Vanvitelli, AOU Federico II. Riporta classe H, prescrizione RRL, distribuzione diretta File F Canale D e riferimento alla nota 0566666/2025 che trasferisce i piani terapeutici su SINFONIA 2.0 per tutte le indicazioni dal 03/11/2025. L'elenco del 2025 si riferisce alla PFIC, non implica la revoca dei centri ALGS del 2023.

**Fonti nel database:** `PTR_NoteRegionali2023_020124/LIVMARLI.pdf#p1` · `PTR_NoteRegionali2023_020124/LIVMARLI.pdf#p2` · `note 2025 - 18.12.2025/LIVMARLI Prot.N.0625098-2025.pdf#p1` · `note 2025 - 18.12.2025/LIVMARLI Prot.N.0625098-2025.pdf#p2`

**Nota di controllo:** OCR 2023: la tabella dei centri ALGS richiede conferma visiva per la disposizione su colonne; distinzione delle due indicazioni chiara.


## 5. Assenza di informazioni nello snapshot

### F17 — KAYFANDA

**Domanda:** Quanti pazienti in Campania hanno effettivamente iniziato il trattamento con KAYFANDA nel 2026, secondo le fonti acquisite?

**Risposta Gold proposta e controllata sul testo SQLite:** Il numero dei pazienti che in Campania hanno effettivamente iniziato KAYFANDA nel 2026 NON È DOCUMENTATO nello snapshot consultato. La nota KAYFANDA 0162816/2026 elenca indicazione, confezioni, centri designati e condizioni di attivazione/SINFONIA, ma non fornisce un conteggio degli inizi di trattamento; il database congelato non contiene una tabella di trattamenti individuali. Non si può concludere che i pazienti siano zero.

**Fonti nel database:** `note-regionali-2026 22.09.2026/KAYFANDA Prot.N.0162816-2026.pdf#p1` · `note-regionali-2026 22.09.2026/KAYFANDA Prot.N.0162816-2026.pdf#p2` · `note-regionali-2026 22.09.2026/KAYFANDA Prot.N.0162816-2026.pdf#p3`

**Nota di controllo:** NEGATIVO su corpus: schema senza trattamenti paziente; testo della nota e ricerca trasversale pagine senza conteggio pertinente.

### F18 — XEMBIFY

**Domanda:** Qual è la data effettiva della prima somministrazione di XEMBIFY presso ciascun presidio campano, secondo le fonti acquisite?

**Risposta Gold proposta e controllata sul testo SQLite:** La data della PRIMA SOMMINISTRAZIONE effettiva di XEMBIFY presso ciascun presidio campano NON È DOCUMENTATA nello snapshot. La nota XEMBIFY 2025 definisce le indicazioni e chiede di abilitare su SANIARP i centri già utilizzatori di immunoglobuline sottocutanee per la stessa indicazione, ma non riporta né date di somministrazione reale né un elenco nominativo di date/ospedali. Il database non ha registri di somministrazioni effettive. Non inferire tali date dal 18/07/2025 della nota.

**Fonti nel database:** `note 2025 - 18.12.2025/XEMBIFY.pdf#p1` · `note 2025 - 18.12.2025/XEMBIFY.pdf#p2`

**Nota di controllo:** NEGATIVO su corpus: nota senza date di trattamento e DB senza tabella di somministrazioni.

### F19 — HEMLIBRA

**Domanda:** Quante confezioni di HEMLIBRA sono state effettivamente dispensate dalle farmacie ospedaliere campane nel 2025?

**Risposta Gold proposta e controllata sul testo SQLite:** Il numero di confezioni HEMLIBRA realmente DISPENSATE dalle farmacie ospedaliere campane nel 2025 NON È DOCUMENTATO nello snapshot. La tabella AIFA registra sei codici/confezioni commerciali HEMLIBRA, ma sono tipologie autorizzative, non unità distribuite; la nota regionale 2024 disciplina indicazioni, centri e distribuzione diretta, senza quantità effettivamente dispensate nel 2025. Non rispondere «6» e non rispondere «0».

**Fonti nel database:** `ptr-note-regionali-11.12.24 ore 16.40/HEMLIBRA.pdf#p1` · `ptr-note-regionali-11.12.24 ore 16.40/HEMLIBRA.pdf#p2`

**Nota di controllo:** NEGATIVO su corpus: sei AIC AIFA non equivalgono a sei confezioni dispensate; nessuna tabella flussi farmacie.

### F20 — ENHERTU

**Domanda:** Qual è stata la spesa effettivamente sostenuta dalle aziende sanitarie campane per ENHERTU nel primo semestre 2025, secondo lo snapshot?

**Risposta Gold proposta e controllata sul testo SQLite:** La spesa EFFETTIVA sostenuta dalle aziende sanitarie campane per ENHERTU nel primo semestre 2025 NON È DOCUMENTATA nello snapshot. Le note regionali ENHERTU 2023 e 2024 disciplinano indicazioni, registri, centri, prescrizione e canali di rendicontazione (File F), ma non riportano importi di spesa effettiva per il periodo richiesto. Il database non comprende un conto economico/registro degli acquisti effettivi per tale intervallo. Non dedurre importi dalla classe H o dal numero di AIC.

**Fonti nel database:** `PTR_NoteRegionali2023_020124/ENHERTU.pdf#p1` · `PTR_NoteRegionali2023_020124/ENHERTU.pdf#p2` · `ptr-note-regionali-11.12.24 ore 16.40/ENHERTU 2024.pdf#p1` · `ptr-note-regionali-11.12.24 ore 16.40/ENHERTU 2024.pdf#p2` · `ptr-note-regionali-11.12.24 ore 16.40/ENHERTU 2024.pdf#p3`

**Nota di controllo:** NEGATIVO su corpus: non sono presenti flussi di spesa delle ASL del 2025 nelle tabelle o nelle note citate.

## Sintesi dei controlli

| Categoria | N | Gold già validati nel CSV del benchmark | Gold documentali proposti |
|---|---:|---:|---:|
| Dirette | 4 | 4 | 0 |
| Relazionali | 4 | 4 | 0 |
| Semantiche | 4 | 0 | 4 |
| Temporali | 4 | 0 | 4 |
| Assenza documentale | 4 | 0 | 4 |
| **Totale** | **20** | **8** | **12** |

Per la promozione delle 12 proposte a `VALIDATO`, effettuare una revisione umana delle pagine OCR incerte e delle esclusioni dei casi negativi. La verifica automatica `tesi.valida_gold` conferma la struttura delle citazioni e l'esistenza delle pagine, **non** giudica il significato normativo. Prima di questa approvazione non avviare `tesi.esegui_holdout`.