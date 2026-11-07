"""Test offline: fallback zero righe, nessun lessico clinico nel codice."""
import sqlite3
import json
import pandas as pd  # Import prima di patch.dict per evitare reimport numpy.
import gzip
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from tesi.recupero_progressivo import (
    normalize_document_note_id, propose_empty_category_fallback,
    propose_partial_center_expansion,
)
from tesi import tag_automatico as auto


QUESTION = (
    "Quali medicinali citati nelle note regionali della Campania per "
    "malattie neuromuscolari prevedono la prescrizione presso l'AOU "
    "Federico II? Indica medicinale, patologia, documento e pagina."
)
SQL_CENTRI_CANDIDATI = (
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "n.indicazione_candidata AS indicazione, "
    "n.id AS documento_id, c.numero_pagina AS pagina "
    "FROM note AS n JOIN centri_candidati AS c ON n.id = c.nota_id "
    "WHERE c.menzione LIKE '%Federico II%' COLLATE NOCASE "
    "AND (c.stato IS NULL OR NOT c.stato IN ('escluso', 'falso'))"
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
            CREATE TABLE centri_candidati(
                nota_id TEXT, numero_pagina INTEGER,
                menzione TEXT, stato TEXT
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
            INSERT INTO centri_candidati VALUES
                ('a',2,'AOU Federico II',NULL),
                ('b',1,'Altro ospedale',NULL);
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

    def test_centri_candidati_alias_documentale_diventa_nota_id(self):
        """Riproduce la SELECT ottenuta dall'LLM su 72 righe tabellari."""
        normalized, fixed = normalize_document_note_id(SQL_CENTRI_CANDIDATI)
        self.assertTrue(fixed)
        self.assertIn("n.id AS nota_id", normalized)
        self.assertNotIn("documento_id", normalized)
        records, partial = auto._run_generated_select(
            self.db, auto.validate_sql(normalized))
        self.assertFalse(partial)
        self.assertEqual([r["nota_id"] for r in records], ["a"])
        candidates, truncated = auto._note_candidates(self.db, records)
        self.assertFalse(truncated)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["nota_id"], "a")
        self.assertIn("Prescrizione presso AOU Federico II",
                      candidates[0]["testo"])
        self.assertIn("#p2", " ".join(candidates[0]["fonti"]))

    def test_non_trasforma_id_che_non_appartiene_a_note(self):
        for sql in [
            "SELECT c.id AS documento_id FROM note n "
            "JOIN centri_candidati c ON n.id=c.nota_id",
            "SELECT n.id AS documento_id FROM altri_documenti n",
            "SELECT n.id AS documento_id FROM note n "
            "UNION SELECT id AS documento_id FROM altra_tabella",
            "SELECT n.id AS nota_id FROM note n",
        ]:
            result, changed = normalize_document_note_id(sql)
            self.assertFalse(changed, sql)
            self.assertEqual(result, sql)

    def test_centri_candidati_end_to_end_torna_a_documenti_pdf(self):
        calls = []
        def mock_ask(model, system, payload, **kwargs):
            calls.append((system, payload))
            if system == auto.SQL_PROMPT:
                return SQL_CENTRI_CANDIDATI, {
                    "token_input":1,"token_output":1,"costo_usd":0
                }
            return "Farmaco A, documento A.pdf, pagina 2.", {
                "token_input":1,"token_output":1,"costo_usd":0
            }
        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_: None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules, {
                "lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result = auto.automatic_tag(self.db, QUESTION, "modello-fittizio")
        self.assertEqual(result["stato"], "OK")
        self.assertFalse(result["recupero_progressivo_usato"])
        self.assertTrue(result["sql_normalizzato_nota_id"])
        # Il recupero ampliato viene verificato anche quando la prima SELECT
        # e' non vuota, ma non sostituisce la query se non aggiunge nuove note.
        self.assertEqual(result["sql_tentativi"], 2)
        self.assertEqual(result["righe_sql"], 1)
        self.assertEqual(result["note_nell_indice"], 1)
        self.assertEqual(result["note_nel_contesto"], 1)
        self.assertTrue(any("#p2" in f for f in result["fonti"]))
        self.assertEqual(len(calls), 2)
        self.assertIn("indice_documentale", calls[-1][1])
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-07-r11-recupero-crosspage")

    def test_non_amplia_filtri_autorizzativi_o_farmaci_precisi(self):
        for sql in [
            SQL_CENTRI_CANDIDATI.replace(
                "(c.stato IS NULL OR NOT c.stato IN ('escluso', 'falso'))",
                "c.stato = 'autorizzato'"),
            SQL_CENTRI_CANDIDATI +
                " AND n.farmaco_candidato='FARMACO-A'",
            SQL_CENTRI_CANDIDATI +
                " UNION SELECT id AS documento_id FROM note",
            SQL_CENTRI_CANDIDATI.replace(
                "JOIN centri_candidati AS c", "JOIN altro AS c"),
        ]:
            proposed, why = propose_partial_center_expansion(sql, QUESTION)
            self.assertIsNone(proposed, why)
        proposed, _ = propose_partial_center_expansion(
            SQL_CENTRI_CANDIDATI, "Quali note riguardano altra struttura?")
        self.assertIsNone(proposed)

    def test_proposta_centri_documentali_conserva_i_candidati_iniziali(self):
        normalized, changed = normalize_document_note_id(SQL_CENTRI_CANDIDATI)
        self.assertTrue(changed)
        suggestion, reason = propose_partial_center_expansion(
            normalized, QUESTION)
        self.assertEqual(
            reason, "ampliamento_centro_documentale_senza_classificazione_clinica")
        self.assertIsNotNone(suggestion)
        self.assertIn(" UNION ", suggestion)
        self.assertIn("centri_candidati", suggestion)
        self.assertIn("pagine", suggestion)
        self.assertIn("LIKE '%Federico%'", suggestion)
        self.assertNotIn("neuromuscolari", suggestion.casefold())
        records, truncated = auto._run_generated_select(
            self.db, auto.validate_sql(suggestion))
        self.assertFalse(truncated)
        self.assertEqual([i["nota_id"] for i in records], ["a"])

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

    def test_snapshot_originale_20261102_documenti_candidati(self):
        """Controlla la query problematica sul database reale, senza Gemini."""
        snapshot = (Path(__file__).resolve().parents[1] /
                    "risultati/tesi_statico_20261102.sqlite.gz")
        if not snapshot.is_file():
            self.skipTest("Snapshot originale non disponibile")
        real_db = sqlite3.connect(":memory:")
        try:
            real_db.deserialize(gzip.decompress(snapshot.read_bytes()))
            real_db.row_factory = sqlite3.Row
            real_db.execute("PRAGMA query_only=ON")
            original, _ = normalize_document_note_id(ORIGINAL_SQL)
            before, _ = auto._run_generated_select(
                real_db, auto.validate_sql(original))
            self.assertEqual(before, [])
            suggestion, _ = propose_empty_category_fallback(
                original, QUESTION)
            after, partial = auto._run_generated_select(
                real_db, auto.validate_sql(suggestion))
            self.assertTrue(after, "Fallback non ha trovato note candidate")
            self.assertFalse(partial, "Troppe note candidate per il budget SQL")
            self.assertTrue(all("nota_id" in row for row in after))
            print("Snapshot 20261102: note candidate dopo fallback:", len(after))
            reference_path = (Path(__file__).resolve().parents[1] /
                "tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json")
            gold = json.loads(reference_path.read_text(encoding="utf-8"))
            ids = {str(row["nota_id"]) for row in after}
            missing = [i["medicinale"] for i in gold["casi_positivi"]
                       if i["sha256_pdf"] not in ids]
            print("Riferimento provvisorio, mancanti dal fallback 132:",
                  ", ".join(missing) if missing else "nessuno")
            broader = (
                "SELECT DISTINCT n.id AS nota_id FROM note n "
                "JOIN pagine p ON p.nota_id=n.id "
                "WHERE p.testo LIKE '%Federico%' COLLATE NOCASE"
            )
            broad, more = auto._run_generated_select(
                real_db, auto.validate_sql(broader))
            missing_broad = [i["medicinale"] for i in gold["casi_positivi"]
                             if i["sha256_pdf"] not in
                             {str(row["nota_id"]) for row in broad}]
            print("Recupero con token denominazione centro: note",
                  len(broad), "parziale", more, "mancanti:",
                  ", ".join(missing_broad) if missing_broad else "nessuno")
        finally:
            real_db.close()

    def test_centri_candidati_nello_snapshot_reale(self):
        """Verifica riconoscimento PDF sullo snapshot congelato senza LLM."""
        snapshot = (Path(__file__).resolve().parents[1] /
                    "risultati/tesi_statico_20261102.sqlite.gz")
        if not snapshot.is_file():
            self.skipTest("Snapshot sperimentale non disponibile")
        db = sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(snapshot.read_bytes()))
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            normalized, fixed = normalize_document_note_id(
                SQL_CENTRI_CANDIDATI)
            self.assertTrue(fixed)
            rows, partial = auto._run_generated_select(
                db, auto.validate_sql(normalized))
            self.assertFalse(partial)
            self.assertGreater(len(rows), 0)
            self.assertTrue(all("nota_id" in row for row in rows))
            docs, truncated = auto._note_candidates(db, rows)
            self.assertFalse(truncated)
            self.assertGreater(len(docs), 0)
            self.assertTrue(all(doc["tipo"] == "REGIONE" for doc in docs))
            self.assertTrue(all(doc["fonti"] for doc in docs))
            print("Snapshot 20261102: righe centri candidati:",
                  len(rows), "PDF distinti:", len(docs))
            reference_path = (Path(__file__).resolve().parents[1] /
                "tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json")
            reference = json.loads(reference_path.read_text(encoding="utf-8"))
            ids = {str(doc["nota_id"]) for doc in docs}
            matching = [item["medicinale"] for item in reference["casi_positivi"]
                        if item["sha256_pdf"] in ids]
            missing = [item["medicinale"] for item in reference["casi_positivi"]
                       if item["sha256_pdf"] not in ids]
            print("Riferimento provvisorio: inclusi", len(matching),
                  "dei", len(reference["casi_positivi"]),
                  "esclusi dalla SELECT iniziale:", ", ".join(missing))
            proposed, reason = propose_partial_center_expansion(
                normalized, QUESTION)
            self.assertIsNotNone(proposed, reason)
            enlarged, enlarged_partial = auto._run_generated_select(
                db, auto.validate_sql(proposed))
            enlarged_ids = {str(row["nota_id"]) for row in enlarged}
            still_missing = [i["medicinale"] for i in
                             reference["casi_positivi"]
                             if i["sha256_pdf"] not in enlarged_ids]
            self.assertFalse(enlarged_partial)
            self.assertEqual(still_missing, [])
            self.assertGreater(len(enlarged_ids), len(ids))
            print("Recupero ampliato centrato sulle pagine: ",
                  len(enlarged_ids), "note, riferimento provvisorio 14/14")
        finally:
            db.close()

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
                         "2026-11-07-r11-recupero-crosspage")
        self.assertEqual(len(calls), 2)  # SQL + sintesi; LOTUS simulato.


if __name__ == "__main__":
    unittest.main()
