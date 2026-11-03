"""Misura per singola interrogazione delle richieste LLM inviate.

Le chiamate dirette usano LiteLLM con num_retries=0. LOTUS 1.2.4 invia
una richiesta per ogni messaggio non in cache tramite batch_completion:
misuriamo tale numero prima dell'invio, inclusi i tentativi falliti.
Non si cambiano callback globali di LiteLLM (Streamlit e' multi-sessione).
"""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar

_CURRENT=ContextVar("farmaquery_llm_metrics",default=None)


class RequestCalls:
    def __init__(self):
        self.direct=0
        self.lotus=0
        self.lotus_expected=False
        self.lotus_instrumented=False
        self.errors=0

    def direct_attempt(self):
        self.direct+=1

    def instrument_lotus(self,model):
        self.lotus_expected=True
        original=getattr(model,"_process_uncached_messages",None)
        if not callable(original):
            return False
        self.lotus_instrumented=True

        def measured(uncached_data,*args,**kwargs):
            # LOTUS (cache disabilitata) trasmette una richiesta per
            # ogni messaggio di uncached_data, anche tramite batch.
            self.lotus+=len(uncached_data)
            return original(uncached_data,*args,**kwargs)

        model._process_uncached_messages=measured
        return True

    def payload(self):
        complete=(not self.lotus_expected or self.lotus_instrumented)
        return {
            "chiamate_llm_effettive":(self.direct+self.lotus) if complete else None,
            "chiamate_llm_dirette":self.direct,
            "chiamate_llm_lotus":self.lotus if self.lotus_instrumented else None,
            "conteggio_llm_completo":complete,
            "chiamate_llm_interne_provider_sconosciute":False,
            "metodo_conteggio_llm":(
                "invii LiteLLM diretti + messaggi LOTUS non in cache; "
                "num_retries=0; non include retry di rete invisibili al client")
        }


@contextmanager
def measure_requests():
    counter=RequestCalls()
    token=_CURRENT.set(counter)
    try:
        yield counter
    finally:
        _CURRENT.reset(token)


def direct_attempt():
    counter=_CURRENT.get()
    if counter is not None:
        counter.direct_attempt()


def instrument_lotus(model):
    counter=_CURRENT.get()
    return counter.instrument_lotus(model) if counter is not None else False


def measured_engine(func):
    """Decorator che assegna diagnostica SOLO al risultato della richiesta."""
    import functools
    import time

    @functools.wraps(func)
    def wrapped(*args,**kwargs):
        with measure_requests() as counter:
            start=time.monotonic()
            try:
                result=func(*args,**kwargs)
            except Exception as exc:
                # L'errore va propagato; allega la diagnostica dove
                # consentito, senza esporre credenziali o prompt sensibili.
                try:
                    exc.metriche_llm={**counter.payload(),
                                     "tempo_backend_s":round(
                                         time.monotonic()-start,3)}
                except Exception:
                    pass
                raise
            if isinstance(result,dict):
                result.update(counter.payload())
                result["tempo_backend_s"]=round(time.monotonic()-start,3)
            return result

    return wrapped
