# Q21 AMVUTTRA — confronto manuale del 3 novembre 2026

**Domanda identica per entrambi i motori:** Quale nota del 2023 è richiamata dalla nota AMVUTTRA 0634617/2026 e come cambiano i canali di rendicontazione ambulatoriale e domiciliare?

**Risposta gold e rubrica:** `tesi/benchmark_regolatorio_8_validati.csv` Q21, nota `AMVUTTRA Prot.N.0634617-2026.pdf` pagina 3. La nota richiamata è prot. 0493819 del 16/10/2023; ambulatoriale File F canale E; domiciliare File F canale D; il testo 2026 introduce una modifica puntuale delle modalità di somministrazione/rendicontazione e non dichiara abrogazione integrale della nota del 2023.

## TAG — output integrale fornito dall'utente

> La nota del 2023 richiamata è la **Nota prot. 0493819 del 16.10.2023** (*AMVUTTRA Prot.N.0634617-2026.pdf#p3*).
>
> I canali di rendicontazione cambiano prevedendo che, se il farmaco viene somministrato in regime ambulatoriale deve essere rendicontato nel File F Canale E, mentre se somministrato in regime domiciliare deve essere rendicontato nel File F Canale D (*AMVUTTRA Prot.N.0634617-2026.pdf#p3*).

Metadati: **2,0 s**; TAG verifica-integrale-v2; `fonte non_recuperato`; AIC 0; revisione LLM no; 11 evidenze; 3 elementi LOTUS; 4 chiamate LLM stimate (non misurate).

Valutazione: nota precedente e due canali corretti (**3/4 elementi del gold**). Manca la precisazione sull'effetto limitato della modifica e assenza di abrogazione integrale. **Completezza del gold con rubrica stretta 0/1** (qualitativamente quasi completa); la correttezza limitata ai soli due sottoquesiti letterali potrebbe essere valutata diversamente e va predefinita prima del riepilogo finale. Il segnale tecnico `fonte non_recuperato` richiede diagnosi separata, non prova di citazioni inesistenti.

## Text-to-SQL — output integrale fornito dall'utente

> La richiesta non è stata completata. (fase: esecuzione SQL; codice: ALTRO; tipo: OperationalError).

**Nessun testo SQL né durata** forniti dall'interfaccia. Esecuzione fallita: **`ERRORE_SQL`** con tipo `OperationalError`. Non è una previsione di assenza dell'informazione; non imputare un `0/1` come errore di contenuto. Conteggiare separatamente come insuccesso operativo; non valutabile per accuratezza condizionata alle risposte prodotte. Ai fini dell'affidabilità end-to-end conta come mancato completamento della richiesta.

Diagnosi: `OperationalError` potrebbe derivare da sintassi, tabella/colonna inesistente o altre condizioni SQL; il codice generico `ALTRO` non permette di stabilire la causa. Richiede query prodotta e log diagnostico privo di segreti.

## Comparazione

| Criterio | TAG | Text-to-SQL |
| --- | --- | --- |
| Nota 2023 | Corretta | Nessuna risposta |
| Canale E, ambulatoriale | Corretto | Nessuna risposta |
| Canale D, domiciliare | Corretto | Nessuna risposta |
| Portata puntuale modifica | Omessa | Nessuna risposta |
| Risposta conforme all'intero gold | 0/1 (parziale) | N/A (errore tecnico) |
| Completamento operativo | Sì | No (`OperationalError`) |
| Latenza dall'app | 2,0 s | N/D |

**Limiti del confronto:** raccolto manualmente sull'app Streamlit, non sul runner con SHA del database congelato 02/11/2026; modello/prompt e hash effettivo dell'app non verificati. Non alterare metodi/gold durante il benchmark.

**Prossima Q28:** In relazione all'EGPA, quale nota precedente è richiamata da FASENRA 0520736/2026 e in che senso vengono sostituiti e aggiornati i centri per mepolizumab?
