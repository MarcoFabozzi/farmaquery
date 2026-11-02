# Revisione del benchmark FarmaQuery — osservazioni del relatore (02/11/2026)

## Stato e perimetro
Il file `benchmark_revisione_relatori_30_candidati.csv` è una **lista di 30 domande candidate**, non un benchmark validato.
Nessuna risposta gold è stata inventata: `risposta_gold` e `fonti_gold` sono vuote e lo stato iniziale è `DA_VERIFICARE`.
Non inviare il CSV al runner di esperimenti LLM come se fosse validato.

## Correzioni applicate
- Escluse domande di consiglio clinico, incluso il quesito sul formato più adatto ai bambini.
- Eliminate le domande di semplice marchio→principio attivo e gli elenchi generici di confezioni, mantenendo quattro controlli regolatori.
- Sostituite le risposte vaghe con domande che richiedono risultati completi: per esempio tutti i centri AMVUTTRA per ciascuna indicazione.
- Aggiunte domande su rimandi normativi, documenti sostitutivi, condizioni regionali, differenze tra indicazioni e astensione.
- Nelle domande che incrociano EMA/AIFA/Regione si richiedono AIC e documenti specifici.

## Fotografia temporale unica: cosa significa
Lo snapshot del benchmark deve essere **un solo file SQLite immutabile** condiviso da TAG e Text-to-SQL; un manifesto SHA-256 deve attestarlo.
Questo NON implica che le fonti abbiano tutte la stessa data: i metadati mantengono la data di pubblicazione o di riferimento.
Gli elenchi A/H attualmente documentati sono del **30/06/2026**, mentre lo snapshot è stato costruito nel novembre 2026. Non indicare come «classe vigente al 02/11/2026» un valore attestato al 30/06/2026.
Non confondere `data_decisione_ue`, data della determina AIFA, data elenco A/H, data della nota regionale e data di acquisizione.
Domande sui tempi EMA→AIFA→Regione sono valide **solo quando le date dei tre provvedimenti sono effettivamente presenti**. La data dell'elenco A/H non sostituisce la data della determina.
Classe C ottenuta per esclusione da A/H: **regola applicativa derivata, non dato ufficiale certificato**. Per il gold valutare una classe solo se documentata con una fonte adatta.

## Materiale già presente nel repository
- `gold_5_verificati_snapshot_online.json`: cinque risposte già dichiarate validate su PDF originali, con hash e pagine.
- `validazioni_manuali_aggiuntive_2026-11-02.json`: ulteriori sette verifiche su PDF, con limiti annotati.
- `prepara_snapshot_online.py` crea tabelle `ema_medicinali`, `aifa_confezioni`, `note`, `pagine`, `pagine_fts`, `strutture_registri`, `rimandi_candidati`, `centri_candidati` e `fonti_snapshot`.

Questi 12 record NON vanno copiati automaticamente nel nuovo CSV: per ogni nuova formulazione della domanda si deve verificare che la risposta gold sia esatta e completa. La presenza di `rimandi_candidati` e `centri_candidati` **non** prova da sola il significato giuridico del rimando o l'autorizzazione di un centro.

## Checklist obbligatoria per ogni risposta gold
1. Confermare che il documento o record sia incluso nello **stesso snapshot** usato dai due metodi. Le fonti esterne non sono ammissibili come evidenza per il gold di quel confronto.
2. Verificare manualmente PDF originale e testo estratto, con identificativo del documento, numero di pagina, AIC/EMA ID e hash dove disponibili.
3. Risposta completa, controllabile, senza «tra cui», «vedere il documento» o liste incomplete. Specificare esattamente indicazione e data di riferimento.
4. Per domande senza risposta, effettuare ricerca anche per sinonimi, nome commerciale, principio attivo, AIC, testo delle pagine e documenti con titoli diversi. Documentare la copertura della ricerca. Assenza nel corpus NON equivale ad assenza nella realtà.
5. Inserire solo dopo la verifica `risposta_gold`, `fonti_gold`, `note_revisore` e `stato_validazione=VALIDATO`. Marcare `SCARTATO` le domande impossibili da verificare senza nuove fonti.
6. Per le domande multifonte attribuire ogni parte della risposta alla sua fonte, evitando di trattare una pagina regionale come prova di classificazione AIFA aggiornata.

## Problemi aperti prima degli esperimenti
- Rivedere documenti e liste completi per SOLIRIS, KEYTRUDA e per tutti i centri enumerati: alcune validazioni preesistenti sintetizzano le liste per ASL e non bastano per un gold esaustivo.
- CAMZYOS e BEYONTTRA: controllare il provvedimento precedente esatto, la relazione giuridica e l'effettiva presenza nello snapshot.
- I quattro negativi sono **ipotesi di assenza documentale**, non fatti validati.
- Per il quesito temporale PLUVICTO verificare se la data della determina AIFA è nel corpus: se non c'è, la risposta deve segnalarlo; non inventare durate del percorso.
- Calcolare accuratezza soltanto sulle domande con gold `VALIDATO`, dichiarando scarti e tasso di copertura; usare identico modello, snapshot, domanda e criteri di valutazione.
- Per misurare TAG e Text-to-SQL registrare tempi, uso token, costo quando disponibile, citazioni e correttezza. Segnalare che la quota API può interrompere il benchmark.

## Validazione e rilascio
L'algoritmo `valida_gold.py` controlla formato ed esistenza delle citazioni regionali, **non** prova automaticamente che la risposta normativa sia corretta. Serve una revisione documentale umana finale.
Non fondere questa revisione con modifiche automatiche alla dashboard: mantenere il benchmark sperimentale separato.
