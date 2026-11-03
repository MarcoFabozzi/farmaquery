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
import re
import unicodedata

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


def _items(value):
    """Campi enumerativi annotati dal revisore, separati da |.

    Vuoto = non valutato. Scrivere [] per un elenco di risposte vuoto,
    cosi' non si confonde l'assenza di misurazione con uno zero.
    """
    raw=str(value or "").strip()
    if not raw:
        return None
    if raw=="[]":
        return set()
    def normalize(text):
        t=unicodedata.normalize("NFKD",text.casefold())
        t="".join(c for c in t if not unicodedata.combining(c))
        return " ".join(re.findall(r"[^\W_]+",t))
    return {normalize(x) for x in raw.split("|") if normalize(x)}


def _micro_list_metrics(records,gold):
    tp=fp=fn=0
    n=0
    for row in records:
        expected=_items(gold[row["id"]].get("elementi_gold"))
        observed=_items(row.get("elementi_predetti"))
        if expected is None or observed is None:
            continue
        n+=1
        tp+=len(expected & observed)
        fp+=len(observed-expected)
        fn+=len(expected-observed)
    if not n:
        return {"elenchi_valutati":0,"precision_micro":None,
                "recall_micro":None,"f1_micro":None}
    precision=tp/(tp+fp) if tp+fp else (1.0 if fn==0 else 0.0)
    recall=tp/(tp+fn) if tp+fn else (1.0 if fp==0 else 0.0)
    f1=(2*precision*recall/(precision+recall)
        if precision+recall else 0.0)
    return {"elenchi_valutati":n,"precision_micro":round(precision,4),
            "recall_micro":round(recall,4),"f1_micro":round(f1,4)}


def evaluate(benchmark,results,manifest):
    gold={x["id"]:x for x in read(benchmark)
          if x["stato_validazione"]=="VALIDATO"}
    if not gold:
        return {"esito":"NESSUN_GOLD_VALIDATO","accuratezza":None,
                "nota":"Prima validare risposte gold e PDF; nessuna metrica inventata."}
    manifest=json.loads(Path(manifest).read_text(encoding="utf-8"))
    digest=manifest["sha256_sqlite"]
    if any(row.get("snapshot_sha256") and row["snapshot_sha256"] != digest
           for row in gold.values()):
        raise ValueError("Le risposte gold appartengono a uno snapshot differente")
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
        seconds=[_number(x["secondi"],float) for x in rows
                 if str(x.get("secondi") or "").strip()]
        costs=[_number(x.get("costo_usd"),float) for x in rows
               if str(x.get("costo_usd") or "").strip()]
        tokens=[_number(x.get("token_input"),int,0)+
                _number(x.get("token_output"),int,0)
                for x in rows]
        calls=[_number(x.get("chiamate_llm_effettive"),int) for x in rows
               if str(x.get("chiamate_llm_effettive") or "").strip()]
        abstained=[int(x["valutazione_astensione"]) for x in rows
                   if gold[x["id"]]["categoria"] in ("ASSENZA_DOCUMENTALE","NEGATIVE")
                   and str(x.get("valutazione_astensione") or "").strip() in ("0","1")]
        errors=[int(x["errore_tecnico"]) for x in rows
                if str(x.get("errore_tecnico") or "").strip() in ("0","1")]
        citation_num=sum(_number(x.get("citazioni_corrette_n"),int,0)
                         for x in rows)
        citation_den=sum(_number(x.get("citazioni_verificate_n"),int,0)
                         for x in rows)
        score={
            "risposte":len(rows),
            "risposte_valutate_manualmente":len(rated),
            "accuratezza_manuale":round(mean(int(x["valutazione_risposta"]) for x in rated),4)
                                  if rated else None,
            "citazioni_valutate_manualmente":len(cited),
            "correttezza_citazioni":round(mean(int(x["valutazione_citazioni"]) for x in cited),4)
                                    if cited else None,
            "precision_citazioni":round(citation_num/citation_den,4)
                                   if citation_den else None,
            "citazioni_verificate":citation_den,
            "tempo_medio_secondi":round(mean(seconds),3) if seconds else None,
            "tempi_registrati":len(seconds),
            "chiamate_llm_medie":round(mean(calls),3) if calls else None,
            "chiamate_llm_registrate":len(calls),
            "astensioni_corrette":sum(abstained),
            "astensioni_valutate":len(abstained),
            "accuratezza_astensione":round(mean(abstained),4) if abstained else None,
            "tasso_errori_tecnici":round(mean(errors),4) if errors else None,
            "errori_tecnici_valutati":len(errors),
            "token_registrati":sum(tokens) if any(tokens) else None,
            "costo_totale_usd":round(sum(costs),6) if costs else None,
            "costo_medio_usd":round(mean(costs),6) if costs else None,
        }
        return {**score,**_micro_list_metrics(rows,gold)}
    methods={}
    for method in METHODS:
        method_rows=[pair[method] for pair in paired.values() if method in pair]
        methods[method]={"totale_gold":len(gold),
                         "copertura":round(len(method_rows)/len(gold),4),
                         **stat(method_rows),
                         "categorie":{cat:stat([x for x in method_rows
                            if gold[x["id"]]["categoria"]==cat])
                            for cat in sorted({x["categoria"] for x in gold.values()})}}
    complete=[key for key,pair in paired.items() if set(pair)==set(METHODS)]
    allcats=sorted({x["categoria"] for x in gold.values()})
    # Una riga per categoria, colonne distinte per entrambi i motori.
    table=[]
    for cat in allcats:
        record={"categoria":cat,
                "domande_gold":sum(x["categoria"]==cat for x in gold.values())}
        for method in METHODS:
            entry=methods[method]["categorie"][cat]
            short="TAG" if method=="TAG" else "Text_to_SQL"
            for source,dest in (
                ("accuratezza_manuale","accuratezza"),
                ("precision_micro","precision"),
                ("recall_micro","recall"),
                ("f1_micro","f1"),
                ("correttezza_citazioni","citazioni"),
                ("accuratezza_astensione","astensione"),
                ("tempo_medio_secondi","tempo_s"),
                ("chiamate_llm_medie","llm_medie"),
                ("costo_medio_usd","costo_usd"),
                ("tasso_errori_tecnici","errori_tecnici")):
                record[short+"_"+dest]=entry[source]
            record[short+"_n"]=entry["risposte"]
            record[short+"_n_valutate"]=entry["risposte_valutate_manualmente"]
        table.append(record)
    return {"esito":"OK","snapshot_sha256":digest,"modello":next(iter(models),None),
            "gold_validati":len(gold),"domande_con_entrambe_le_risposte":len(complete),
            "metodi":methods,"tabella_categorie":table,
            "nota":"Metriche cliniche/giuridiche soltanto da annotazioni manuali; "
                   "vuoto = non misurato. Precision/recall/F1 micro richiedono "
                   "elementi_gold ed elementi_predetti. Chiamate LLM effettive "
                   "solo se strumentate per l'intera pipeline."}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--benchmark",required=True)
    p.add_argument("--risultati",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--tabella-csv",help="Tabella righe=categorie; colonne=misure dei due metodi")
    a=p.parse_args()
    report=evaluate(a.benchmark,a.risultati,a.manifest)
    Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",
                           encoding="utf-8")
    if a.tabella_csv and report.get("tabella_categorie"):
        table=report["tabella_categorie"]
        with Path(a.tabella_csv).open("w",encoding="utf-8-sig",newline="") as fh:
            writer=csv.DictWriter(fh,fieldnames=list(table[0]),delimiter=";")
            writer.writeheader()
            writer.writerows(table)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
