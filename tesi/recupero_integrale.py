"""Recupero integrale *mirato* di articoli GU e tabelle regionali.

Il contenuto è sempre copiato dallo SQLite congelato: nessun valore clinico,
centro, classe o AIC è predeterminato nel codice. Serve a evitare che i tagli
dei primi 1800/2150 caratteri producano elenchi falsamente incompleti.
"""
from __future__ import annotations

import re

PAGE_REQUEST = re.compile(r"\b(?:pagina|pag\.?|p\.)\s*(\d{1,3})\b",re.I)
NORM_REQUEST = re.compile(
    r"protocoll|richiam|sostitu|annull|rettific|abrog|precedent|"
    r"tutti|tutte|tabella",re.I)
GU_CODE = re.compile(r"\b\d{2}[a-z]\d{5}\b",re.I)
GU_ENUMERATION = re.compile(
    r"\b(?:tutti|tutte|quante|quanti|elenc|aic|confezion|articolo)\b",re.I)
NORM_TOKENS = re.compile(
    r"\b(?:protocollo|prot\.?|PG[/\.\-\s]|annulla|annullata|"
    r"sostituisce|sostituita|rettifica|abroga|richiama|"
    r"precedente|in riferimento|variazione)\b",re.I)


def norm_context(text,cap=10000):
    """Seleziona finestre attorno ai rimandi, mantenendo i verbi giuridici."""
    if len(text)<=cap:
        return text
    intervals=[]
    for m in list(NORM_TOKENS.finditer(text))[:18]:
        left=max(0,m.start()-320)
        right=min(len(text),m.end()+440)
        if intervals and left<=intervals[-1][1]:
            intervals[-1]=(intervals[-1][0],max(intervals[-1][1],right))
        else:
            intervals.append((left,right))
    if not intervals:
        return text[:cap] + " [ESTRATTO PARZIALE]"
    result=" [...] ".join(text[a:b] for a,b in intervals)
    return (result[:cap]+" [ESTRATTO PARZIALE]" if len(result)>cap else result)


def regional_precise_evidence(db, question, target):
    """La pagina esplicita o il testo del rimando dalle note di quel farmaco.

    Limitare l'accesso a una nota identificata nella domanda; in assenza
    di riscontro non dedurre l'esistenza di un documento.
    """
    if not target or not (PAGE_REQUEST.search(question) or NORM_REQUEST.search(question)):
        return []
    q=question.casefold()
    asked=PAGE_REQUEST.search(question)
    page=int(asked.group(1)) if asked else None
    escaped=target.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
    try:
        notes=db.execute(
            "SELECT id,nome_file,farmaco_candidato,percorso_zip,archivio_url "
            "FROM note WHERE farmaco_candidato=? COLLATE NOCASE "
            "OR nome_file LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "ORDER BY anno DESC LIMIT 3",(target,"%"+escaped+"%")).fetchall()
    except Exception:
        return []
    result=[]
    for n in notes:
        rows=db.execute(
            "SELECT numero_pagina,testo,metodo FROM pagine "
            "WHERE nota_id=? ORDER BY numero_pagina",(n["id"],)).fetchall()
        readable=[p for p in rows if p["metodo"] in ("TESTO","OCR") and p["testo"]]
        if page is not None:
            readable=[p for p in readable if p["numero_pagina"]==page]
        elif NORM_TOKENS.search(q):
            hits=[p for p in readable if NORM_TOKENS.search(str(p["testo"]))]
            readable=hits[:3] if hits else readable[:2]
        else:
            readable=readable[:4]
        for p in readable[:4]:
            body=str(p["testo"])
            # Per elenchi espliciti si conserva la tabella effettiva, non
            # soltanto la prima finestra o l'intestazione ripetuta.
            excerpt=(norm_context(body) if NORM_TOKENS.search(q) and page is None
                     else body[:12000])
            cut=len(body)>len(excerpt)
            source=(str(n["percorso_zip"])+"#p"+str(p["numero_pagina"])
                    +" | archivio: "+str(n["archivio_url"]))
            result.append({
                "tipo":"REGIONE",
                "chiave":"REGIONE:PAGINA_COMPLETA:"+str(n["id"])+"#p"+
                         str(p["numero_pagina"]),
                "testo":("Documento: "+str(n["nome_file"])+
                         "; farmaco candidato: "+str(n["farmaco_candidato"])+
                         "; pagina "+str(p["numero_pagina"])+
                         "; testo effettivo della pagina: "+excerpt+
                         (" [ESTRATTO PARZIALE]" if cut and
                          "ESTRATTO PARZIALE" not in excerpt else "")),
                "testo_selezione":(
                    "Documento: "+str(n["nome_file"])+
                    "; pagina "+str(p["numero_pagina"])+
                    "; estratto mirato completo disponibile per la sintesi. "
                    + (excerpt[:650] if len(excerpt)<=1200
                       else norm_context(excerpt,cap=1000))),
                "fonte":source,
                "fonti":[source],
                "integrale_pagina":not cut,
            })
    return result


def gu_article_evidence(db, question):
    """Restituisce l'intero articolo richiesto, non i primi k segmenti FTS."""
    match=GU_CODE.search(question)
    if not match or not GU_ENUMERATION.search(question):
        return []
    code=match.group().upper()
    try:
        docs=db.execute(
            "SELECT documento_id,tipo_documento,url_fonte,testo "
            "FROM gu_documenti WHERE codice=? AND tipo_documento='ATTO' "
            "ORDER BY documento_id LIMIT 1",(code,)).fetchall()
    except Exception:
        return []
    output=[]
    for doc in docs:
        body=str(doc["testo"])
        start=re.search(r"\bArt\.\s*1\b",body,re.I)
        if start:
            tail=body[start.start():]
            next_article=re.search(r"\bArt\.\s*[2-9]\d*\b",tail[10:],re.I)
            article=tail[:10+next_article.start()] if next_article else tail
        else:
            article=body
        # Tutta la sezione, inclusa l'ultima confezione. Se enorme, la
        # limitazione si segnala anziché fingere che l'elenco sia esaustivo.
        cut=len(article)>13000
        excerpt=article[:13000]
        source="GU "+code+" | "+str(doc["url_fonte"])
        output.append({
            "tipo":"GU","chiave":"GU:ARTICOLO:"+str(doc["documento_id"]),
            "testo":("Atto GU "+code+"; articolo integrale ricavato dal "
                     "testo archiviato (entro limite dichiarato): "+
                     excerpt+(" [ESTRATTO PARZIALE]" if cut else "")),
            "testo_selezione":(
                "GU "+code+"; articolo che contiene l'elenco completo "
                "delle confezioni e dei rispettivi AIC, testo originale "
                "disponibile per la sintesi. "+
                excerpt[:800]),
            "fonte":source,"fonti":[source],
            "integrale_articolo":not cut
        })
    return output
