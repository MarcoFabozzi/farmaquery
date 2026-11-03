"""Verifica post-sintesi di enumerazioni sul testo ORIGINALE dello snapshot.

Non contiene AIC, medicinali o centri gold precodificati. Il controllo
compara solo stringhe effettivamente estratte dalla stessa fonte citata.
"""
from __future__ import annotations

import re

ABSTENTION_RE=re.compile(r"\bnon documentat[oaie]\b|\bnessuna informazione\b",re.I)


def source_identifiers(rows):
    """Rileva AIC unici dal documento originale, non dalla risposta LLM."""
    return list(dict.fromkeys(
        str(code) for row in rows
        for code in row.get("aic_trovati_nel_testo",())
    ))


def missing_identifiers(answer,source_rows):
    value=str(answer).casefold()
    return [code for code in source_identifiers(source_rows)
            if code.casefold() not in value]


def missing_requirement_cues(question,answer,source_rows):
    """Indizi di condizioni omesse, letti SOLO dalle pagine originali.

    Non deduce requisiti normativi da parole isolate: cerca legami testuali
    ravvicinati, e attiva solo un RICONTROLLO LLM, non una risposta predefinita.
    """
    if not re.search(r"\brequisit\w*|\bcondizion\w*|\bobblig\w*",
                     str(question),re.I):
        return []
    source=" ".join(" ".join(str(row.get("testo") or "").split())
                    for row in source_rows)
    checks=(
        ("abilitazione al registro",
         r"\babilit\w*.{0,130}\bregistr\w*|\bregistr\w*.{0,130}\babilit\w*",
         r"\bregistr\w*"),
        ("autorizzazione alla detenzione",
         r"\bautorizz\w*.{0,130}\bdetenzion\w*|\bdetenzion\w*.{0,130}\bautorizz\w*",
         r"\bdetenzion\w*"),
    )
    return [name for name,source_pattern,answer_pattern in checks
            if re.search(source_pattern,source,re.I)
            and not re.search(answer_pattern,str(answer),re.I)]


def check_enumeration(answer,rows):
    """Indicatori diagnostici, non punteggi di correttezza clinica."""
    expected=source_identifiers(rows)
    missing=missing_identifiers(answer,rows)
    return {"aic_nel_testo":len(expected),
            "aic_omessi_nella_risposta":len(missing),
            "risposta_di_astensione":bool(ABSTENTION_RE.search(str(answer)))}


def revise_if_needed(model,question,answer,rows,complete,ask_fn):
    """Un solo secondo tentativo basato sulla fonte se la sintesi fallisce.

    LOTUS ha già selezionato i documenti. Non genera una risposta da
    repertori o gold; chiede al medesimo LLM di ricontrollare la sezione.
    Il nuovo uso API va sempre sommato a quello della prima sintesi.
    """
    metrics=check_enumeration(answer,rows)
    missing_conditions=missing_requirement_cues(question,answer,rows)
    if not rows or not complete:
        return answer,None,False,metrics
    need_retry=(metrics["aic_omessi_nella_risposta"]>0 or
                metrics["risposta_di_astensione"] or bool(missing_conditions))
    if not need_retry:
        return answer,None,False,metrics
    context={
        "domanda":question,
        "prima_risposta_da_verificare":answer,
        "fonti_integrali":rows,
        "identificativi_aic_rilevati_dal_testo":source_identifiers(rows),
        "condizioni_potenzialmente_omesse_da_ricontrollare":missing_conditions,
        "avviso":"I conteggi automatici sono indizi testuali, non una risposta gold."
    }
    revised,extra=ask_fn(
        model,
        "Rivedi la risposta SOLO leggendo le FONTI INTEGRALI. "
        "Se la domanda richiede tutti gli elementi di una tabella, "
        "riporta ogni riga della tabella richiesta senza ometterne la fine. "
        "Se sono presenti AIC, verifica uno per uno che gli identificativi "
        "nell\u0027atto siano rappresentati, comprese confezioni con stesso dosaggio. "
        "Non dedurre un centro da un\u0027altra indicazione e non inventare dati. "
        "Se la domanda chiede requisiti aggiuntivi, verifica TUTTE le "
        "condizioni esplicite nella nota, comprese eventuali abilitazioni "
        "a registri e autorizzazioni alla detenzione. Gli indizi indicati "
        "non sono prove: controlla che ciascuno riguardi realmente i centri "
        "e l'indicazione della domanda, senza importare altre sezioni. "
        "Se il testo non consente la verifica, dillo e cita il limite. "
        "Rispondi in italiano con fonte/pagina.",
        context,timeout=90,max_tokens=1600
    )
    # Non pubblicare una seconda risposta palesemente meno completa.
    if (revised
        and len(missing_identifiers(revised,rows)) <=
            metrics["aic_omessi_nella_risposta"]
        and (not missing_conditions or
             len(missing_requirement_cues(question,revised,rows)) <
             len(missing_conditions))):
        answer=revised
    metrics=check_enumeration(answer,rows)
    return answer,extra,True,metrics


def enumeration_warning(answer,rows):
    """Non presentare la risposta come esaustiva se restano AIC omessi."""
    missing=missing_identifiers(answer,rows)
    if not missing:
        return ""
    total=len(source_identifiers(rows))
    return ("\n\n**Controllo automatico di completezza:** il testo "
            "originale della fonte contiene "+str(total)+
            " identificativi AIC distinti, ma la risposta non riporta "
            "tutti i codici ("+", ".join(missing)+"). "
            "La risposta generata non è un elenco completo.")