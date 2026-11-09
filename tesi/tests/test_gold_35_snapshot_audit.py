"""Audit automatico delle fonti delle Gold candidate (solo presenza, NON verita' normativa).
Usa esclusivamente il file SQLite statico del 02/11/2026. Non interroga LLM.
"""
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unittest

ROOT=Path(__file__).resolve().parents[2]
SNAPSHOT=ROOT/"risultati/tesi_statico_20261102.sqlite.gz"
MANIFEST=ROOT/"risultati/tesi_statico_20261102.json"
GOLD=ROOT/"tesi/FarmaQuery_Gold_35_20261109.json"
REF_PDF=re.compile(r"([^|]+?\.pdf)#p([1-9]\d*)",re.I)


def normalize(s):
    return " ".join(str(s).casefold().split())


def candidate_docs(source, rows):
    # Preferisci un percorso ZIP completo, poi un nome file univoco.
    p=normalize(source)
    full=[r for r in rows if normalize(r["percorso_zip"])==p]
    if full:
        return full, "PERCORSO_ESATTO"
    last=p.split("/")[-1]
    ends=[r for r in rows if normalize(r["nome_file"])==last]
    if len(ends)==1:
        return ends, "NOME_UNIVOCO"
    if len(ends)>1:
        return ends, "NOME_AMBIGUO"
    return [], "ASSENTE"


class Gold35SnapshotEvidenceAudit(unittest.TestCase):
    def test_refs_and_static_hash(self):
        g=json.loads(GOLD.read_text(encoding="utf-8"))
        manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
        db_bytes=gzip.decompress(SNAPSHOT.read_bytes())
        self.assertEqual(hashlib.sha256(db_bytes).hexdigest(),
                         manifest["sha256_sqlite"])
        self.assertEqual(g["meta"]["snapshot_statico"],
                         manifest["sha256_sqlite"])
        db=sqlite3.connect(":memory:")
        db.row_factory=sqlite3.Row
        db.deserialize(db_bytes)
        try:
            notes=db.execute(
                "SELECT id,nome_file,percorso_zip,anno,stato_estrazione "
                "FROM note").fetchall()
            all_questions=g["domande"]
            self.assertEqual(len(all_questions),35)
            failures=[]
            stats={"pagine_verificate":0,"pagine_assenti":0,
                   "pagine_ambigue":0,"riferimenti_esterni":0}
            for q in all_questions:
                sources=q.get("fonti") or []
                report=[]
                found=0
                for source in sources:
                    refs=REF_PDF.findall(source)
                    if not refs:
                        # In Gold convivono riferimenti strutturati/esterni:
                        # la loro validita' semantica viene controllata separatamente.
                        report.append("NON_PAGINA: "+source[:100])
                        stats["riferimenti_esterni"]+=1
                        continue
                    for name,page in refs:
                        docs,strategy=candidate_docs(name,notes)
                        page=int(page)
                        if not docs:
                            failures.append(q["id"]+":"+name+"#p"+str(page)+" ASSENTE")
                            stats["pagine_assenti"]+=1
                            report.append("ASSENTE: "+name+"#p"+str(page))
                            continue
                        if len(docs)>1:
                            stats["pagine_ambigue"]+=1
                            report.append("AMBIGUO: "+name+"#p"+str(page))
                            # Non scegliere arbitrariamente una delle omonimie.
                            continue
                        doc=docs[0]
                        row=db.execute(
                            "SELECT metodo,testo FROM pagine "
                            "WHERE nota_id=? AND numero_pagina=?",
                            (doc["id"],page)
                        ).fetchone()
                        if row is None or not (row["testo"] or "").strip():
                            failures.append(q["id"]+":"+name+"#p"+str(page)+" SENZA_TESTO")
                            stats["pagine_assenti"]+=1
                            report.append("NON_ESTRATTA: "+name+"#p"+str(page))
                        else:
                            stats["pagine_verificate"]+=1
                            found+=1
                            report.append("OK "+strategy+": "+doc["percorso_zip"]+
                                "#p"+str(page)+" metodo="+str(row["metodo"])+
                                " chars="+str(len(row["testo"])))
                print("GOLD_AUDIT",q["id"],q["categoria"],
                      "stato_precedente="+q["stato"],
                      "pagine_leggibili="+str(found),
                      "report="+json.dumps(report,ensure_ascii=False),flush=True)
            # Verifica esplicitamente la presenza di RYSTIGGO e il limite noto.
            doc=db.execute("SELECT id FROM note WHERE nome_file='RYSTIGGO.pdf'").fetchone()
            self.assertIsNotNone(doc)
            p3=db.execute("SELECT testo FROM pagine WHERE nota_id=? "
                          "AND numero_pagina=3",(doc["id"],)).fetchone()
            self.assertIsNotNone(p3)
            self.assertIn("RYSTIGGO",(p3["testo"] or "").upper())
            self.assertNotIn("federico",(p3["testo"] or "").casefold())
            table_names={r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            print("GOLD_AUDIT_TABLES",sorted(table_names),flush=True)
            print("GOLD_AUDIT_SUMMARY",json.dumps(stats,ensure_ascii=False),
                  "ERRORS",failures,flush=True)
            self.assertEqual(failures,[])
        finally:
            db.close()
