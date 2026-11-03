"""Test interfaccia motori senza API esterne né Streamlit."""
import os
from pathlib import Path
import tempfile
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
