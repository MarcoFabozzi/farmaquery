#!/usr/bin/env python3
"""Motori sperimentali TAG (LOTUS) e Text-to-SQL su un unico SQLite online.

Solo SELECT e database in read-only. Nessuna chiamata remota alla sola
importazione del modulo. I dati regolatori sono datati: non dedurre
rimborsabilita' vigente o autorizzazione dei centri da una semplice menzione.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import time


SCHEMA = """Tabelle disponibili (SQLite, SOLA LETTURA):
aifa_confezioni(aic, nome, principio_attivo, descrizione, classe_a_h_snapshot, classe_a_h_data)
ema_medicinali(ema_id, nome, principio_attivo, stato_ema, data_decisione_ue, indicazione_ema, url_ema)
note(id, nome_file, percorso_zip, anno, farmaco_candidato, protocollo_candidato, data_candidata, indicazione_candidata, archivio_url)
pagine(nota_id, numero_pagina, testo, metodo)
strutture_registri(id, medicinale, patologia, indicazione, struttura, regione, data_riferimento, fonte_url)
centri_candidati(nota_id, numero_pagina, menzione, stato)
rimandi_candidati(nota_id, numero_pagina, riferimento, stato)
fonti_snapshot(fonte, url, sha256, data_riferimento)
pagine_fts(nota_id, numero_pagina, testo) -- FTS5, opzionale.

