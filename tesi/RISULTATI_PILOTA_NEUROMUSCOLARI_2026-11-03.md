# Pilot esplorativo: medicinali neuromuscolari e AOU Federico II

**Data:** 3 novembre 2026. **Stato:** prova esplorativa; non è un confronto formale versionato.  
**Riferimento:** `riferimento_neuromuscolari_federico_ii_2026-11-03.json` (13 core, 14 esteso), snapshot del 02/11/2026 SHA-256 `bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`.

## Ambito e provenienza
Questa scheda registra le **liste di nomi** e i **tempi dichiarati** nei resoconti conversazionali delle precedenti esecuzioni; **non** ricostruisce le risposte integrali, l'identità del modello, i parametri, il commit del codice o gli hash dei DB effettivamente consultati dai motori. Non usare per affermare un esperimento a parità di condizioni. Il gold è documentale ma **provvisorio**; la revisione della tassonomia e la ricerca di eventuali omissioni restano aperte.

## Presenza dei nomi nel riferimento

| Indicatore | TAG | Text-to-SQL |
| --- | ---: | ---: |
| Nomi riportati | 7 | 4 |
| Corrispondenti al riferimento core (13) | 7 | 4 |
| Copertura nomi, core | **53,85%** | **30,77%** |
| Copertura nomi, core senza HIZENTRA (12) | **58,33%** | **33,33%** |
| Copertura nomi, esteso con SKYCLARYS (14) | **50,00%** | **28,57%** |
| Tempo dichiarato, non verificato da log | 10,5 s | 11,0 s |

**Entrambi:** EVRYSDI, ULTOMIRIS.  
**Solo TAG:** AGAMREE, DUVYZAT, SOLIRIS, ZILBRYSQ, VYVGART.  
**Solo Text-to-SQL:** KIOVIG, HYQVIA.  
**Nessuno dei due:** AMVUTTRA, GAMTEN, HIZENTRA, WAINZUA.  
**Solo nel gold esteso e non riportato:** SKYCLARYS.  
**Copertura della unione:** 9/13 = 69,23%, ma la correttezza di ciascuna associazione indicazione-centro non è qui completamente valutata.

### Errore documentale accertato nel resoconto
La risposta **Text-to-SQL** ha associato per ULTOMIRIS la **pagina 2** (tabella NMOSD) alla miastenia gravis generalizzata; la tabella di **pagina 3** riguarda i presidi per quest'ultima. La presenza del nome ULTOMIRIS è dunque corretta nel conteggio dei nomi, **non** nella prova documentale utilizzata dalla risposta. Non trasferire strutture tra tabelle cliniche diverse.

**KIOVIG e HYQVIA:** la validazione dei PDF originali conferma i medicinali e la presenza di AOU Federico II per CIDP.  
**HIZENTRA:** caso sostenuto da richiamo esplicito nella nota HYQVIA; l'analisi senza HIZENTRA rende trasparente la scelta del perimetro.
**AMVUTTRA:** distinguere tabella ATTR-CM (p. 2) da polineuropatia ereditaria (p. 3). Il nome omesso da entrambe le risposte è nel gold per la seconda indicazione.

## Limiti
Queste percentuali misurano **solo il recupero del nome del medicinale**. Non rappresentano l'accuracy della domanda, la precisione delle citazioni, la correttezza clinico-regolatoria o la validità odierna dei centri. Un nome giusto con l'indicazione o la pagina sbagliata **non** è una risposta complessivamente corretta. Mancano gli output grezzi per assegnare giudizi completi alle due risposte. Le prove sono state effettuate durante lo sviluppo e potrebbero non essere omogenee per commit/prompt/parametri.

## Riproducibilità senza LLM

```bash
python -m unittest -v tesi.tests.test_valuta_richiamo_medicinali
python -m tesi.valuta_richiamo_medicinali --out dist_tesi/metriche_pilota_neuromuscolari.json
```

Input di osservazioni: `tesi/pilota_neuromuscolari_2026-11-03.json`. Lo script verifica che il riferimento mantenga lo stesso SHA-256 e calcola le coperture di nomi nei tre perimetri. Non legge i PDF, non invoca Gemini, non attribuisce voti semantici automatici e non modifica TAG o Text-to-SQL.

## Passaggio al benchmark formale
Il benchmark principale `tesi/benchmark_regolatorio_30.csv` ha **8 gold validati e 22 ancora da verificare**; il caso di elenco neuromuscolare non va confuso con una delle 30 domande valutate. Per il confronto sperimentale successivo servono: (1) fissare codice, snapshot, modello, prompt e parametri; (2) archiviare le risposte integrali e i log delle due pipeline; (3) giudicare per ciascuna delle otto domande già validate completezza, indicazioni, centri, citazioni e temporizzazione, utilizzando `tesi/valuta_confronto.py`; (4) estendere gradualmente ai gold restanti dopo verifica indipendente. Evitare modifiche alle pipeline motivate da un'unica domanda del test.
