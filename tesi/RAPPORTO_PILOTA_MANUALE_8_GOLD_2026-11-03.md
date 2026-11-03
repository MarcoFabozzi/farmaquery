# Risultati del pilota manuale TAG vs Text-to-SQL: otto gold regolatori

**Data delle prove:** 3 novembre 2026  
**Software:** FarmaQuery, interfaccia Streamlit.  
**Riferimento documentale:** `tesi/benchmark_regolatorio_8_validati.csv`, gold Q05, Q06, Q07, Q08, Q09, Q21, Q28, Q29.  
**Dati analitici:** `tesi/RISULTATI_MANUALI_8_GOLD_2026-11-03.csv`.  
**Fonti dei risultati:** trascrizioni e tempi dell'interfaccia fornite dall'utilizzatore nella stessa sessione; ogni valutazione è archiviata in un file `tesi/VALUTAZIONE_MANUALE_<ID>_...md`.

## 1. Scopo e condizioni

L'obiettivo è confrontare la capacità dei due motori di rispondere a quesiti basati sulle note regolatorie della Regione Campania, non di fornire consigli clinici. Ogni domanda è stata inviata una volta a TAG e una volta a Text-to-SQL, con formulazione identica, senza modificare i motori tra una prova e la successiva. L'app indica "modello e snapshot invariati" nel pannello Text-to-SQL; **non sono stati però acquisiti** l'hash dello SQLite effettivamente in uso sull'app, l'identificativo del modello esatto e il commit dei prompt. Non si deve equiparare questo pilota alle esecuzioni automatizzate sullo snapshot SQLite congelato del 02/11/2026 (`bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`).

Il gold è stato validato sulle pagine PDF indicate nel benchmark. Le prove sono esplorative, campione piccolo e selezionato; i risultati **non** costituiscono evidenza generalizzabile di superiorità di una tecnica.

## 2. Rubrica usata

- **Risposta completa = 1** solo quando copre tutti gli elementi richiesti dalla rubrica del gold già validato, senza associazioni sostanziali false.
- **Risposta parziale = 0** per completezza binaria, ma si conserva separatamente la copertura degli elementi corretti. Lo zero non significa assenza di contenuti corretti.
- **Falso negativo di recupero = 0** quando il motore dichiara "informazione non documentata" malgrado il gold documenti la risposta.
- **Errore tecnico = N/A nella precisione condizionata alla generazione**; è invece una mancata risposta nel tasso di successo end-to-end. Non assimilare `OperationalError` a risposta falsa.
- Le citazioni PDF sono considerate pertinenti nel contenuto riportato quando corrispondono alle pagine del gold. Il campo `fonte non_recuperato` di TAG e l'avviso di risultati parziali di Text-to-SQL restano **anomalie tecniche autonome**: richiedono verifica prima di certificare la tracciabilità delle fonti.
- I tempi provengono dalla UI; non sono latenza del provider né quantità di chiamate effettive. Le chiamate LOTUS mostrate come stimate **non sono misurate**.

## 3. Risultati per quesito

| ID | Tipo | TAG: completezza | TAG: secondi | Text-to-SQL: esito | SQL: secondi | Osservazione chiave |
| --- | --- | ---: | ---: | --- | ---: | --- |
| Q05 PLUVICTO | Interpretazione | 0 (parziale) | 5,5 | Falso negativo, 0 | 1,1 | TAG 5/5 centri ma omette lutezio-177; SQL JOIN e filtro data da diagnosticare |
| Q06 DUVYZAT | Interpretazione | 0 (parziale) | 3,4 | Falso negativo, 0 | 1,2 | TAG 4/4 presidi; omette classe H/registro; SQL filtra percorso ZIP con Campania |
| Q07 AMVUTTRA | Interpretazione | 1 | 5,3 | Falso negativo, 0 | 1,1 | TAG recupera 6/6 ATTR-CM e 3/3 polineuropatia; SQL filtra termini patologici nei campi candidati |
| Q08 KEYTRUDA | Interpretazione | 0 (parziale) | 5,3 | Falso negativo, 0 | 1,1 | TAG 2/3 associazioni; SQL cerca protocollo con slash nel nome del PDF |
| Q09 RYBREVANT | Interpretazione | 0 (parziale) | 5,4 | Falso negativo, 0 | 1,0 | TAG 1/3 indicazioni; filtro SQL su protocollo_candidato da diagnosticare |
| Q21 AMVUTTRA | Temporale | 0 (parziale) | 2,0 | **OperationalError, N/A** | N/D | TAG identifica nota 2023 e canali E/D ma non esplicita la portata limitata della modifica |
| Q28 FASENRA | Rimandi | 1 | 6,3 | 1, risposta prodotta | 2,3 | Entrambi corretti; SQL avvisa di risultati parziali |
| Q29 CASGEVY | Rimandi | 1 | 4,9 | Falso negativo, 0 | 1,1 | TAG riconosce il richiamo operativo; SQL cerca n.anno=2024 invece della nota del 2025 |

