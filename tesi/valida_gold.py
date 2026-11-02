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
REF_EMA=re.compile(r"^EMA:(.+)$")
REF_AIFA=re.compile(r"^AIFA:([0-9]{9})$")
REF_GU=re.compile(r"^GU:([0-9]{2}[A-Z][0-9]{5})(?::(atto|allegato:[0-9a-f]{16})#s([1-9][0-9]*))?$")


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
        is_negative=category in ("NEGATIVE","ASSENZA_DOCUMENTALE")
        if not is_negative and not refs:
            result["errori"].append(key+": nessuna citazione verificabile (EMA:ID, AIFA:AIC o file.pdf#pN)")
            continue
        if is_negative and "non" not in answer.casefold():
            result["errori"].append(key+": negativo: indicare espressamente il limite del corpus")
            continue
        bad=False
        cited=set()
        for ref in refs:
            ema=REF_EMA.fullmatch(ref)
            aifa=REF_AIFA.fullmatch(ref)
            regional=REF.fullmatch(ref)
            gu=REF_GU.fullmatch(ref)
            if ema:
                exists=connection.execute(
                    "SELECT 1 FROM ema_medicinali WHERE ema_id=?",
                    (ema.group(1),)).fetchone()
                cited.add("EMA")
                if not exists:
                    result["errori"].append(key+": EMA ID assente: "+ref)
                    bad=True
                continue
            if aifa:
                exists=connection.execute(
                    "SELECT 1 FROM aifa_confezioni WHERE aic=?",
                    (aifa.group(1),)).fetchone()
                cited.add("AIFA")
                if not exists:
                    result["errori"].append(key+": AIC assente: "+ref)
                    bad=True
                continue
            if gu:
                codice = gu.group(1)
                document = gu.group(2)
                segment = gu.group(3)
                if document:
                    exists = connection.execute(
                        "SELECT 1 FROM gu_segmenti s "
                        "JOIN gu_documenti d ON d.documento_id=s.documento_id "
                        "WHERE d.codice=? AND d.documento_id=? "
                        "AND s.numero_segmento=?",
                        (codice, codice + ":" + document, int(segment))
                    ).fetchone()
                else:
                    exists = connection.execute(
                        "SELECT 1 FROM gu_atti WHERE codice=?", (codice,)
                    ).fetchone()
                cited.add("GU")
                if not exists:
                    result["errori"].append(key+": documento GU assente: "+ref)
                    bad=True
                continue
            if not regional:
                result["errori"].append(key+": formato citazione non valido: "+ref)
                bad=True
                continue
            pdf,page=regional.group(1),int(regional.group(2))
            cited.add("REGIONE")
            row=connection.execute(
                "SELECT p.testo,p.metodo FROM note n JOIN pagine p "
                "ON p.nota_id=n.id WHERE n.percorso_zip=? AND p.numero_pagina=?",
                (pdf,page)).fetchone()
            if row is None or not row[0].strip() or row[1] not in ("TESTO","OCR"):
                result["errori"].append(key+": pagina non trovata/non leggibile: "+ref)
                bad=True
        if state=="VALIDATO" and not is_negative and (rec.get("fonti_richieste") or rec.get("fonti_previste")):
            needed=set((rec.get("fonti_richieste") or rec.get("fonti_previste")).split("+"))
            if not needed.issubset(cited):
                result["errori"].append(key+": citazioni mancanti per: "+
                                         ", ".join(sorted(needed-cited)))
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
