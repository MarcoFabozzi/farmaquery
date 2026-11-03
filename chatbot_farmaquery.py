"""Logica del chatbot FarmaQuery: snapshot verificato e scelta del motore.

Moduli LLM non importati finche' l'utente non invia una domanda.
Le chiavi API si leggono SOLO dal server, mai dalla chat.
"""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import gzip
import shutil
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


BUNDLED_STATIC = (
    "risultati/tesi_statico_20261102.sqlite.gz",
    "risultati/tesi_statico_20261102.json",
)


CACHE_CODE_SOURCES=(
    "tesi/pilota_tag_vs_sql.py",
    "tesi/contesto_integrale.py",
    "tesi/verifica_completezza_tag.py",
    "tesi/recupero_regionale.py",
    "tesi/sintesi_tag.py",
    "tesi/revisione_categoria.py",
)


def _static_paths(environ=None,root=ROOT):
    """Prima snapshot fisso esplicito, poi copia distribuita con il codice."""
    environ=os.environ if environ is None else environ
    db=str(environ.get("FARMAQUERY_STATIC_DB_PATH") or "").strip()
    manifest=str(environ.get("FARMAQUERY_STATIC_MANIFEST_PATH") or "").strip()
    if bool(db)!=bool(manifest):
        raise ValueError("Imposta sia FARMAQUERY_STATIC_DB_PATH sia "
                         "FARMAQUERY_STATIC_MANIFEST_PATH")
    if db:
        return Path(db).expanduser().resolve(),Path(manifest).expanduser().resolve()
    # Evita che i test con un root temporaneo ereditino la copia pubblica.
    if Path(root).resolve()!=ROOT.resolve():
        return None
    fixed=ROOT/"risultati"/"tesi_statico_20261102.sqlite.gz"
    info=ROOT/"risultati"/"tesi_statico_20261102.json"
    if fixed.exists()!=info.exists():
        raise ValueError("Fotografia statica incompleta: manca SQLite o manifesto")
    return (fixed,info) if fixed.is_file() and info.is_file() else None


def _file_digest(path):
    digest=sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def _verified_static_snapshot(source,manifest):
    """Non usa fonti online: verifica hash del binario, schema ed integrita."""
    if not source.is_file() or not manifest.is_file():
        raise FileNotFoundError("Snapshot statico o relativo manifesto assenti")
    meta=json.loads(manifest.read_text(encoding="utf-8"))
    expected=meta.get("sha256_sqlite")
    if not expected:
        raise ValueError("Manifesto statico senza sha256_sqlite")
    if source.suffix.lower()==".gz":
        packed_sha=meta.get("sha256_gzip")
        if packed_sha and _file_digest(source)!=packed_sha:
            raise ValueError("Archivio compresso statico diverso dal manifesto")
        # Il builder esistente conserva soltanto SHA-256 del contenuto
        # decompresso: è comunque obbligatorio validarlo prima dell'uso.
        folder=Path(tempfile.mkdtemp(prefix="farmaquery_static_"))
        db=folder/"fotografia_statica.sqlite"
        try:
            total=0
            digest=sha256()
            with gzip.open(source,"rb") as packed,db.open("wb") as out:
                while block:=packed.read(1024*1024):
                    total+=len(block)
                    if total>90_000_000:
                        raise ValueError("Snapshot SQLite statico troppo grande")
                    out.write(block)
                    digest.update(block)
            if digest.hexdigest()!=expected:
                raise ValueError("SQLite statico diverso dal manifesto")
        except Exception:
            db.unlink(missing_ok=True)
            raise
    else:
        db=source
        if _file_digest(db)!=expected:
            raise ValueError("Snapshot statico diverso dal manifesto")
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
    return db,meta


def snapshot_version(root=ROOT):
    """La cache usa la fotografia statica se presente, senza sorgenti online."""
    paths=_static_paths(root=root)
    if paths is not None:
        return tuple((str(path),path.stat().st_mtime_ns,path.stat().st_size)
                     for path in paths)
    base=Path(root)
    relevant=REQUIRED+CACHE_CODE_SOURCES
    return tuple((name,(base/name).stat().st_mtime_ns,
                  (base/name).stat().st_size) for name in relevant)


def prepare_snapshot(root=ROOT):
    """Sceglie la copia congelata se presente; altrimenti retrocompatibilità."""
    paths=_static_paths(root=root)
    if paths is not None:
        return _verified_static_snapshot(*paths)
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
