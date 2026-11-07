"""Regressioni offline per recupero categoria/centro su pagine distinte.

Nessuna chiamata reale a Gemini. Database della tesi sempre sola lettura.
"""
import gzip
import json
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd  # Prima dei mock di sys.modules, come negli altri test.

from tesi import tag_automatico as auto
from tesi.recupero_progressivo import (
    normalize_document_note_id,
    propose_empty_crosspage_category_fallback,
)

QUESTION = (
    "Quali medicinali citati nelle note regionali della Campania per "
    "malattie neuromuscolari prevedono la prescrizione presso l'AOU "
    "Federico II? Per ciascuno indica medicinale, patologia, "
    "documento e pagina del centro prescrittore."
)
SQL = (
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "n.indicazione_candidata AS indicazione, "
    "n.id AS documento_id, NULL AS aic, NULL AS ema_id, "
    "p.numero_pagina FROM note AS n "
    "JOIN pagine AS p ON n.id = p.nota_id "
    "JOIN centri_candidati AS cc ON p.nota_id = cc.nota_id "
    "AND p.numero_pagina = cc.numero_pagina "
    "WHERE (cc.menzione LIKE '%Federico II%' COLLATE NOCASE "
    "OR p.testo LIKE '%Federico II%' COLLATE NOCASE) "
    "AND (n.indicazione_candidata LIKE '%neuromuscolar%' COLLATE NOCASE "
    "OR p.testo LIKE '%neuromuscolar%' COLLATE NOCASE)"
)


class CrossPageFallbackTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE note (
            id TEXT PRIMARY KEY,nome_file TEXT,anno INTEGER,
            protocollo_candidato TEXT,data_candidata TEXT,
            farmaco_candidato TEXT,indicazione_candidata TEXT,
            percorso_zip TEXT,archivio_url TEXT
          );
          CREATE TABLE pagine (
            nota_id TEXT,numero_pagina INTEGER,testo TEXT,metodo TEXT
          );
          CREATE TABLE centri_candidati (
            nota_id TEXT,numero_pagina INTEGER,menzione TEXT,stato TEXT
          );
          INSERT INTO note VALUES (
            'id-a','med-a.pdf',2026,NULL,NULL,'MED-A',
            'Patologia del nervo periferico','med-a.pdf','https://example.org/a.zip'
          );
          INSERT INTO pagine VALUES
            ('id-a',1,'MED-A: patologia del nervo periferico','TESTO'),
            ('id-a',2,'Centro prescrittore AOU Federico II','TESTO');
          INSERT INTO centri_candidati VALUES
            ('id-a',2,'AOU Federico II',NULL);
        """)
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    def test_riproduce_query_e_amplia_senza_dizionari(self):
        initial, changed = normalize_document_note_id(SQL)
        self.assertTrue(changed)
        before, _ = auto._run_generated_select(
            self.db, auto.validate_sql(initial))
        self.assertEqual(before, [])
        suggested, reason = propose_empty_crosspage_category_fallback(
            initial, QUESTION)
        self.assertEqual(reason,
                         "categoria_clinica_e_join_stessa_pagina_ampliati")
        self.assertIn("AS nota_id", suggested)
        self.assertIn("LIKE '%Federico%'", suggested)
        self.assertNotIn("neuromuscolar", suggested.casefold())
        after, partial = auto._run_generated_select(
            self.db, auto.validate_sql(suggested))
        self.assertFalse(partial)
        self.assertEqual([r["nota_id"] for r in after], ["id-a"])
        docs, truncated = auto._note_candidates(self.db, after)
        self.assertFalse(truncated)
        self.assertEqual(len(docs), 1)
        self.assertIn("[pagina 1]", docs[0]["testo"])
        self.assertIn("[pagina 2]", docs[0]["testo"])

    def test_rifiuta_vincoli_extra_o_joins_alterate(self):
        for altered in (
            SQL + " AND n.anno=2026",
            SQL.replace(
                "p.numero_pagina = cc.numero_pagina",
                "p.numero_pagina = cc.nota_id"),
            SQL.replace(
                "p.nota_id = cc.nota_id",
                "n.id = cc.numero_pagina"),
            SQL.replace("centri_candidati AS cc", "altro AS cc"),
            SQL.replace("JOIN centri_candidati AS cc",
                        "LEFT JOIN centri_candidati AS cc"),
            SQL + " LIMIT 10",
            SQL + " UNION SELECT NULL,NULL,NULL,NULL,NULL,NULL",
        ):
            proposal, reason = propose_empty_crosspage_category_fallback(
                altered, QUESTION)
            self.assertIsNone(proposal, reason)

    def test_non_amplia_centro_non_richiesto_o_categoria_nuova(self):
        for altered in (
            SQL.replace("%Federico II%", "%Ospedale Altro%"),
            SQL.replace("%neuromuscolar%", "%oncolog%"),
            SQL.replace("p.testo LIKE '%Federico II%'",
                        "p.testo LIKE '%Altro Centro%'"),
            SQL.replace("n.indicazione_candidata LIKE '%neuromuscolar%'",
                        "n.indicazione_candidata LIKE '%oncolog%'"),
        ):
            candidate, reason = propose_empty_crosspage_category_fallback(
                altered, QUESTION)
            self.assertIsNone(candidate, reason)

    def test_pipeline_tag_r11_legge_pagine_pdf(self):
        calls = []
        def fake_ask(model, system, payload, **kwargs):
            calls.append((system, payload))
            if system == auto.SQL_PROMPT:
                return SQL, {"token_input":1,"token_output":1,"costo_usd":0}
            return "MED-A — patologia del nervo periferico (med-a.pdf, p.2).", {
                "token_input":1,"token_output":1,"costo_usd":0
            }
        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_: None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_, **__: types.SimpleNamespace()
        with patch.dict(sys.modules, {
              "lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=fake_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame, instruction:frame):
            result = auto.automatic_tag(self.db, QUESTION, "mock")
        self.assertTrue(result["recupero_progressivo_usato"])
        self.assertEqual(result["righe_sql_primo_tentativo"], 0)
        self.assertEqual(result["sql_tentativi"], 2)
        self.assertEqual(result["righe_sql"], 1)
        self.assertEqual(result["note_nel_contesto"], 1)
        self.assertEqual(result["note_nell_indice"], 1)
        self.assertTrue(any("#p2" in ref for ref in result["fonti"]))
        self.assertEqual(len(calls),2)
        self.assertEqual(
            result["tag_auto_revision"],"2026-11-07-r12-raffinamento-documentale"
        )

    def test_snapshot_statico_documenti_gold_nei_candidati(self):
        root = Path(__file__).resolve().parents[1]
        dbfile = root/"risultati/tesi_statico_20261102.sqlite.gz"
        goldfile = root/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
        if not dbfile.is_file() or not goldfile.is_file():
            self.skipTest("Snapshot o riferimento non disponibile")
        db = sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(dbfile.read_bytes()))
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            original, _ = normalize_document_note_id(SQL)
            rows, _ = auto._run_generated_select(db,auto.validate_sql(original))
            self.assertFalse(rows)
            suggestion, reason = propose_empty_crosspage_category_fallback(
                original, QUESTION)
            self.assertIsNotNone(suggestion, reason)
            retrieved, partial = auto._run_generated_select(
                db,auto.validate_sql(suggestion))
            self.assertFalse(partial)
            ids = {r["nota_id"] for r in retrieved}
            gold = json.loads(goldfile.read_text(encoding="utf-8"))
            expected = {case["sha256_pdf"]
                        for case in gold["casi_positivi"]}
            self.assertTrue(expected <= ids)
            print("Snapshot statico: documenti candidati",
                  len(retrieved),"; casi gold rappresentati",
                  len(expected),"/",len(expected))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
