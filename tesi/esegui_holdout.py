#!/usr/bin/env python3
"""Esegue una sola volta un holdout VALIDATO, senza usare le risposte gold.

Non contiene risposte attese né le trasmette al modello; registra sia
successi sia errori. L'annotazione della correttezza è un passaggio umano
successivo. Non avvia l'esperimento finché il gold non è congelato.
"""
from __future__ import annotations
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import time

from tesi.valida_gold import read,run as validate_gold
from chatbot_farmaquery import answer_question

COLUMNS=("id","metodo","modello","snapshot_sha256","risposta","fonti",
         "secondi","token_input","token_output","costo_usd",
         "valutazione_risposta","valutazione_citazioni","note_revisore",
         "chiamate_llm_effettive","elementi_predetti",
         "valutazione_astensione","errore_tecnico",
         "citazioni_corrette_n","citazioni_verificate_n","codice_commit")
METHODS=("Text-to-SQL","TAG")


def file_sha(path):
    digest=sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_holdout(gold_file,db_file,manifest_file):
    gold=read(gold_file)
    if any(x["stato_validazione"]!="VALIDATO" for x in gold):
        raise ValueError("Holdout non pronto: tutte le risposte gold devono "
                         "essere validate PRIMA dell'esperimento")
    status=validate_gold(gold_file,db_file)
    if status["esito"]!="OK" or status["validati"]!=len(gold):
        raise ValueError("Gold non verificata rispetto alle fonti dello snapshot")
    manifest=json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    expected=manifest["sha256_sqlite"]
    if file_sha(db_file)!=expected:
        raise ValueError("SHA-256 dello snapshot SQLite diverso dal manifesto")
    for row in gold:
        if row.get("snapshot_sha256") and row["snapshot_sha256"]!=expected:
            raise ValueError("Gold riferita a uno snapshot diverso")
    return gold,expected


def collect(gold_file,db_file,manifest_file,model,out,commit,answer_fn=answer_question):
    if not commit or len(commit.strip())<7:
        raise ValueError("Specificare il commit Git congelato (--commit)")
    if Path(out).exists():
        raise FileExistsError("File risultati esistente: nessun sovrascrittura "
                              "o rerun involontario del benchmark holdout")
    gold,digest=frozen_holdout(gold_file,db_file,manifest_file)
    dest=Path(out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("w",encoding="utf-8-sig",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=COLUMNS,delimiter=";")
        writer.writeheader()
        for index,item in enumerate(gold):
            # Ordine bilanciato per non favorire sistematicamente il
            # primo metodo rispetto alla variabilita' temporale delle API.
            order=METHODS if index%2==0 else METHODS[::-1]
            for method in order:
                start=time.monotonic()
                error=False
                try:
                    result=answer_fn(db_file,item["domanda"],method,model)
                except Exception as exc:
                    error=True
                    metrics=getattr(exc,"metriche_llm",{})
                    result={
                        "risposta":"ERRORE_TECNICO: "+type(exc).__name__,
                        "fonti":[],**metrics
                    }
                elapsed=round(time.monotonic()-start,3)
                citations=result.get("fonti") or []
                if isinstance(citations,str):
                    citations=[citations]
                row={
                    "id":item["id"],"metodo":method,"modello":model,
                    "snapshot_sha256":digest,
                    "risposta":result.get("risposta",""),
                    "fonti":"|".join(str(x).split(" | ",1)[0] for x in citations),
                    "secondi":elapsed,
                    "token_input":result.get("token_input"),
                    "token_output":result.get("token_output"),
                    "costo_usd":result.get("costo_usd"),
                    "chiamate_llm_effettive":result.get("chiamate_llm_effettive"),
                    "errore_tecnico":int(error),
                    "codice_commit":commit,
                    # Queste informazioni si compilano SOLO DOPO aver letto
                    # le risposte: non possono essere autoassegnate dal modello.
                    "valutazione_risposta":"","valutazione_citazioni":"",
                    "note_revisore":"","elementi_predetti":"",
                    "valutazione_astensione":"","citazioni_corrette_n":"",
                    "citazioni_verificate_n":"",
                }
                writer.writerow(row)
                handle.flush()
                print(item["id"],method,elapsed,
                      "ERRORE" if error else "risposta acquisita")
    return dest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--benchmark",required=True)
    p.add_argument("--db",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--commit",required=True)
    a=p.parse_args()
    collect(a.benchmark,a.db,a.manifest,a.model,a.out,a.commit)


if __name__=="__main__":
    main()
