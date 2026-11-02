#!/usr/bin/env python3
"""Confronto senza giudizi inventati: gold e correttezza revisati da esseri umani.

CSV delle predizioni: id;metodo;modello;snapshot_sha256;risposta;fonti;secondi;
token_input;token_output;costo_usd;valutazione_risposta;valutazione_citazioni;note_revisore

valutazione_* = 0/1 inseriti dopo la lettura delle risposte, non generati
da un LLM. Le domande prive di gold non sono valutabili.
"""
import argparse
import csv
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean

from tesi.valida_gold import read

METHODS=("TAG","Text-to-SQL")


def _number(value,kind,default=None):
    if str(value or "").strip()=="":
        return default
    try:
        number=kind(value)
        if number<0:raise ValueError
        return number
    except (ValueError,TypeError) as e:
        raise ValueError("Numero non valido: "+str(value)) from e


def evaluate(benchmark,results,manifest):
    gold={x["id"]:x for x in read(benchmark)
          if x["stato_validazione"]=="VALIDATO"}
    if not gold:
        return {"esito":"NESSUN_GOLD_VALIDATO","accuratezza":None,
                "nota":"Prima validare risposte gold e PDF; nessuna metrica inventata."}
    manifest=json.loads(Path(manifest).read_text(encoding="utf-8"))
    digest=manifest["sha256_sqlite"]
    with Path(results).open(encoding="utf-8-sig",newline="") as fh:
        responses=list(csv.DictReader(fh,delimiter=";"))
    required={"id","metodo","modello","snapshot_sha256","risposta","fonti","secondi",
              "valutazione_risposta","valutazione_citazioni","note_revisore"}
    if not responses or not required.issubset(set(responses[0])):
        raise ValueError("Schema risultati mancante")
    ids=set()
    models=set()
    paired=defaultdict(dict)
    for rec in responses:
        if rec["id"] not in gold:continue
        method=rec["metodo"]
        if method not in METHODS:raise ValueError("Metodo sconosciuto")
        if rec["snapshot_sha256"]!=digest:
            raise ValueError("Il modello ha interrogato uno snapshot diverso")
        if (rec["id"],method) in ids:
            raise ValueError("Più risposte dello stesso metodo alla stessa domanda")
        ids.add((rec["id"],method))
        model=rec["modello"].strip()
        if not model:raise ValueError("Modello LLM mancante")
        models.add(model)
        if rec["valutazione_risposta"].strip() not in ("0","1",""):
            raise ValueError("Valutazione risposta deve essere 0, 1 o vuota")
        if rec["valutazione_citazioni"].strip() not in ("0","1",""):
            raise ValueError("Valutazione citazioni deve essere 0, 1 o vuota")
        paired[rec["id"]][method]=rec
    if len(models)>1:
        raise ValueError("Il confronto deve usare lo stesso modello LLM")
    def stat(rows):
        rated=[x for x in rows if x["valutazione_risposta"].strip() in ("0","1")]
        cited=[x for x in rows if x["valutazione_citazioni"].strip() in ("0","1")]
        seconds=[_number(x["secondi"],float) for x in rows if x["secondi"].strip()]
        costs=[_number(x.get("costo_usd"),float) for x in rows if str(x.get("costo_usd") or "").strip()]
        tokens=[_number(x.get("token_input"),int,0)+_number(x.get("token_output"),int,0)
                for x in rows]
        return {
            "risposte":len(rows),
            "risposte_valutate_manualmente":len(rated),
            "accuratezza_manuale":round(mean(int(x["valutazione_risposta"]) for x in rated),4)
                                  if rated else None,
            "citazioni_valutate_manualmente":len(cited),
            "correttezza_citazioni":round(mean(int(x["valutazione_citazioni"]) for x in cited),4)
                                    if cited else None,
            "tempo_medio_secondi":round(mean(seconds),3) if seconds else None,
            "token_registrati":sum(tokens) if any(tokens) else None,
            "costo_totale_usd":round(sum(costs),6) if costs else None,
        }
    methods={}
    for method in METHODS:
        method_rows=[pair[method] for pair in paired.values() if method in pair]
        methods[method]={"totale_gold":len(gold),
                         "copertura":round(len(method_rows)/len(gold),4),
                         **stat(method_rows),
                         "categorie":{cat:stat([x for x in method_rows
                            if gold[x["id"]]["categoria"]==cat])
                            for cat in ("DIRETTE","SEMANTICHE","RIMANDI","NEGATIVE")}}
    complete=[key for key,pair in paired.items() if set(pair)==set(METHODS)]
    return {"esito":"OK","snapshot_sha256":digest,"modello":next(iter(models),None),
            "gold_validati":len(gold),"domande_con_entrambe_le_risposte":len(complete),
            "metodi":methods,
            "nota":"Accuratezza e correttezza delle citazioni sono riportate SOLO se "
                   "le annotazioni manuali 0/1 sono presenti; altrimenti NULL."}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--benchmark",required=True)
    p.add_argument("--risultati",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    report=evaluate(a.benchmark,a.risultati,a.manifest)
    Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",
                           encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
