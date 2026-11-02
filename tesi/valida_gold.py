#!/usr/bin/env python3
"""Controlli strutturali sulle risposte gold della tesi.

NON verifica automaticamente la correttezza clinica/normativa: il revisore
deve leggere i PDF originali e approvare ogni risposta e relativa citazione.
"""
import argparse
import csv
from pathlib import Path
import re
import sqlite3
import json

STATI={"VALIDATO","DA_VERIFICARE","SCARTATO"}
REF=re.compile(r"^(.*?)#p([1-9]\d*)$")


def read(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as fh:
        rows=list(csv.DictReader(fh,delimiter=";"))
    required={"id","categoria","domanda","risposta_gold","fonti_gold",
              "stato_validazione","note_revisore"}
    if not rows or not required.issubset(set(rows[0])):
        raise ValueError("Schema benchmark gold incompleto")
    if len({x["id"] for x in rows})!=len(rows):
        raise ValueError("ID domande duplicati")
    return rows


def inspect(rows,connection):
    """Verifica esistenza di ogni citazione; NON assegna automaticamente VALIDATO."""
    result={"totale":len(rows),"validati":0,"da_verificare":0,
            "scartati":0,"errori":[],"categorie":{}}
    for rec in rows:
        key=rec["id"]; category=rec["categoria"]
        c=result["categorie"].setdefault(category,{"totali":0,"validati":0})
        c["totali"]+=1
        state=rec["stato_validazione"].strip()
        if state not in STATI:
            result["errori"].append(key+": stato non riconosciuto")
            continue
        if state=="DA_VERIFICARE":
            result["da_verificare"]+=1
            if rec["risposta_gold"].strip() or rec["fonti_gold"].strip():
                result["errori"].append(key+": dati gold compilati ma stato non validato")
            continue
        if state=="SCARTATO":
            result["scartati"]+=1
            continue
        answer=rec["risposta_gold"].strip()
        if len(answer)<12:
            result["errori"].append(key+": risposta gold mancante/troppo breve")
            continue
        if len(rec["note_revisore"].strip())<12:
            result["errori"].append(key+": motivazione del revisore mancante")
            continue
        refs=[part.strip() for part in rec["fonti_gold"].split("|") if part.strip()]
        is_negative=category=="NEGATIVE"
        if not is_negative and not refs:
            result["errori"].append(key+": nessuna citazione PDF#pN")
            continue
        if is_negative and "non" not in answer.casefold():
            result["errori"].append(key+": negativo: indicare espressamente il limite del corpus")
            continue
        bad=False
        for ref in refs:
            found=REF.fullmatch(ref)
            if not found:
                result["errori"].append(key+": formato citazione non valido: "+ref)
                bad=True
                continue
            pdf,page=found.group(1),int(found.group(2))
            row=connection.execute(
                "SELECT p.testo,p.metodo FROM note n JOIN pagine p "
                "ON p.nota_id=n.id WHERE n.percorso_zip=? AND p.numero_pagina=?",
                (pdf,page)).fetchone()
            if row is None or not row[0].strip() or row[1] not in ("TESTO","OCR"):
                result["errori"].append(key+": pagina non trovata/non leggibile: "+ref)
                bad=True
        if not bad:
            result["validati"]+=1
            c["validati"]+=1
    result["esito"]="OK" if not result["errori"] else "ERRORE"
    result["nota"]=("OK significa solo che la struttura delle citazioni esiste; "
                    "la verifica semantica e temporale resta a carico del revisore.")
    return result


def run(csv_file,sqlite_file):
    with sqlite3.connect(Path(sqlite_file).resolve().as_uri()+"?mode=ro",uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        return inspect(read(csv_file),db)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--benchmark",required=True)
    p.add_argument("--db",required=True)
    p.add_argument("--report")
    a=p.parse_args()
    info=run(a.benchmark,a.db)
    result=json.dumps(info,ensure_ascii=False,indent=2)
    print(result)
    if a.report:Path(a.report).write_text(result+"\n",encoding="utf-8")
    if info["esito"]!="OK":raise SystemExit(2)


if __name__=="__main__":
    main()
