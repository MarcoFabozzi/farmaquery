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
    return bool(re.search(
        r"\b(tutti|tutte|complet[oaie]|"
        r"quante\s+(?:confezioni|penne)|"
        r"quanti\s+(?:centri|aic|farmaci|medicinali)|"
        r"numero\s+d(?:i|elle?)\s+(?:confezioni|centri|aic)|"
        r"tabella\s*\d+|articolo\s*\d+|art\.\s*\d+|"\n        r"pagina\s*\d+|pag\.\s*\d+|"
        r"quali\s+protocolli|quale\s+precedente\s+nota|"
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
    ids=[r[0] for r in db.execute(
        "SELECT id FROM note WHERE farmaco_candidato=? COLLATE NOCASE "
        "OR nome_file LIKE ? ESCAPE '\\' COLLATE NOCASE "
        "ORDER BY anno DESC,id LIMIT 2",(target,"%"+escaped+"%"))]
    if not ids:
        return [],True

    page_matches=re.findall(r"\b(?:pagina|pag\.)\s*(\d+)\b",question,re.I)
    requested_pages=set(int(n) for n in page_matches)
    for note_id in ids[:2]:
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
        # Senza pagina esplicita, conserva l'ordine del PDF: le intestazioni
        # delle tabelle e le clausole giuridiche non vanno separate arbitrariamente.
        for page in pages:
            src=(str(page["percorso_zip"])+"#p"+str(page["numero_pagina"])
                 +" | archivio: "+str(page["archivio_url"]))
            header=("TESTO DI PAGINA REGIONALE; interpretare la struttura "
                    "delle tabelle senza trasferire i centri ad altre "
                    "indicazioni. Documento: "+str(page["nome_file"])+
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
