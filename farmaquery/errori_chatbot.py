"""Errori leggibili per la chat senza mostrare token, prompt o chiavi API."""
from __future__ import annotations

import logging
import sqlite3

logger=logging.getLogger("farmaquery.chatbot")


class EnginePhaseError(Exception):
    """Errore di esecuzione con fase nota; eccezione originale in __cause__."""

    def __init__(self,phase,original):
        self.phase=phase
        self.original=original
        self.error_type=type(original).__name__
        super().__init__(f"{phase}: {self.error_type}")


def diagnose_error(exc):
    """Diagnostica sicura senza messaggi, URL o chiavi del provider."""
    cause=(exc.__cause__ or exc.original) if isinstance(exc,EnginePhaseError) else exc
    kind=type(cause).__name__
    try:
        http=int(getattr(cause,"status_code",0) or 0)
    except (TypeError,ValueError):
        http=0
    low=kind.casefold()
    if http==429 or any(word in low for word in ("ratelimit","resourceexhausted","quota")):
        code="QUOTA"
    elif http==503 or "serviceunavailable" in low:
        code="SERVIZIO"
    elif http in (401,403) or any(word in low for word in ("authentication","unauthorized","permission")):
        code="AUTH"
    elif http==404 or "notfound" in low:
        code="MODELLO"
    elif http in (502,503,504) or any(word in low for word in ("timeout","connection","connect")):
        code="CONNESSIONE"
    elif http==400 or "badrequest" in low or "invalidrequest" in low:
        code="RICHIESTA"
    elif (isinstance(exc,EnginePhaseError) and "sql" in exc.phase.casefold()) or isinstance(cause,sqlite3.DatabaseError):
        code="SQL"
    else:
        code="ALTRO"
    return {"codice":code,
            "fase":exc.phase if isinstance(exc,EnginePhaseError) else "esecuzione",
            "tipo":kind}


def _sqlite_error_diagnostic(cause):
    """Diagnostica a categorie fisse; NON mostra il messaggio grezzo SQLite."""
    if not isinstance(cause,sqlite3.DatabaseError):
        return None
    detail=str(cause).casefold()
    for marker,message in (
        ("no such column","La SELECT fa riferimento a una colonna non esistente."),
        ("no such table","La SELECT fa riferimento a una tabella non esistente."),
        ("no such function","La SELECT usa una funzione SQL non disponibile."),
        ("syntax error","SQLite ha segnalato un errore di sintassi."),
        ("ambiguous column name","Una colonna è ambigua nella SELECT."),
        ("interrupted","La query ha superato il limite di esecuzione."),
    ):
        if marker in detail:
            return message
    return "SQLite non è riuscito a eseguire la SELECT; controlla la query mostrata."


def label_error(exc):
    """Restituisce SOLO informazioni diagnostiche sicure, mai str(exc)."""
    cause=(exc.__cause__ or exc.original) if isinstance(exc,EnginePhaseError) else exc
    kind=type(cause).__name__
    phase=exc.phase if isinstance(exc,EnginePhaseError) else "esecuzione"
    # Classificazioni basate sulla classe, non sul testo dell'errore (che
    # potrebbe contenere URL, prompt o credenziali).
    low=kind.lower()
    # Il codice HTTP è informazione diagnostica non sensibile.
    try:
        http_code=int(getattr(cause,"status_code",0) or 0)
    except (TypeError,ValueError):
        http_code=0
    if http_code==429 or any(word in low for word in ("ratelimit","resourceexhausted","quota")):
        message="Gemini ha raggiunto un limite API (al minuto, ai token o giornaliero). Controlla le quote del modello; non è un errore nella risposta TAG."
        code="QUOTA"
    elif http_code==503 or "serviceunavailable" in low:
        message=("Gemini ha restituito un errore temporaneo di servizio (503). "
                 "Non indica necessariamente che sia scaduto il timeout.")
        code="SERVIZIO"
    elif http_code in (401,403) or any(word in low for word in ("authentication","unauthorized","permission")):
        message="La chiave API è rifiutata dal provider. Controlla i Secrets."
        code="AUTH"
    elif http_code==404 or "notfound" in low:
        message="Il modello configurato non risulta disponibile presso il provider."
        code="MODELLO"
    elif http_code in (502,503,504) or any(word in low for word in ("timeout","connection","connect")):
        message="La connessione al provider non è riuscita o è scaduta."
        code="CONNESSIONE"
    elif http_code==400 or "badrequest" in low or "invalidrequest" in low:
        message="Il provider ha rifiutato la richiesta del modello."
        code="RICHIESTA"
    elif "sql" in phase.casefold() or isinstance(cause,sqlite3.DatabaseError) or "parse" in low:
        message=(_sqlite_error_diagnostic(cause) or
                 "La query SQL generata non è valida o non è eseguibile.")
        code="SQL"
    elif phase=="selezione TAG":
        message="L'operatore semantico LOTUS ha incontrato un errore."
        code="LOTUS"
    elif phase=="risposta del modello" or phase=="generazione SQL":
        message="Non è stato possibile generare la risposta con il modello."
        code="MODELLO"
    else:
        message="La richiesta non è stata completata."
        code="ALTRO"
    logger.warning("FarmaQuery failure: fase=%s categoria=%s tipo=%s",
                   phase,code,kind)
    result={"risposta":f"{message} (fase: {phase}; codice: {code}; "
                        f"tipo: {kind}).",
            "fonti":[],"stato":"ERRORE","codice_errore":code,
            "fase_errore":phase,"tipo_errore":kind}
    # Solo SELECT già validata, fallita in esecuzione; non mostrare SQL
    # rifiutata in validazione o richieste grezze del provider.
    if (isinstance(exc,EnginePhaseError) and phase=="esecuzione SQL"
            and isinstance(getattr(exc,"sql",None),str)
            and len(exc.sql)<=9000):
        result["sql"]=exc.sql
    return result
