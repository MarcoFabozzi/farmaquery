"""Regressioni offline per le protezioni v2: nessun accesso LLM reale."""
import sqlite3
import unittest
from unittest.mock import patch

from tesi.sql_sicurezza_risposta import (
    motivo_select_non_probante, domanda_volume_operativo,
    sintesi_contraddittoria,
)
from tesi.sql_autocorrezione import sql_autocorrezione
from tesi import pilota_tag_vs_sql as p

USAGE = {"token_input": 10, "token_output": 5, "costo_usd": 0.001}


class SQLControlliV2Test(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE note (id TEXT, anno INT, protocollo_candidato TEXT)"
        )
        self.db.execute(
            "INSERT INTO note VALUES ('a', 2026, 'Protocollo 123')"
        )

    def tearDown(self):
        self.db.close()

    def run_sql(self, question, responses):
        with patch.object(p, "ask", side_effect=[(r, USAGE) for r in responses]) as llm:
            result = sql_autocorrezione(self.db, question, "mock-model")
        return result, llm.call_count

    def test_select_without_data_source_is_not_evidence(self):
        self.assertEqual(
            motivo_select_non_probante("SELECT NULL WHERE 1 = 0"),
            "SELECT_SENZA_TABELLE",
        )
        result, calls = self.run_sql(
            "Quale dato economico?", ["SELECT NULL WHERE 1 = 0"]
        )
        self.assertEqual(result["stato"], "SQL_NON_PROBANTE")
        self.assertEqual(calls, 1)
        self.assertEqual(result["correzioni_sql"], 0)

    def test_contradictory_constant_predicate_is_not_evidence(self):
        self.assertEqual(
            motivo_select_non_probante("SELECT id FROM note WHERE 1=0"),
            "PREDICATO_SEMPRE_FALSO",
        )
        self.assertEqual(
            motivo_select_non_probante("SELECT id FROM note LIMIT 0"),
            "LIMIT_ZERO",
        )
        self.assertIsNone(
            motivo_select_non_probante("SELECT id FROM note WHERE anno = 2025"),
        )

    def test_no_false_zero_for_actual_patient_counts(self):
        question = "Quanti pazienti sono stati realmente trattati in ospedale?"
        self.assertTrue(domanda_volume_operativo(question))
        result, calls = self.run_sql(
            question, ["SELECT COUNT(*) AS conteggio FROM note"]
        )
        self.assertEqual(result["stato"], "DATO_OPERATIVO_NON_VERIFICABILE")
        self.assertNotIn("0 pazienti", result["risposta"])
        self.assertEqual(calls, 1)
        self.assertEqual(result["righe_sql"], 1)

    def test_no_false_zero_for_real_administrations(self):
        question = "Quante somministrazioni sono state effettuate nel 2025?"
        self.assertTrue(domanda_volume_operativo(question))
        result, calls = self.run_sql(
            question, ["SELECT COUNT(*) AS conteggio FROM note"]
        )
        self.assertEqual(result["stato"], "DATO_OPERATIVO_NON_VERIFICABILE")
        self.assertEqual(calls, 1)

    def test_does_not_block_package_counts(self):
        self.assertFalse(domanda_volume_operativo(
            "Quante confezioni sono presenti nella tabella AIFA?"
        ))
        result, calls = self.run_sql(
            "Quante note sono presenti?",
            ["SELECT COUNT(*) AS totale FROM note", "Risulta una nota."],
        )
        self.assertEqual(result["stato"], "OK")
        self.assertEqual(calls, 2)

    def test_synthesis_cannot_deny_retrieved_relevant_rows(self):
        rows = [{"nota_id": "a", "anno": 2026, "protocollo_candidato": "123"}]
        self.assertTrue(sintesi_contraddittoria(
            rows, "Le informazioni relative a quali note regionali "
                  "menzionano il farmaco non sono documentate nei risultati SQL."
        ))
        self.assertFalse(sintesi_contraddittoria(
            rows, "Le pagine non sono specificate nelle righe."
        ))
        result, calls = self.run_sql(
            "Quali note?", [
                "SELECT id AS nota_id, anno, protocollo_candidato FROM note",
                "Le informazioni relative a quali note regionali menzionano "
                "il farmaco non sono documentate nei risultati SQL.",
            ],
        )
        self.assertEqual(result["stato"], "SINTESI_INCOERENTE")
        self.assertEqual(calls, 2)
        self.assertIn("123", result["risposta"])
        self.assertIn("risposta_originale_llm", result)
        self.assertNotIn("non sono documentate nei risultati SQL", result["risposta"])

    def test_genuine_empty_result_is_not_retried(self):
        result, calls = self.run_sql(
            "Quali note riguardano un farmaco inesistente?",
            ["SELECT id FROM note WHERE anno=1901"],
        )
        self.assertEqual(result["stato"], "NESSUNA_EVIDENZA")
        self.assertEqual(calls, 1)
        self.assertEqual(result["sql_tentativi"], 1)


if __name__ == "__main__":
    unittest.main()
