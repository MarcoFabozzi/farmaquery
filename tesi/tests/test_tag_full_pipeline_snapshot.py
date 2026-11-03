"""Test completi del percorso TAG su snapshot reale, senza servizi LLM.

Eseguono recupero, raggruppamento LOTUS simulato, sintesi e controllo finale.
I valori di fonte NON sono incorporati nel codice dell'applicazione.
"""
from contextlib import closing
import json
import re
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
        first=("Medicinale: EVRYSDI — SMA, Federico II, p.2.\n"
               "Medicinale: AGAMREE — Duchenne, Federico II, p.2.\n"
               "Medicinale: DUVYZAT — Duchenne, Federico II, p.2.\n"
               "Medicinale: ZILBRYSQ — miastenia, Federico II, p.2.\n"
               "Medicinale: VYVGART — miastenia, Federico II, p.3.\n"
               "Medicinale: SOLIRIS — miastenia gravis, "
               "Federico II, p.4.\n*Nota: ULTOMIRIS va verificato.")
        missing=missing_category_candidates(first,compact)
        self.assertTrue(any("ULTOMIRIS" in
                            c["documento_e_medicinale_candidato"]
                            for c in missing))
        def confirmed_omission(payload):
            notes=payload["documenti_candidati_non_elencati"]
            note=next(d for d in notes if
                      d["medicinale_candidato"].upper()=="ULTOMIRIS")
            page3=next(p["estratto"] for p in note["passaggi"]
                       if p["pagina"]==3)
            indication=re.search(r"miastenia gravis.{0,35}",page3,re.I)
            center=re.search(r"FEDERICO\s+II.{0,20}",page3,re.I|re.S)
            self.assertIsNotNone(indication)
            self.assertIsNotNone(center)
            return json.dumps({"nuove_voci":[{
                "confermato":True,
                "medicinale":"ULTOMIRIS",
                "patologia":"Miastenia gravis generalizzata",
                "indicazione":"Trattamento di MGg per l'indicazione della nota",
                "pagina_indicazione":3,
                "pagina_centro":3,
                "citazione_indicazione":indication.group(),
                "citazione_centro":center.group(),
            }]},ensure_ascii=False)

        # Questa regressione isola la revisione di UN documento omesso.
        # Il richiamo ampliato del corpus non deve aggiungere chiamate
        # al mock di questo scenario puntuale.
        expected={"ULTOMIRIS","EVRYSDI","AGAMREE","DUVYZAT",
                  "ZILBRYSQ","VYVGART","SOLIRIS"}
        subset=[row for row in candidates if any(
            "farmaco candidato: "+name.casefold() in row["testo"].casefold()
            for name in expected)]
        self.assertEqual(len(subset),7)
        with patch.object(engine,"evidence_candidates",return_value=subset):
            result,calls=self._run(question,[
                lambda payload:first,
                confirmed_omission
            ])
        self.assertEqual(len(calls),2)
        self.assertTrue(result["revisione_categoria_llm"])
        review_doc=next(d for d in calls[1]["documenti_candidati_non_elencati"]
                        if d["medicinale_candidato"]=="ULTOMIRIS")
        page3=next(p["estratto"] for p in review_doc["passaggi"]
                   if p["pagina"]==3)
        self.assertGreater(len(page3),900)
        self.assertIn("FEDERICO",page3.upper())
        self.assertEqual(result["chiamate_llm_stimate"],6)
        self.assertIn("Medicinale: ULTOMIRIS",result["risposta"])
        self.assertIn("Medicinale: SOLIRIS",result["risposta"])
        self.assertLess(result["risposta"].index("Medicinale: ULTOMIRIS"),
                        result["risposta"].index("*Nota:"))
        self.assertEqual(result["statistiche_revisione_categoria"]["chiamate"],1)
        self.assertTrue(any(x["medicinale"]=="ULTOMIRIS"
                            and x["esito"]=="accettato"
                            for x in result["diagnostica_revisione_categoria"]))
        self.assertTrue(any("ULTOMIRIS" in c for c in
                            result["candidati_categoria_da_ricontrollare"]))

    def test_ultomiris_stesso_snapshot_ancora_centro_esteso(self):
        # Il PDF originale usa una denominazione ospedaliera estesa:
        # una citazione abbreviata del LLM non equivale a fonte assente.
        from tesi.sintesi_tag import (
            compact_category_evidence,expand_review_pages,_candidate_short_name)
        from tesi.revisione_categoria import verified_additions
        q=("Quali medicinali per malattie neuromuscolari prevedono "
           "la prescrizione presso l'AOU Federico II?")
        with closing(sqlite3.connect(self.dbfile)) as db:
            db.row_factory=sqlite3.Row
            docs=compact_category_evidence(
                engine.evidence_candidates(db,q,max_rows=22))
            expanded=expand_review_pages(db,q,"Nessun elenco.",docs)
        note=next(d for d in expanded
                  if _candidate_short_name(d)=="ULTOMIRIS")
        page3=next(p["estratto"] for p in note["passaggi"]
                   if p["pagina"]==3)
        self.assertIn("FEDERICO II",page3.upper())
        self.assertIn("MIASTENIA",page3.upper())
        proposal={"nuove_voci":[{
            "confermato":True,
            "medicinale":"ULTOMIRIS",
            "patologia":"Miastenia gravis",
            "indicazione":"Miastenia gravis generalizzata refrattaria",
            "pagina_indicazione":3,"pagina_centro":3,
            "citazione_indicazione":
                "Trattamento della miastenia gravis generalizzata",
            "citazione_centro":"AOU Federico II, Napoli"
        }]}
        audit=[]
        additions=verified_additions(
            json.dumps(proposal,ensure_ascii=False),[note],q,
            _candidate_short_name,diagnostics=audit)
        self.assertEqual(len(additions),1,audit)
        self.assertEqual(audit[-1]["esito"],"accettato_con_ancore")
        self.assertIn("pagina 3",additions[0])

    def test_sql_standard_legge_le_note_con_query_generata(self):
        # Verifica soltanto l'accessibilità delle righe con una SELECT.
        # Il motore standard non recupera le note escluse né ripete query.
        query=(
            "SELECT DISTINCT n.id AS nota_id,p.numero_pagina,"
            "n.nome_file,n.farmaco_candidato AS medicinale,p.testo "
            "FROM note AS n JOIN pagine AS p ON p.nota_id=n.id "
            "WHERE EXISTS(SELECT 1 FROM pagine AS i "
            "WHERE i.nota_id=n.id AND "
            "(i.testo LIKE '%miastenia%' OR i.testo LIKE '%spinale%' "
            "OR i.testo LIKE '%distrofia%' OR i.testo LIKE '%muscolare%')) "
            "AND EXISTS(SELECT 1 FROM pagine AS c "
            "WHERE c.nota_id=n.id AND c.testo LIKE '%Federico II%') "
            "LIMIT 80"
        )
        with closing(sqlite3.connect(self.dbfile)) as db:
            db.row_factory=sqlite3.Row
            validated=engine.validate_sql(query)
            rows,truncated=engine._execute_generated_select(db,validated)
        self.assertTrue(rows)
        self.assertIsInstance(truncated,bool)
        self.assertTrue(all("nota_id" in r for r in rows))

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
