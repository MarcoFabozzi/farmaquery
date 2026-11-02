# Chatbot FarmaQuery — uso del menu Text-to-SQL / TAG

L'applicazione Streamlit dispone di una pagina **💬 Chatbot**, accessibile dalla dashboard principale o dal menu laterale. L'utente:

1. Seleziona **Text-to-SQL** oppure **TAG** dal menu a tendina.
2. Scrive la domanda nella chat e invia.
3. Legge la risposta, con le **fonti consultate**; in Text-to-SQL può aprire anche la query SQL.

La chat mantiene **due cronologie separate**, una per ciascun metodo. Ogni domanda viene interpretata indipendentemente dalle precedenti: questo è intenzionale perché le 40 domande del benchmark saranno confrontate equamente sui due metodi.

## Dati e metodi

Entrambi utilizzano un **unico snapshot SQLite verificato**, costruito dalle fonti ufficiali presenti in `risultati` (EMA, AIFA, Regione Campania); l'aggiornamento della dashboard resta indipendente. Lo snapshot è memorizzato in cache dal server e viene ricreato quando cambiano i file di origine.

- **Text-to-SQL:** il modello genera una `SELECT` SQLite validata con SQLGlot; il DB è aperto in sola lettura.
- **TAG:** LOTUS usa `sem_filter` sulle evidenze candidate di EMA, AIFA e pagine regionali, poi il medesimo LLM formula la risposta.
- **Citazioni:** fonti AIFA con AIC, EMA con ID/URL, regione con nome PDF e numero di pagina.
- La classe C **non** è provata dall'assenza nei registri A/H; l'abilitazione ai registri AIFA **non** dimostra da sola la prescrivibilità per una indicazione regionale.

## Abilitazione sicura su Streamlit Community Cloud

**Configurazione necessaria per rendere operative le risposte con LLM**:

1. L'app deve usare **Python 3.12**, perché `lotus-ai==1.2.4` richiede Python 3.10–3.12. Su Streamlit Community Cloud la versione Python è una impostazione del deployment, non va configurata con `runtime.txt`.
2. In **Manage app → Settings → Secrets** configurare soltanto sul server:

```toml
GEMINI_API_KEY = "chiave_ottenuta_dal_provider"
FARMAQUERY_CHAT_PASSWORD = "password_privata_per_la_demo"
FARMAQUERY_LLM_MODEL = "gemini/gemini-2.5-flash"
```

Il modello di esempio è soltanto un identificativo LiteLLM: il provider potrebbe avere restrizioni di disponibilità o quota. Si può modificare `FARMAQUERY_LLM_MODEL` per utilizzare un altro modello compatibile con LOTUS e LiteLLM. Per OpenAI usare `OPENAI_API_KEY` e modello con prefisso `openai/`; per Anthropic `ANTHROPIC_API_KEY` e modello con prefisso `anthropic/`.

**Non** inserire password e API key nel repository GitHub, nel testo della chat o nella pagina Streamlit. Il chatbot richiede una password di accesso per limitare l'uso della quota API, e impone un massimo di 12 domande per sessione. Questo limite non è una protezione assoluta contro abuso: per uso pubblico su larga scala occorrono autenticazione e limiti lato server.

## Stato delle prove

I test automatici verificano il percorso menu → motore effettivo, la verifica delle versioni delle fonti e la sicurezza delle SELECT. Le risposte **non sono ancora state provate con API reali** finché le chiavi non saranno configurate e non si farà una domanda.

Le **40 domande** saranno definite dall'autrice della tesi e potranno essere poste in entrambe le chat. Per le metriche con tempi, token e costi si può usare anche `tesi/esegui_benchmark.py` con le stesse domande; non è obbligatorio per l'uso ordinario del chatbot.
