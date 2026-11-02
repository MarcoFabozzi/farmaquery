"""Test dei motori e del runner senza API esterne né LOTUS installato."""
import csv
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tesi.esegui_benchmark import execute, load_questions
from tesi.pilota_tag_vs_sql import evidence_candidates, validate_sql


class ExperimentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)
        self.db=self.path/"dataset.sqlite"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
            CREATE TABLE note(id TEXT,percorso_zip TEXT,archivio_url TEXT);
            CREATE TABLE pagine(nota_id TEXT,numero_pagina INTEGER,testo TEXT,metodo TEXT);
            CREATE VIRTUAL TABLE pagine_fts USING fts5(
                nota_id UNINDEXED, numero_pagina UNINDEXED, testo);
            CREATE TABLE aifa_confezioni(
                aic TEXT, nome TEXT, principio_attivo TEXT,descrizione TEXT,
                classe_a_h_snapshot TEXT, classe_a_h_data TEXT);
            CREATE TABLE ema_medicinali(
                ema_id TEXT, nome TEXT, principio_attivo TEXT, stato_ema TEXT,
                data_decisione_ue TEXT,indicazione_ema TEXT,url_ema TEXT);
            CREATE TABLE strutture_registri(
                id TEXT,medicinale TEXT,patologia TEXT,indicazione TEXT,
                struttura TEXT,data_riferimento TEXT,fonte_url TEXT);
            INSERT INTO note VALUES
                ('n1','campania/JIVI.pdf','https://www.regione.campania.it/note2026.zip');
            INSERT INTO pagine VALUES
                ('n1',2,'JIVI e trattamento della emofilia A','TESTO');
            INSERT INTO pagine_fts VALUES
                ('n1',2,'JIVI e trattamento della emofilia A');
            INSERT INTO aifa_confezioni VALUES
                ('012345678','JIVI','damoctocog alfa pegol','Flaconcino', 'H','2026-06-30');
            INSERT INTO ema_medicinali VALUES
                ('EMA-1','JIVI','damoctocog alfa pegol','Autorizzato',
                 '2018-11-22','Emofilia A','https://www.ema.europa.eu/en/medicines');
            INSERT INTO strutture_registri VALUES
                ('s1','JIVI','Emofilia A','indicazione test','Ospedale test',
                 '2026-09-14','https://www.aifa.gov.it/strutture');
            """)
        self.manifest=self.path/"manifest.json"
        self.digest=sha256(self.db.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps({"sha256_sqlite":self.digest,
                                              "git_commit":"abc123"}),encoding="utf-8")
        self.questions=self.path/"domande.csv"
        self.questions.write_text("id;categoria;domanda\n"
                                  "Q1;Semplice;JIVI in quale classe è?\n"
                                  "Q2;Intermedia;JIVI è autorizzato nell'UE?\n",
                                  encoding="utf-8")
        self.out=self.path/"risposte.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_multifonte_su_stesso_database(self):
        with sqlite3.connect(self.db) as db:
            db.row_factory=sqlite3.Row
            data=evidence_candidates(db,"Qual è la classe del JIVI?")
        kinds={x["tipo"] for x in data}
        self.assertTrue({"AIFA","EMA","REGIONE","REGISTRO_AIFA"}.issubset(kinds),kinds)
        self.assertTrue(any("JIVI.pdf#p2" in x["fonte"] for x in data))

    def test_anteprima_e_hash(self):
        report=execute(self.db,self.manifest,self.questions,self.out,max_questions=2)
        self.assertEqual(report["esito"],"ANTEPRIMA_SENZA_CHIAMATE")
        self.assertFalse(self.out.exists())
        self.assertEqual(len(report["domande"]),2)
        wrong=self.path/"wrong.json"
        wrong.write_text(json.dumps({"sha256_sqlite":"0"*64}))
        with self.assertRaises(ValueError):
            execute(self.db,wrong,self.questions,self.out)

    def test_due_metodi_e_colonne_valutazione_manuale(self):
        def tag(db,question,model):
            self.assertEqual(model,"mock-model")
            self.assertIn("JIVI",question)
            return {"stato":"OK","risposta":"Risposta TAG",
                    "fonti":["AIFA AIC 012345678"],"token_input":15,
                    "token_output":6,"costo_usd":None,"costo_completo":False}
        def sql(db,question,model):
            return {"stato":"OK","risposta":"Risposta SQL",
                    "fonti":["EMA EMA-1"],"sql":"SELECT * FROM note",
                    "token_input":11,"token_output":5,"costo_usd":0.0,
                    "costo_completo":True}
        result=execute(self.db,self.manifest,self.questions,self.out,
                       "mock-model",max_questions=2,confirm=True,
                       tag_fn=tag,sql_fn=sql)
        self.assertEqual(result["righe_aggiunte"],4)
        with self.out.open(encoding="utf-8-sig",newline="") as fh:
            rows=list(csv.DictReader(fh,delimiter=";"))
        self.assertEqual(len(rows),4)
        self.assertEqual({r["metodo"] for r in rows},{"TAG","Text-to-SQL"})
        self.assertTrue(all(r["valutazione_risposta"]=="" and
                            r["valutazione_citazioni"]=="" for r in rows))
        self.assertTrue(all(r["snapshot_sha256"]==self.digest for r in rows))
        again=execute(self.db,self.manifest,self.questions,self.out,
                      "mock-model",max_questions=2,confirm=True,resume=True,
                      tag_fn=tag,sql_fn=sql)
        self.assertEqual(again["righe_aggiunte"],0)
        with self.assertRaises(ValueError):
            execute(self.db,self.manifest,self.questions,self.out,
                    "other-model",max_questions=2,confirm=True,resume=True,
                    tag_fn=tag,sql_fn=sql)

    def test_csv_comma_e_sql_sicuro(self):
        comma=self.path/"comma.csv"
        comma.write_text('id,domanda\nQ1,"Cos’è JIVI, in Italia?"\n',encoding="utf-8")
        self.assertEqual(load_questions(comma)[0]["id"],"Q1")
        self.assertEqual(validate_sql("SELECT aic FROM aifa_confezioni LIMIT 3"),
                         "SELECT aic FROM aifa_confezioni LIMIT 3")
        for unsafe in ("PRAGMA database_list",
                       "DELETE FROM aifa_confezioni",
                       "SELECT * FROM sqlite_master",
                       "SELECT * FROM main.note",
                       "SELECT load_extension('evil')",
                       "SELECT * FROM note; DROP TABLE note"):
            with self.subTest(sql=unsafe),self.assertRaises(ValueError):
                validate_sql(unsafe)


if __name__=="__main__":
    unittest.main()
