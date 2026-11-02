"""Gold strutturale: pagine esistenti, revisore obbligatorio e confronto senza LLM."""
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tesi.valida_gold import inspect
from tesi.valuta_confronto import evaluate

GOLD_FIELDS=["id","categoria","domanda","risposta_gold","fonti_gold",
             "stato_validazione","note_revisore"]
PRED_FIELDS=["id","metodo","modello","snapshot_sha256","risposta","fonti",
             "secondi","token_input","token_output","costo_usd",
             "valutazione_risposta","valutazione_citazioni","note_revisore"]


def write_csv(path,cols,rows):
    with Path(path).open("w",encoding="utf-8-sig",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=cols,delimiter=";")
        w.writeheader()
        w.writerows(rows)


class GoldAndComparisonTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE note(id TEXT,percorso_zip TEXT);
            CREATE TABLE pagine(nota_id TEXT,numero_pagina INTEGER,testo TEXT,metodo TEXT);
            INSERT INTO note VALUES ('x','archivio/nota.pdf');
            INSERT INTO pagine VALUES ('x',2,'Testo sulla struttura autorizzata','TESTO');
        """)
        self.gold={
            "id":"DIR-01","categoria":"DIRETTE",
            "domanda":"La nota contiene il centro?",
            "risposta_gold":"Sì, il testo indica quel centro.",
            "fonti_gold":"archivio/nota.pdf#p2",
            "stato_validazione":"VALIDATO",
            "note_revisore":"Controllata pagina originale e indicazione."
        }

    def tearDown(self):
        self.db.close()

    def test_citations_exist_and_reviewer_required(self):
        report=inspect([self.gold],self.db)
        self.assertEqual(report["esito"],"OK")
        self.assertEqual(report["validati"],1)
        bad=dict(self.gold,fonti_gold="archivio/nota.pdf#p3")
        result=inspect([bad],self.db)
        self.assertEqual(result["esito"],"ERRORE")
        self.assertEqual(result["validati"],0)
        unverified=dict(self.gold,risposta_gold="",fonti_gold="",
                        stato_validazione="DA_VERIFICARE",note_revisore="")
        result=inspect([unverified],self.db)
        self.assertEqual(result["validati"],0)
        self.assertEqual(result["da_verificare"],1)

    def test_accuracy_only_from_manual_review(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            gold=folder/"gold.csv"
            preds=folder/"preds.csv"
            manifest=folder/"manifest.json"
            write_csv(gold,GOLD_FIELDS,[self.gold])
            manifest.write_text(json.dumps({"sha256_sqlite":"a"*64}),encoding="utf-8")
            rows=[]
            for method,grade in (("TAG","1"),("Text-to-SQL","0")):
                rows.append({
                    "id":"DIR-01","metodo":method,"modello":"provider/test-model",
                    "snapshot_sha256":"a"*64,"risposta":"una risposta",
                    "fonti":"archivio/nota.pdf#p2","secondi":"1.5",
                    "token_input":"10","token_output":"20","costo_usd":"0.001",
                    "valutazione_risposta":grade,
                    "valutazione_citazioni":"1",
                    "note_revisore":"Verificato sul documento originale",
                })
            write_csv(preds,PRED_FIELDS,rows)
            report=evaluate(gold,preds,manifest)
            self.assertEqual(report["domande_con_entrambe_le_risposte"],1)
            self.assertEqual(report["metodi"]["TAG"]["accuratezza_manuale"],1.0)
            self.assertEqual(report["metodi"]["Text-to-SQL"]["accuratezza_manuale"],0.0)
            rows[0]["valutazione_risposta"]=""
            write_csv(preds,PRED_FIELDS,rows)
            report=evaluate(gold,preds,manifest)
            self.assertIsNone(report["metodi"]["TAG"]["accuratezza_manuale"])
            rows[0]["snapshot_sha256"]="b"*64
            write_csv(preds,PRED_FIELDS,rows)
            with self.assertRaises(ValueError):
                evaluate(gold,preds,manifest)

    def test_no_gold_no_accuracy(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            gold=folder/"gold.csv"
            write_csv(gold,GOLD_FIELDS,[dict(self.gold,stato_validazione="DA_VERIFICARE",
                                            risposta_gold="",fonti_gold="")])
            result=evaluate(gold,folder/"missing.csv",folder/"missing.json")
            self.assertIsNone(result["accuratezza"])
            self.assertEqual(result["esito"],"NESSUN_GOLD_VALIDATO")


if __name__=="__main__":
    unittest.main()
