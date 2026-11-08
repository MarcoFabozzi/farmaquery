# FarmaQuery — 20 domande realistiche da farmacista (proposta V2)

**Data:** 8 novembre 2026  
**Stato:** **BOZZA DA APPROVARE**, non somministrata ai motori. Nessuna risposta Gold assegnata in questa versione.
**Approvazione:** FAR01–FAR08 scelte dall'utente (formato interrogativo uniformato); FAR09–FAR12 riformulate secondo la definizione originaria di «RIMANDO»; FAR13–FAR16 senza riferimento alla data dello snapshot nel testo delle domande; FAR17–FAR20 ancora in revisione.  
**Perimetro:** informazioni disponibili nello snapshot SQLite regolatorio del 2 novembre 2026. Le formulazioni riguardano verifiche documentali: **non richiedono consigli clinici personalizzati**, non attestano la situazione attuale né sostituiscono le fonti ufficiali.

## Criterio di scelta

Le quattro categorie concordate con il relatore — **SEMPLICE, CATEGORIA_IMPLICITA, RIMANDO, NESSUNA_RISPOSTA** — sono mantenute. Aggiungiamo **MULTIFONTE** per testare esplicitamente le relazioni tra EMA, AIFA, GU e Regione. **Quattro domande per categoria = 20**.

Le domande sono concepite per attività di farmacisti ospedalieri e farmacisti impegnati nella verifica regolatoria: prima di dispensare, registrare, programmare l'approvvigionamento o controllare i centri, devono sapere cosa attestano i documenti. Le domande sono limitate al corpus, quindi le conclusioni non rappresentano automaticamente la normativa vigente.

Le domande pilota già usate e i quesiti F01-F20 della prima proposta rimangono **materiali di sviluppo e non sono cancellati**. Alcuni medicinali o argomenti sono già comparsi in test esplorativi: non considerare automaticamente questa V2 un holdout indipendente prima di verificare la separazione dai test precedenti. Il gold si compilerà **solo dopo l'approvazione del questionario**, mediante revisione documentale.


## 1. Domande semplici — verifiche di prescrizione e dispensazione

Il farmacista controlla classe, forma o via di somministrazione, tipo di prescrizione, canale di distribuzione e piano terapeutico su un record o una nota ben identificata.

**FAR01.**

Per XEMBIFY qual è la classe di rimborsabilità?

Quale via di somministrazione è prevista?

Che tipo di prescrizione richiede la nota campana?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — XEMBIFY.pdf, pp. 1-2: classe, via e regime di fornitura; non confondere accesso regionale e giacenze.

</details>

**FAR02.**

Per KAYFANDA, la nota regionale prevede distribuzione diretta oppure convenzionata?

Quale canale File F e quale sistema di piani terapeutici indica?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KAYFANDA Prot.N.0162816-2026.pdf, p. 3: File F e SINFONIA.

</details>

**FAR03.**

Per HEMLIBRA AIC 046130047, quale classe risulta nell'elenco AIFA acquisito?

La nota campana richiede un piano terapeutico?

<details><summary>Fonti previste e controllo da eseguire</summary>

AIFA+REGIONE — AIFA AIC 046130047, lista A/H 30/06/2026; HEMLIBRA.pdf, p. 1.

</details>

**FAR04.**

Per SIVEXTRO, quale classe risulta per la confezione in compresse AIC 044020016?

Invece per quella endovenosa AIC 044020030?

Le due formulazioni hanno la stessa classe documentata?

<details><summary>Fonti previste e controllo da eseguire</summary>

AIFA — AIFA confezioni, AIC 044020016 e 044020030, campi classe_a_h_snapshot e data.

</details>


## 2. Categoria implicita — indicazione e centri

La domanda parte da una patologia o da un servizio ospedaliero, non dal nome del farmaco. Il sistema deve individuare i documenti pertinenti, non scambiare l'indicazione di una tabella con quella di un'altra e controllare le pagine.

**FAR05.**

Quali sono le terapie per miastenia gravis generalizzata prescrivibili presso l'AOU Federico II?

Quali medicinali sono individuati dalle note campane per questa indicazione?

Per ciascuno, qual è il documento e la pagina che individuano il centro per la miastenia gravis e non per la neuromielite ottica?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — Riferimenti da controllare: VYVGART, SOLIRIS, ULTOMIRIS, ZILBRYSQ e altre note eventualmente pertinenti; centro e indicazione nella stessa sezione.

</details>

**FAR06.**

Per una richiesta relativa alla polineuropatia demielinizzante infiammatoria cronica (CIDP), quali medicinali citati nelle note regionali indicano l'AOU Federico II tra i centri prescrittori?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KIOVIG.pdf p.2; HYQVIA CIDP.pdf p.2 con riferimento HIZENTRA; controllo completo delle note pertinenti.

