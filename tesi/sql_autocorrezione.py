"""Terza baseline controllata: Text-to-SQL con massimo due autocorrezioni.

L'esperimento conserva lo stesso primo prompt e lo stesso SQL in sola lettura
della baseline standard. Corregge soltanto SQL rifiutata/non eseguibile;
non ripete query valide che restituiscono zero righe e non usa LOTUS.
"""
from __future__ import annotations

from errori_chatbot import EnginePhaseError, label_error
from tesi.contatore_llm import measured_engine
from tesi import pilota_tag_vs_sql as sql_base

MAX_CORREZIONI = 2

CORRECTION_PROMPT = (
    "Correggi la query SQL SQLite che e' fallita. Usa soltanto lo schema "
    "fornito e preserva esattamente lo scopo della domanda originale. "
    "Correggi soltanto l'errore sintattico, di colonna/tabella o di JOIN. "
    "Non ampliare semanticamente la ricerca, non usare LOTUS, non inventare "
    "colonne o dati e non introdurre domande aggiuntive. "
    "Restituisci UNA sola SELECT in sola lettura, senza Markdown."
)


def _errore_sql(exc):
    return (isinstance(exc,EnginePhaseError) and
            exc.phase in {"validazione SQL","esecuzione SQL"})


def _descrizione_errore(exc):
    """Restituisce al correttore soltanto una motivazione SQL limitata."""
    if not _errore_sql(exc):
        return "Errore SQL non riconosciuto"
    cause=exc.__cause__ or exc.original
    return str(cause)[:350]


@measured_engine
def sql_autocorrezione(db,question,model):
    """Prima SELECT identica alla baseline; al piu' due riscritture LLM.

    Errore del provider, quote e sintesi non attivano altri tentativi.
    """
    schema=sql_base._sql_schema(db)
    generated,usage=sql_base._in_phase(
        "generazione SQL",sql_base.ask,model,
        sql_base.SQL_GENERATION_PROMPT,{"schema":schema,"domanda":question}
    )
    initial=generated
    proposed=[]
    failures=[]
    sql=None
    corrections=0
    for attempt in range(MAX_CORREZIONI+1):
        proposed.append(generated)
        try:
            sql=sql_base._in_phase("validazione SQL",sql_base.validate_sql,generated)
            rows,truncated=sql_base._execute_generated_select(db,sql)
            break
        except EnginePhaseError as exc:
            if not _errore_sql(exc):
                raise
            failures.append({
                "tentativo":attempt+1,
                "fase":exc.phase,
                "tipo":exc.error_type,
                "errore_sql":_descrizione_errore(exc),
            })
            if attempt==MAX_CORREZIONI:
                result=label_error(exc)
                result.update({
                    "stato":"ERRORE_SQL",
                    "sql":sql or "",
                    "sql_originale_llm":initial,
                    "sql_proposte":proposed,
                    "errori_sql_tentativi":failures,
                    "sql_tentativi":len(proposed),
                    "correzioni_sql":corrections,
                    "versione_text_to_sql":"autocorrezione-v1",
                    **usage,
                })
                return result
            generated,next_usage=sql_base._in_phase(
                "correzione SQL",sql_base.ask,model,CORRECTION_PROMPT,
                {"domanda":question,"schema":schema,
                 "sql_errata":generated,
                 "errore":_descrizione_errore(exc)}
            )
            usage=sql_base._accumulate(usage,next_usage)
            corrections+=1

    metadata={
        "sql_originale_llm":initial,
        "sql_proposte":proposed,
        "errori_sql_tentativi":failures,
        "sql_tentativi":len(proposed),
        "correzioni_sql":corrections,
        "versione_text_to_sql":"autocorrezione-v1",
        "categoria_implicita":False,
    }
    if not rows:
        return {
            "risposta":(
                "La query SQL generata non ha restituito risultati "
                "nella base di dati consultata. Questo non dimostra "
                "che l'informazione sia assente nei documenti."
            ),
            "fonti":[],"sql":sql,"righe_sql":0,
            "stato":"NESSUNA_EVIDENZA","risultato_parziale":False,
            **usage,"costo_completo":usage.get("costo_usd") is not None,
            **metadata,
        }
    citations=sql_base._sql_sources(db,rows)
    answer,next_usage=sql_base._in_phase(
        "sintesi SQL",sql_base.ask,model,sql_base.SQL_ANSWER_PROMPT,
        {"domanda":question,"righe_sql":rows,"fonti_recuperate":citations,
         "risultati_parziali":truncated}
    )
    usage=sql_base._accumulate(usage,next_usage)
    if truncated:
        answer+=(
            "\n\nAvvertenza: risultati SQL parziali per limite di righe, "
            "limite della query o di contesto. L'elenco non puo' essere "
            "considerato completo."
        )
    evidence=[{
        "tipo":"SQL","fonte":"Riga "+str(i+1),
        "testo":str(row.get("testo") or row.get("indicazione_ema")
                   or row.get("descrizione") or "")
    } for i,row in enumerate(rows) if (
        row.get("testo") or row.get("indicazione_ema") or row.get("descrizione")
    )]
    return {
        "risposta":answer,"fonti":citations,"sql":sql,
        "evidenze_fonti":sql_base._source_previews(evidence),
        "righe_sql":len(rows),
        "stato":"RISULTATI_PARZIALI" if truncated else "OK",
        "risultato_parziale":truncated,
        **usage,"costo_completo":usage.get("costo_usd") is not None,
        **metadata,
    }
