#!/usr/bin/env python3
"""Applica SOLTANTO gold verificati visivamente allo snapshot online immutabile.

La lista gold e' curata manualmente e controllata contro hash documento,
percorso PDF, pagina, ancore testuali e hash dell'intero SQLite.
Non interpreta nuove note e non inventa risposte per gli altri 31 quesiti.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from tesi.valida_gold import inspect, read


def digest_file(path):
    h=sha256()
    with Path(path).open("rb") as f:
        while chunk:=f.read(1024*1024):
            h.update(chunk)
    return h.hexdigest()


def apply(benchmark,db_file,manifest_file,gold_file,out_csv,report_file):
    manifest=json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    golden=json.loads(Path(gold_file).read_text(encoding="utf-8"))
    actual=digest_file(db_file)
    if actual!=manifest.get("sha256_sqlite") or actual!=golden.get("snapshot_sha256"):
        raise ValueError("Snapshot / manifesto / gold non corrispondono")
    if golden.get("schema")!=1:
        raise ValueError("Formato gold sconosciuto")
    entries=golden.get("records",[])
    if not isinstance(entries,list) or not entries:
        raise ValueError("Nessun gold sottoposto a verifica")
    rows=read(benchmark)
    index={r["id"]:r for r in rows}
    conn=sqlite3.connect(Path(db_file).resolve().as_uri()+"?mode=ro",uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        seen=set()
        for entry in entries:
            key=entry["id"]
            if key in seen or key not in index:
                raise ValueError("Gold ID duplicato/non presente nel benchmark: "+key)
            seen.add(key)
            row=index[key]
            if row["stato_validazione"] not in ("DA_VERIFICARE","VALIDATO"):
                raise ValueError("Gold non applicabile a record scartato")
            expected=conn.execute("SELECT id,percorso_zip,hash_pdf FROM note "
                                  "WHERE percorso_zip=?",
                                  (entry["file_pdf"],)).fetchone()
            if (expected is None or expected["hash_pdf"]!=entry["sha256_documento"]
                or expected["id"]!=row["nota_id"]
                or row["file_pdf"]!=entry["file_pdf"]):
                raise ValueError("Documento differente dal PDF verificato: "+key)
            citations=[]
            for page in entry["pagine"]:
                if not isinstance(page,int) or page<1 or str(page) not in entry["ancore_ocr"]:
                    raise ValueError("Pagina/ancore mancanti nel gold: "+key)
                evidence=conn.execute(
                    "SELECT testo,metodo FROM pagine WHERE nota_id=? AND numero_pagina=?",
                    (expected["id"],page)
                ).fetchone()
                if not evidence or evidence["metodo"] not in ("OCR","TESTO"):
                    raise ValueError("Pagina non leggibile: "+key)
                for anchor in entry["ancore_ocr"][str(page)]:
                    if str(anchor).casefold() not in evidence["testo"].casefold():
                        raise ValueError("Ancora di verifica assente: "+key+" p."+str(page))
                citations.append(entry["file_pdf"]+"#p"+str(page))
            if entry["fonti_gold"]!="|".join(citations):
                raise ValueError("Citazioni gold non coerenti con le pagine: "+key)
            if len(entry["risposta_gold"].strip())<24 or len(entry["note_revisore"].strip())<24:
                raise ValueError("Risposta o motivazione di revisione mancante: "+key)
            row["risposta_gold"]=entry["risposta_gold"]
            row["fonti_gold"]=entry["fonti_gold"]
            row["note_revisore"]=entry["note_revisore"]
            row["stato_validazione"]="VALIDATO"
        result=inspect(rows,conn)
        if result["esito"]!="OK" or result["validati"]!=len(entries):
            raise ValueError("La validazione strutturale dei gold non e' riuscita: "+
                             str(result["errori"]))
    finally:
        conn.close()
    out_csv=Path(out_csv)
    report_file=Path(report_file)
    out_csv.parent.mkdir(parents=True,exist_ok=True)
    report_file.parent.mkdir(parents=True,exist_ok=True)
    fieldnames=list(rows[0])
    with out_csv.open("w",encoding="utf-8-sig",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=fieldnames,delimiter=";")
        w.writeheader()
        w.writerows(rows)
    result["snapshot_sha256"]=actual
    result["origine_gold"]=str(gold_file)
    result["gold_pubblicati"]=sorted(seen)
    result["verifica_semantica"]="Eseguita manualmente sui PDF originali con SHA-256 coincidente"
    result["limite"]="Altri quesiti rimangono DA_VERIFICARE. La presenza storica di un centro non certifica l'abilitazione attuale."
    report_file.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--benchmark",required=True)
    p.add_argument("--db",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--gold",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--report",required=True)
    a=p.parse_args()
    print(json.dumps(apply(a.benchmark,a.db,a.manifest,a.gold,a.out,a.report),
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
