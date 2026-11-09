"""Test runner: nessuna chiamata reale al provider, nessun uso dei gold."""
import csv
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tesi.esegui_holdout import collect


class HoldoutRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"x.sqlite"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE note(id TEXT,percorso_zip TEXT);
                CREATE TABLE pagine(
                    nota_id TEXT,numero_pagina INTEGER,testo TEXT,metodo TEXT);
                INSERT INTO note VALUES('n1','test/f.pdf');
                INSERT INTO pagine VALUES('n1',1,'Testo documentato','TESTO');
            """)
        self.digest=sha256(self.db.read_bytes()).hexdigest()
        self.manifest=self.root/"manifest.json"
        self.manifest.write_text(json.dumps({"sha256_sqlite":self.digest}))
        self.gold=self.root/"gold.csv"
        self.header=["id","categoria","domanda","risposta_gold","fonti_gold",
                     "stato_validazione","note_revisore","snapshot_sha256"]
        self.record=dict(id="B01",categoria="DIRETTE",
                         domanda="Domanda fittizia non del benchmark reale",
                         risposta_gold="Risposta documentata dello snapshot",
                         fonti_gold="test/f.pdf#p1",
                         stato_validazione="VALIDATO",
                         note_revisore="Verifica completa nel documento originale",
                         snapshot_sha256=self.digest)
        self._write_gold(self.record)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_gold(self,row):
        with self.gold.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=self.header,delimiter=";")
            w.writeheader()
            w.writerow(row)

    def test_non_esegue_gold_da_verificare(self):
        self._write_gold(dict(self.record,stato_validazione="DA_VERIFICARE",
                              risposta_gold="",fonti_gold=""))
        called=[]
        with self.assertRaisesRegex(ValueError,"Holdout non pronto"):
            collect(self.gold,self.db,self.manifest,"mock",
                    self.root/"ris.csv","abcdef123",
                    answer_fn=lambda *a: called.append(a))
        self.assertEqual(called,[])

    def test_unico_run_scrive_due_metodi_e_misure_reali(self):
        def answer(db,q,method,model):
            return {"risposta":"test","fonti":["test/f.pdf#p1"],
                    "chiamate_llm_effettive":(4 if method=="TAG automatico" else 2),
                    "token_input":10,"token_output":7,"costo_usd":0.001,
                    "sql_originale_llm":"SELECT 1",
                    "sql":"SELECT 2","tag_auto_revision":"test-r0",
                    "sql_primo_tentativo":"SELECT 1",
                    "sql_fallback":"SELECT 2",
                    "recupero_progressivo_usato":True,
                    "sql_tentativi":2,"correzioni_sql":1,
                    "versione_text_to_sql":"autocorrezione-v2-controlli",
                    "motivo_controllo_sql":"TEST",
                    "sql_proposte":["SELECT 1","SELECT 2"]}
        path=self.root/"ris.csv"
        collect(self.gold,self.db,self.manifest,"mock",path,"abcdef123",
                answer_fn=answer)
        with path.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f,delimiter=";"))
        self.assertEqual({r["metodo"] for r in rows},
                         {"Text-to-SQL con auto-correzione","TAG automatico"})
        self.assertEqual({r["chiamate_llm_effettive"] for r in rows},
                         {"2","4"})
        self.assertTrue(all(r["valutazione_risposta"]=="" for r in rows))
        self.assertTrue(all(r["sql_originale_llm"]=="SELECT 1" for r in rows))
        self.assertTrue(all(r["sql_eseguito"]=="SELECT 2" for r in rows))
        self.assertTrue(all(r["sql_primo_tentativo"]=="SELECT 1" for r in rows))
        self.assertTrue(all(r["sql_fallback"]=="SELECT 2" for r in rows))
        self.assertTrue(all(r["sql_tentativi"]=="2" for r in rows))
        self.assertTrue(all(r["correzioni_sql"]=="1" for r in rows))
        self.assertTrue(all(r["versione_text_to_sql"]=="autocorrezione-v2-controlli" for r in rows))
        self.assertTrue(all("SELECT 1" in r["sql_proposte"] for r in rows))
        self.assertTrue(all(r["tag_auto_revision"]=="test-r0" for r in rows))
        with self.assertRaises(FileExistsError):
            collect(self.gold,self.db,self.manifest,"mock",path,"abcdef123",
                    answer_fn=answer)


    def test_ordine_a_rotazione_senza_ripetizioni(self):
        # Rotazione dei due motori su tre domande valide con identica fonte.
        for i in range(1,4):
            row=dict(self.record,id=f"B0{i}",domanda=f"Domanda prova {i}")
            if i==1:
                with self.gold.open("w",newline="",encoding="utf-8") as fh:
                    writer=csv.DictWriter(fh,fieldnames=self.header,delimiter=";")
                    writer.writeheader()
                    writer.writerow(row)
            else:
                with self.gold.open("a",newline="",encoding="utf-8") as fh:
                    writer=csv.DictWriter(fh,fieldnames=self.header,delimiter=";")
                    writer.writerow(row)
        order=[]
        def answer(db,q,method,model):
            order.append((q,method))
            return {"risposta":"test","fonti":["test/f.pdf#p1"]}
        collect(self.gold,self.db,self.manifest,"mock",self.root/"tre.csv",
                "abcdef123",answer_fn=answer)
        actual=[x[1] for x in order]
        self.assertEqual(actual[:2],["Text-to-SQL con auto-correzione","TAG automatico"])
        self.assertEqual(actual[2:4],["TAG automatico","Text-to-SQL con auto-correzione"])
        self.assertEqual(actual[4:6],["Text-to-SQL con auto-correzione","TAG automatico"])
        self.assertEqual(len(order),6)


if __name__=="__main__":
    unittest.main()
