#!/usr/bin/env python3
"""36 quesiti *candidati* dal dataset online congelato: 9 per categoria.

NON genera risposte gold: le risposte si compilano dopo confronto sui PDF.
Produce anche un fascicolo JSONL di pagine candidato per revisione umana.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

CATEGORIES=("DIRETTE","SEMANTICHE","RIMANDI","NEGATIVE")
COLUMNS=("id","categoria","domanda","medicinale","nota_id","file_pdf",
         "pagina_evidenza_candidata","risposta_gold","fonti_gold",
         "stato_validazione","note_revisore")


def normalizza(value):
    val=unicodedata.normalize("NFKD",str(value or "").upper())
    return re.sub("[^A-Z0-9]","",
                  "".join(c for c in val if not unicodedata.combining(c)))


def read_rows(db,sql,args=()):
    return [dict(r) for r in db.execute(sql,args)]


def evidence_pages(db,docid,focus,limit=3):
    if not docid:
        return []
    rows=read_rows(db,"SELECT numero_pagina,testo,metodo FROM pagine "
                   "WHERE nota_id=? ORDER BY numero_pagina",(docid,))
    selected=sorted(rows,key=lambda r:(r["numero_pagina"]!=focus,
                      r["metodo"] not in ("TESTO","OCR"),r["numero_pagina"]))[:limit]
    return [{"pagina":r["numero_pagina"],"metodo":r["metodo"],
             "testo_estratto":r["testo"][:1600]} for r in selected]


def generate(db_path,manifest_path,output_csv,output_evidence,output_report):
    db_path=Path(db_path)
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    digest=sha256(db_path.read_bytes()).hexdigest()
    if digest!=manifest["sha256_sqlite"]:
        raise ValueError("Lo snapshot non corrisponde al manifesto; benchmark annullato")
    db=sqlite3.connect(db_path.resolve().as_uri()+"?mode=ro",uri=True)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    records=[]
    docs=[]
    per_category={category:0 for category in CATEGORIES}
    used={category:set() for category in CATEGORIES}

    def add(category,name,question,source=None,page=None,why=""):
        key=normalizza(name)
        if not key or key in used[category] or per_category[category]>=9:
            return
        used[category].add(key)
        per_category[category]+=1
        ident={"DIRETTE":"DIR","SEMANTICHE":"SEM",
               "RIMANDI":"RIM","NEGATIVE":"NEG"}[category]+f"-{per_category[category]:02d}"
        doc_id=source["id"] if source else ""
        pdf=source["percorso_zip"] if source else ""
        record={
            "id":ident,"categoria":category,"domanda":question,"medicinale":name,
            "nota_id":doc_id,"file_pdf":pdf,
            "pagina_evidenza_candidata":page or "",
            "risposta_gold":"","fonti_gold":"","stato_validazione":"DA_VERIFICARE",
            "note_revisore":why
        }
        records.append(record)
        docs.append({
            "id":ident,"categoria":category,"medicinale":name,
            "stato":"CANDIDATO_NON_VALIDATO",
            "nota_id":doc_id,"file_pdf":pdf,
            "pagina_candidata":page,"fonte_archivio":source.get("archivio_url") if source else None,
            "pagine_da_controllare":evidence_pages(db,doc_id,page),
            "avvertenza":(
                "La menzione di un centro NON attesta una sua autorizzazione."
                if category!="NEGATIVE"
                else "L'assenza dai titoli NON prova assenza di note per sinonimi, AIC o principi attivi."
            )
        })

    direct=read_rows(db,
        "SELECT n.id,n.percorso_zip,n.archivio_url,n.farmaco_candidato,n.anno,"
        "MIN(c.numero_pagina) AS pagina,COUNT(DISTINCT c.menzione) AS menzioni "
        "FROM note n JOIN centri_candidati c ON c.nota_id=n.id "
        "WHERE LENGTH(TRIM(COALESCE(n.farmaco_candidato,'')))>3 "
        "GROUP BY n.id ORDER BY menzioni DESC,n.anno DESC,n.percorso_zip LIMIT 90"
    )
    for d in direct:
        med=d["farmaco_candidato"]
        add("DIRETTE",med,
            f"Secondo la nota regionale relativa a {med}, quali strutture sono "
            "indicate per la prescrizione? Riporta la nota, la pagina e l'indicazione.",
            d,d["pagina"],"Verificare che le menzioni siano una vera autorizzazione.")

    semantic=read_rows(db,
        "SELECT n.id,n.percorso_zip,n.archivio_url,n.farmaco_candidato,n.anno,"
        "p.numero_pagina AS pagina,LENGTH(p.testo) AS caratteri "
        "FROM note n JOIN pagine p ON p.nota_id=n.id "
        "WHERE LENGTH(p.testo)>300 AND p.metodo IN ('TESTO','OCR') "
        "ORDER BY n.anno DESC,caratteri DESC,n.percorso_zip LIMIT 250"
    )
    for d in semantic:
        med=d["farmaco_candidato"]
        add("SEMANTICHE",med,
            f"Quali indicazioni terapeutiche, criteri e limitazioni sono descritti "
            f"dalla nota regionale su {med}? Fornisci pagina e passaggio a sostegno.",
            d,d["pagina"],"Verificare indicazione, posologia e ambito di applicazione.")

    refs=read_rows(db,
        "SELECT n.id,n.percorso_zip,n.archivio_url,n.farmaco_candidato,n.anno,"
        "MIN(r.numero_pagina) AS pagina,COUNT(*) AS rimandi "
        "FROM note n JOIN rimandi_candidati r ON r.nota_id=n.id "
        "WHERE LENGTH(TRIM(COALESCE(n.farmaco_candidato,'')))>3 "
        "GROUP BY n.id ORDER BY rimandi DESC,n.anno DESC,n.percorso_zip LIMIT 120"
    )
    for d in refs:
        med=d["farmaco_candidato"]
        add("RIMANDI",med,
            f"Nel documento regionale su {med} compare un riferimento a una nota "
            "o provvedimento precedente? Individua il riferimento e verifica "
            "se modifica, integra o si limita a citarlo. Cita tutte le pagine.",
            d,d["pagina"],"Rimando estratto automaticamente: relazione normativa non confermata.")

    # Negativi *candidati*: il primo controllo e' il titolo, NON una prova.
    titles={normalizza(r["farmaco_candidato"]) for r in
            read_rows(db,"SELECT farmaco_candidato FROM note")}
    names=read_rows(db,
        "SELECT medicinale,COUNT(*) AS n FROM strutture_registri "
        "WHERE LENGTH(medicinale)>4 GROUP BY medicinale ORDER BY n DESC,medicinale LIMIT 250"
    )
    for d in names:
        med=d["medicinale"]
        if normalizza(med) in titles:
            continue
        # Una menzione anche nel testo non deve diventare un falso negativo.
        found=db.execute("SELECT 1 FROM pagine WHERE instr(UPPER(testo),?)>0 LIMIT 1",
                         (med.upper(),)).fetchone()
        if found:
            continue
        add("NEGATIVE",med,
            f"Nel corpus regionale fissato per l'esperimento esiste una nota che "
            f"documenti i centri per {med}? Se non è documentata, dichiara "
            "l'assenza di evidenza nel corpus, senza concludere che la "
            "prescrizione sia vietata.",
            why="Controllare alias, principi attivi e documenti con nomi diversi.")

    counts={key:per_category[key] for key in CATEGORIES}
    if any(n!=9 for n in counts.values()):
        raise ValueError("Impossibile formare 9 esempi per categoria: "+repr(counts))
    db.close()

    for loc in (output_csv,output_evidence,output_report):
        Path(loc).parent.mkdir(parents=True,exist_ok=True)
    with Path(output_csv).open("w",encoding="utf-8-sig",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=COLUMNS,delimiter=";")
        w.writeheader()
        w.writerows(records)
    with Path(output_evidence).open("w",encoding="utf-8") as stream:
        for item in docs:
            stream.write(json.dumps(item,ensure_ascii=False)+"\n")
    summary={
        "schema":1,"benchmark":"36_DOMANDE_CANDIDATE_NON_VALIDATE",
        "snapshot_sha256":digest,
        "manifest_git_commit":manifest.get("git_commit"),
        "classi_ah_data":manifest["fonti_ufficiali"]["classi_ah"]["data_riferimento"],
        "categorie":counts,"gold_validati":0,
        "nota":"Nessuna risposta gold generata automaticamente; la revisione "
               "deve verificare PDF, pagina, rimandi ed eventuali note successive."
    }
    Path(output_report).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",
                                   encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--evidenze",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(generate(a.db,a.manifest,a.out,a.evidenze,a.report),
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
