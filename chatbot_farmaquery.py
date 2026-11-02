"""Logica del chatbot FarmaQuery: snapshot verificato e scelta del motore.

Moduli LLM non importati finche' l'utente non invia una domanda.
Le chiavi API si leggono SOLO dal server, mai dalla chat.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"risultati"
MODEL_DEFAULT="gemini/gemini-2.5-flash"
REQUIRED=(
    "risultati/regione_campania.sqlite.gz",
    "risultati/aifa_confezioni_complete.sqlite.gz",
    "risultati/farmaci_automatico.sqlite",
    "risultati/aifa_classi_ah.json",
    "risultati/stato_fonti/regione_campania.json",
    "risultati/stato_fonti/aifa_anagrafica.json",
    "risultati/stato_fonti/aifa_ah.json",
    "risultati/stato_fonti/ema.json",
)


def snapshot_version(root=ROOT):
    """La cache Streamlit si invalida quando cambia una fonte ufficiale."""
    base=Path(root)
    return tuple((name, (base/name).stat().st_mtime_ns,
                  (base/name).stat().st_size) for name in REQUIRED)


def prepare_snapshot(root=ROOT):
    """Genera file temporanei in sola lettura; non modifica il sito o il repo."""
    from tesi.prepara_snapshot_online import build_snapshot
    folder=Path(tempfile.mkdtemp(prefix="farmaquery_chat_"))
    db=folder/"esperimento_online.sqlite"
    manifest=folder/"manifest_fonti_online.json"
    try:
        metadata=build_snapshot(root,db,manifest)
        return db,metadata
    except Exception:
        db.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        raise


def model_from_settings(secrets=None,environ=None):
    config=secrets or {}
    environ=os.environ if environ is None else environ
    model=(config.get("FARMAQUERY_LLM_MODEL") or
           environ.get("FARMAQUERY_LLM_MODEL") or MODEL_DEFAULT)
    model=str(model).strip()
    if not model or len(model)>100:
        raise ValueError("Modello LLM non valido")
    return model


def enable_server_key(model,secrets=None,environ=None):
    """Restituisce se esiste una chiave server-side per il provider scelto.

    La chiave non viene mai restituita o inserita negli output del chatbot.
    """
    environ=os.environ if environ is None else environ
    secrets=secrets or {}
    if model.startswith(("gemini/","google/")):
        names=("GEMINI_API_KEY","GOOGLE_API_KEY")
        canonical="GEMINI_API_KEY"
    elif model.startswith("openai/"):
        names=("OPENAI_API_KEY",)
        canonical="OPENAI_API_KEY"
    elif model.startswith("anthropic/"):
        names=("ANTHROPIC_API_KEY",)
        canonical="ANTHROPIC_API_KEY"
    else:
        return False
    if environ.get(canonical):
        return True
    for name in names:
        value=secrets.get(name) or environ.get(name)
        if value:
            environ[canonical]=str(value)
            return True
    return False


def answer_question(db_file,question,method,model):
    """Instrada realmente ai due motori: nessuna selezione fittizia."""
    from tesi import pilota_tag_vs_sql
    if method not in ("Text-to-SQL","TAG"):
        raise ValueError("Metodo sconosciuto")
    question=question.strip()
    if not question or len(question)>700:
        raise ValueError("Inserisci una domanda di massimo 700 caratteri")
    with closing(pilota_tag_vs_sql.read_only(db_file)) as db:
        return (pilota_tag_vs_sql.tag(db,question,model)
                if method=="TAG"
                else pilota_tag_vs_sql.sql_method(db,question,model))



def verify_provider(model):
    """Prova minima della connessione Gemini/LiteLLM, separata dal database.

    Eseguita SOLO se l'utente preme il relativo pulsante. Consuma una
    piccola quota del provider ma non verifica la correttezza delle risposte.
    """
    from litellm import completion
    out=completion(model=model,temperature=0,timeout=20,num_retries=0,
                   max_tokens=12,
                   messages=[{"role":"user",
                              "content":"Rispondi solo con la parola OK."}])
    # Una risposta HTTP valida prova la connessione anche se il modello
    # non produce testo per un limite di token di ragionamento.
    return bool(out.choices)


def history_key(method):
    if method not in ("Text-to-SQL","TAG"):
        raise ValueError("Metodo sconosciuto")
    return "farmaquery_chat_"+("sql" if method=="Text-to-SQL" else "tag")
