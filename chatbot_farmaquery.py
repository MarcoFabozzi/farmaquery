"""Logica del chatbot FarmaQuery: snapshot verificato e scelta del motore.

Moduli LLM non importati finche' l'utente non invia una domanda.
Le chiavi API si leggono SOLO dal server, mai dalla chat.
"""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import sqlite3
import json
import os
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"risultati"
MODEL_DEFAULT="gemini/gemini-3.5-flash-lite"
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


CACHE_CODE_SOURCES=(
    "tesi/pilota_tag_vs_sql.py",
    "tesi/contesto_integrale.py",
    "tesi/verifica_completezza_tag.py",
    "tesi/recupero_regionale.py",
    "tesi/sintesi_tag.py",
    "tesi/revisione_categoria.py",
)


def _static_paths(environ=None):
    """Modalita' fissa: due file espliciti, senza fallback sugli aggiornamenti."""
    environ=os.environ if environ is None else environ
    db=str(environ.get("FARMAQUERY_STATIC_DB_PATH") or "").strip()
    manifest=str(environ.get("FARMAQUERY_STATIC_MANIFEST_PATH") or "").strip()
    if bool(db)!=bool(manifest):
        raise ValueError("Imposta sia FARMAQUERY_STATIC_DB_PATH sia "
                         "FARMAQUERY_STATIC_MANIFEST_PATH")
    return (Path(db).expanduser().resolve(),
            Path(manifest).expanduser().resolve()) if db else None


def _verified_static_snapshot(db,manifest):
    """Verifica la copia statica prima di offrirla a entrambi i motori."""
    if not db.is_file() or not manifest.is_file():
        raise FileNotFoundError("Snapshot statico o relativo manifesto assenti")
    meta=json.loads(manifest.read_text(encoding="utf-8"))
    expected=meta.get("sha256_sqlite")
    if not expected:
        raise ValueError("Manifesto statico senza sha256_sqlite")
    h=sha256()
    with db.open("rb") as reader:
        for block in iter(lambda:reader.read(1024*1024),b""):
            h.update(block)
    if h.hexdigest()!=expected:
        raise ValueError("Snapshot statico diverso dal manifesto; nessuna "
                         "ricostruzione automatica dalle fonti online")
    with sqlite3.connect(db.as_uri()+"?mode=ro",uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("SQLite statico non integro")
        necessary={"note","pagine","aifa_confezioni","ema_medicinali",
                   "strutture_registri","nota_centro_documentato"}
        found={r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not necessary<=found:
            raise ValueError("Database statico privo di tabelle richieste")
    return meta


def snapshot_version(root=ROOT):
    """La cache usa SOLO i file statici se la modalità fissa è configurata."""
    paths=_static_paths()
    if paths is not None:
        return tuple((str(path),path.stat().st_mtime_ns,path.stat().st_size)
                     for path in paths)
    base=Path(root)
    relevant=REQUIRED+CACHE_CODE_SOURCES
    return tuple((name,(base/name).stat().st_mtime_ns,
                  (base/name).stat().st_size) for name in relevant)


def prepare_snapshot(root=ROOT):
    """Snapshot statico quando configurato; altrimenti modalità legacy."""
    paths=_static_paths()
    if paths is not None:
        database,manifest=paths
        return database,_verified_static_snapshot(database,manifest)
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
