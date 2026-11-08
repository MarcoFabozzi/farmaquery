# RECAP DA INCOLLARE IN UNA NUOVA CHAT — TESI FARMAQUERY

**Progetto:** tesi triennale su FarmaQuery, assistente conversazionale per informazioni regolatorie sui medicinali (EMA, AIFA, Gazzetta Ufficiale, note regionali Campania). Lo studio confronta **Text-to-SQL** con **TAG (Table-Augmented Generation)**: accuratezza sul Gold manuale, completezza, citazioni, tempo e chiamate LLM. La finalità è *valutare* i due approcci, NON rendere TAG perfetto.

**Repository:** https://github.com/MarcoFabozzi/farmaquery  
**App:** https://farmaquery.streamlit.app/  
**Motore congelato per gli esperimenti:** TAG r24, `2026-11-08-r24-errore-lotti-diagnosticabile`, codice di riferimento commit `0d81dd516e8e4e9a6e2151cd1c0478204389aacb`. Le successive modifiche GitHub sono solo documentali; non toccare TAG per migliorare le risposte ai quesiti.
**Database statico:** `risultati/tesi_statico_20261102.sqlite.gz`, SQLite decompresso SHA-256 `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`. Lo snapshot del **2 novembre 2026** resta il riferimento metodologico, MA NON deve essere citato come data nelle domande di assenza documentale.

## Questionario attuale — 20 nuove domande realistiche per farmacista

**File leggibile su GitHub:** https://github.com/MarcoFabozzi/farmaquery/blob/main/tesi/QUESITI_FARMACISTA_20_V2_DA_APPROVARE_20261108.md  
**CSV:** https://github.com/MarcoFabozzi/farmaquery/blob/main/tesi/QUESITI_FARMACISTA_20_V2_DA_APPROVARE_20261108.csv

**Categorie originarie richieste dal relatore:**
1. `SEMPLICE` — informazioni prescrittive dirette.
2. `CATEGORIA_IMPLICITA` — individuare più medicinali tramite patologia/centro, senza confondere le diverse indicazioni.
3. `RIMANDO` — il documento cita un altro atto: identificare protocollo e funzione del richiamo; distinguere semplice richiamo, aggiornamento, annullamento o sostituzione *espressamente dichiarati*. NON un generico confronto temporale. Esempi del pilota storico: CASGEVY e CAMZYOS, **non riutilizzare quelle domande nel test indipendente**.
4. `NESSUNA_RISPOSTA` — riconoscere quando un dato operativo non è documentato nel corpus, senza inventare conteggi o affermare zero.
5. `MULTIFONTE` — categoria aggiuntiva per relazioni EMA/AIFA/GU/Regione.

**Quattro quesiti per categoria = 20.** Ogni domanda composta da più interrogativi deve mostrare i singoli interrogativi su righe separate, ciascuno terminante con `?`; nel CSV può rimanere su una sola riga per compatibilità.

**Stato di approvazione:**
- **FAR01–FAR04** già scelte dall'utente: XEMBIFY, KAYFANDA, HEMLIBRA AIC 046130047, SIVEXTRO due AIC.
- **FAR05–FAR08** già scelte dall'utente: miastenia gravis generalizzata/Federico II, CIDP/Federico II, fibrosi cistica/Federico II, Alagille/Federico II.
- **FAR09–FAR12** appena **riformulate e DA APPROVARE** per essere veri rimandi: VOXZOGO 2025→nota PG/2024/0503681 (SINFONIA); LIVMARLI 2025→nota 0566666/2025 (migrazione SINFONIA e chiusura SANIARP); AMVUTTRA 2026→nota 0493819/2023 e rendicontazione File F E/D; DUPIXENT 2026→Determina AIFA 102/2026 (piano EoE) e D.D. 182/2022 (centri pediatrici).
- **FAR13–FAR16** riformulate, **DA APPROVARE**, SENZA «2 novembre»: medici KAYFANDA effettivamente abilitati SINFONIA, giacenza effettiva XEMBIFY al Santobono, numero pazienti realmente trattati con ALYFTREK alla Federico II, prezzo netto realmente pagato per ENHERTU. La data del primo semestre 2025 per quest'ultima rimane perché individua un periodo economico, NON la data dello snapshot.
- **FAR17–FAR20** categoria MULTIFONTE **DA APPROVARE**: WEGOVY EMA/GU, DUVYZAT EMA/AIFA/Regione, DUPIXENT AIFA/Regione, AMVUTTRA EMA/Regione.

**IMPORTANTISSIMO:** le 20 nuove domande hanno ancora i campi Gold vuoti e stato `DA_VERIFICARE`. I vecchi file `HOLDOUT_FINALE_20_R24...` con 8 Gold validati e 12 proposti si riferiscono a UN QUESTIONARIO PRECEDENTE, NON alle nuove FAR01–FAR20; non mescolare o trasferire automaticamente le risposte.

## Stato della sperimentazione e metodo

- Lo sviluppo del TAG r24 è congelato. Un test di sviluppo su medicinali neuromuscolari/Federico II ha ottenuto 11 associazioni interne, 3/5 lotti completati, errore `QUOTA RateLimitError` al quarto lotto, 17 chiamate LLM e 16,7 s. **Non è prova di accuratezza 100%** né risultato del nuovo questionario.
- Le domande già usate per correggere i motori sono prove di sviluppo, non holdout indipendente. La coincidenza di argomenti con domande pilota va registrata; non rivendicare indipendenza assoluta senza revisione.
- Dopo l'approvazione letterale delle 20 FAR, preparare il **Gold tramite lettura manuale** dello stesso database SQLite (`note`, `pagine`, `ema_medicinali`, `aifa_confezioni`, `gu_atti` ecc.), citando PDF/pagine o EMA ID/AIC. Per testi OCR ambigui, verificare il PDF originale. Distinguere citazione di un atto, effetti espressi e deduzioni non supportate.
- Successivamente inviare le *identiche domande* a Text-to-SQL e TAG automatico sullo snapshot congelato, senza ulteriore tuning, e annotare risposte corrette/parziali/errate, astensioni, tempi, invii LLM, quota ed errori.
- Scrivere il capitolo sperimentale della tesi dai risultati effettivi; non inventare percentuali.

## COSA FARE NELLA NUOVA CHAT

**Prossimo passo:** chiedermi di mostrarti soltanto le nuove **domande 9–12 della categoria RIMANDO**, una interrogativa per riga, affinché tu possa approvarle o correggerle. Poi approvare 13–16 e 17–20. Solo a questionario definitivo passare al Gold manuale. Non ricominciare il lavoro di sviluppo TAG.

*Questa sintesi è autosufficiente per riprendere il progetto anche senza questa conversazione. Per i testi integrali e il CSV usare i link GitHub sopra.*
