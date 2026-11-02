# Revisione del benchmark secondo le osservazioni del relatore — 2 novembre 2026

## Risultato e stato effettivo
Il benchmark **revisione 30** e' in tesi/benchmark_regolatorio_30.csv
(30 quesiti) e si fonda ESCLUSIVAMENTE sullo snapshot sperimentale
`bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`
prodotto dal workflow GitHub Actions n. `41436480339` (2 novembre 2026).

**8 risposte gold** riprendono una revisione visiva gia' documentata in
`gold_5_verificati_snapshot_online.json` e
`validazioni_manuali_aggiuntive_2026-11-02.json`.
Le **22 restanti sono DA_VERIFICARE**, e nel CSV hanno risposta e citazione gold
vuote; non si attribuiscono loro punteggi. I quattro casi NEGATIVA richiedono
una ricerca esaustiva nel corpus, non soltanto assenza di corrispondenza nel titolo.

Per un test pilota, il file `tesi/benchmark_regolatorio_8_validati.csv`
contiene solo gli otto gold precedentemente controllati sul medesimo snapshot.
La completezza dei testi degli atti, l'efficacia attuale dei provvedimenti e
l'eventuale presenza di fonti successive NON sono automaticamente certificate.

## Revisione delle domande
- **4 CONTROLLO**: indicazione, AIC, classi esplicite, date EMA — pochi casi base.
- **7 INTERPRETAZIONE**: condizioni/regole e liste complete di strutture delle note.
- **7 MULTIFONTE**: ciascuna parte della domanda richiede EMA, AIFA e Campania.
- **5 TEMPORALE**: atti e versioni, aggiornamenti, intervalli tra date **documentate**.
- **4 NEGATIVA**: casi di dati operativi non necessariamente presenti nello snapshot; verifica
  manuale dell'assenza prima di dichiararli gold.
- **3 RIMANDI**: relazione esplicita tra due note o tra nota e provvedimento.
  
Eliminate le domande sul formato piu' adatto ai bambini e quelle ripetitive
marchio/principio attivo o semplici elenchi confezioni.
Le domande possono essere proposte da medici/farmacisti, ma valutano
**informazioni regolatorie**, non decisioni cliniche individuali.

## Fonti e temporalita'
Una singola fotografia sperimentale e' l'insieme di **byte congelati** dello
SQLite, non la finzione che tutti i suoi atti abbiano la medesima data.

- Snapshot SQLite: 02/11/2026, hash sopra.
- EMA: record con data di decisione UE del singolo medicinale; il download
  del catalogo non e' la data della sua autorizzazione.
