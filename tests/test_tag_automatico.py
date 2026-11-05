"""Verifiche offline della terza pipeline: nessuna API LLM coinvolta."""
from __future__ import annotations

import sqlite3
import sys
import types
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


if __name__ == "__main__":
    unittest.main()
