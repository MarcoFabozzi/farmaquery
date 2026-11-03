"""Recupero delle sezioni integralmente disponibili per il TAG.

Le evidenze sono SOLO testo del medesimo SQLite dello snapshot sperimentale.
Il filtro LOTUS resta attivo a monte; questi passaggi conservano l'integrità
della sezione per le richieste esplicitamente esaustive/documento-specifiche.
Non contiene identificativi predefiniti di medicinali, AIC o centri.
"""
from __future__ import annotations

import re


AIC_RE=re.compile(r"\bA\.?\s*I\.?\s*C\.?\s*n\.?\s*(\d{8,10}(?:/E)?)",re.I)
CODE_RE=re.compile(r"\b\d{2}[A-Za-z]\d{5}\b")


def richiede_sezione_completa(question):
    q=question.casefold()
    # Una domanda su una nota identificata da anno/protocollo o che
    # richiede indicazioni e combinazioni usa l'intero documento, non
    # soltanto l'estratto scelto da LOTUS. Non usa risposte gold.
    nota_nominata=bool(
        re.search(r"\\bnota\\b",q) and
        re.search(r"\\b(?:20\\d{2}|prot\\.?|indicazion\\w*|"
                  r"associazion\\w*|combinazion\\w*|richiam\\w*|"
                  r"rimand\\w*|sostitui\\w*|condizion\\w*|"
                  r"requisit\\w*)\\b",q)
    )
    return nota_nominata or bool(re.search(
        r"\b(tutti|tutte|complet[oaie]|"
        r"quante\s+(?:confezioni|penne)|"
        r"quanti\s+(?:centri|aic|farmaci|medicinali)|"
        r"numero\s+d(?:i|elle?)\s+(?:confezioni|centri|aic)|"
        r"tabella\s*\d+|articolo\s*\d+|art\.\s*\d+|"
        r"pagina\s*\d+|pag\.\s*\d+|"
        r"quali\s+protocolli|quale\s+precedente\s+nota|"
        r"quale\s+nota(?:\s+del\s+20\d{2})?\s+(?:richiam\w*|cit\w*)|"
        r"quali\s+sono\s+(?:esattamente\s+)?(?:i|le|gli)\s+"
        r"(?:\w+\s+)?(?:centri|strutture|presidi)|"
        r"annulla\s+e\s+sostituisce)\b",q))


