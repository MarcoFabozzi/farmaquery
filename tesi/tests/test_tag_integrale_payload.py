"""Test dell'intero percorso TAG fino al payload della sintesi, senza API.

Non verifica che il LLM sia corretto: verifica che a Gemini arrivi davvero
la fonte integrale, anziché soltanto l'estratto troncato da LOTUS.
"""
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tesi.prepara_snapshot_online import ROOT, build_snapshot
from tesi import pilota_tag_vs_sql as engine


class FakeFrame:
    def __init__(self, records):
        self.records=list(records)
    def head(self, count):
        return FakeFrame(self.records[:count])
    def __getitem__(self, columns):
        return FakeFrame([{key:row[key] for key in columns}
                          for row in self.records])
    def to_dict(self, orient):
        assert orient=="records"
        return self.records


def run_without_provider(db, question, answer):
    fake_pandas=types.ModuleType("pandas")
    fake_pandas.DataFrame=FakeFrame
    fake_lotus=types.ModuleType("lotus")
    fake_models=types.ModuleType("lotus.models")
    class FakeLM:
        def __init__(self,*args,**kwargs):
            self.stats=None
    fake_models.LM=FakeLM
    fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
    fake_lotus.models=fake_models
    requests=[]
    def fake_ask(model,system,payload,**kwargs):
        requests.append((system,payload,kwargs))
        return answer,{
            "token_input":8,"token_output":4,"costo_usd":0.001}
    with patch.dict(sys.modules,{"lotus":fake_lotus,
                                 "lotus.models":fake_models,
                                 "pandas":fake_pandas}):
        with patch.object(engine,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            with patch.object(engine,"ask",side_effect=fake_ask):
                result=engine.tag(db,question,"modello-test")
    return result,requests


class TagIntegralPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.path=Path(cls.temp.name)/"snapshot.sqlite"
        build_snapshot(ROOT,cls.path,Path(cls.temp.name)/"manifest.json")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_amvuttra_pagina_intera_raggiunge_sintesi(self):
        question=("Quali sono tutti i centri elencati nella Tabella 1, "
                  "pagina 2, della nota AMVUTTRA 0634617/2026 per ATTR-CM? "
                  "Riporta esclusivamente questa indicazione.")
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            result,requests=run_without_provider(
                db,question,"Sintesi di esempio")
        self.assertEqual(len(requests),1)
        sources=requests[0][1]["evidenze"]
        raw=" ".join(str(x["testo"]) for x in sources)
        self.assertIn("FEDERICO",raw.upper())
        self.assertIn("CARDARELLI",raw.upper())
        self.assertIn("RUGGI",raw.upper())
        self.assertTrue(result["contesto_integrale"])
        self.assertTrue(result["contesto_integrale_completo"])
        self.assertNotIn("troncata per limiti",result["risposta"])

    def test_wegovy_sei_aic_raggiungono_sintesi(self):
        question=("Quante confezioni di WEGOVY sono presenti "
                  "nell'articolo 1 della determina 23A02767? "
                  "Riporta tutti gli AIC, distinguendo le diverse "
                  "confezioni da 2,4 mg.")
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            result,requests=run_without_provider(
                db,question,"Nell'articolo 1 sono presenti 5 confezioni.")
        self.assertEqual(len(requests),1)
        payload=requests[0][1]
        ids={x for row in payload["evidenze"]
             for x in row.get("aic_trovati_nel_testo",[])}
        self.assertEqual(len(ids),6)
        self.assertIn("049883111/E",ids)
        self.assertEqual(result["aic_mancanti_rispetto_al_testo"],6)
        self.assertTrue(result["contesto_integrale_completo"])
        self.assertIn("049883111/E",result["risposta"])
        self.assertIn("6",result["risposta"])


if __name__=="__main__":
    unittest.main()
