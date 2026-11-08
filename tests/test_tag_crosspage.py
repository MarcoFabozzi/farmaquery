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
    propose_partial_crosspage_center_expansion,
    propose_empty_note_page_semantic_fallback,
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


SQL_CENTER_DIRECT = (
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "n.indicazione_candidata AS indicazione, "
    "n.id AS nota_id, p.numero_pagina "
    "FROM note AS n JOIN pagine AS p ON n.id = p.nota_id "
    "JOIN centri_candidati AS cc "
    "ON cc.nota_id = p.nota_id AND cc.numero_pagina = p.numero_pagina "
    "WHERE cc.menzione LIKE '%Federico II%' "
    "AND (n.indicazione_candidata LIKE '%neuromuscolari%' "
    "OR p.testo LIKE '%neuromuscolari%')"
)

SQL_NOTE_PAGES = (
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "n.indicazione_candidata AS indicazione, "
    "n.id AS nota_id, p.numero_pagina FROM note AS n "
    "JOIN pagine AS p ON n.id = p.nota_id "
    "WHERE (p.testo LIKE '%Federico II%' COLLATE NOCASE) "
    "AND (p.testo LIKE '%neuromuscolar%' COLLATE NOCASE "
    "OR n.indicazione_candidata LIKE '%neuromuscolar%' COLLATE NOCASE)"
)

SQL_CENTER_DIRECT_R15 = (
    "SELECT DISTINCT note.farmaco_candidato AS nome, "
    "note.indicazione_candidata AS patologia, "
    "note.id AS documento_id, pagine.numero_pagina "
    "FROM note JOIN pagine ON note.id = pagine.nota_id "
    "JOIN centri_candidati "
    "ON centri_candidati.nota_id = pagine.nota_id "
    "AND centri_candidati.numero_pagina = pagine.numero_pagina "
    "WHERE centri_candidati.menzione LIKE '%Federico II%' COLLATE NOCASE"
)