def _tables(db):
    return {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _append_with_budget(out,remaining,item,source_complete=True):
    full=str(item["testo"])
    if len(full)>remaining:
        if remaining>180:
            shorter=dict(item)
            shorter["testo"]=full[:remaining]+"\n[TESTO TAGLIATO: NON ESAUSTIVO]"
            shorter["integrale"]=False
            out.append(shorter)
        return 0,False
    item["integrale"]=source_complete
    out.append(item)
    return remaining-len(full),True


def contesto_integrale(db,question,target,max_chars=18500):
    """Restituisce (passaggi, copertura_integrale) dalla fonte effettiva.

    Il valore False segnala sezioni/documenti non interamente rappresentati.
    Non ricostruisce informazioni mancanti da registri o risposte gold.
    """
    if not richiede_sezione_completa(question):
        return [],True
    available=_tables(db)
    remaining=max_chars
    out=[]
    complete=True

    codes=list(dict.fromkeys(x.upper() for x in CODE_RE.findall(question)))
    if codes and {"gu_documenti","gu_atti"}.issubset(available):
        for code in codes[:2]:
            documents=[dict(r) for r in db.execute(
                "SELECT documento_id,tipo_documento,url_fonte,testo "
                "FROM gu_documenti WHERE codice=? "
                "ORDER BY CASE WHEN tipo_documento='ATTO' THEN 0 ELSE 1 END,"
                "documento_id",(code,))]
            for doc in documents:
                # Articolo puntuale: l'atto è l'unità richiesta; non
                # consumare la quota su allegati non menzionati.
                if (re.search(r"\b(?:articolo|art\.)\s*\d+\b",
                              question,re.I)
                    and doc["tipo_documento"]!="ATTO"
                    and "allegat" not in question.casefold()):
                    continue
                body=str(doc["testo"])
                # Se si chiede un articolo preciso, nessun altro articolo
                # deve consumare il budget riservato alla sua enumerazione.
                article=re.search(r"\b(?:articolo|art\.)\s*(\d+)\b",question,re.I)
                if article:
                    number=article.group(1)
                    start=re.search(r"\bArt\.\s*"+re.escape(number)+r"\b",body,re.I)
                    if start:
                        next_article=re.search(
                            r"\bArt\.\s*\d+\b",body[start.end():],re.I)
                        end=(start.end()+next_article.start()
                             if next_article else len(body))
                        body=body[start.start():end]
                if not body.strip():
                    continue
                src=("GU "+code+" | "+str(doc["url_fonte"]))
                identifiers=list(dict.fromkeys(AIC_RE.findall(body)))
                header=("DOCUMENTO ORIGINALE GU "+code+
                        " (tipo "+str(doc["tipo_documento"])+
                        "; identificativi AIC rilevati nel testo "+
                        str(len(identifiers))+"; contarli e verificarli "
                        "sull'originale):\n")
                remaining,ok=_append_with_budget(out,remaining,{
                    "tipo":"GU",
                    "chiave":"GU:INTEGRALE:"+str(doc["documento_id"]),
                    "testo":header+body,
                    "fonte":src,
                    "aic_trovati_nel_testo":identifiers,
                })
                complete=complete and ok
                if not ok:
                    break
            if remaining<=0:
                break
        return out,complete and bool(out)

    if not target or not {"note","pagine"}.issubset(available):
        return [],True

    escaped=(str(target).replace("\\","\\\\").replace("%","\\%")
             .replace("_","\\_"))
    notes=[dict(r) for r in db.execute(
        "SELECT id,anno,nome_file FROM note "
        "WHERE farmaco_candidato=? COLLATE NOCASE "
        "OR nome_file LIKE ? ESCAPE '\\' COLLATE NOCASE "
        "ORDER BY anno DESC,id LIMIT 8",(target,"%"+escaped+"%"))]
    if not notes:
        return [],True

    # In "CASGEVY nel 2025" il 2024 riguarda la nota RICHIAMATA:
    # privilegiare l'anno vicino al nome del medicinale, non il primo
    # anno presente nella domanda. Mai scegliere una fonte fuori dallo SQLite.
    match_year=re.search(re.escape(str(target))+r".{0,55}?(20\d{2})",
                         question,re.I)
    if match_year:
        matching=[r for r in notes if str(r["anno"])==match_year.group(1)]
        if matching:
            notes=matching
    # Se è riportato un protocollo della nota oggetto della domanda,
    # preferire la corrispondenza nel nome del PDF; NON cercare qui la
    # nota precedente menzionata dal testo.
    protocols=re.findall(r"\b\d{6,10}\b",question)
    named=[r for r in notes if any(p in r["nome_file"] for p in protocols)]
    if named:
        notes=named
    ids=[r["id"] for r in notes[:2]]

    page_matches=re.findall(r"\b(?:pagina|pag\.)\s*(\d+)\b",question,re.I)
    requested_pages=set(int(n) for n in page_matches)
    for note_id in ids:
        pages=[dict(r) for r in db.execute(
            "SELECT p.numero_pagina,p.testo,n.nome_file,n.percorso_zip,"
            "n.archivio_url FROM pagine p JOIN note n ON n.id=p.nota_id "
            "WHERE p.nota_id=? AND p.metodo IN ('TESTO','OCR') "
            "AND length(trim(p.testo))>0 ORDER BY p.numero_pagina",
            (note_id,))]
        if requested_pages:
            pages=[p for p in pages if p["numero_pagina"] in requested_pages]
            if requested_pages - {p["numero_pagina"] for p in pages}:
                complete=False
        else:
            # Alcuni PDF uniscono la nota amministrativa a una procedura
            # operativa autonoma, con intestazione e numero di revisione.
            # Se si chiede la NOTA (non la procedura), il testo integrale
            # richiesto termina prima di quella sezione separata. Senza
            # questo confine il budget si esaurisce sulle appendici e
            # la prima nota viene falsamente marcata come parziale.
            if (re.search(r"\bnota\b",question,re.I)
                and not re.search(r"\bprocedur\w*\b",question,re.I)):
                for i,page in enumerate(pages):
                    heading=" ".join(str(page["testo"]).split())[:340]
                    if (i>0 and re.match(
                        r"\s*PROCEDURA\s+PER\s+LA\s+GESTIONE\b",
                        heading,re.I)
                        and re.search(r"\bRevisione\b",heading,re.I)):
                        pages=pages[:i]
                        break
            # Con un budget limitato leggere PRIMA le pagine che rispondono
            # alla domanda, non consumarlo sulla copertina/introduzione.
            # Ogni pagina mantiene testo e citazione originali; i punteggi
            # servono solo all'ordinamento, non sono prove regolatorie.
            q=question.casefold()
            words=set(re.findall(r"[a-zà-ÿ0-9]{4,}",q))
            words-=set(("quali","quale","sono","della","delle","della",
                        "secondo","nota","regionale","individuati",
                        "esattamente","precedente","documento"))
            def priority(page):
                body=str(page["testo"]).casefold()
                score=sum(2 for word in words if word in body)
                if any(word in q for word in ("centr","struttur","prescr")):
                    if re.search(r"\b(?:aou|aorn|irccs|tabella|u\.o\.)\b",body):
                        score+=8
                if any(word in q for word in ("requisit","condizion","abilitat")):
                    if re.search(r"registro|detenzion|abilitat|autorizzat",body):
                        score+=6
                if any(word in q for word in ("richiam","rimand","sostitui")):
                    if re.search(r"pg\s*/\s*20\d{2}|prot|sinfonia",body):
                        score+=6
                return (-score,page["numero_pagina"])
            pages.sort(key=priority)
        for page in pages:
            src=(str(page["percorso_zip"])+"#p"+str(page["numero_pagina"])
                 +" | archivio: "+str(page["archivio_url"]))
            header=("TESTO DI PAGINA REGIONALE; interpretare la struttura "
                    "delle tabelle senza trasferire i centri ad altre "
                    "indicazioni. Ogni affermazione va citata con la pagina "
                    "che CONTIENE il relativo passo. Documento: "+
                    str(page["nome_file"])+
                    "; pagina "+str(page["numero_pagina"])+"\n")
            remaining,ok=_append_with_budget(out,remaining,{
                "tipo":"REGIONE",
                "chiave":"REGIONE:INTEGRALE:"+str(note_id)+
                         "#p"+str(page["numero_pagina"]),
                "testo":header+str(page["testo"]),
                "fonte":src,
            })
            if not ok:
                complete=False
                break
        if remaining<=0:
            break
    return out,complete and bool(out)