</details>

**FAR07.**

Nella programmazione della farmacia ospedaliera per la fibrosi cistica, quali medicinali citati nelle note regionali riportano centri prescrittori dell'AOU Federico II?

Quali fasce d'età sono previste per ciascuna terapia, dove documentate?

In quale nota e a quale pagina è individuato il centro?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KAFTRIO+KALYDECO.pdf, KAFTRIO 2026, KALYDECO 2026, ALIFTREK/ALYFTREK 2026; rivedere tutte le note pertinenti.

</details>

**FAR08.**

Per pazienti con sindrome di Alagille e prurito colestatico, quali medicinali hanno una nota campana che include l'AOU Federico II fra i centri prescrittori?

Qual è per ciascuno l'età minima documentata?

Qual è la pagina della nota che individua il centro?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — LIVMARLI.pdf 2023 e KAYFANDA Prot.N.0162816-2026.pdf; verificare presenza di ulteriori note e distinzione delle indicazioni.

</details>


## 3. Rimandi espliciti tra documenti

Questa categoria valuta il riconoscimento di **un atto esplicitamente citato da un altro documento** e la corretta identificazione del rapporto dichiarato: semplice richiamo, applicazione di una procedura, eventuale annullamento o sostituzione. **Non** è un confronto generico tra note di anni differenti. Un annullamento non può essere dedotto se non compare nel testo.

**FAR09.**

Per l'abilitazione alla prescrizione di VOXZOGO su SINFONIA, quale nota precedente è richiamata dal provvedimento regionale del 2025?

Quale procedura viene collegata a quel richiamo?

Il documento dichiara l'annullamento o la sostituzione della nota precedente?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — VOXZOGO Prot.N.0625081-2025.pdf, p. 3: cita Nota PG/2024/0503681 del 24/10/2024, chiarimento del percorso di abilitazione su SINFONIA; distinguere richiamo da annullamento.

</details>

**FAR10.**

Per la gestione dei piani terapeutici di LIVMARLI, quale nota precedente è richiamata nel provvedimento regionale del 2025?

Che cosa stabilisce quel richiamo sul passaggio a SINFONIA e sulla chiusura di SANIARP?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — LIVMARLI Prot.N.0625098-2025.pdf, p. 2: cita Nota Prot.N.0566666/2025 del 28/10/2025, passaggio a SINFONIA dal 03/11/2025 e chiusura SA.NI.A.R.P.; distinguere richiamo procedurale da sostituzione.

</details>

**FAR11.**

Per la rendicontazione delle somministrazioni di AMVUTTRA, quale nota precedente è richiamata dal documento regionale del 2026?

Quale rapporto viene esplicitamente dichiarato con la nota richiamata?

Quali canali File F sono indicati per il trattamento ambulatoriale e quello domiciliare?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — AMVUTTRA Prot.N.0634617-2026.pdf, p. 3: richiamo alla nota prot.0493819 del 16/10/2023; File F canale E per ambulatorio e canale D per domicilio. Verificare il rapporto esplicito prima del Gold.

</details>

**FAR12.**

Per prescrivere DUPIXENT nell'esofagite eosinofila, quale determina AIFA viene richiamata per il piano terapeutico?

Quale provvedimento regionale è richiamato per individuare i centri pediatrici?

Quale funzione svolge ciascun riferimento?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — DUPIXENT Prot.N.0368563-2026.pdf, pp. 2-3: determina AIFA Pres.102/2026 per piano terapeutico esofagite eosinofila; D.D. regionale 182/2022 per centri pediatrici; distinguere i due ruoli.

</details>


## 4. Nessuna risposta — limiti del corpus

Domande realistiche su stato operativo, disponibilità reale, terapie effettuate e prezzo d'acquisto: il sistema deve distinguere la designazione normativa dai dati che un gestionale locale o un registro operativo potrebbe contenere ma che il database sperimentale non documenta.

**FAR13.**

Per KAYFANDA, i medici dei centri individuati dalla Regione risultano effettivamente già abilitati alla prescrizione su SINFONIA?

Il database contiene una conferma operativa di tale abilitazione?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KAYFANDA Prot.N.0162816-2026.pdf, pp.2-3: condizioni di attivazione; assenza di log utenti.

</details>

**FAR14.**

La farmacia dell'AORN Santobono-Pausilipon dispone effettivamente di XEMBIFY in magazzino?

Le fonti del database riportano una giacenza verificabile?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — XEMBIFY.pdf pp.1-2 e verifica dello schema: il corpus non è un gestionale di magazzino.

