"""Test interfaccia motori senza API esterne né Streamlit."""
import os
from pathlib import Path
import tempfile
import json
import hashlib
import sqlite3
import unittest
from unittest.mock import patch

import chatbot_farmaquery as chat


class ChatbotTests(unittest.TestCase):
    def test_method_routes_to_correct_real_engine(self):
        with patch("tesi.pilota_tag_vs_sql.read_only") as connect, \
             patch("tesi.pilota_tag_vs_sql.tag") as tag, \
             patch("tesi.pilota_tag_vs_sql.sql_method") as sql:
            connect.return_value.close.return_value=None
            tag.return_value={"risposta":"via LOTUS"}
            sql.return_value={"risposta":"via SQL"}
            self.assertEqual(chat.answer_question("db.sqlite","Quale classe ha JIVI?",
                                                   "TAG","mock")["risposta"],"via LOTUS")
            self.assertEqual(chat.answer_question("db.sqlite","Quale classe ha JIVI?",
                                                   "Text-to-SQL","mock")["risposta"],"via SQL")
            self.assertEqual(tag.call_count,1)
            self.assertEqual(sql.call_count,1)
            self.assertEqual(connect.return_value.close.call_count,2)

    def test_invalid_method_rejected(self):
        with self.assertRaises(ValueError):
            chat.answer_question("db.sqlite","Test?","RAG","mock")
        with self.assertRaises(ValueError):
            chat.history_key("RAG")
        self.assertNotEqual(chat.history_key("TAG"),
                            chat.history_key("Text-to-SQL"))

    def test_local_sources_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for fname in chat.REQUIRED+chat.CACHE_CODE_SOURCES:
                p=root/fname
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text("test",encoding="utf-8")
            version1=chat.snapshot_version(root)
            (root/chat.REQUIRED[0]).write_text("modified",encoding="utf-8")
            version2=chat.snapshot_version(root)
            self.assertNotEqual(version1,version2)
            (root/"tesi/sintesi_tag.py").write_text(
                "new version",encoding="utf-8")
            self.assertNotEqual(version2,chat.snapshot_version(root))

    def test_snapshot_statico_usato_per_entrambe_le_tecniche(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            db=folder/"statico.sqlite"
            manifest=folder/"manifest.json"
            with sqlite3.connect(db) as con:
                for table in ("note","pagine","aifa_confezioni",
                              "ema_medicinali","strutture_registri",
                              "nota_centro_documentato"):
                    con.execute(f"CREATE TABLE {table}(id INTEGER)")
            digest=hashlib.sha256(db.read_bytes()).hexdigest()
            manifest.write_text(json.dumps({"sha256_sqlite":digest}),
                                encoding="utf-8")
            config={"FARMAQUERY_STATIC_DB_PATH":str(db),
                    "FARMAQUERY_STATIC_MANIFEST_PATH":str(manifest)}
            with patch.dict(os.environ,config), \
                 patch("tesi.pilota_tag_vs_sql.tag",
                       return_value={"risposta":"TAG"}) as tag, \
                 patch("tesi.pilota_tag_vs_sql.sql_method",
                       return_value={"risposta":"SQL"}) as sql:
                selected,meta=chat.prepare_snapshot()
                self.assertEqual(selected,db.resolve())
                self.assertEqual(meta["sha256_sqlite"],digest)
                version=chat.snapshot_version()
                self.assertTrue(version)
                self.assertEqual(chat.answer_question(selected,"Domanda",
                                 "TAG","mock")["risposta"],"TAG")
                self.assertEqual(chat.answer_question(selected,"Domanda",
                                 "Text-to-SQL","mock")["risposta"],"SQL")
                tag.assert_called_once()
                sql.assert_called_once()
                # Nessun motore altera lo SQLite.
                self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),digest)

    def test_snapshot_statico_non_fa_fallback_su_hash_errato(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            db=folder/"statico.sqlite"
            manifest=folder/"manifest.json"
            db.write_bytes(b"non coincide")
            manifest.write_text(json.dumps({"sha256_sqlite":"a"*64}),
                                encoding="utf-8")
            with patch.dict(os.environ,{
                "FARMAQUERY_STATIC_DB_PATH":str(db),
                "FARMAQUERY_STATIC_MANIFEST_PATH":str(manifest)}):
                with self.assertRaisesRegex(ValueError,"diverso"):
                    chat.prepare_snapshot()

    def test_modalita_statica_richiede_entrambi_i_percorsi(self):
        with patch.dict(os.environ,{"FARMAQUERY_STATIC_DB_PATH":"file.sqlite",
                                     "FARMAQUERY_STATIC_MANIFEST_PATH":""}):
            with self.assertRaisesRegex(ValueError,"sia"):
                chat.prepare_snapshot()

    def test_model_and_secret_from_server_only(self):
        model=chat.model_from_settings(
            {"FARMAQUERY_LLM_MODEL":"gemini/gemini-3.5-flash-lite"},environ={})
        self.assertEqual(model,"gemini/gemini-3.5-flash-lite")
        env={}
        self.assertTrue(chat.enable_server_key(model,
                        {"GEMINI_API_KEY":"TEST_SECRET"},env))
        self.assertEqual(env["GEMINI_API_KEY"],"TEST_SECRET")
        self.assertFalse(chat.enable_server_key("unknown/provider",{},{}))
        self.assertEqual(chat.model_from_settings({},{}),chat.MODEL_DEFAULT)


if __name__=="__main__":
    unittest.main()