SQL_ONLY_CENTER = (
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "n.indicazione_candidata AS indicazione, "
    "n.id AS nota_id, p.numero_pagina AS numero_pagina "
    "FROM note n JOIN pagine p ON n.id = p.nota_id "
    "JOIN centri_candidati c "
    "ON c.nota_id = p.nota_id AND c.numero_pagina = p.numero_pagina "
    "WHERE (c.menzione LIKE '%Federico II%' COLLATE NOCASE "
    "OR p.testo LIKE '%Federico II%' COLLATE NOCASE)"
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

    def test_like_singolo_centro_categoria_or_su_pagine_distinte(self):
        """Riproduce letteralmente la nuova query LLM della r13."""
        rows, _ = auto._run_generated_select(
            self.db,auto.validate_sql(SQL_CENTER_DIRECT))
        self.assertEqual(rows, [])
        proposed, reason = propose_empty_crosspage_category_fallback(
            SQL_CENTER_DIRECT, QUESTION)
        self.assertEqual(
            reason,"categoria_clinica_e_join_stessa_pagina_ampliati")
        self.assertIn("SELECT DISTINCT n.id AS nota_id",proposed)
        self.assertIn("LIKE '%Federico%'",proposed)
        self.assertNotIn("neuromuscolari",proposed.casefold())
        expanded, partial = auto._run_generated_select(
            self.db,auto.validate_sql(proposed))
        self.assertFalse(partial)
        self.assertEqual([r["nota_id"] for r in expanded],["id-a"])
        docs,truncated=auto._note_candidates(self.db,expanded)
        self.assertFalse(truncated)
        self.assertIn("[pagina 2]",docs[0]["testo"])

    def test_like_singolo_non_rimuove_vincoli_oggettivi(self):
        for altered in (
            SQL_CENTER_DIRECT + " AND n.anno=2026",
            SQL_CENTER_DIRECT.replace(
                "%Federico II%","%Ospedale Altro%"),
            SQL_CENTER_DIRECT.replace(
                "%neuromuscolari%","%oncologia%"),
            SQL_CENTER_DIRECT.replace(
                "cc.menzione LIKE","cc.stato LIKE"),
            SQL_CENTER_DIRECT.replace(
                "cc.numero_pagina = p.numero_pagina",
                "cc.numero_pagina = p.nota_id"),
            SQL_CENTER_DIRECT.replace(
                "JOIN centri_candidati","LEFT JOIN centri_candidati"),
            SQL_CENTER_DIRECT + " LIMIT 8",
            SQL_CENTER_DIRECT.replace(
                "OR p.testo LIKE '%neuromuscolari%'",
                "OR p.testo LIKE '%diversa%'"),
        ):
            proposed, reason = propose_empty_crosspage_category_fallback(
                altered, QUESTION)
            self.assertIsNone(proposed,reason)

    def test_pipeline_nuova_forma_fallback_e_pagine_pdf(self):
        calls=[]
        def fake_ask(model,system,payload,**kwargs):
            calls.append(system)
            if system == auto.SQL_PROMPT:
                return SQL_CENTER_DIRECT,{
                    "token_input":1,"token_output":1,"costo_usd":0
                }
            return "MED-A e struttura; pagina 2.",{
                "token_input":1,"token_output":1,"costo_usd":0
            }
        lotus=types.ModuleType("lotus")
        lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        models=types.ModuleType("lotus.models")
        models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{
                "lotus":lotus,"lotus.models":models}), \
             patch.object(auto,"ask",side_effect=fake_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(self.db,QUESTION,"mock")
        self.assertTrue(result["recupero_progressivo_usato"])
        self.assertEqual(result["sql_tentativi"],2)
        self.assertEqual(result["righe_sql_primo_tentativo"],0)
        self.assertEqual(result["righe_sql"],1)
        self.assertEqual(result["note_nel_contesto"],1)
        self.assertTrue(any("#p2" in f for f in result["fonti"]))
        self.assertEqual(len(calls),2)
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-08-r20-controllo-copertura-documentale")

    def test_snapshot_query_llm_r13_copertura_referenze_documentali(self):
        root=Path(__file__).resolve().parents[1]
        db_path=root/"risultati/tesi_statico_20261102.sqlite.gz"
        gold_path=root/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
        if not db_path.is_file() or not gold_path.is_file():
            self.skipTest("Snapshot o riferimento non presente")
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(db_path.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            before,_=auto._run_generated_select(
                db,auto.validate_sql(SQL_CENTER_DIRECT))
            self.assertEqual(before,[])
            proposed,why=propose_empty_crosspage_category_fallback(
                SQL_CENTER_DIRECT,QUESTION)
            self.assertIsNotNone(proposed,why)
            rows,partial=auto._run_generated_select(
                db,auto.validate_sql(proposed))
            self.assertFalse(partial)
            ids={str(r["nota_id"]) for r in rows}
            gold=json.loads(gold_path.read_text(encoding="utf-8"))
            expected={str(item["sha256_pdf"])
                      for item in gold["casi_positivi"]}
            self.assertTrue(expected<=ids)
            self.assertEqual(len(ids),161)
            print("Query r13: 0 iniziali;",len(ids),
                  "note ampliate, copertura PDF gold:",len(expected))
        finally:
            db.close()

    def test_sql_note_pagine_esatta_r14_zero_poi_fallback(self):
        first, partial = auto._run_generated_select(
            self.db, auto.validate_sql(SQL_NOTE_PAGES))
        self.assertEqual(first, [])
        self.assertFalse(partial)
        candidate, why = propose_empty_note_page_semantic_fallback(
            SQL_NOTE_PAGES, QUESTION)
        self.assertEqual(
            why, "categoria_clinica_letterale_esclusa_da_note_pagine")
        self.assertNotIn("neuromuscolar", candidate.casefold())
        self.assertIn("LIKE '%Federico%'", candidate)
        found, truncated = auto._run_generated_select(
            self.db, auto.validate_sql(candidate))
        self.assertFalse(truncated)
        self.assertEqual([r["nota_id"] for r in found], ["id-a"])
        docs, missing_pages = auto._note_candidates(self.db, found)
        self.assertFalse(missing_pages)
        self.assertEqual(len(docs),1)
        self.assertIn("[pagina 1]", docs[0]["testo"])
        self.assertIn("[pagina 2]", docs[0]["testo"])

    def test_note_pagine_rifiuta_extra_vincoli_e_join_diverse(self):
        variations = (
            SQL_NOTE_PAGES + " AND n.anno=2026",
            SQL_NOTE_PAGES.replace(
                "n.id = p.nota_id", "n.id = p.numero_pagina"),
            SQL_NOTE_PAGES.replace(
                "JOIN pagine", "LEFT JOIN pagine"),
            SQL_NOTE_PAGES.replace(
                "%Federico II%", "%Ospedale Altro%"),
            SQL_NOTE_PAGES.replace(
                "%neuromuscolar%", "%malattia_non_nella_domanda%"),
            SQL_NOTE_PAGES.replace(
                "p.testo LIKE '%Federico II%'",
                "n.farmaco_candidato LIKE '%Federico II%'"),
            SQL_NOTE_PAGES + " LIMIT 10",
            SQL_NOTE_PAGES + " UNION SELECT 1,2,3,4",
            SQL_NOTE_PAGES.replace(
                "OR n.indicazione_candidata LIKE '%neuromuscolar%'",
                "OR n.indicazione_candidata LIKE '%altra%'")
        )
        for altered in variations:
            suggested, why = propose_empty_note_page_semantic_fallback(
                altered, QUESTION)
            self.assertIsNone(suggested, (why,altered))

    def test_pipeline_note_pagine_restituisce_pdf_non_righe(self):
        calls=[]
        def fake_ask(model,system,payload,**kwargs):
            calls.append(system)
            if system == auto.SQL_PROMPT:
                return SQL_NOTE_PAGES,{
                    "token_input":1,"token_output":1,"costo_usd":0
                }
            return "MED-A: patologia del nervo periferico (pagina 2).",{
                "token_input":1,"token_output":1,"costo_usd":0
            }
        lotus=types.ModuleType("lotus")
        lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        models=types.ModuleType("lotus.models")
        models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{
                "lotus":lotus,"lotus.models":models}), \
             patch.object(auto,"ask",side_effect=fake_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(self.db, QUESTION, "mock")
        self.assertEqual(result["sql_tentativi"],2)
        self.assertTrue(result["recupero_progressivo_usato"])
        self.assertEqual(result["righe_sql_primo_tentativo"],0)
        self.assertEqual(result["righe_sql"],1)
        self.assertEqual(result["note_nell_indice"],1)
        self.assertEqual(result["note_nel_contesto"],1)
        self.assertTrue(any("#p2" in x for x in result["fonti"]))
        self.assertEqual(len(calls),2)
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-08-r20-controllo-copertura-documentale")

    def test_snapshot_sql_note_pagine_ricopre_gold(self):
        root=Path(__file__).resolve().parents[1]
        snapshot=root/"risultati/tesi_statico_20261102.sqlite.gz"
        goldpath=root/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
        if not snapshot.is_file() or not goldpath.is_file():
            self.skipTest("Snapshot o gold non disponibili")
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(snapshot.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            rows,partial=auto._run_generated_select(
                db,auto.validate_sql(SQL_NOTE_PAGES))
            self.assertEqual(rows,[])
            self.assertFalse(partial)
            suggestion,why=propose_empty_note_page_semantic_fallback(
                SQL_NOTE_PAGES,QUESTION)
            self.assertIsNotNone(suggestion,why)
            after,more=auto._run_generated_select(
                db,auto.validate_sql(suggestion))
            self.assertFalse(more)
            gold=json.loads(goldpath.read_text(encoding="utf-8"))
            wanted={x["sha256_pdf"] for x in gold["casi_positivi"]}
            ids={x["nota_id"] for x in after}
            self.assertTrue(wanted<=ids)
            self.assertEqual(len(ids),161)
            print("R15 note/pagine:",len(rows),"->",len(ids),
                  "PDF di riferimento:",len(wanted))
        finally:
            db.close()

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

    def test_centro_senza_filtro_clinico_ampliato_su_pagine_diverse(self):
        proposed,reason=propose_partial_crosspage_center_expansion(
            SQL_ONLY_CENTER,QUESTION)
        self.assertEqual(reason,"recupero_centro_tra_pagine_documentali")
        self.assertIn(" UNION ",proposed)
        self.assertIn("LIKE '%Federico%'",proposed)
        self.assertNotIn("neuromuscolar",proposed.casefold())
        rows,partial=auto._run_generated_select(
            self.db,auto.validate_sql(proposed))
        self.assertFalse(partial)
        self.assertEqual([r["nota_id"] for r in rows],["id-a"])

    def test_sql_reale_r15_like_diretto_recupera_pagine_e_note(self):
        """Riproduce la SELECT non vuota che selezionava solo 68 PDF."""
        original, normalized = normalize_document_note_id(SQL_CENTER_DIRECT_R15)
        self.assertTrue(normalized)
        before,partial=auto._run_generated_select(
            self.db,auto.validate_sql(original))
        self.assertFalse(partial)
        self.assertEqual(len(before),1)
        suggestion,reason=propose_partial_crosspage_center_expansion(
            original,QUESTION)
        self.assertEqual(reason,"recupero_centro_tra_pagine_documentali")
        self.assertIn(" UNION ",suggestion)
        self.assertIn("LIKE '%Federico%'",suggestion)
        self.assertNotIn("neuromuscolar",suggestion.casefold())
        after,partial=auto._run_generated_select(
            self.db,auto.validate_sql(suggestion))
        self.assertFalse(partial)
        self.assertEqual([x["nota_id"] for x in after],["id-a"])

    def test_filtro_diretto_non_confonde_predicati_e_vincoli(self):
        for sql in (
            SQL_CENTER_DIRECT_R15+" AND note.anno=2026",
            SQL_CENTER_DIRECT_R15.replace(
                "centri_candidati.menzione LIKE",
                "centri_candidati.stato LIKE"),
            SQL_CENTER_DIRECT_R15.replace(
                "%Federico II%","%Ospedale differente%"),
            SQL_CENTER_DIRECT_R15.replace(
                "centri_candidati.numero_pagina = pagine.numero_pagina",
                "centri_candidati.numero_pagina = pagine.nota_id"),
            SQL_CENTER_DIRECT_R15+" LIMIT 4",
            SQL_CENTER_DIRECT_R15+" UNION SELECT 1,2,3,4",
        ):
            suggestion,reason=propose_partial_crosspage_center_expansion(
                sql,QUESTION)
            self.assertIsNone(suggestion,(reason,sql))

    def test_sql_reale_r15_snapshot_espande_68_a_161(self):
        root=Path(__file__).resolve().parents[1]
        snapshot=root/"risultati/tesi_statico_20261102.sqlite.gz"
        gold_file=root/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
        if not snapshot.is_file() or not gold_file.is_file():
            self.skipTest("Snapshot o riferimento non presenti")
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(snapshot.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            normalized,changed=normalize_document_note_id(SQL_CENTER_DIRECT_R15)
            self.assertTrue(changed)
            initial,partial=auto._run_generated_select(
                db,auto.validate_sql(normalized))
            self.assertFalse(partial)
            before={x["nota_id"] for x in initial}
            self.assertGreater(len(before),0)
            suggested,reason=propose_partial_crosspage_center_expansion(
                normalized,QUESTION)
            self.assertIsNotNone(suggested,reason)
            enlarged,partial=auto._run_generated_select(
                db,auto.validate_sql(suggested))
            self.assertFalse(partial)
            after={x["nota_id"] for x in enlarged}
            self.assertTrue(before<=after)
            self.assertGreater(len(after),len(before))
            gold=json.loads(gold_file.read_text(encoding="utf-8"))
            expected={x["sha256_pdf"] for x in gold["casi_positivi"]}
            self.assertTrue(expected<=after)
            self.assertEqual(len(after),161)
            print("R15 SQL diretto: iniziali",len(before),
                  "dopo ampliamento",len(after),
                  "PDF riferimenti",len(expected))
        finally:
            db.close()

    def test_pipeline_r16_amplia_anche_se_prima_sql_non_e_vuota(self):
        # Nel sintetico c'e' una nota inizialmente selezionata e una che
        # menziona Federico II su una pagina senza centri_candidati.
        self.db.execute("PRAGMA query_only=OFF")
        self.db.execute(
            "INSERT INTO note VALUES ('id-b','med-b.pdf',2026,NULL,NULL,"
            "'MED-B','disturbo differente','med-b.pdf',"
            "'https://example.org/b.zip')"
        )
        self.db.execute(
            "INSERT INTO pagine VALUES("
            "'id-b',1,'Centro prescrittore presso AOU Federico II','TESTO')"
        )
        self.db.execute("PRAGMA query_only=ON")
        calls=[]
        def fake_ask(model,system,payload,**kwargs):
            calls.append((system,payload))
            if system==auto.SQL_PROMPT:
                return SQL_CENTER_DIRECT_R15, {
                    "token_input":1,"token_output":1,"costo_usd":0
                }
            return "Risposta dimostrativa basata sui PDF.", {
                "token_input":1,"token_output":1,"costo_usd":0
            }
        lotus=types.ModuleType("lotus")
        lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        models=types.ModuleType("lotus.models")
        models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{
                "lotus":lotus,"lotus.models":models}), \
             patch.object(auto,"ask",side_effect=fake_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(self.db, QUESTION,"mock")
        self.assertTrue(result["recupero_progressivo_usato"])
        self.assertEqual(result["righe_sql_primo_tentativo"],1)
        self.assertEqual(result["sql_tentativi"],2)
        self.assertEqual(result["righe_sql"],2)
        self.assertEqual(result["note_nell_indice"],2)
        self.assertEqual(result["note_nel_contesto"],2)
        self.assertEqual(len(calls),2)
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-08-r20-controllo-copertura-documentale")

    def test_non_amplia_query_con_vincoli_aggiuntivi(self):
        for altered in (
            SQL_ONLY_CENTER+" AND n.anno=2026",
            SQL_ONLY_CENTER+" LIMIT 5",
            SQL_ONLY_CENTER.replace(
                "c.numero_pagina = p.numero_pagina",
                "c.numero_pagina = p.nota_id"),
            SQL_ONLY_CENTER.replace(
                "centri_candidati c","nota_centro_documentato c"),
            SQL_ONLY_CENTER.replace(
                "%Federico II%","%Altro Centro%"),
        ):
            suggestion,reason=propose_partial_crosspage_center_expansion(
                altered,QUESTION)
            self.assertIsNone(suggestion,reason)

    def test_snapshot_recupero_centro_senza_join_stessa_pagina(self):
        root=Path(__file__).resolve().parents[1]
        path=root/"risultati/tesi_statico_20261102.sqlite.gz"
        gold_path=root/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
        if not path.is_file() or not gold_path.is_file():
            self.skipTest("Snapshot o riferimento non disponibile")
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(path.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            original,old_partial=auto._run_generated_select(
                db,auto.validate_sql(SQL_ONLY_CENTER))
            self.assertFalse(old_partial)
            proposed,why=propose_partial_crosspage_center_expansion(
                SQL_ONLY_CENTER,QUESTION)
            self.assertIsNotNone(proposed,why)
            expanded,partial=auto._run_generated_select(
                db,auto.validate_sql(proposed))
            self.assertFalse(partial)
            old_ids={r["nota_id"] for r in original}
            new_ids={r["nota_id"] for r in expanded}
            self.assertTrue(old_ids<=new_ids)
            self.assertGreater(len(new_ids),len(old_ids))
            gold=json.loads(gold_path.read_text(encoding="utf-8"))
            target={d["sha256_pdf"] for d in gold["casi_positivi"]}
            self.assertTrue(target<=new_ids)
            print("Centro cross-page: prima",len(old_ids),
                  "dopo",len(new_ids),"fonti gold",len(target))
        finally:
            db.close()

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
            result["tag_auto_revision"],"2026-11-08-r20-controllo-copertura-documentale"
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