</details>

**FAR15.**

Quanti pazienti hanno effettivamente iniziato ALYFTREK nei due centri per fibrosi cistica dell'AOU Federico II?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — ALIFTREK Prot.N.0259328-2026.pdf pp.1-2 e schema: centri individuati, assenza di dati paziente.

</details>

**FAR16.**

Qual è il prezzo netto realmente pagato dall'AOU Federico II per un flaconcino di ENHERTU nel primo semestre 2025?

È ricavabile dai documenti presenti nello snapshot?

<details><summary>Fonti previste e controllo da eseguire</summary>

AIFA+REGIONE — ENHERTU note 2023/2024 e tabelle AIFA: non equiparare classe/prezzo di listino a prezzo effettivo di acquisto.

</details>


## 5. Categoria aggiuntiva: multifonte — EMA/AIFA/GU/Regione

Il farmacista riconcilia autorizzazione UE, AIC e classe rimborsabilità, provvedimenti nazionali e condizioni regionali. Non confondere autorizzazione, rimborsabilità, indicazione, abilitazione operativa e somministrazione.

**FAR17.**

Per WEGOVY, l'autorizzazione europea implica automaticamente la rimborsabilità SSN?

Quale indicazione è registrata da EMA?

Quale classe viene attribuita alle sei confezioni nella determina pubblicata in Gazzetta Ufficiale 23A02767 e quali sono i rispettivi AIC?

<details><summary>Fonti previste e controllo da eseguire</summary>

EMA+GU — EMA EMEA/H/C/005422 e GU atto 23A02767, AIC confezioni; evitare confusione tra autorizzazione e rimborso.

</details>

**FAR18.**

Per DUVYZAT, quali pazienti rientrano nell'indicazione registrata da EMA?

Quale classe risulta per AIC 052202013 nello snapshot AIFA?

Quali strutture regionali sono designate per la prescrizione nella nota campana del 2026?

<details><summary>Fonti previste e controllo da eseguire</summary>

EMA+AIFA+REGIONE — Record EMA DUVYZAT, AIFA AIC 052202013, DUVYZAT Prot.N.0368583-2026.pdf pp.1-2.

</details>

**FAR19.**

Per la confezione DUPIXENT AIC 045676069, quale classe risulta nel database AIFA?

Per l'indicazione BPCO, quali centri la nota campana del 2026 considera prescrittori?

Quale monitoraggio AIFA è previsto?

<details><summary>Fonti previste e controllo da eseguire</summary>

AIFA+REGIONE — AIFA AIC 045676069; DUPIXENT Prot.N.0368563-2026.pdf pp.1-3, Nota AIFA 99 e registro BPCO.

</details>

**FAR20.**

Per AMVUTTRA, quali differenze emergono fra le indicazioni europee per polineuropatia da transtiretina e cardiomiopatia ATTR-CM e le rispettive liste di centri prescrittori indicate dalla nota campana del 2026?

Quale rendicontazione è prevista per le somministrazioni ambulatoriali e domiciliari?

<details><summary>Fonti previste e controllo da eseguire</summary>

EMA+REGIONE — Record EMA AMVUTTRA; AMVUTTRA Prot.N.0634617-2026.pdf, pp.1-3: due tabelle indicazione-centro e File F E/D.

</details>

## Regole di valutazione prima dei test

- Nessuna risposta viene considerata corretta solo perché una SELECT termina senza errori.
- Per le domande a elenco il Gold deve essere **esaustivo rispetto al perimetro definito**; indicazione terapeutica, struttura e pagina devono riferirsi allo stesso rapporto.
- Per le domande sui rimandi va distinto l'effetto esplicito del provvedimento da una semplice citazione di un atto precedente.
- Per le domande senza risposta il Gold dovrà riportare **«non documentato nel corpus»** se confermato da controllo di schema e fonti: non «zero» o «mai avvenuto».
- Per le domande multifonte va verificata ogni componente contro la fonte corrispondente, senza inferire rimborsabilità dall'autorizzazione EMA.
- I due sistemi saranno interrogati **con la stessa domanda letterale** e lo stesso snapshot, solo dopo l'approvazione del Gold e il congelamento del questionario; risposte e tempi vanno registrati senza correggere i motori in funzione degli esiti.

## Documento macchina

Le medesime 20 domande sono nel CSV `tesi/QUESITI_FARMACISTA_20_V2_DA_APPROVARE_20261108.csv`, con campi previsti per risposta Gold e citazioni **intenzionalmente vuoti**. Questo file serve per scegliere e approvare le formulazioni, non per avviare già il benchmark.
