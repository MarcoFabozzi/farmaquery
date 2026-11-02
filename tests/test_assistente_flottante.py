"""Verifica che FarmaQuery abbia un chatbot flottante senza domande precompilate."""
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
WIDGET=ROOT/"chatbot_widget.py"
DASHBOARD=ROOT/"dashboard_regolatorio.py"


class FloatingAssistantTests(unittest.TestCase):
    def test_floating_chat_has_real_method_choice(self):
        src=WIDGET.read_text(encoding="utf-8")
        self.assertIn('position:fixed!important',src)
        self.assertIn('right:22px!important',src)
        self.assertIn('bottom:64px!important',src)
        self.assertIn('st.popover("💬"',src)
        self.assertIn('("Text-to-SQL","TAG")',src)
        self.assertIn("answer_question(db,question,method,model)",src)
        self.assertIn("st.form_submit_button",src)
        self.assertNotIn("FARMAQUERY_CHAT_PASSWORD",src)
        self.assertNotIn("domande_utente_35.csv",src)
        self.assertNotIn("domande_della_tesi",src)

    def test_nuova_conversazione_cancella_davvero_entrambe_le_chat(self):
        import chatbot_widget as widget
        state={
            "farmaquery_chat_sql":[{"role":"user","text":"prima domanda"}],
            "farmaquery_chat_tag":[{"role":"assistant","text":"risposta"}],
            "farmaquery_chat_count":5,
        }
        with patch.object(widget.st,"session_state",state):
            widget.start_new_conversation()
        self.assertEqual(state["farmaquery_chat_sql"],[])
        self.assertEqual(state["farmaquery_chat_tag"],[])
        self.assertEqual(state["farmaquery_chat_count"],5)
        self.assertTrue(state["farmaquery_chat_just_cleared"])

    def test_dashboard_contains_widget_not_old_page_link(self):
        src=DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("render_assistant()",src)
        self.assertNotIn("pages/1_Chatbot.py",src)
        self.assertFalse((ROOT/"pages"/"1_Chatbot.py").exists())
        self.assertFalse((ROOT/"tesi"/"domande_utente_35.csv").exists())


if __name__=="__main__":
    unittest.main()
