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
    missing=[name for name,source_pattern,answer_pattern in checks
             if re.search(source_pattern,source,re.I)
             and not re.search(answer_pattern,str(answer),re.I)]
    # Prescrizione e condizioni possono includere la classe e un registro
    # della specifica indicazione. Sono segnali di revisione, NON fatti
    # da aggiungere automaticamente alla risposta.
    if re.search(r"\bcondizion\w*",str(question),re.I):
        if (re.search(r"\bclass[ei]\s+[AH]\b",source,re.I)
            and not re.search(r"\bclass[ei]\s+[AH]\b",str(answer),re.I)):
            missing.append("classe specificata nel documento")
        if (re.search(r"\bregistr[oi]\b",source,re.I)
            and not re.search(r"\bregistr\w*",str(answer),re.I)):
            missing.append("registro specificato nel documento")
    # Un requisito di detenzione può specificare un radionuclide:
    # controlla il nome e il numero realmente estratti dalla fonte,
    # senza usare alcun isotopo predefinito nel codice.
    if re.search(r"\bdetenzion\w*",source,re.I):
        for match in re.finditer(r"\bdetenzion\w*",source,re.I):
            local=source[max(0,match.start()-160):match.end()+160]
            for isotope in re.findall(
                    r"\b[A-Za-zÀ-ÿ]{4,}[-\s]+\d{2,3}\b",local):
                number=re.search(r"\d{2,3}",isotope).group()
                if not re.search(r"\b"+re.escape(number)+r"\b",str(answer)):
                    missing.append("specificità del requisito: "+isotope)
                    break
            if any(item.startswith("specificità") for item in missing):
                break
    return list(dict.fromkeys(missing))


def missing_therapy_associations(question,answer,source_rows):
    """Indizio di associazioni omesse: conta frasi esplicite nella risposta.

    Non deriva farmaci né indicazioni dal gold. Un indizio attiva soltanto
    una seconda lettura delle pagine originali dallo stesso SQLite.
    """
    q=str(question)
    if (not source_rows or
        not re.search(r"\b(?:associazion\w*|combinazion\w*)\b",q,re.I) or
        not re.search(r"\b(?:indicazion\w*|condizion\w*)\b",q,re.I)):
        return []
    counts={"due":2,"tre":3,"quattro":4,"cinque":5,"sei":6}
    number=re.search(r"\b(due|tre|quattro|cinque|sei|\d+)\s+"
                     r"(?:nuov[ea]\s+)?indicazion\w*\b",q,re.I)
    expected=(int(number.group(1)) if number and number.group(1).isdigit()
              else counts.get(number.group(1).casefold(),2) if number else 2)
    observed=len(re.findall(
        r"\bin\s+associazione\b|\bassociat[oaie]\b|"
        r"\bcombinat[oaie]\b|\w\s*\+\s*\w",str(answer),re.I))
    if observed>=expected:
        return []
    return ["combinazioni documentali da riesaminare: "+
            str(observed)+"/"+str(expected)]



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
    missing_therapies=missing_therapy_associations(question,answer,rows)
    if not rows or not complete:
        return answer,None,False,metrics
    need_retry=(metrics["aic_omessi_nella_risposta"]>0 or
                metrics["risposta_di_astensione"] or bool(missing_conditions)
                or bool(missing_therapies))
    if not need_retry:
        return answer,None,False,metrics
    context={
        "domanda":question,
        "prima_risposta_da_verificare":answer,
        "fonti_integrali":rows,
        "identificativi_aic_rilevati_dal_testo":source_identifiers(rows),
        "condizioni_potenzialmente_omesse_da_ricontrollare":missing_conditions,
        "associazioni_potenzialmente_omesse":missing_therapies,
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
        "Per quesiti su indicazioni e combinazioni terapeutiche distinte, "
        "ricostruisci le associazioni PER OGNI indicazione, mutazione, linea "
        "di trattamento e via di somministrazione documentata. Non "
        "raggruppare sezioni diverse nella prima indicazione incontrata. "
        "Se il testo non consente la verifica, dillo e cita il limite. "
        "Rispondi in italiano con fonte/pagina.",
        context,timeout=90,max_tokens=1600
    )
    # Accetta solo se la revisione riduce le omissioni rilevabili,
    # senza introdurre AIC mancanti; un LLM non è mai il gold.
    original_missing=(metrics["aic_omessi_nella_risposta"]+
                      len(missing_conditions)+len(missing_therapies)+
                      int(metrics["risposta_di_astensione"]))
    revised_missing=(len(missing_identifiers(revised,rows))+
                     len(missing_requirement_cues(question,revised,rows))+
                     len(missing_therapy_associations(question,revised,rows))+
                     int(bool(ABSTENTION_RE.search(revised or ""))))
    if (revised and revised_missing<original_missing and
        len(missing_identifiers(revised,rows)) <=
        metrics["aic_omessi_nella_risposta"]):
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