Le classificazioni dei rapporti singoli costituiscono la fonte dettagliata di ogni riga e non sostituiscono una revisione indipendente delle risposte.

## 4. Indicatori aggregati

| Metrica | TAG | Text-to-SQL |
| --- | ---: | ---: |
| Domande inviate | 8 | 8 |
| Risposte effettivamente prodotte | 8/8 | 7/8 |
| Risposte complete secondo gold (su 8 tentativi) | **3/8 = 37,5%** | **1/8 = 12,5%** |
| Risposte parziali con fatti utili | 5/8 | 0/8 |
| Risposte "informazione non documentata" in contrasto col gold | 0/8 | **6/8** |
| Errori tecnici senza risposta | 0/8 | **1/8** |
| Precisione binaria sulle sole risposte prodotte | 3/8 = 37,5% | 1/7 = 14,3% |
| Tempo medio UI su tutte le risposte con durata | **4,76 s** (8) | **1,27 s** (7) |

**Confronto appaiato dei tempi:** per le sole 7 domande con durata in entrambi i motori (esclusa Q21), TAG **5,16 s** medi e Text-to-SQL **1,27 s**; il secondo è circa **4,1 volte più rapido** in questo sottocampione, ma ha fornito cinque/sei falsi negativi sulle domande documentali e un unico risultato contenutisticamente completo. Il confronto dei tempi riguarda pipeline diverse e non misura il costo del modello né il tasso di successo della sola LLM.

**Anomalia TAG:** `fonte non_recuperato` compare in Q08, Q09, Q21 e Q28, **4/8** prove. Negli altri quattro casi il pannello mostra `fonte integrale`. Questo richiede diagnosi della tracciabilità, senza assumere un rapporto causale con la completezza.

### Sensibilità della rubrica

Q21 mostra l'effetto di un gold più severo della formulazione letterale: TAG risponde al protocollo e ai canali direttamente domandati, ma non spiega il perimetro giuridico della modifica come richiesto dal gold. La valutazione formale del pilota conserva **0/1** per coerenza con la rubrica gold. Se si adottasse *a posteriori* una rubrica ridotta alla sola domanda letterale, il suo giudizio potrebbe cambiare: non modificare silenziosamente il criterio o il totale 3/8.

## 5. Analisi degli errori

**Text-to-SQL.** Il principale risultato del pilota è il recupero insufficiente di fonti documentate, spesso collegato a filtri generati che non rispettano la struttura dei dati:
- **Q08:** `n.nome_file LIKE '%0116205/2026%'` contro il nome del PDF `0116205-2026`; mismatch stringa/normalizzazione identificatore nel campo interrogato.
- **Q29:** `n.anno=2024` contro documento CASGEVY oggetto della domanda del 2025; inversione temporale tra fonte citante e fonte citata.
- **Q06:** `n.percorso_zip LIKE '%Campania%'`, parola non presente nel percorso PDF del gold.
- **Q07:** filtro ATTR-CM/polineuropatia nei campi `c.menzione` e `c.stato` anziché consultare la struttura delle tabelle alle pagine 2–3.
- **Q05 e Q09:** possibili filtri e join troppo selettivi, non ancora verificati su conteggi delle righe reali.
- **Q21:** `OperationalError` durante esecuzione SQL, senza query e messaggio diagnostico completo: **causa sconosciuta**.

**TAG.** Recupera spesso i documenti e nomi corretti, ma non sempre tutti i dettagli necessari: Q05 requisito Lutezio-177, Q06 classe H/registro, Q08 combinazione chemioradioterapia, Q09 indicazioni EGFR del19/L858R, Q21 portata limitata della modifica. Il modello talvolta etichetta «EMA» contenuti citati dal PDF regionale. È utile distinguere recupero, interpretazione, completezza e attribuzione delle fonti.

## 6. Conclusione provvisoria e prossime azioni

Nelle otto domande esplorative, TAG ha prodotto più risposte complete e molte risposte sostanzialmente informative ma parziali; Text-to-SQL è stato più rapido nelle esecuzioni misurate, ma ha registrato sei falsi negativi e un errore operativo. Il risultato **non autorizza** a dichiarare la superiorità statistica di TAG in generale: valuta queste implementazioni e queste domande, con dati e stato del modello non completamente congelati.

Per una valutazione da tesi più solida: (1) recuperare hash database, commit, modello e parametri dell'app; (2) mantenere le domande e gold fissati prima dell'esecuzione; (3) archiviare SQL e citazioni e verificare gli errori con SELECT di diagnosi; (4) eseguire una serie riproducibile su uno snapshot comune; (5) riferire separatamente accuratezza binaria, copertura dei fatti, validità citazioni, errori tecnici, latenza e costo/chiamate misurate; (6) estendere le domande a più categorie senza selezione post hoc.

**Integrità del confronto:** questi risultati sono stati registrati senza correggere TAG/Text-to-SQL nel mezzo delle otto prove. Le correzioni vanno testate dopo, in un esperimento separato rispetto alla baseline.
