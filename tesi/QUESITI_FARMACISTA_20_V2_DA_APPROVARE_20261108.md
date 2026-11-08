# FarmaQuery — 20 domande realistiche da farmacista (proposta V2)

**Data:** 8 novembre 2026  
**Stato:** **BOZZA DA APPROVARE**, non somministrata ai motori. Nessuna risposta Gold assegnata in questa versione.  
**Perimetro:** informazioni disponibili nello snapshot SQLite regolatorio del 2 novembre 2026. Le formulazioni riguardano verifiche documentali: **non richiedono consigli clinici personalizzati**, non attestano la situazione attuale né sostituiscono le fonti ufficiali.

## Criterio di scelta

Le quattro categorie concordate con il relatore — **SEMPLICE, CATEGORIA_IMPLICITA, RIMANDO, NESSUNA_RISPOSTA** — sono mantenute. Aggiungiamo **MULTIFONTE** per testare esplicitamente le relazioni tra EMA, AIFA, GU e Regione. **Quattro domande per categoria = 20**.

Le domande sono concepite per attività di farmacisti ospedalieri e farmacisti impegnati nella verifica regolatoria: prima di dispensare, registrare, programmare l'approvvigionamento o controllare i centri, devono sapere cosa attestano i documenti. Le domande sono limitate al corpus, quindi le conclusioni non rappresentano automaticamente la normativa vigente.

Le domande pilota già usate e i quesiti F01-F20 della prima proposta rimangono **materiali di sviluppo e non sono cancellati**. Alcuni medicinali o argomenti sono già comparsi in test esplorativi: non considerare automaticamente questa V2 un holdout indipendente prima di verificare la separazione dai test precedenti. Il gold si compilerà **solo dopo l'approvazione del questionario**, mediante revisione documentale.


## 1. Domande semplici — verifiche di prescrizione e dispensazione

Il farmacista controlla classe, forma o via di somministrazione, tipo di prescrizione, canale di distribuzione e piano terapeutico su un record o una nota ben identificata.

**FAR01.** Per XEMBIFY qual è la classe di rimborsabilità? Quale via di somministrazione è prevista? Che tipo di prescrizione richiede la nota campana?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — XEMBIFY.pdf, pp. 1-2: classe, via e regime di fornitura; non confondere accesso regionale e giacenze.

</details>

**FAR02.** Per KAYFANDA, la nota regionale prevede distribuzione diretta oppure convenzionata? Quale canale File F e quale sistema di piani terapeutici indica?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KAYFANDA Prot.N.0162816-2026.pdf, p. 3: File F e SINFONIA.

</details>

**FAR03.** Per HEMLIBRA AIC 046130047, quale classe risulta nell'elenco AIFA acquisito e la nota campana richiede un piano terapeutico?

<details><summary>Fonti previste e controllo da eseguire</summary>

AIFA+REGIONE — AIFA AIC 046130047, lista A/H 30/06/2026; HEMLIBRA.pdf, p. 1.

</details>

**FAR04.** Per SIVEXTRO, quale classe risulta per la confezione in compresse AIC 044020016? Invece per quella endovenosa AIC 044020030? Le due formulazioni hanno la stessa classe documentata?

<details><summary>Fonti previste e controllo da eseguire</summary>

AIFA — AIFA confezioni, AIC 044020016 e 044020030, campi classe_a_h_snapshot e data.

</details>


## 2. Categoria implicita — indicazione e centri

La domanda parte da una patologia o da un servizio ospedaliero, non dal nome del farmaco. Il sistema deve individuare i documenti pertinenti, non scambiare l'indicazione di una tabella con quella di un'altra e controllare le pagine.

