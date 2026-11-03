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


def run_without_provider(db, question, answer, select_none=False):
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
                          side_effect=lambda frame,instruction:(
                              FakeFrame([]) if select_none else frame)):
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

    def test_casgevy_pagina_3_sinfonia_raggiunge_sintesi(self):
        question=(
            "Secondo la pagina 3 della nota CASGEVY Prot.N.0655032-2025, "
            "a quale scopo viene richiamata la nota PG/2024/0503681 "
            "del 24 ottobre 2024? Riporta esclusivamente quanto scritto "
            "nella pagina 3 sulla piattaforma SINFONIA, senza cercare "
            "il testo della nota precedente.")
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            result,requests=run_without_provider(
                db,question,"Risposta basata sulla pagina 3.")
        self.assertEqual(len(requests),1)
        context=requests[0][1]
        self.assertTrue(context.get("sezione_integralmente_disponibile"))
        pages=context["evidenze"]
        self.assertTrue(pages)
        self.assertTrue(all("#p3" in x["fonte"] for x in pages))
        raw=" ".join(x["testo"] for x in pages).upper()
        self.assertIn("SINFONIA",raw)
        self.assertIn("0503681",raw)
        self.assertTrue(result["contesto_integrale_completo"])
        self.assertEqual(result["verifica_contesto"],"integrale")

    def test_camzyos_pagina_1_rimane_disponibile_con_lotus_vuoto(self):
        question=(
            "Trascrivi le frasi della pagina 1 della nota CAMZYOS "
            "Prot.N.0641382-2025 in cui compaiono i protocolli "
            "0624981/2025 e PG/2024/0503681. Per ciascuno indica "
            "esclusivamente il rapporto esplicitamente dichiarato "
            "nel testo, distinguendo annullamento e sostituzione "
            "da semplice richiamo.")
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            result,requests=run_without_provider(
                db,question,"Risposta dalla pagina originale.",select_none=True)
        self.assertEqual(len(requests),1)
        self.assertTrue(result["fallback_pagina_integrale"])
        self.assertTrue(result["contesto_integrale_completo"])
        self.assertEqual(result["righe_selezionate_lotus"],0)
        self.assertNotIn("non documentata",result["risposta"])
        pages=requests[0][1]["evidenze"]
        self.assertTrue(pages)
        self.assertTrue(all("#p1" in x["fonte"] for x in pages))
        text=" ".join(x["testo"] for x in pages)
        # La pagina 1 originale contiene SOLO la nota sostituita:
        # il protocollo 2024 non deve essere inventato per compiacere
        # la domanda, pur comparendo in alcuni avvisi sui rimandi.
        self.assertIn("0624981",text)
        self.assertNotIn("0503681",text)
        self.assertIn("annulla e  sostituisce",text)


    def test_casgevy_domanda_relatore_senza_numero_pagina(self):
        question=(
            "Quale nota del 2024 richiama CASGEVY nel 2025 per SINFONIA, "
            "e questo rimando annulla o sostituisce la nota precedente?")
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            result,requests=run_without_provider(db,question,"Risposta di test.")
        self.assertTrue(result["contesto_integrale"])
        self.assertNotEqual(result["verifica_contesto"],"non_recuperato")
        pages=requests[0][1]["evidenze"]
        page3=[r for r in pages if "#p3" in r["fonte"]]
        self.assertTrue(page3,"Il testo della pagina 3 CASGEVY deve arrivare al LLM.")
        self.assertIn("0503681"," ".join(r["testo"] for r in page3))

    def test_amvuttra_domanda_relatore_senza_tabella_esplicita(self):
        question=(
            "Quali sono esattamente i sei centri per ATTR-CM e i tre "
            "per polineuropatia ereditaria indicati nella nota AMVUTTRA 2026?")
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            result,requests=run_without_provider(db,question,"Risposta di test.")
        self.assertTrue(result["contesto_integrale"])
        pages=requests[0][1]["evidenze"]
        page2=" ".join(r["testo"] for r in pages if "#p2" in r["fonte"]).upper()
        page3=" ".join(r["testo"] for r in pages if "#p3" in r["fonte"]).upper()
        self.assertIn("RUGGI",page2)
        self.assertIn("CARDARELLI",page2)
        self.assertIn("VANVITELLI",page3)

    def test_pluvicto_domanda_relatore_con_requisiti(self):
        question=(
            "Secondo la nota regionale PLUVICTO del 18/04/2025, quali "
            "sono tutte le cinque strutture di Medicina Nucleare "
            "individuate e quali requisiti aggiuntivi sono richiesti?")
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            result,requests=run_without_provider(db,question,"Risposta di test.")
        self.assertTrue(result["contesto_integrale"])
        pages=requests[0][1]["evidenze"]
        page2=" ".join(r["testo"] for r in pages if "#p2" in r["fonte"]).casefold()
        self.assertIn("lutezio",page2)
        self.assertIn("registro",page2)


    def test_debug_source_statistics_pluvicto(self):
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            notes=[dict(r) for r in db.execute(
                "SELECT id,anno,nome_file,percorso_zip FROM note "
                "WHERE nome_file LIKE '%PLUVICTO%' COLLATE NOCASE")]
            for note in notes:
                pages=[dict(p) for p in db.execute(
                    "SELECT numero_pagina,length(testo) AS n,testo "
                    "FROM pagine WHERE nota_id=? ORDER BY numero_pagina",
                    (note["id"],))]
                print("PLUV-DIAG",note["anno"],note["nome_file"],
                      [(p["numero_pagina"],p["n"],"lutezio" in (p["testo"] or "").casefold(),
                        "registro" in (p["testo"] or "").casefold())
                       for p in pages],flush=True)
                for p in pages:
                    raw=" ".join(str(p["testo"] or "").split())
                    pos=raw.casefold().find("registro")
                    print("PLUV-PAGE",p["numero_pagina"],"START",raw[:175],
                          "REGISTRO",raw[max(0,pos-110):pos+200] if pos>=0 else "-",
                          flush=True)

    def test_wegovy_sei_aic_raggiungono_sintesi(self):
        question=("Quante confezioni di WEGOVY sono presenti "
                  "nell'articolo 1 della determina 23A02767? "
                  "Riporta tutti gli AIC, distinguendo le diverse "
                  "confezioni da 2,4 mg.")
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            result,requests=run_without_provider(
                db,question,"Nell'articolo 1 sono presenti 5 confezioni.")
        self.assertEqual(len(requests),2)
        payload=requests[0][1]
        ids={x for row in payload["evidenze"]
             for x in row.get("aic_trovati_nel_testo",[])}
        self.assertEqual(len(ids),6)
        self.assertIn("049883111/E",ids)
        self.assertEqual(result["aic_mancanti_rispetto_al_testo"],6)
        self.assertTrue(result["revisione_completezza_llm"])
        self.assertTrue(result["contesto_integrale_completo"])
        self.assertIn("049883111/E",result["risposta"])
        self.assertIn("6",result["risposta"])


if __name__=="__main__":
    unittest.main()
