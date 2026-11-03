"""Collaudo reale e ripetibile della demo FarmaQuery su SQLite statico.

Il preflight non usa API: verifica fonti, checksum e pagine.
Le risposte sono prodotte dai due motori SOLO con --live e credenziali disponibili.
Non trasforma risposte attese in prompt né assegna punteggi gold automaticamente.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import os
import sqlite3
import time
import traceback

from chatbot_farmaquery import answer_question,prepare_snapshot,model_from_settings
from errori_chatbot import diagnose_error

CASES=[
 ("S1","SEMPLICE",
  "Secondo la nota PLUVICTO del 18 aprile 2025, quali sono i centri "
  "indicati per la prescrizione o somministrazione e quali requisiti "
  "sono richiesti? Indica il PDF e la pagina."),
 ("S2","CATEGORIA_IMPLICITA",
  "Quali medicinali citati nelle note della Regione Campania per "
  "malattie neuromuscolari sono collegati all'AOU Federico II? "
  "Riporta patologia, indicazione, nota e pagina, senza inventare."),
 ("S3","RIMANDI",
  "Nella nota CAMZYOS Prot. N.0641382/2025 quali note precedenti "
  "sono annullate e sostituite e quali sono soltanto richiamate? "
  "Indica per ciascun riferimento la pagina."),
 ("S4","NON_DOCUMENTATA",
  "Nella nota PLUVICTO del 18 aprile 2025 è indicata la data "
  "di effettiva attivazione di ciascuno dei cinque centri? "
  "Se non è documentata nella nota, dichiaralo esplicitamente.")
]


def preflight(db_path,metadata):
    if metadata.get("data_fonte")!="2026-11-02":
        raise ValueError("Lo snapshot non è quello congelato per la tesi")
    if metadata.get("gazzetta_commit")!="630613a1b3e5353fe33e207e843fb8dad5591b2a":
        raise ValueError("La Gazzetta non proviene dal commit congelato")
    with sqlite3.connect(Path(db_path).resolve().as_uri()+"?mode=ro",uri=True) as db:
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        counts={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in (
            "note","pagine","aifa_confezioni","ema_medicinali",
            "nota_centro_documentato","nota_rimando_revisionato",
            "gu_atti","gu_documenti","gu_segmenti")}
        expected={"note":380,"pagine":942,"nota_centro_documentato":28,
                  "nota_rimando_revisionato":2}
        for table,count in expected.items():
            if counts[table]!=count:
                raise ValueError("Conteggio errato "+table)
        if counts["gu_atti"]<1 or counts["gu_documenti"]<1:
            raise ValueError("Fonti Gazzetta assenti dal corpus")
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("SQLite corrotto")
        relations=[dict(row) for row in db.execute(
            """SELECT r.id,r.nota_id,r.numero_pagina,r.centro,
                      r.ancora_testuale,n.nome_file,p.testo
               FROM nota_centro_documentato r
               JOIN note n ON n.id=r.nota_id
               JOIN pagine p ON p.nota_id=r.nota_id
                            AND p.numero_pagina=r.numero_pagina""")]
        if len(relations)!=28:
            raise ValueError("Numero relazioni non atteso")
        for row in relations:
            if row["ancora_testuale"] not in row["testo"]:
                raise ValueError("Centro senza prova sulla pagina: "+row["nome_file"])
        pluv=[r for r in relations if r["nome_file"]=="PLUVICTO.pdf"]
        if len(pluv)!=5:
            raise ValueError("PLUVICTO: cinque centri attesi")
        cam=list(db.execute(
            """SELECT r.numero_pagina,r.protocollo_richiamato,r.rapporto,r.frase,p.testo
               FROM nota_rimando_revisionato r
               JOIN pagine p ON p.nota_id=r.nota_id
                            AND p.numero_pagina=r.numero_pagina
               JOIN note n ON n.id=r.nota_id
               WHERE n.nome_file LIKE 'CAMZYOS  Prot.N.0641382%'
               ORDER BY r.numero_pagina"""))
        if len(cam)!=2 or cam[0]["rapporto"]!="ANNULLA_E_SOSTITUISCE" or (
            cam[1]["rapporto"]!="SEMPLICE_RICHIAMO"
        ) or any(row["frase"] not in row["testo"] for row in cam):
            raise ValueError("Rimandi CAMZYOS non coerenti")
        gu=db.execute("SELECT codice FROM gu_atti WHERE codice='23A02767'").fetchone()
        if not gu:
            raise ValueError("Gazzetta WEGOVY 23A02767 non disponibile")
        notes=sorted({r["nome_file"] for r in relations
                      if "Federico II" in r["centro"]})
        return {"esito":"PRECOLLAUDO_DOCUMENTALE_OK",
                "conteggi":counts,
                "pluvicto_centri":[r["centro"] for r in pluv],
                "camzyos_rimandi":[{"pagina":r["numero_pagina"],
                     "protocollo":r["protocollo_richiamato"],
                     "rapporto":r["rapporto"]} for r in cam],
                "note_con_federico_ii_gia_revisionate":notes,
                "avvertenza":("Questo è un preflight SQL sul database reale, "
                    "non una risposta dei modelli. Le 28 relazioni non "
                    "rappresentano tutte le menzioni nel corpus.")}


def live(db_path,model,max_questions=2):
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        return {"esito":"NON_ESEGUITO_MANCANO_CREDENZIALI",
                "spiegazione":"La chiave Gemini non è configurata per questo processo."}
    result=[]
    for ident,category,question in CASES[:max_questions]:
        for method in ("Text-to-SQL","TAG"):
            started=time.monotonic()
            item={"id":ident,"categoria":category,"domanda":question,
                  "metodo":method,"modello":model}
            try:
                reply=answer_question(db_path,question,method,model)
                item.update({
                    "stato":reply.get("stato","OK"),
                    "risposta":str(reply.get("risposta","")),
                    "fonti":reply.get("fonti",[]),
                    "sql":reply.get("sql",""),
                    "righe_sql":reply.get("righe_sql"),
                    "sql_tentativi":reply.get("sql_tentativi"),
                    "righe_sem_filter":reply.get("righe_sem_filter"),
                    "righe_recuperate":reply.get("righe_recuperate"),
                    "modalita_tag":reply.get("modalita_selezione"),
                    "token_input":reply.get("token_input"),
                    "token_output":reply.get("token_output"),
                    "costo_usd":reply.get("costo_usd")})
            except Exception as err:
                classified=diagnose_error(err)
                item.update({"stato":"ERRORE_TECNICO",
                             "codice_errore":classified.get("codice"),
                             "fase_errore":classified.get("fase"),
                             "errore_tipo":type(err).__name__})
            item["secondi"]=round(time.monotonic()-started,3)
            result.append(item)
    errors=sum(row["stato"]=="ERRORE_TECNICO" for row in result)
    return {"esito":"ESEGUITO" if errors==0 else "ESEGUITO_CON_ERRORI",
            "numero_interrogazioni":len(result),"errori_tecnici":errors,
            "risposte":result,
            "avvertenza":"Risposte grezze, non valutazioni gold o prove normative."}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--live",action="store_true")
    p.add_argument("--max-domande",type=int,default=2,choices=range(1,5))
    p.add_argument("--model",default=os.environ.get(
        "FARMAQUERY_LLM_MODEL","gemini/gemini-3.5-flash-lite"))
    args=p.parse_args()
    path,meta=prepare_snapshot()
    report={
        "data_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_sha256":meta.get("sha256_sqlite"),
        "snapshot_origine_sha256":meta.get("snapshot_origine_sha256"),
        "modello":args.model,
        "modalita":("LIVE_GEMINI" if args.live else "SOLO_PREFLIGHT")}
    report["verifica"]=preflight(path,meta)
    if args.live:
        report["interrogazione"]=live(path,args.model,args.max_domande)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+"\n",
                        encoding="utf-8")
    print(json.dumps({"verifica":report["verifica"]["esito"],
                      "esito_llm":report.get("interrogazione",{}).get("esito"),
                      "file":str(args.out)},ensure_ascii=False))


if __name__=="__main__":
    main()
