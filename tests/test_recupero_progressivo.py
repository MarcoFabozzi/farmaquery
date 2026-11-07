"""Test offline: fallback zero righe, nessun lessico clinico nel codice."""
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

from tesi.recupero_progressivo import (
    normalize_document_note_id, propose_empty_category_fallback,
)
from tesi import tag_automatico as auto


QUESTION = (
    "Quali medicinali citati nelle note regionali della Campania per "
    "malattie neuromuscolari prevedono la prescrizione presso l'AOU "
    "Federico II? Indica medicinale, patologia, documento e pagina."
)
ORIGINAL_SQL = (
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "n.indicazione_candidata AS indicazione, n.id AS documento_id, "
    "p.numero_pagina AS pagina, c.centro AS struttura "
    "FROM note AS n JOIN pagine AS p ON n.id = p.nota_id "
    "JOIN nota_centro_documentato AS c "
    "ON n.id = c.nota_id AND p.numero_pagina = c.numero_pagina "
    "WHERE (c.centro LIKE '%Federico II%' COLLATE NOCASE) "
    "AND (p.testo LIKE '%neuromuscolari%' COLLATE NOCASE "
    "OR n.indicazione_candidata LIKE '%neuromuscolari%' COLLATE NOCASE)"
)


class ProgressiveRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE note(
                id TEXT PRIMARY KEY, nome_file TEXT, anno INTEGER,
                protocollo_candidato TEXT, data_candidata TEXT,
                farmaco_candidato TEXT, indicazione_candidata TEXT,
                percorso_zip TEXT, archivio_url TEXT
            );
            CREATE TABLE pagine(
                nota_id TEXT, numero_pagina INTEGER, testo TEXT, metodo TEXT
            );
            CREATE TABLE nota_centro_documentato(
                nota_id TEXT, numero_pagina INTEGER, centro TEXT
            );
            INSERT INTO note VALUES
                ('a','A.pdf',2026,NULL,NULL,'FARMACO-A',
                 'Disturbo documentato A','A.pdf','https://example.org/a.zip'),
                ('b','B.pdf',2025,NULL,NULL,'FARMACO-B',
                 'Disturbo documentato B','B.pdf','https://example.org/b.zip');
            INSERT INTO pagine VALUES
                ('a',1,'Farmaco A, condizione A','TESTO'),
                ('a',2,'Prescrizione presso AOU Federico II','TESTO'),
                ('b',1,'Altra struttura ospedaliera','TESTO');
        """)
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    def test_input_reale_fallback_senza_dizionari_e_senza_llm(self):
        initial, fixed = normalize_document_note_id(ORIGINAL_SQL)
        self.assertTrue(fixed)
        self.assertIn("AS nota_id", initial)
        rows, _ = auto._run_generated_select(self.db, auto.validate_sql(initial))
        self.assertEqual(rows, [])
        candidate, reason = propose_empty_category_fallback(initial, QUESTION)
        self.assertEqual(reason, "categoria_semantica_da_valutare_con_lotus")
        self.assertNotIn("neuromuscolari", candidate.casefold())
        fallback, _ = auto._run_generated_select(
            self.db, auto.validate_sql(candidate))
        self.assertEqual([r["nota_id"] for r in fallback], ["a"])
        docs, partial = auto._note_candidates(self.db, fallback)
        self.assertFalse(partial)
        self.assertEqual(len(docs), 1)
        self.assertIn("[pagina 2]", docs[0]["testo"])

    def test_non_allarga_se_esiste_una_condizione_oggettiva_aggiuntiva(self):
        for extra in [
            " AND n.anno=2026",
            " AND n.farmaco_candidato LIKE '%FARMACO-A%'",
            " AND c.centro LIKE '%Altro%'",
        ]:
            candidate, reason = propose_empty_category_fallback(
                ORIGINAL_SQL + extra, QUESTION)
            self.assertIsNone(candidate, reason)

    def test_non_allarga_categorie_senza_ancora_ospedaliera(self):
        candidate, _ = propose_empty_category_fallback(
            ORIGINAL_SQL.replace("%Federico II%", "%Ospedale Z%"),
            QUESTION)
        self.assertIsNone(candidate)
        candidate, _ = propose_empty_category_fallback(
            ORIGINAL_SQL.replace(
                "JOIN nota_centro_documentato AS c",
                "JOIN altra_tabella AS c"),
            QUESTION)
        self.assertIsNone(candidate)

    def test_non_allarga_sql_con_union_or_o_filtro_tabulare(self):
        for sql in [
            ORIGINAL_SQL + " UNION SELECT * FROM note",
            ORIGINAL_SQL.replace(" AND (p.testo", " OR (p.testo"),
            "SELECT nome, aic FROM aifa_confezioni WHERE nome='FARMACO-A'",
        ]:
            candidate, reason = propose_empty_category_fallback(sql, QUESTION)
            self.assertIsNone(candidate, reason)

    def test_no_fallback_when_initial_query_has_rows(self):
        sql = ("SELECT DISTINCT n.id AS nota_id FROM note n "
               "JOIN pagine p ON p.nota_id=n.id "
               "WHERE p.testo LIKE '%Federico II%'")
        self.assertEqual(normalize_document_note_id(sql), (sql, False))
        candidate, _ = propose_empty_category_fallback(sql, QUESTION)
        self.assertIsNone(candidate)
        rows, _ = auto._run_generated_select(self.db, auto.validate_sql(sql))
        self.assertEqual(len(rows), 1)

    def test_integrazione_con_audit_e_numero_chiamate_immutato(self):
        calls = []
        def mock_ask(model, system, payload, **kwargs):
            calls.append(system)
            if system == auto.SQL_PROMPT:
                return ORIGINAL_SQL, {
                    "token_input":1, "token_output":1, "costo_usd":0
                }
            return "Documento A esaminato.", {
                "token_input":1, "token_output":1, "costo_usd":0
            }

        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_: None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_, **__: types.SimpleNamespace()
        with patch.dict(sys.modules, {
                "lotus": fake_lotus, "lotus.models": fake_models}), \
             patch.object(auto, "ask", side_effect=mock_ask), \
             patch.object(auto, "sem_filter_controlled",
                          side_effect=lambda frame, instruction: frame):
            result = auto.automatic_tag(self.db, QUESTION, "modello-fittizio")
        self.assertTrue(result["recupero_progressivo_usato"])
        self.assertEqual(result["sql_tentativi"], 2)
        self.assertEqual(result["righe_sql_primo_tentativo"], 0)
        self.assertEqual(result["righe_sql"], 1)
        self.assertIn("nota_id", result["sql"])
        self.assertEqual(result["note_nell_indice"], 1)
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-07-r8-recupero-progressivo")
        self.assertEqual(len(calls), 2)  # SQL + sintesi; LOTUS simulato.


if __name__ == "__main__":
    unittest.main()
