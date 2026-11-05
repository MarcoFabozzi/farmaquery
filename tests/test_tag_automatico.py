"""Verifiche offline della terza pipeline: nessuna API LLM coinvolta."""
from __future__ import annotations

import sqlite3
import sys
import types
import pandas as pd  # Import prima delle patch ai moduli, evita reimport numpy nei test.
import unittest
from unittest.mock import patch

from tesi import tag_automatico as auto


class TAGAutomaticoTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE note(
                id TEXT PRIMARY KEY, nome_file TEXT,
                farmaco_candidato TEXT, indicazione_candidata TEXT,
                percorso_zip TEXT, archivio_url TEXT
            );
            CREATE TABLE pagine(
                nota_id TEXT, numero_pagina INTEGER, testo TEXT, metodo TEXT
            );
            INSERT INTO note VALUES
              ('n1','nota1.pdf','MED-A','categoria clinica A','nota1.pdf','https://example.org/a.zip'),
              ('n2','nota2.pdf','MED-B','categoria clinica B','nota2.pdf','https://example.org/b.zip');
            INSERT INTO pagine VALUES
              ('n1',1,'Menzione Federico II e descrizione documento A','TESTO'),
              ('n1',2,'Indicazione terapeutica del documento A','TESTO'),
              ('n2',1,'Menzione Federico II e descrizione documento B','TESTO');
        """)
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    @staticmethod
    def candidate_sql():
        return ("SELECT DISTINCT n.id AS nota_id FROM note n "
                "JOIN pagine p ON p.nota_id=n.id "
                "WHERE p.testo LIKE '%Federico%'")

    def test_retrieval_includes_every_page_of_candidate_notes(self):
        sql = self.candidate_sql()
        records, partial = auto._run_generated_select(self.db, sql)
        self.assertEqual(len(records), 2)
        self.assertFalse(partial)
        notes, page_partial = auto._note_candidates(self.db, records)
        self.assertFalse(page_partial)
        self.assertEqual(len(notes), 2)
        self.assertIn("[pagina 2]", notes[0]["testo_selezione"])
        self.assertIn("#p2", " ".join(notes[0]["fonti"]))
        groups, members = auto._lotus_plan(notes)
        self.assertEqual(sum(map(len, members.values())), 2)
        self.assertTrue(groups)

    def test_no_manual_clinical_expansion_in_prompt(self):
        self.assertNotIn("miastenia", auto.SQL_PROMPT.casefold())
        self.assertNotIn("neuromuscolar", auto.SQL_PROMPT.casefold())
        self.assertNotIn("distrofia", auto.SQL_PROMPT.casefold())

    def test_llm_sql_then_lotus_then_answer(self):
        messages = []
        def mock_ask(model,system,payload,**kwargs):
            messages.append(system)
            if system == auto.SQL_PROMPT:
                return self.candidate_sql(), {"token_input":2,"token_output":3,"costo_usd":0}
            return "Due note consultate, citando i documenti.", {"token_input":5,"token_output":6,"costo_usd":0}
        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_: None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_, **__: types.SimpleNamespace()
        with patch.dict(sys.modules, {"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(self.db,"Documenti del Federico II", "modello-fittizio")
        self.assertEqual(result["versione_tag"],"automatico-v1")
        self.assertEqual(result["righe_sql"],2)
        self.assertEqual(result["righe_recuperate"],2)
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(len(messages),2)
        self.assertTrue(any("#p2" in f for f in result["fonti"]))


    def test_scalar_attribute_sql_is_selected_by_lotus(self):
        """Regressione D01: il valore puo' essere senza nome nella SELECT."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni(aic TEXT, nome TEXT, principio_attivo TEXT);
            CREATE TABLE ema_medicinali(ema_id TEXT, nome TEXT, principio_attivo TEXT);
            INSERT INTO aifa_confezioni VALUES ('001','BEYONTTRA','sostanza-demo');
            INSERT INTO ema_medicinali VALUES ('EM-01','BEYONTTRA','sostanza-demo');
        """)
        self.db.execute("PRAGMA query_only=ON")
        sql = ("SELECT principio_attivo FROM aifa_confezioni "
               "WHERE nome LIKE '%BEYONTTRA%' "
               "UNION SELECT principio_attivo FROM ema_medicinali "
               "WHERE nome LIKE '%BEYONTTRA%'")
        seen = []
        called_system_prompts = []
        def mock_ask(model, system, payload, **kwargs):
            called_system_prompts.append(system)
            if system == auto.SQL_PROMPT:
                return sql, {"token_input":1,"token_output":1,"costo_usd":0}
            return "Principio attivo: sostanza-demo.", {
                "token_input":1,"token_output":1,"costo_usd":0
            }
        def fake_sem_filter(frame, instruction):
            seen.append(instruction)
            # Simula un filtro che passa i campi utili solo se trattati come
            # attributi tabellari, anziche' richiedere prove cliniche.
            if "RISULTATI SQL STRUTTURATI" in instruction and \
                    "sostanza-demo" in frame.iloc[0]["testo"]:
                return frame
            return frame.iloc[0:0]
        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_:None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",side_effect=fake_sem_filter):
            result=auto.automatic_tag(
                self.db,"Qual e' il principio attivo del medicinale BEYONTTRA?",
                "modello-fittizio"
            )
        self.assertEqual(result["stato"],"OK")
        self.assertIn("sostanza-demo",result["risposta"])
        self.assertEqual(result["righe_sql"],1)
        self.assertEqual(result["righe_selezionate_lotus"],1)
        self.assertIn("attributo",seen[0])
        self.assertEqual(called_system_prompts[-1],auto.TABULAR_ANSWER_PROMPT)

    def test_tabular_prompt_preserves_llm_sql_retrieval(self):
        self.assertIn("denominazione del medicinale (nome)",auto.SQL_PROMPT)
        self.assertIn("valore non vuoto",auto.TABULAR_SEMANTIC_PROMPT)
        self.assertNotIn("miastenia",auto.TABULAR_SEMANTIC_PROMPT.casefold())


    def test_identifier_provenance_is_grounded(self):
        """Il fallback trova solo codici realmente presenti nello SQLite."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni (
                aic TEXT, nome TEXT, principio_attivo TEXT
            );
            CREATE TABLE ema_medicinali (
                ema_id TEXT, nome TEXT, principio_attivo TEXT,
                url_ema TEXT
            );
            INSERT INTO aifa_confezioni VALUES
              ('050000111','BEYONTTRA','ACORAMIDIS'),
              ('050000222','BEYONTTRA','ACORAMIDIS');
            INSERT INTO ema_medicinali VALUES
              ('EMEA/H/C/006333','Beyonttra',
               'acoramidis hydrochloride','https://example.org/ema');
        """)
        self.db.execute("PRAGMA query_only=ON")
        rows = [
            {"nome":"BEYONTTRA","principio_attivo":"ACORAMIDIS",
             "aic":None,"ema_id":None,"fonte_origine":"AIFA"},
            {"nome":"Beyonttra","principio_attivo":"acoramidis hydrochloride",
             "aic":None,"ema_id":"EMEA/H/C/006333","fonte_origine":"EMA"},
        ]
        result = auto._tabular_candidates(self.db,rows)
        self.assertEqual(len(result),2)
        self.assertTrue(any("050000111" in src for src in result[0]["fonti"]))
        self.assertTrue(any("050000222" in src for src in result[0]["fonti"]))
        self.assertFalse(any("EMEA/" in src for src in result[0]["fonti"]))
        self.assertTrue(any("EMEA/H/C/006333" in src for src in result[1]["fonti"]))
        unknown = auto._verify_tabular_identifiers(
            self.db,{"nome":"BEYONTTRA",
                     "principio_attivo":"sostanza non presente",
                     "fonte_origine":"AIFA"})
        self.assertEqual(unknown,[])

    def test_sql_prompt_preserves_real_identifiers(self):
        self.assertIn("VERO aic", auto.SQL_PROMPT)
        self.assertIn("VERO ema_id", auto.SQL_PROMPT)
        self.assertIn("fonte_origine", auto.SQL_PROMPT)
        self.assertIn("NON richiedere numeri", auto.TABULAR_ANSWER_PROMPT)
        self.assertIn("differenza di denominazione", auto.TABULAR_ANSWER_PROMPT)
        self.assertIn("senza evidenze", auto.TABULAR_ANSWER_PROMPT)
        self.assertNotIn("BEYONTTRA", auto.TABULAR_ANSWER_PROMPT)
        self.assertIn("Cita nome del documento e pagina", auto.ANSWER_PROMPT)


    def test_union_different_identifiers_not_mislabelled_as_aic(self):
        """D03: UNION ALL deve conservare l'identità EMA, non un falso AIC."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni (
                aic TEXT, nome TEXT, principio_attivo TEXT
            );
            CREATE TABLE ema_medicinali (
                ema_id TEXT, nome TEXT, principio_attivo TEXT, url_ema TEXT
            );
            INSERT INTO aifa_confezioni VALUES
              ('050231012','VABYSMO','FARICIMAB'),
              ('050231024','VABYSMO','FARICIMAB');
            INSERT INTO ema_medicinali VALUES
              ('EMEA/H/C/005642','Vabysmo','Faricimab',
               'https://example.org/vabysmo');
        """)
        self.db.execute("PRAGMA query_only=ON")
        generated = (
            "SELECT aic, nome, principio_attivo FROM aifa_confezioni "
            "WHERE nome LIKE '%VABYSMO%' UNION ALL "
            "SELECT ema_id, nome, principio_attivo FROM ema_medicinali "
            "WHERE nome LIKE '%VABYSMO%'"
        )
        rows, partial = auto._run_generated_select(self.db, generated)
        self.assertFalse(partial)
        self.assertEqual(len(rows),3)
        candidates = auto._tabular_candidates(self.db,rows)
        self.assertEqual(sum(bool(x["provenienza_sql_riconciliata"]) for x in candidates),1)
        ema_row = next(x for x in candidates if "EMEA/H/C/005642" in x["testo"])
        self.assertIn('"aic": null',ema_row["testo"])
        self.assertIn('"ema_id": "EMEA/H/C/005642"',ema_row["testo"])
        self.assertEqual(ema_row["fonti"],[
            "EMA EMEA/H/C/005642 | https://example.org/vabysmo"
        ])
        self.assertFalse(any("AIFA AIC EMEA" in src
                             for item in candidates for src in item["fonti"]))

    def test_elrexfio_exact_name_case_insensitive(self):
        """D04: non considerare assente un medicinale per le maiuscole."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE ema_medicinali (
                ema_id TEXT, nome TEXT, data_decisione_ue TEXT
            );
            INSERT INTO ema_medicinali VALUES
              ('EMEA/H/C/005908','Elrexfio','2023-12-07');
        """)
        self.db.execute("PRAGMA query_only=ON")
        generated = ("SELECT ema_id,nome,data_decisione_ue "
                     "FROM ema_medicinali WHERE nome = 'ELREXFIO'")
        original, _ = auto._run_generated_select(self.db,generated)
        self.assertEqual(original,[])
        fixed = auto._normalize_exact_name_comparisons(generated)
        self.assertIn("COLLATE NOCASE",fixed)
        self.assertEqual(fixed,auto._normalize_exact_name_comparisons(fixed))
        records, partial = auto._run_generated_select(self.db,fixed)
        self.assertEqual(len(records),1)
        self.assertFalse(partial)
        self.assertEqual(records[0]["data_decisione_ue"],"2023-12-07")


    def test_full_pipeline_normalizes_exact_name_and_reports_revision(self):
        """D04/D05: query prodotta senza NOCASE, recupero completo e audit."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE ema_medicinali(
                ema_id TEXT,nome TEXT,data_decisione_ue TEXT,url_ema TEXT
            );
            INSERT INTO ema_medicinali VALUES
              ('EMA-DEMO','Elrexfio','data-snapshot-demo','https://example.org/ema');
        """)
        self.db.execute("PRAGMA query_only=ON")
        original = (
            "SELECT ema_id,nome,data_decisione_ue "
            "FROM ema_medicinali WHERE nome = 'ELREXFIO'"
        )
        seen = []
        def mock_ask(model,system,payload,**kwargs):
            seen.append(system)
            if system == auto.SQL_PROMPT:
                return original, {"token_input":1,"token_output":1,"costo_usd":0}
            return "Data: data-snapshot-demo", {
                "token_input":1,"token_output":1,"costo_usd":0
            }
        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_:None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(
                self.db,"Data della decisione UE per ELREXFIO",
                "modello-fittizio"
            )
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["righe_sql"],1)
        self.assertIn("data-snapshot-demo",result["risposta"])
        self.assertIn("COLLATE NOCASE",result["sql"])
        self.assertNotIn("COLLATE NOCASE",result["sql_originale_llm"])
        self.assertTrue(result["sql_normalizzato_nome"])
        self.assertEqual(result["tag_auto_revision"],auto.TAG_AUTO_REVISION)
        self.assertEqual(len(seen),2)

    def test_full_pipeline_audits_misaligned_ema_id(self):
        """D03: controlla che l'etichetta falsa AIC non passi a LOTUS."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni(
                aic TEXT,nome TEXT,principio_attivo TEXT
            );
            CREATE TABLE ema_medicinali(
                ema_id TEXT,nome TEXT,principio_attivo TEXT,url_ema TEXT
            );
            INSERT INTO aifa_confezioni VALUES
              ('AIC-DEMO','Medicinale-X','Principio-A');
            INSERT INTO ema_medicinali VALUES
              ('EMA-DEMO','Medicinale-X','Principio-A','https://example.org/ema');
        """)
        self.db.execute("PRAGMA query_only=ON")
        generated=(
            "SELECT aic,nome,principio_attivo FROM aifa_confezioni "
            "WHERE nome LIKE '%Medicinale-X%' UNION ALL "
            "SELECT ema_id,nome,principio_attivo FROM ema_medicinali "
            "WHERE nome LIKE '%Medicinale-X%'"
        )
        def mock_ask(model,system,payload,**kwargs):
            if system == auto.SQL_PROMPT:
                return generated,{"token_input":1,"token_output":1,"costo_usd":0}
            return "Principio-A",{"token_input":1,"token_output":1,"costo_usd":0}
        fake_lotus=types.ModuleType("lotus")
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        fake_models=types.ModuleType("lotus.models")
        fake_models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(
                self.db,"Principio attivo di Medicinale-X","modello-fittizio"
            )
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["identificativi_sql_riconciliati"],1)
        self.assertEqual(result["righe_sql"],2)
        self.assertTrue(any(src.startswith("EMA EMA-DEMO")
                            for src in result["fonti"]))
        self.assertFalse(any("AIFA AIC EMA-DEMO" in src
                             for src in result["fonti"]))


if __name__ == "__main__":
    unittest.main()
