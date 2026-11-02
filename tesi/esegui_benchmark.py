#!/usr/bin/env python3
"""Esecuzione riproducibile del benchmark FarmaQuery TAG vs Text-to-SQL.

Non usa automaticamente i gold: il CSV e' prodotto con le colonne
valutazione_risposta / valutazione_citazioni vuote, per la revisione umana.
I due metodi usano lo stesso SQLite, manifest e modello.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time

from tesi import pilota_tag_vs_sql as motori

FIELDS=["id","categoria","domanda","metodo","modello","snapshot_sha256",
        "risposta","fonti","secondi","token_input","token_output","costo_usd",
        "costo_completo","stato","errore","sql","data_utc",
        "valutazione_risposta","valutazione_citazioni","note_revisore"]

METHODS=("TAG","Text-to-SQL")


def hash_file(path):
    h=sha256()
    with Path(path).open("rb") as f:
        while chunk:=f.read(1024*1024):
            h.update(chunk)
    return h.hexdigest()


def load_questions(path):
    """CSV semplice id;domanda[;categoria...] oppure id,domanda,..."""
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        sample=f.read(4096)
        f.seek(0)
        delimiter=";" if sample.count(";")>=sample.count(",") else ","
        reader=csv.DictReader(f,delimiter=delimiter)
        if not reader.fieldnames or "domanda" not in reader.fieldnames:
            raise ValueError("Nel CSV deve essere presente la colonna 'domanda'")
        questions=[]
        used=set()
        for i,row in enumerate(reader,1):
            question=(row.get("domanda") or "").strip()
            if not question:
                continue
            if len(question)>800:
                raise ValueError("Domanda troppo lunga alla riga "+str(i))
            ident=(row.get("id") or ("Q%02d"%i)).strip()
            if ident in used:
                raise ValueError("ID domanda duplicato: "+ident)
            if len(ident)>60:
                raise ValueError("ID domanda troppo lungo")
            used.add(ident)
            questions.append({"id":ident,"categoria":(row.get("categoria") or "").strip(),
                              "domanda":question})
    if not questions:
        raise ValueError("Nessuna domanda nel CSV")
    if len(questions)>500:
        raise ValueError("Troppi quesiti: limita il CSV a 500")
    return questions


def verify_snapshot(db,manifest_path):
    obj=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    expected=obj.get("sha256_sqlite")
    actual=hash_file(db)
    if not expected or expected!=actual:
        raise ValueError("Lo snapshot SQLite non coincide con il manifesto. "
                         "Non e' possibile confrontare risultati su dataset diversi.")
    return obj


def _check_credentials(model):
    if model.startswith(("gemini/","google/")):
        keys=("GEMINI_API_KEY","GOOGLE_API_KEY")
    elif model.startswith(("openai/","gpt-","o1","o3","o4")):
        keys=("OPENAI_API_KEY",)
    elif model.startswith("anthropic/"):
        keys=("ANTHROPIC_API_KEY",)
    else:
        return
    if not any(os.getenv(x) for x in keys):
        raise ValueError("Manca la chiave API. Imposta una delle variabili: "+
                         ", ".join(keys)+" (non inserire chiavi nel repository).")


def _existing_results(path,model,digest):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f,delimiter=";")
        if reader.fieldnames!=FIELDS:
            raise ValueError("CSV esistente con colonne incompatibili")
        rows=list(reader)
    for row in rows:
        if row["modello"]!=model or row["snapshot_sha256"]!=digest:
            raise ValueError("Un file di risultati appartiene a un altro modello/snapshot")
    return {(row["id"],row["metodo"]) for row in rows if row["stato"]=="OK"}


def execute(db_path,manifest_path,question_path,out_path,model=None,
            max_questions=3,confirm=False,resume=False,
            tag_fn=None,sql_fn=None):
    manifest=verify_snapshot(db_path,manifest_path)
    questions=load_questions(question_path)
    if not isinstance(max_questions,int) or max_questions<1:
        raise ValueError("--max-domande deve essere positivo")
    selected=questions[:max_questions]
    preview={"snapshot_sha256":manifest["sha256_sqlite"],
             "git_commit":manifest.get("git_commit"),
             "domande_disponibili":len(questions),"domande_selezionate":len(selected),
             "modello":model,"metodi":list(METHODS),
             "chiamate_esterne_abilitate":bool(confirm)}
    if not confirm:
        return {"esito":"ANTEPRIMA_SENZA_CHIAMATE","riepilogo":preview,
                "domande":[x["id"]+": "+x["domanda"] for x in selected]}
    if not model or not model.strip():
        raise ValueError("Indicare --model per avviare i due motori")
    _check_credentials(model)
    file=Path(out_path)
    file.parent.mkdir(parents=True,exist_ok=True)
    completed=set()
    if file.exists():
        if not resume:
            raise ValueError("Il CSV esiste gia': usa --riprendi per evitare sovrascritture")
        completed=_existing_results(file,model,manifest["sha256_sqlite"])
    tag_fn=tag_fn or motori.tag
    sql_fn=sql_fn or motori.sql_method
    count=0
    errors=0
    with file.open("a",encoding="utf-8-sig" if not file.exists() else "utf-8",
                   newline="") as output:
        writer=csv.DictWriter(output,fieldnames=FIELDS,delimiter=";",extrasaction="ignore")
        if output.tell()==0:
            writer.writeheader()
        for item in selected:
            for method,runner in (("TAG",tag_fn),("Text-to-SQL",sql_fn)):
                if (item["id"],method) in completed:
                    continue
                started=time.monotonic()
                result={}
                status="OK"
                error=""
                try:
                    with motori.read_only(db_path) as db:
                        result=runner(db,item["domanda"],model)
                    status=result.get("stato","OK")
                    if status not in ("OK","NESSUNA_EVIDENZA"):
                        status="ERRORE"
                    if status=="ERRORE":
                        errors+=1
                except Exception as e:
                    status="ERRORE"
                    error=type(e).__name__+": "+str(e)[:250]
                    errors+=1
                row={
                    "id":item["id"],"categoria":item["categoria"],
                    "domanda":item["domanda"],"metodo":method,"modello":model,
                    "snapshot_sha256":manifest["sha256_sqlite"],
                    "risposta":result.get("risposta",""),
                    "fonti":" | ".join(result.get("fonti",[])),
                    "secondi":round(time.monotonic()-started,3),
                    "token_input":result.get("token_input"),
                    "token_output":result.get("token_output"),
                    "costo_usd":result.get("costo_usd"),
                    "costo_completo":result.get("costo_completo"),
                    "stato":status,"errore":error,
                    "sql":result.get("sql",""),
                    "data_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "valutazione_risposta":"","valutazione_citazioni":"",
                    "note_revisore":"",
                }
                writer.writerow({k:"" if v is None else v for k,v in row.items()})
                output.flush()
                count+=1
    return {"esito":"ESECUZIONE_COMPLETATA_CON_ERRORI" if errors else "ESECUZIONE_COMPLETATA",
            "righe_aggiunte":count,"errori":errors,"risultati":str(file),
            "riepilogo":preview,
            "nota":"Le valutazioni manuali rimangono vuote. "
                   "I costi TAG escludono la selezione LOTUS salvo contabilizzazione separata."}


def main():
    p=argparse.ArgumentParser(description="FarmaQuery: confronto TAG con LOTUS vs Text-to-SQL")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--domande",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("risultati/risposte_tag_vs_sql.csv"))
    p.add_argument("--model",help="Stesso modello LiteLLM per entrambi, es. gemini/gemini-2.5-flash")
    p.add_argument("--max-domande",type=int,default=3)
    p.add_argument("--conferma-chiamate",action="store_true",
                   help="Richiede quota API; senza questo flag e' solo un'anteprima")
    p.add_argument("--riprendi",action="store_true")
    a=p.parse_args()
    outcome=execute(a.db,a.manifest,a.domande,a.out,a.model,a.max_domande,
                    a.conferma_chiamate,a.riprendi)
    print(json.dumps(outcome,ensure_ascii=False,indent=2))
    if outcome.get("errori"):
        return 2
    return 0


if __name__=="__main__":
    sys.exit(main())