**FAR05.** Dobbiamo verificare le terapie per miastenia gravis generalizzata prescrivibili presso l'AOU Federico II: quali medicinali sono individuati dalle note campane per questa indicazione? Per ciascuno indica il documento e la pagina del centro, senza confondere le tabelle per neuromielite ottica.

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — Riferimenti da controllare: VYVGART, SOLIRIS, ULTOMIRIS, ZILBRYSQ e altre note eventualmente pertinenti; centro e indicazione nella stessa sezione.

</details>

**FAR06.** Per una richiesta relativa alla polineuropatia demielinizzante infiammatoria cronica (CIDP), quali medicinali citati nelle note regionali indicano l'AOU Federico II tra i centri prescrittori? Specifica se una nota aggiorna anche i centri di un altro medicinale.

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KIOVIG.pdf p.2; HYQVIA CIDP.pdf p.2 con riferimento HIZENTRA; controllo completo delle note pertinenti.

</details>

**FAR07.** Nella programmazione della farmacia ospedaliera per la fibrosi cistica, quali medicinali citati nelle note regionali riportano centri prescrittori dell'AOU Federico II? Distingui le eventuali fasce d'età e cita la nota e la pagina per ciascuna terapia.

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KAFTRIO+KALYDECO.pdf, KAFTRIO 2026, KALYDECO 2026, ALIFTREK/ALYFTREK 2026; rivedere tutte le note pertinenti.

</details>

**FAR08.** Per pazienti con sindrome di Alagille e prurito colestatico, quali medicinali hanno una nota campana che include l'AOU Federico II fra i centri prescrittori? Riporta per ciascuno l'età minima documentata e la pagina della nota.

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — LIVMARLI.pdf 2023 e KAYFANDA Prot.N.0162816-2026.pdf; verificare presenza di ulteriori note e distinzione delle indicazioni.

</details>


## 3. Rimandi — modifiche tra note e registri

Il farmacista confronta documenti di anni diversi per interpretare un'estensione di indicazione, un aggiornamento di registro o un cambio di procedura. La sola presenza di un documento successivo non dimostra una revoca.

**FAR09.** È arrivata una prescrizione di VOXZOGO per un bambino di 18 mesi. Quale aggiornamento della nota regionale del 2025 modifica il quadro documentato nel 2023 per questa fascia d'età? Distingui indicazione rimborsata e aggiornamento del registro.

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — VOXZOGO nota 2023 pp.1-2; VOXZOGO Prot.N.0625081-2025.pdf pp.1-3; risposta riferita al corpus, non giudizio clinico sul paziente.

</details>

**FAR10.** Per attivare il registro ENHERTU in una nuova indicazione, che cosa cambia nella nota regionale del 2024 rispetto a quella del 2023 per carcinoma mammario HER2-low e carcinoma gastrico? Quali GOM sono previsti per ciascuna indicazione?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — ENHERTU.pdf 2023 pp.1-2; ENHERTU 2024.pdf pp.1-3; GOM mammella e stomaco, evitare revoche inferite.

</details>

**FAR11.** Per una prescrizione di KAFTRIO, quali nuove fasce d'età e condizioni relative alle mutazioni CFTR sono riportate nella nota 2026 rispetto a KAFTRIO+KALYDECO del 2022? Che cosa viene detto sui registri di monitoraggio precedenti?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KAFTRIO+KALYDECO.pdf 2022 pp.1-3; KAFTRIO Prot.N.0259319-2026.pdf pp.1-2.

</details>

**FAR12.** La nota LIVMARLI del 2025 aggiunge la PFIC alla precedente indicazione per sindrome di Alagille del 2023: quali centri sono individuati per la nuova indicazione e che cosa dispone sul passaggio dei piani terapeutici a SINFONIA?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — LIVMARLI.pdf 2023 pp.1-2; LIVMARLI Prot.N.0625098-2025.pdf pp.1-2; separare elenchi ALGS e PFIC.

</details>


## 4. Nessuna risposta — limiti del corpus

