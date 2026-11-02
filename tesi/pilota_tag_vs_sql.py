#!/usr/bin/env python3
"""Pilota TAG LOTUS contro Text-to-SQL sullo stesso SQLite congelato.

Dipendenze separate dalla dashboard: lotus-ai, litellm, pandas, sqlglot.
Richiede una chiave API e un modello LiteLLM forniti dall'utente.
"""
import argparse, json, re, sqlite3, time
from pathlib import Path

SCHEMA = """note(id,nome_file,percorso_zip,anno,farmaco_candidato,protocollo_candidato)
pagine(nota_id,numero_pagina,testo,metodo)
strutture_registri(medicinale,patologia,indicazione,struttura,regione)
centri_candidati(nota_id,numero_pagina,menzione,stato)
rimandi_candidati(nota_id,numero_pagina,riferimento,stato)
pagine_fts(nota_id,numero_pagina,testo) -- FTS5"""

def read_only(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db

def candidates(db,question,limit=32):
    stop={"quali","quale","della","delle","regione","campania","farmaco",
          "medicinale","nota","centri","sono","prescrizione","specifica",
          "secondo","pagine","documenti","tutte","qual","autorizzati"}
    words=[x for x in re.findall(r"[a-zA-ZÀ-ÿ0-9]{4,}",question.casefold()) if x not in stop]
    if not words:return []
    pattern=" OR ".join('"'+x+'"' for x in dict.fromkeys(words[:10]))
    sql="""SELECT n.percorso_zip,p.nota_id,p.numero_pagina,p.testo
           FROM pagine_fts f JOIN pagine p ON p.nota_id=f.nota_id
              AND p.numero_pagina=f.numero_pagina
           JOIN note n ON n.id=p.nota_id
           WHERE pagine_fts MATCH ? AND p.metodo IN ('TESTO','OCR')
           ORDER BY bm25(pagine_fts) LIMIT ?"""
    return [dict(r) for r in db.execute(sql,(pattern,limit))]

def ask(model,system,payload):
    from litellm import completion
    out=completion(model=model,temperature=0,messages=[
        {"role":"system","content":system},
        {"role":"user","content":json.dumps(payload,ensure_ascii=False)}
    ])
    return out.choices[0].message.content,getattr(out.usage,"total_tokens",None)

def tag(db,question,model):
    import pandas as pd
    import lotus
    from lotus.models import LM
    docs=candidates(db,question)
    if not docs:return {"risposta":"Nessuna evidenza trovata nel corpus.","fonti":[]}
    lotus.settings.configure(lm=LM(model=model))
    df=pd.DataFrame([{"testo":x["testo"][:7000],
        "fonte":x["percorso_zip"]+"#p"+str(x["numero_pagina"])} for x in docs])
    relevant=df.sem_filter("{testo} contiene prove pertinenti alla domanda: "+
        question+"? Una intestazione NON dimostra un'autorizzazione.").head(8)
    if relevant.empty:return {"risposta":"Nessuna evidenza sufficiente.","fonti":[]}
    evidence=relevant.to_dict("records")
    answer,tokens=ask(model,"Rispondi in italiano esclusivamente dalle prove. "
        "Cita PDF#pN e non confondere menzioni di centri con autorizzazioni. "
        "Per mancanza di prove astieniti.",{"domanda":question,"evidenze":evidence})
    return {"risposta":answer,"fonti":[e["fonte"] for e in evidence],
            "token_sintesi":tokens}

def validate_sql(sql):
    import sqlglot
    from sqlglot import exp
    statements=sqlglot.parse(sql.strip().strip(chr(96)),read="sqlite")
    if len(statements)!=1 or not isinstance(statements[0],(exp.Select,exp.Union)):
        raise ValueError("È ammessa una sola SELECT SQLite")
    tree=statements[0]
    for cls in (exp.Insert,exp.Update,exp.Delete,exp.Drop,exp.Create,exp.Alter,exp.Command):
        if tree.find(cls):raise ValueError("SQL non in sola lettura")
    allowed={"note","pagine","strutture_registri","centri_candidati",
             "rimandi_candidati","pagine_fts"}
    ctes={cte.alias for cte in tree.find_all(exp.CTE)}
    for tab in tree.find_all(exp.Table):
        if tab.name not in allowed|ctes or tab.db or tab.catalog:
            raise ValueError("Tabella non consentita")
    return tree.sql(dialect="sqlite")

def sql_method(db,question,model):
    generated,used=ask(model,"Produci solo una SELECT SQLite con LIMIT 40. "
        "Usa le colonne del corpus. Mantieni nota_id e numero_pagina in output "
        "quando citi una nota; nessuna modifica al database.",
        {"domanda":question,"schema":SCHEMA})
    cleaned=re.sub(r"^"+chr(96)*3+r"(?:sql)?\s*|\s*"+chr(96)*3+r"$","",
                   generated.strip(),flags=re.I)
    sql=validate_sql(cleaned)
    t0=time.monotonic()
    db.set_progress_handler(lambda:1 if time.monotonic()-t0>12 else 0,10000)
    rows=[dict(r) for r in db.execute(sql).fetchmany(40)]
    answer,tokens=ask(model,"Rispondi in italiano solo dalle righe SQL. "
        "Non dedurre prescrivibilità da menzioni di centri o dall'assenza "
        "di una nota. Se mancano prove, scrivi non documentato nel corpus.",
        {"domanda":question,"righe":rows})
    refs=[]
    for row in rows:
        if row.get("nota_id") and row.get("numero_pagina"):
            source=db.execute("SELECT percorso_zip FROM note WHERE id=?",
                              (row["nota_id"],)).fetchone()
            if source:
                refs.append(str(source["percorso_zip"])+"#p"+str(row["numero_pagina"]))
    return {"risposta":answer,"sql":sql,"fonti":list(dict.fromkeys(refs)),
            "token_sql":used,"token_sintesi":tokens}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--method",choices=["TAG","Text-to-SQL"],required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--question",required=True)
    p.add_argument("--out")
    a=p.parse_args()
    start=time.monotonic()
    with read_only(a.db) as db:
        result=tag(db,a.question,a.model) if a.method=="TAG" else sql_method(db,a.question,a.model)
    row={"metodo":a.method,"modello":a.model,"domanda":a.question,
         "secondi":round(time.monotonic()-start,3),**result}
    output=json.dumps(row,ensure_ascii=False,indent=2)
    print(output)
    if a.out:Path(a.out).write_text(output,encoding="utf-8")

if __name__=="__main__":main()
