"""Recupero SQL-first per TAG: le righe precedono la lettura dei PDF.

Prima interroga tutte le pagine che menzionano la struttura richiesta, SENZA
prendere i primi N PDF; poi usa una preselezione lessicale ad alto richiamo
e conserva, per ogni nota, indicazione candidata e pagine citabili.
La categoria clinica e l'associazione indicazione-centro saranno verificate
dall'LLM sul testo della nota. Nessuna risposta predefinita o lista gold.
"""
from __future__ import annotations

import re
from tesi.recupero_regionale import categoria


def _tables(db):
    return {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _requested_center(question):
    text=str(question).casefold()
    # Espressioni di strutture, NON nomi di medicinali.
    for key in ("federico", "cardarelli", "vanvitelli", "santobono",
                "pascale", "ruggi", "monaldi"):
        if key in text:
            return key
    match=re.search(r"(?:presso|centro|ospedale|aou|aorn)\s+(?:l'|il|la)?"
                    r"\s*([A-Za-zÀ-ÿ]{5,})",str(question),re.I)
    return match.group(1).casefold() if match else ""


def _window(body, keywords, max_chars=1450):
    """Estratto con contesto, mai prova autonoma di autorizzazione."""
    clean=" ".join(str(body or "").split())
    lower=clean.casefold()
    hits=[]
    for key in keywords:
        if not key:
            continue
        m=re.search(re.escape(key.casefold()),lower)
        if m:
            hits.append(m.start())
    if not hits:
        return clean[:max_chars]
    at=min(hits)
    left=max(0,at-220)
    return clean[left:left+max_chars]


def retrieve_category_sql_first(db,question,max_rows=180):
    """(evidenze, diagnostica) per domande su categoria + centro.

    Lo stadio 1 recupera tutte le note contenenti il centro attraverso SQL;
    lo stadio 2 consulta TUTTE le loro pagine prima della preselezione
    lessicale. Nessuna nota viene esclusa per ordinamento top-k.
    """
    kind,keywords=categoria(question)
    center=_requested_center(question)
    if not kind or not center:
        return [],{"applicabile":False}
    required={"note","pagine"}
    if not required <= _tables(db):
        return [],{"applicabile":False}
    available=_tables(db)
    metadata=("LEFT JOIN nota_metadati_revisionati m ON m.nota_id=n.id "
              if "nota_metadati_revisionati" in available else "")
    indication=("COALESCE(NULLIF(m.indicazione,''),"
                "n.indicazione_candidata) AS indicazione"
                if metadata else "n.indicazione_candidata AS indicazione")
    sql=(
        "SELECT DISTINCT n.id AS nota_id,n.farmaco_candidato,n.nome_file,"
        "n.percorso_zip,n.archivio_url,p.numero_pagina AS pagina_centro,"
        "p.testo AS testo_centro,"+indication+
        " FROM note n JOIN pagine p ON p.nota_id=n.id "+
        metadata+
        "WHERE p.metodo IN ('TESTO','OCR') "
        "AND p.testo LIKE ? COLLATE NOCASE "
        "ORDER BY n.id,p.numero_pagina"
    )
    # Filtrare % e _ evita che il nome della struttura diventi un pattern SQL.
    escaped=center.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
    sql=sql.replace("p.testo LIKE ? COLLATE NOCASE",
                    "p.testo LIKE ? ESCAPE '\\' COLLATE NOCASE")
    center_hits=[dict(x) for x in db.execute(sql,("%"+escaped+"%",))]
    found={}
    for hit in center_hits:
        found.setdefault(str(hit["nota_id"]),[]).append(hit)
    eligible=[]
    for note_id,center_rows in found.items():
        pages=[dict(x) for x in db.execute(
            "SELECT numero_pagina,testo,metodo FROM pagine "
            "WHERE nota_id=? AND metodo IN ('TESTO','OCR') "
            "AND length(trim(testo))>0 ORDER BY numero_pagina",(note_id,))]
        full="\n".join(str(p["testo"] or "") for p in pages).casefold()
        # Questa ricerca amplia i candidati; non decide la patologia
        # e non assegna ad alcun farmaco una struttura autorizzata.
        matched=[kw for kw in keywords if kw.casefold() in full]
        if not matched:
            continue
        first=center_rows[0]
        rank=lambda p: (
            0 if (center in str(p["testo"]).casefold() and
                  any(k in str(p["testo"]).casefold() for k in matched)) else
            1 if center in str(p["testo"]).casefold() else
            2 if any(k in str(p["testo"]).casefold() for k in matched) else 3,
            p["numero_pagina"]
        )
        ordered=sorted(pages,key=rank)
        selected=ordered[:3]
        references=[
            str(first["percorso_zip"])+"#p"+str(p["numero_pagina"])+
            " | archivio: "+str(first["archivio_url"])
            for p in selected]
        snippets=[
            {"pagina":int(p["numero_pagina"]),
             "estratto":_window(p["testo"],[center]+matched,1600)}
            for p in selected]
        medication=str(first.get("farmaco_candidato") or "")
        indication=str(first.get("indicazione") or "")
        descr=(
            "DOCUMENTO CANDIDATO SQL-FIRST; NESSUNA AUTORIZZAZIONE "
            "CERTIFICATA DALLA SOLA MENZIONE. "
            "Documento: "+str(first.get("nome_file") or "")+
            "; farmaco candidato: "+medication+
            "; indicazione tabellare (da verificare sul testo): "+indication+
            "; pagine in cui compare la struttura: "+
            ", ".join(str(r["pagina_centro"]) for r in center_rows)+
            "; estratti: "+" ".join(
                "[pagina "+str(x["pagina"])+"] "+x["estratto"]
                for x in snippets))
        eligible.append({
            "tipo":"REGIONE",
            "chiave":"REGIONE:DOC:"+note_id,
            "testo":descr[:6000],
            "testo_selezione":(
                "Documento: "+str(first.get("nome_file") or "")+
                "; farmaco candidato: "+medication+
                "; indicazione tabellare: "+indication+
                "; evidenze: "+" ".join(
                    "[p"+str(x["pagina"])+"] "+x["estratto"][:370]
                    for x in snippets)),
            "fonte":references[0],
            "fonti":references,
            "passaggi_sintesi":snippets,
            "farmaco_sql":medication,
            "indicazione_sql":indication,
            "pagine_centro_sql":[int(r["pagina_centro"]) for r in center_rows],
            "note_sql_esaminate":len(found)
        })
    truncated=len(eligible)>max_rows
    if truncated:
        # Limite dichiarato: NON confondere un output parziale con un elenco
        # completo. Il conteggio precedente preserva la copertura totale.
        eligible=eligible[:max_rows]
    for item in eligible:
        item["copertura_documenti"]=len(found)
        item["documenti_troncati"]=truncated
    return eligible,{
        "applicabile":True,"tipo":"SQL_PRIMA_DEL_TESTO",
        "note_con_centro_sql":len(found),
        "righe_centro_sql":len(center_hits),
        "note_preselezionate":len(eligible),
        "preselezione_troncata":truncated,
        "colonna_indicazione":"nota_metadati_revisionati.indicazione"
        if metadata else "note.indicazione_candidata"
    }
