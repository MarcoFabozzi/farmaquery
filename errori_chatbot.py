"""Errori leggibili per la chat senza mostrare token, prompt o chiavi API."""
from __future__ import annotations

import logging

logger=logging.getLogger("farmaquery.chatbot")


class EnginePhaseError(Exception):
    """Errore di esecuzione con fase nota; eccezione originale in __cause__."""

    def __init__(self,phase,original):
        self.phase=phase
        self.original=original
        self.error_type=type(original).__name__
        super().__init__(f"{phase}: {self.error_type}")


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
        message="Gemini ha esaurito la quota di richieste per questo modello."
        code="QUOTA"
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
    elif "sql" in phase or "sqlite" in low or "parse" in low:
        message="La query SQL generata non è valida o non è eseguibile."
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
    return {"risposta":f"{message} (fase: {phase}; codice: {code}; "
                       f"tipo: {kind}).",
            "fonti":[],"stato":"ERRORE","codice_errore":code,
            "fase_errore":phase,"tipo_errore":kind}