Domande realistiche su stato operativo, disponibilità reale, terapie effettuate e prezzo d'acquisto: il sistema deve distinguere la designazione normativa dai dati che un gestionale locale o un registro operativo potrebbe contenere ma che il database sperimentale non documenta.

**FAR13.** La nota KAYFANDA autorizza alcuni centri alla prescrizione: dal database possiamo sapere se, al 2 novembre 2026, i relativi medici erano già stati effettivamente abilitati su SINFONIA?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — KAYFANDA Prot.N.0162816-2026.pdf, pp.2-3: condizioni di attivazione; assenza di log utenti.

</details>

**FAR14.** La farmacia dell'AORN Santobono-Pausilipon aveva realmente XEMBIFY disponibile in magazzino il 2 novembre 2026? Quale evidenza di giacenza risulta nel database?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — XEMBIFY.pdf pp.1-2 e verifica dello schema: il corpus non è un gestionale di magazzino.

</details>

**FAR15.** Quanti pazienti hanno effettivamente iniziato ALYFTREK nei due centri per fibrosi cistica della Federico II entro il 2 novembre 2026?

<details><summary>Fonti previste e controllo da eseguire</summary>

REGIONE — ALIFTREK Prot.N.0259328-2026.pdf pp.1-2 e schema: centri individuati, assenza di dati paziente.

</details>

**FAR16.** Qual è il prezzo netto realmente pagato dall'AOU Federico II per un flaconcino di ENHERTU nel primo semestre 2025? È ricavabile dai documenti presenti nello snapshot?

<details><summary>Fonti previste e controllo da eseguire</summary>

AIFA+REGIONE — ENHERTU note 2023/2024 e tabelle AIFA: non equiparare classe/prezzo di listino a prezzo effettivo di acquisto.

</details>


## 5. Categoria aggiuntiva: multifonte — EMA/AIFA/GU/Regione

Il farmacista riconcilia autorizzazione UE, AIC e classe rimborsabilità, provvedimenti nazionali e condizioni regionali. Non confondere autorizzazione, rimborsabilità, indicazione, abilitazione operativa e somministrazione.

**FAR17.** Per WEGOVY, l'autorizzazione europea implica automaticamente la rimborsabilità SSN? Confronta l'indicazione registrata da EMA con la classe attribuita alle sei confezioni nella determina pubblicata in Gazzetta Ufficiale 23A02767, riportando gli AIC.

<details><summary>Fonti previste e controllo da eseguire</summary>

EMA+GU — EMA EMEA/H/C/005422 e GU atto 23A02767, AIC confezioni; evitare confusione tra autorizzazione e rimborso.

</details>

**FAR18.** Per DUVYZAT, quali pazienti rientrano nell'indicazione registrata da EMA, quale classe risulta per AIC 052202013 nello snapshot AIFA e quali strutture regionali sono designate per la prescrizione nella nota campana 2026?

<details><summary>Fonti previste e controllo da eseguire</summary>

EMA+AIFA+REGIONE — Record EMA DUVYZAT, AIFA AIC 052202013, DUVYZAT Prot.N.0368583-2026.pdf pp.1-2.

</details>

**FAR19.** Per la confezione DUPIXENT AIC 045676069, quale classe risulta nel database AIFA? Per l'indicazione BPCO, quali centri la nota campana 2026 considera prescrittori e quale monitoraggio AIFA è previsto?

<details><summary>Fonti previste e controllo da eseguire</summary>

AIFA+REGIONE — AIFA AIC 045676069; DUPIXENT Prot.N.0368563-2026.pdf pp.1-3, Nota AIFA 99 e registro BPCO.

</details>

**FAR20.** Per AMVUTTRA, quali differenze emergono fra le indicazioni europee per polineuropatia da transtiretina e cardiomiopatia ATTR-CM e le rispettive liste di centri prescrittori indicate dalla nota campana del 2026? Specifica anche la diversa rendicontazione per somministrazione ambulatoriale e domiciliare.

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
