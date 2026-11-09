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
        self.assertIn('right:23px!important',src)
        self.assertIn('bottom:70px!important',src)
        self.assertIn('@st.dialog("Assistente FarmaQuery"',src)
        self.assertIn('st.button("💬"',src)
        self.assertNotIn('st.popover(',src)
        self.assertIn('width:86px!important',src)
        self.assertIn('height:86px!important',src)
        self.assertIn('border-radius:50%!important',src)
        self.assertIn('st.text_area(',src)
        self.assertIn('disabled=False',src)
        self.assertIn('st.rerun(scope="fragment")',src)
        self.assertIn('if not has_key:',src)
        self.assertIn('if remaining<=0:',src)
        self.assertIn('("Text-to-SQL","TAG automatico")',src)
        self.assertIn("answer_question(db,question,method,model)",src)
        self.assertIn("st.form_submit_button",src)
        self.assertNotIn("FARMAQUERY_CHAT_PASSWORD",src)
        self.assertNotIn("domande_utente_35.csv",src)
        self.assertNotIn("domande_della_tesi",src)

    def test_nuova_conversazione_cancella_tutte_tre_le_chat(self):
        import chatbot_widget as widget
        state={
            "farmaquery_chat_sql":[{"role":"user","text":"prima domanda"}],
            "farmaquery_chat_tag":[{"role":"assistant","text":"risposta"}],
            "farmaquery_chat_tag_auto":[{"role":"assistant","text":"altro"}],
            "farmaquery_chat_count":5,
        }
        with patch.object(widget.st,"session_state",state):
            widget.start_new_conversation()
        self.assertEqual(state["farmaquery_chat_sql"],[])
        self.assertEqual(state["farmaquery_chat_tag"],[])
        self.assertEqual(state["farmaquery_chat_tag_auto"],[])
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
