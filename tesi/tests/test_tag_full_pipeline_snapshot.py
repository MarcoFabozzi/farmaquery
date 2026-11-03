"""Test completi del percorso TAG su snapshot reale, senza servizi LLM.

Eseguono recupero, raggruppamento LOTUS simulato, sintesi e controllo finale.
I valori di fonte NON sono incorporati nel codice dell'applicazione.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from tesi.prepara_snapshot_online import ROOT,build_snapshot
from tesi import pilota_tag_vs_sql as engine


class SelectedGroups:
    def __init__(self, rows):
        self.rows=rows
    def head(self, n):
        return self
    def __getitem__(self, key):
        return self
    def to_dict(self, kind):
        return [{"chiave":r["chiave"]} for r in self.rows]


class TagFullPipelineSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        cls.dbfile=Path(cls.folder.name)/"snapshot.sqlite"
        cls.manifest=Path(cls.folder.name)/"manifest.json"
        build_snapshot(ROOT,cls.dbfile,cls.manifest)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def _run(self, question, responses):
        fake_pd=types.ModuleType("pandas")
        fake_pd.DataFrame=lambda entries: entries
        fake_lotus=types.ModuleType("lotus")
        fake_models=types.ModuleType("lotus.models")
        class FakeLM:
            def __init__(self,*args,**kwargs):
                self.stats=types.SimpleNamespace(physical_usage=types.SimpleNamespace(
                    prompt_tokens=12,completion_tokens=5,total_cost=0.0))
        fake_models.LM=FakeLM
        fake_lotus.models=fake_models
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **kw: None)
        captured=[]
        def fake_ask(model,sys_prompt,payload,**kwargs):
            captured.append(payload)
            return responses[len(captured)-1](payload),{
                "token_input":30,"token_output":15,"costo_usd":0.0}
        with patch.dict(sys.modules,{"pandas":fake_pd,"lotus":fake_lotus,
                                     "lotus.models":fake_models}),\
             patch.object(engine,"sem_filter_controlled",
                          side_effect=lambda frame,prompt: SelectedGroups(frame)),\
             patch.object(engine,"ask",side_effect=fake_ask):
            with closing(sqlite3.connect(self.dbfile)) as db:
                db.row_factory=sqlite3.Row
                result=engine.tag(db,question,"mock-model")
        return result,captured



    def test_categorie_ultomiris_raggiunge_risposta_verificata(self):
        # Verifica il caso reale: la fonte e il centro sono nell'evidenza,
        # ma la prima sintesi può dimenticare il documento.
        question=("Quali medicinali citati nelle note regionali della "
                  "Campania per malattie neuromuscolari prevedono la "
                  "prescrizione presso l'AOU Federico II? Per ciascuno "
                  "indica medicinale, patologia, indicazione e pagina "
                  "della nota.")
        from tesi.sintesi_tag import (compact_category_evidence,
                                      missing_category_candidates)
        with closing(sqlite3.connect(self.dbfile)) as db:
            db.row_factory=sqlite3.Row
            candidates=engine.evidence_candidates(db,question,max_rows=22)
        compact=compact_category_evidence(candidates)
        source=[c for c in compact if "ULTOMIRIS" in
                c["documento_e_medicinale_candidato"].upper()]
        self.assertEqual(len(source),1)
        self.assertTrue(any(p["pagina"]==3 and "miastenia" in
                            p["estratto"].casefold() and "federico" in
                            p["estratto"].casefold()
                            for p in source[0]["passaggi"]))
        first=("Medicinale: SOLIRIS — miastenia gravis, "
               "Federico II, p.4.\\nNota: ULTOMIRIS va verificato.")
        missing=missing_category_candidates(first,compact)
        self.assertTrue(any("ULTOMIRIS" in
                            c["documento_e_medicinale_candidato"]
                            for c in missing))
        result,calls=self._run(question,[
            lambda payload:first,
            lambda payload:("Medicinale: SOLIRIS — miastenia gravis, "
                            "Federico II, p.4.\\n"
                            "Medicinale: ULTOMIRIS — miastenia gravis "
                            "generalizzata refrattaria, Federico II, "
                            "pagina 3, nota PG/2024/0427490.")
        ])
        self.assertEqual(len(calls),2)
        self.assertTrue(result["revisione_categoria_llm"])
        self.assertEqual(result["chiamate_llm_stimate"],6)
        self.assertIn("Medicinale: ULTOMIRIS",result["risposta"])
        self.assertIn("Medicinale: SOLIRIS",result["risposta"])
        self.assertTrue(any("ULTOMIRIS" in c for c in
                            result["candidati_categoria_da_ricontrollare"]))

    def test_wegovy_non_pubblica_cinque_come_elenco_completo(self):
        question=("Quante confezioni di WEGOVY sono presenti nell'articolo 1 "
                  "della determina 23A02767? Riporta tutti gli AIC, "
                  "distinguendo le diverse confezioni da 2,4 mg.")
        result,calls=self._run(question,[
            lambda p:"L'articolo 1 contiene cinque AIC: 049883061/E, "
                     "049883073/E, 049883085/E, 049883097/E, 049883109/E.",
            lambda p:"L'atto contiene sei AIC: "+
                      ", ".join(p["identificativi_aic_rilevati_dal_testo"])
        ])
        self.assertEqual(len(calls),2,"La sintesi con 5 AIC deve attivare revisione")
        self.assertEqual(result["aic_nel_testo_integrale"],6)
        self.assertEqual(result["aic_mancanti_rispetto_al_testo"],0)
        self.assertTrue(result["contesto_integrale_completo"])
        self.assertEqual(result["verifica_contesto"],"integrale")
        self.assertIn("049883111/E",result["risposta"])
        self.assertTrue(result["revisione_completezza_llm"])
        self.assertEqual(result["versione_tag"],"verifica-integrale-v2")
        self.assertTrue(all(x["chiave"].startswith("GU:INTEGRALE:")
                            for x in calls[0]["evidenze"]))

    def test_amvuttra_usa_pagina_due_completa_e_rivede_astensione(self):
        question=("Quali sono tutti i centri elencati nella Tabella 1, pagina 2, "
                  "della nota AMVUTTRA 0634617/2026 per ATTR-CM? "
                  "Riporta esclusivamente questa indicazione.")
        result,calls=self._run(question,[
            lambda p:"Non documentato nello snapshot.",
            lambda p:"È presente la pagina completa del documento: "+
                     p["fonti_integrali"][0]["fonte"]
        ])
        self.assertEqual(len(calls),2,"L'astensione erronea richiede revisione")
        self.assertTrue(result["contesto_integrale_completo"])
        self.assertTrue(result["revisione_completezza_llm"])
        self.assertEqual(result["verifica_contesto"],"integrale")
        self.assertTrue(any("#p2" in e["fonte"] for e in calls[0]["evidenze"]))
        source=" ".join(x["testo"] for x in calls[0]["evidenze"]).casefold()
        for name in ("ruggi","cardarelli","federico"):
            self.assertIn(name,source)
        self.assertNotIn("almeno una pagina della fonte è stata troncata",
                         result["risposta"])


if __name__=="__main__":
    unittest.main()
