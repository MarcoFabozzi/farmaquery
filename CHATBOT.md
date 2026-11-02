# Assistente flottante FarmaQuery

Nella dashboard il pulsante **💬** resta fisso in **basso a destra**.
Cliccandolo si apre una finestra Streamlit indipendente con un campo di scrittura e un menu a tendina per scegliere
**Text-to-SQL** oppure **TAG (LOTUS)**.

**Non esiste password di accesso.** Le chiavi del modello sono
esclusivamente nei *Secrets* privati di Streamlit Community Cloud:
```toml
GEMINI_API_KEY = "la_tua_chiave"
FARMAQUERY_LLM_MODEL = "gemini/gemini-3.5-flash-lite"
```
Il Secret `FARMAQUERY_CHAT_PASSWORD` non viene più utilizzato e può essere
rimosso dal pannello Secrets.

L'assistente è integrato nella dashboard (nessun cambio pagina). La bolla apre un dialog indipendente: il testo non è dentro il contenitore CSS del pulsante. Non ci sono
domande precompilate e non sono salvate le domande dell'utente nel repository.
Ogni utente può digitare liberamente qualsiasi domanda, entro 700 caratteri.

Le cronologie di Text-to-SQL e TAG sono distinte, per poter ripetere una
domanda con entrambe le tecniche. Le risposte mostrano le fonti e, nel
caso di Text-to-SQL, anche la SELECT SQL generata.

Per evitare consumi illimitati è previsto un limite di 12 domande per
sessione; **non è una quota globale anti-abuso**: dato che il sito è pubblico,
l'account del provider LLM deve avere limiti di spesa/quota adeguati.
L'app è un prototipo e non è idonea a decisioni cliniche senza verifica
umana delle fonti.

## Stato tecnico

I test automatici verificano che i motori siano instradati correttamente.
Non è possibile verificare chiamate reali a Gemini tramite le GitHub Actions
senza aggiungere segreti API ai workflow (non farlo). Se la pagina non
risponde, verificare Python 3.12 e gli errori nei log del deployment
Streamlit Cloud.

## Classificazione A/H/C

La classificazione mostrata dall'interfaccia usa la regola stabilita per
FarmaQuery: A se la confezione è nell'elenco A, H se è nell'elenco H,
**C in tutti gli altri casi**. L'etichetta esposta è semplicemente A, H o C,
senza ulteriori distinzioni.

La data dello snapshot e la data di riferimento degli elenchi A/H sono
registrate separatamente nel manifesto delle fonti.