- AIFA classe A/H: elenchi del **30/06/2026**, anche se acquisiti il 02/11.
  La pagina AIFA documenta questa data (https://www.aifa.gov.it/liste-farmaci-a-h).
  Una data di aggiornamento dell'elenco NON equivale a data di determina AIFA.
- Regione Campania: note del 2022-2026 con protocolli, date e pagine.
  Una tabella di strutture AIFA non prova da sola l'abilitazione regionale
  per la specifica indicazione, ne' l'effettiva attivazione operativa.

Per una misura **EMA -> determina AIFA -> Regione** e' necessario verificare
che nel corpus sia presente la determina AIFA con data dell'atto.
Con la sola lista A/H non si puo' calcolare il passaggio AIFA.
Q20 e Q23 distinguono date di atti e date di liste proprio per evitare questo errore.
Un quesito non supportato dal corpus resta DA_VERIFICARE o viene SCARTATO,
non deve essere risolto cercando fuori dal database.

### Classe C
Nel database sperimentale, `classe_a_h_snapshot` e' NULL quando
l'AIC non compare negli elenchi A/H caricati. La dashboard puo' continuare
a mostrare C per convenzione, ma questa e' una **deduzione per esclusione**,
non la prova che AIFA abbia classificato ufficialmente la confezione in C.
Il testo delle risposte TAG e Text-to-SQL specifica tale distinzione.

## Regole di valutazione
Una risposta e' corretta solo se:
1. Riporta TUTTI gli elementi richiesti (es. ogni centro per ciascuna indicazione).
2. Le citazioni rimandano a documenti/pagine o identificativi AIFA/EMA effettivamente
   presenti nello SQLite; niente fonti aggiunte dall'esterno.
3. Attribuisce dati e date alla fonte corretta (EMA, AIFA o nota regionale).
4. Per i quesiti negativi usa "non documentato NELLO SNAPSHOT" solo dopo la
   verifica esaustiva; non conclude "vietato/non esistente".
5. Non inventa termini, centri, classificazioni, date di attivazione.
6. Non integra risposte incomplete con formule "tra cui"/"vedere nota"/"fare riferimento
   all'RCP". L'elenco incompleto va valutato come errore, non come risposta parzialmente esatta.

Valutare separatamente accuratezza della risposta, precisione delle citazioni,
correttezza temporale, astensione appropriata, latenza, chiamate e token.
Riportare il denominatore dei gold effettivamente VALIDATI, evitando una
"accuratezza sulle 30" finche' non esistono 30 gold verificati.
Il programma di valutazione non assegna giudizi 0/1 automaticamente.

## Esecuzione senza API
1. Scaricare l'artefatto GitHub Actions
   [tesi-snapshot-fonti-online, run 41436480339](https://github.com/MarcoFabozzi/farmaquery/actions/runs/41436480339)
   e collocare `esperimento_online.sqlite` e `manifest_fonti_online.json`
   in `dist_tesi/`.
2. Controllare il benchmark senza alcuna chiamata al provider:
   
   `python -m unittest -v tesi.tests.test_benchmark_regolatorio_30`
   
   `python -m tesi.audit_benchmark_regolatorio --db dist_tesi/esperimento_online.sqlite --manifest dist_tesi/manifest_fonti_online.json --out dist_tesi/audit_30.json`
3. Validare i 22 gold mancanti sui documenti ORIGINARI (e sulla loro
   versione presente nello SQLite), compilare risposta **completa**,
   fonti esatte e nota revisore, solo allora passare a VALIDATO.
   Per un quesito NEGATIVA, riportare almeno l'ambito delle ricerche nel
   corpus, gli alias/principi attivi verificati e le varianti dei nomi in
   note_revisore (minimo 80 caratteri), con origine_validazione nel formato
   `RICERCA_ESAUSTIVA: descrizione della revisione`.
4. Test senza chiamate:
   
   `python -m tesi.esegui_benchmark --db dist_tesi/esperimento_online.sqlite --manifest dist_tesi/manifest_fonti_online.json --domande tesi/benchmark_regolatorio_8_validati.csv --max-domande 2`
5. Test reale sul sottoinsieme validato solo con consenso e quota API adeguata,
   usando `--conferma-chiamate`, e lo stesso identico modello.
   Per il benchmark completo usare il CSV di 30 **solo quando** saranno validati
   tutti i gold delle domande selezionate.

I test del protocollo non invocano Gemini; TAG puo' generare diverse
richieste API per domanda e superare rapidamente i limiti del piano gratuito.

## Limitazioni da esplicitare in tesi
- TAG usa pre-recupero deterministico da SQLite seguito da filtro semantico
  LOTUS e sintesi. Text-to-SQL usa query generate dal LLM: il confronto
  e' tra **pipeline complete**, non tra due meccanismi astratti isolati.
- Le fonti vengono assegnate attraverso processi differenti; misurare il numero
  di candidate e le citazioni, non confondere "fonte recuperata" con "fonte usata".
- I documenti aggiornati dopo il congelamento non si mescolano ai gold.
  Se viene scelta una versione successiva, occorre un **nuovo benchmark
  riprodotto e riverificato**, non cambiare l'hash a mano.
- Gli artefatti GitHub Actions hanno **scadenza**: conservare una copia
  del file SQLite e del manifesto con i rispettivi SHA256 in un archivio
  durevole e accessibile alla commissione.

La vecchia generazione di 36 domande candidate resta per la tracciabilita'
ma **non e' il protocollo rivisto**.
