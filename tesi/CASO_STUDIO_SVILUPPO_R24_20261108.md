# Caso di studio esplorativo — TAG automatico r24, AOU Federico II

**8 novembre 2026 — esercizio di sviluppo, NON parte del nuovo holdout.**

## Domanda osservata
«Quali medicinali citati nelle note regionali della Campania per malattie neuromuscolari prevedono la prescrizione presso l'AOU Federico II? Per ciascuno indica il medicinale, la patologia o indicazione, il documento e la pagina in cui è individuato il centro prescrittore».

## Esecuzione documentata tramite diagnostica FarmaQuery

| Voce | Valore osservato |
|---|---|
| Revisione | `2026-11-08-r24-errore-lotti-diagnosticabile` |
| Snapshot | `tesi_statico_20261102.sqlite.gz` |
| Note candidate nella prima fase | 161 |
| Note selezionate per la seconda fase | 15 |
| Verifiche finali completate | 3 lotti su 5 |
| Schede inviate al verificatore | 12 (il lotto 4 ha fallito) |
| Associazioni proposte | 11 |
| Associazioni accettate dal controllo interno | 11 |
| Associazioni respinte | 0 |
| Tempo | 16,7 s |
| Invii LLM misurati | 17 (15 diretti; 2 LOTUS) |
| Interruzione | `QUOTA`, `RateLimitError`, lotto finale 4 |

## Associazioni riportate dalla risposta

| Medicinale | Indicazione citata | PDF | Pagina centro |
|---|---|---|---:|
| VYVGART | Miastenia gravis generalizzata refrattaria | `VYVGART.pdf` (2023) | 3 |
| AMVUTTRA | Amiloidosi hATTR con polineuropatia | `AMVUTTRA.pdf` (2023) | 2 |
| NEXVIADYME | Malattia di Pompe | `NEXVIADYME.pdf` | 2 |
| POMBILITI | Malattia di Pompe a esordio tardivo | `POMBILITI-OPFOLDA.pdf` | 2 |
| OPFOLDA | Malattia di Pompe a esordio tardivo, terapia associata | `POMBILITI-OPFOLDA.pdf` | 2 |
| DUVYZAT | Distrofia muscolare di Duchenne | `DUVYZAT Prot.N.0368583-2026.pdf` | 2 |
| SOLIRIS | Neuromielite ottica NMOSD | `SOLIRIS.pdf` | 3 |
| SOLIRIS | Miastenia gravis generalizzata refrattaria | `SOLIRIS.pdf` | 4 |
| HYQVIA | CIDP | `HYQVIA CIDP.pdf` | 2 |
| SKYCLARYS | Atassia di Friedreich | `SKYCLARYS Prot.N.0143659-2026.pdf` | 2 |
| AGAMREE | Distrofia muscolare di Duchenne | `AGAMREE Prot.N.0663946-2026.pdf` | 2 |

Il riepilogo contiene **11 associazioni**, non 11 PDF distinti: i PDF distinti citati sono 9; POMBILITI e OPFOLDA condividono una nota, SOLIRIS compare con due indicazioni e due pagine differenti.

## Evidenze e limiti della verifica

Un audit in sola lettura sullo snapshot SQLite ha confrontato il testo delle pagine elencate con le denominazioni e le indicazioni riportate. I riscontri sono complessivamente coerenti; **la sola presenza di stringhe nel testo OCR non costituisce attestazione clinico-normativa indipendente**, soprattutto per tabelle con layout degradato. Per SOLIRIS pagina 3, il testo OCR della struttura è particolarmente deteriorato.

La nota `HYQVIA CIDP.pdf` a pagina 2 menziona anche l'**aggiornamento dei centri HIZENTRA** per la CIDP, che non appare nella risposta. Questo è un caso concreto di possibile omissione di un medicinale citato **all'interno della nota di un altro medicinale**.

La lista di riferimento neuromuscolare preesistente (`riferimento_neuromuscolari_federico_ii_2026-11-03.json`) descrive 13 voci *core* e 14 in un perimetro esteso, ma viene dichiarata esplicitamente **provvisoria**. Inoltre NEXVIADYME, POMBILITI e OPFOLDA, relativi alla malattia di Pompe, non compaiono in quella lista, nonostante l'interesse neuromuscolare della patologia; la tassonomia e la completezza del gold richiedono una revisione indipendente **prima** di qualunque valutazione quantitativa su tale domanda. Non è scientificamente corretto conteggiare automaticamente queste voci come falsi positivi.

Sono rimasti senza associazione accettata KIOVIG, ZILBRYSQ, EVRYSDI, ULTOMIRIS, AMVUTTRA 2026 e UPLIZNA. **Non si tratta di sei rifiuti documentali**: il lotto 4 si è interrotto per quota e il lotto 5 non è stato eseguito. Il sistema ha conservato correttamente le prove raccolte nei lotti precedenti.

## Interpretazione sperimentale

La prova evidenzia contemporaneamente:
1. la capacità del recupero documentale di includere molte note potenzialmente pertinenti;
2. l'importanza della verifica a livello di singola associazione e di pagina;
3. l'impossibilità di inferire la completezza di una risposta dal rapporto 11/11 fra associazioni proposte e accettate;
4. il costo di più passaggi semantici e il rischio di interruzione per quota LLM;
5. la necessità di una ground truth **indipendente dall'output dei motori**, definita prima di misurare precision e recall.

Questa prova può essere riportata come **esempio qualitativo di analisi degli errori e del funzionamento del sistema**. Non deve essere sommata alle misure del blocco finale indipendente né spacciata per un risultato di accuratezza del TAG.

*Provenienza: output integrale della prova r24 e riscontro di sola lettura del testo estratto nelle tabelle `note` e `pagine` dello snapshot statico. Le citazioni dei singoli PDF, le pagine e la revisione originale devono essere conservate nell'appendice sperimentale.*