AIFA: classe_a_h_snapshot vale A/H oppure NULL; NULL NON prova classe C.
Regione: centri_candidati e strutture_registri non certificano autorizzazione
per una indicazione, senza testo esplicito della nota regionale.
Per citare, seleziona aic per AIFA; ema_id per EMA;
nota_id e numero_pagina per le note (con join su pagine)."""

ALLOWED = {"aifa_confezioni","ema_medicinali","note","pagine",
           "strutture_registri","centri_candidati","rimandi_candidati",
           "fonti_snapshot","pagine_fts"}
STOP = {"quali","quale","quali","della","delle","nelle","degli","sono",
        "questa","questo","regione","campania","farmaco","farmaci",
        "medicinale","medicinali","centri","centro","prescrive",
        "prescrivere","prescritto","indicazioni","indicazione",
        "terapeutiche","terapeutica","classe","aifa","ema","europea",
        "autorizzato","autorizzata","rimborsato","rimborsata",
        "invece","dopo","secondo","presso","farmacista","medico",
        "posso","quale","quando","nota","italia","disponibile",
        "esiste","delle","essere","sulle","della","dalla","paziente"}


def read_only(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def terms(question):
    words=[word.casefold() for word in re.findall(r"[A-Za-zÀ-ÿ0-9-]{4,}",question)]
    return list(dict.fromkeys(w for w in words if w not in STOP))[:8]


def _like(term):
    return "%"+term.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"


def candidates(db,question,limit=12):
    """Pagine FTS deterministiche; compatibile con i test precedenti."""
    tokens=terms(question)
    if not tokens:
        return []
    pattern=" OR ".join('"'+token.replace('"','')+'"' for token in tokens[:6])
    sql="""SELECT n.percorso_zip,n.archivio_url,p.nota_id,p.numero_pagina,p.testo
           FROM pagine_fts f
           JOIN pagine p ON p.nota_id=f.nota_id
             AND p.numero_pagina=f.numero_pagina
           JOIN note n ON n.id=p.nota_id
           WHERE pagine_fts MATCH ? AND p.metodo IN ('TESTO','OCR')
           ORDER BY bm25(pagine_fts) LIMIT ?"""
    return [dict(r) for r in db.execute(sql,(pattern,limit))]


def evidence_candidates(db,question,max_rows=18):
    """Seleziona righe sia strutturate EMA/AIFA sia regionali per LOTUS.

    Il recupero preliminare e' testuale/deterministico, NON un RAG vettoriale.
    Tutte le righe restano nello stesso SQLite congelato usato da Text-to-SQL.
    """
    tokens=terms(question)
    if not tokens:
        return []
    out=[]
    def put(tipo,uid,description,source):
        if len(out)<max_rows:
            out.append({"tipo":tipo,"chiave":uid,"testo":str(description)[:2600],
                        "fonte":source})
    for item in candidates(db,question,limit=7):
        put("REGIONE",item["nota_id"]+"#p"+str(item["numero_pagina"]),
            item["testo"][:1750],
            item["percorso_zip"]+"#p"+str(item["numero_pagina"]) +
            " | archivio: "+str(item["archivio_url"]))
    # Query LIKE per nome/principio attivo; no ricerche di centri sul solo
    # elenco AIFA come prova di autorizzazione per indicazione.
    seen={row["chiave"] for row in out}
    for token in tokens[:4]:
        like=_like(token)
        for row in db.execute(
            "SELECT aic,nome,principio_attivo,descrizione,"
            "classe_a_h_snapshot,classe_a_h_data FROM aifa_confezioni "
            "WHERE nome LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "OR principio_attivo LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT 4",
            (like,like)):
            uid="AIFA:"+row["aic"]
            if uid in seen: continue
            seen.add(uid)
            description=("AIC: "+str(row["aic"])+", nome: "+str(row["nome"])
                         +", principio attivo: "+str(row["principio_attivo"])
                         +", presentazione: "+str(row["descrizione"])
                         +", classe A/H (lista datata): "+str(row["classe_a_h_snapshot"])
                         +", data: "+str(row["classe_a_h_data"]))
            put("AIFA",uid,description,"AIFA AIC "+str(row["aic"]))
        for row in db.execute(
            "SELECT ema_id,nome,principio_attivo,stato_ema,data_decisione_ue,"
            "indicazione_ema,url_ema FROM ema_medicinali "
            "WHERE nome LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "principio_attivo LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT 3",
            (like,like)):
            uid="EMA:"+str(row["ema_id"])
            if uid in seen:continue
            seen.add(uid)
            descr=("EMA ID: "+str(row["ema_id"])+", medicinale: "+str(row["nome"])
                   +", principio attivo: "+str(row["principio_attivo"])
                   +", stato: "+str(row["stato_ema"])
                   +", decisione UE: "+str(row["data_decisione_ue"])
                   +", indicazione: "+str(row["indicazione_ema"]))
            put("EMA",uid,descr,"EMA "+str(row["ema_id"])+" | "+str(row["url_ema"]))
        for row in db.execute(
            "SELECT id,medicinale,patologia,indicazione,struttura,"
            "data_riferimento,fonte_url FROM strutture_registri "
            "WHERE medicinale LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "OR patologia LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT 3",
            (like,like)):
            uid="REGISTRO:"+row["id"]
            if uid in seen:continue
            seen.add(uid)
            put("REGISTRO_AIFA",uid,
                "Medicinale "+row["medicinale"]+", patologia "+str(row["patologia"])
                +", indicazione "+str(row["indicazione"])+", struttura "+row["struttura"]
                +", data "+row["data_riferimento"],
                "AIFA strutture abilitate ai registri | "+row["fonte_url"])
    return out[:max_rows]


def ask(model,system,payload):
    """LiteLLM con restituzione di token e costo quando disponibili."""
    from litellm import completion
    result=completion(model=model,temperature=0,messages=[
        {"role":"system","content":system},
        {"role":"user","content":json.dumps(payload,ensure_ascii=False,default=str)}
    ])
    usage=getattr(result,"usage",None)
    data={
        "token_input":getattr(usage,"prompt_tokens",None),
        "token_output":getattr(usage,"completion_tokens",None),
        "costo_usd":None,
    }
    try:
        from litellm import completion_cost
        data["costo_usd"]=float(completion_cost(completion_response=result))
    except (ValueError,TypeError,KeyError,AttributeError):
        pass
    return str(result.choices[0].message.content or ""),data


def _accumulate(a,b):
    return {key:(a.get(key) or 0)+(b.get(key) or 0)
            if a.get(key) is not None and b.get(key) is not None else None
            for key in ("token_input","token_output","costo_usd")}


def tag(db,question,model):
    import pandas as pd
    import lotus
    from lotus.models import LM
    rows=evidence_candidates(db,question)
    if not rows:
        return {"risposta":"Informazione non documentata nello snapshot consultato.",
                "fonti":[],"stato":"NESSUNA_EVIDENZA","token_input":None,
                "token_output":None,"costo_usd":None}
    lotus.settings.configure(lm=LM(model=model),enable_cache=False)
    frame=pd.DataFrame(rows)
    selected=frame.sem_filter(
        "Il contenuto di {testo} fornisce informazioni pertinenti alla domanda "
        +json.dumps(question,ensure_ascii=False)
        +". I riferimenti a strutture nei registri AIFA non equivalgono "
         "automaticamente a centri prescrittori autorizzati nella regione."
    ).head(8)
    if selected.empty:
        return {"risposta":"Informazione non documentata nello snapshot consultato.",
                "fonti":[],"stato":"NESSUNA_EVIDENZA","token_input":None,
                "token_output":None,"costo_usd":None}
    evidence=selected[["tipo","testo","fonte"]].to_dict("records")
    answer,usage=ask(model,"Rispondi in italiano esclusivamente dalle evidenze. "
        "Distingui autorizzazione europea EMA, classe A/H di una confezione AIFA "
        "e centri prescrittori di specifiche note campane. "
        "La classe C non si deduce dall'assenza negli elenchi A/H. "
        "Non dichiarare un centro autorizzato soltanto dal registro AIFA. "
        "Indica le fonti; se mancano, scrivi 'non documentato nello snapshot'.",
        {"domanda":question,"evidenze":evidence})
    return {"risposta":answer,"fonti":list(dict.fromkeys(x["fonte"] for x in evidence)),
            "stato":"OK","token_input":usage["token_input"],
            "token_output":usage["token_output"],"costo_usd":usage["costo_usd"],
            "costo_completo":False,
            "nota_costi":"Le statistiche della selezione semantica LOTUS non sono incluse nel costo della sintesi."}


def validate_sql(text):
    """Accetta una sola SELECT, niente istruzioni PRAGMA, DDL, DML o funzioni rischiose."""
    import sqlglot
    from sqlglot import exp
    cleaned=re.sub(r"^\s*"+chr(96)*3+r"(?:sql)?\s*|\s*"+chr(96)*3+r"\s*$","",text.strip(),flags=re.I)
    instructions=sqlglot.parse(cleaned,read="sqlite")
    if len(instructions)!=1 or not isinstance(instructions[0],(exp.Select,exp.Union)):
        raise ValueError("Sono consentite solo SELECT")
    root=instructions[0]
    blocked=(exp.Insert,exp.Update,exp.Delete,exp.Drop,exp.Create,exp.Alter,
             exp.Command,exp.Pragma,exp.Attach,exp.Detach)
    for banned in blocked:
        if root.find(banned):
            raise ValueError("SQL non consentito")
    for table in root.find_all(exp.Table):
        ctes={c.alias for c in root.find_all(exp.CTE)}
        if (table.name not in ALLOWED|ctes or table.db or table.catalog):
            raise ValueError("Tabella o schema non consentito: "+table.name)
    deny_names={"load_extension","readfile","writefile","fts5_tokenize",
                "sqlite_compileoption_get","sqlite_compileoption_used"}
    for item in root.find_all(exp.Func):
        if getattr(item,"name","").lower() in deny_names:
            raise ValueError("Funzione SQL non consentita")
    # Limita anche le funzioni non nominate/collateralmente pericolose.
    if re.search(r"\b(load_extension|readfile|writefile|randomblob)\s*\(",
                 cleaned,re.I):
        raise ValueError("Funzione SQL non consentita")
    return root.sql(dialect="sqlite")


def _sql_sources(db,rows):
    found=[]
    for row in rows:
        note=row.get("nota_id")
        page=row.get("numero_pagina")
        if note and page:
            src=db.execute("SELECT percorso_zip,archivio_url FROM note WHERE id=?",
                           (note,)).fetchone()
            if src:
                found.append(str(src["percorso_zip"])+"#p"+str(page)+
                             " | archivio: "+str(src["archivio_url"]))
        aic=row.get("aic")
        if aic:
            found.append("AIFA AIC "+str(aic)+" | snapshot elenchi ufficiali A/H")
        ema=row.get("ema_id")
        if ema:
            src=db.execute("SELECT url_ema FROM ema_medicinali WHERE ema_id=?",
                           (ema,)).fetchone()
            found.append("EMA "+str(ema)+(" | "+str(src["url_ema"]) if src else ""))
        if row.get("fonte_url"):
            found.append(str(row["fonte_url"]))
        if row.get("url"):
            found.append(str(row["url"]))
    return list(dict.fromkeys(found))


def sql_method(db,question,model):
    generated,first=ask(model,
        "Genera SOLO UNA query SELECT SQLite eseguibile, senza Markdown. "
        "Usa esclusivamente le tabelle documentate; non generare DDL, DML, "
        "PRAGMA né più istruzioni. LIMIT 30. Per citazioni includi "
        "aic, ema_id oppure nota_id e numero_pagina nel risultato, "
        "e archivio_url o fonte_url quando pertinenti. "
        "Non dedurre classe C dall'assenza nelle liste A/H.",
        {"schema":SCHEMA,"domanda":question})
    sql=validate_sql(generated)
    start=time.monotonic()
    db.set_progress_handler(lambda:1 if time.monotonic()-start>12 else 0,10000)
    try:
        raw=db.execute(sql).fetchmany(31)
        rows=[{key:(str(value)[:2500] if value is not None else None)
               for key,value in dict(r).items()} for r in raw[:30]]
    finally:
        db.set_progress_handler(None,0)
    citations=_sql_sources(db,rows)
    answer,second=ask(model,
        "Rispondi in italiano SOLO in base alle righe SELECT e alle fonti. "
        "Non interpretare un dato AIFA/EMA come autorizzazione regionale. "
        "L'assenza dagli elenchi A/H non prova classe C. "
        "Se mancano dati o evidenze, scrivi 'non documentato nello snapshot'. "
        "Non inventare citazioni.",
        {"domanda":question,"righe_sql":rows,"fonti_recuperate":citations})
    total=_accumulate(first,second)
    return {"risposta":answer,"fonti":citations,"sql":sql,
            "righe_sql":len(rows),"stato":"OK",**total,"costo_completo":True}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--method",choices=["TAG","Text-to-SQL"],required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--question",required=True)
    p.add_argument("--out",type=Path)
    p.add_argument("--conferma-chiamate",action="store_true")
    a=p.parse_args()
    if not a.conferma_chiamate:
        p.error("Le API LLM consumano quote: aggiungi --conferma-chiamate")
    start=time.monotonic()
    with closing(read_only(a.db)) as db:
        result=tag(db,a.question,a.model) if a.method=="TAG" else sql_method(db,a.question,a.model)
    record={"metodo":a.method,"modello":a.model,"domanda":a.question,
            "secondi":round(time.monotonic()-start,3),**result}
    payload=json.dumps(record,ensure_ascii=False,indent=2)
    print(payload)
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(payload+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
