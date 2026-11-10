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
        self.assertIn('("Text-to-SQL con auto-correzione","TAG automatico")',src)
        self.assertIn('mostra_dettagli=st.toggle(',src)
        self.assertIn('if mostra_dettagli and not screenshot_view:',src)
        self.assertIn('"Scarica CSV"',src)
        self.assertIn('"Scarica JSON"',src)
        self.assertIn("answer_question(db,question,method,model)",src)
        self.assertIn("st.form_submit_button",src)
        self.assertNotIn("FARMAQUERY_CHAT_PASSWORD",src)
        self.assertNotIn("domande_utente_35.csv",src)
        self.assertNotIn("domande_della_tesi",src)

    def test_chat_toolbar_is_one_horizontal_row(self):
        src=WIDGET.read_text(encoding="utf-8")
        self.assertIn('details_col,quota_col,new_chat_col=st.columns(',src)
        self.assertIn('vertical_alignment="center"',src)
        self.assertIn('with details_col:\n        mostra_dettagli=st.toggle(',src)
        self.assertIn('with quota_col:\n        st.caption(f"Richieste disponibili:',src)
        self.assertIn('with new_chat_col:\n        st.button("↺ Nuova conversazione"',src)
        self.assertIn('use_container_width=True',src)
        self.assertEqual(src.count('key="farmaquery_start_new_conversation"'),1)
        self.assertEqual(src.count('key="farmaquery_show_technical_details"'),1)
    def test_large_chat_and_full_answer_screenshot_mode(self):
        src=WIDGET.read_text(encoding="utf-8")
        self.assertIn('"Vista per screenshot (risposta completa)"',src)
        self.assertIn('key="farmaquery_screenshot_view"',src)
        self.assertIn('visible_history=history[-2:] if screenshot_view else history',src)
        self.assertIn('with _conversation_box(screenshot_view):',src)
        self.assertNotIn('height=None',src)
        self.assertIn('height=125,max_chars=700,disabled=False',src)
        self.assertIn('width:min(1200px,96vw)!important',src)
        self.assertIn('with st.form("farmaquery_message_form_"+method',src)
        self.assertIn('nullcontext()',src)
        self.assertIn('st.rerun(scope="fragment")',src)

    def test_screenshot_container_does_not_pass_invalid_height(self):
        import chatbot_widget as widget
        from unittest.mock import sentinel

        with patch.object(widget.st,"container",return_value=sentinel.container) as container:
            self.assertIs(widget._conversation_box(True),sentinel.container)
            container.assert_called_once_with(border=True)

        with patch.object(widget.st,"container",return_value=sentinel.container) as container:
            self.assertIs(widget._conversation_box(False),sentinel.container)
            container.assert_called_once_with(height=560,border=True)

    def test_screenshot_cleanup_preserves_full_raw_error(self):
        import chatbot_widget as widget
        item={"role":"assistant",
              "text":"Query non eseguibile. (fase: esecuzione SQL; codice: SQL; tipo: OperationalError).",
              "stato":"ERRORE"}
        self.assertEqual(widget._visible_message(item,False),"Query non eseguibile.")
        self.assertEqual(widget._visible_message(item,True),item["text"])
        self.assertIn("codice: SQL",item["text"])

    def test_csv_export_preserves_full_question_answer_and_telemetry(self):
        import csv
        import io
        import chatbot_widget as widget
        payload={
            "modello":"gemini/example",
            "snapshot_sha256":"test-sha",
            "esportazione_utc":"2026-11-09T20:00:00Z",
            "metodi":[{
                "metodo":"Text-to-SQL con auto-correzione",
                "etichetta":"Text-to-SQL",
                "messaggi":[
                    {"role":"user","text":"Quali AIC per NINLARO?"},
                    {"role":"assistant","text":'Risposta; completa, "citata".\nSeconda riga.',
                     "sql":"SELECT aic FROM aifa_confezioni",
                     "sql_tentativi":2,"correzioni_sql":1,
                     "chiamate_llm_effettive":3,"secondi":3.2,
                     "fonti":["AIFA AIC 045181017"]},
                ],
            }]
        }
        output=widget._full_results_csv(payload)
        self.assertTrue(output.startswith("\ufeff"))
        parsed=list(csv.DictReader(io.StringIO(output.lstrip("\ufeff")),
                                   delimiter=";"))
        self.assertEqual(len(parsed),1)
        row=parsed[0]
        self.assertEqual(row["domanda"],"Quali AIC per NINLARO?")
        self.assertEqual(row["risposta_integrale"],
                         'Risposta; completa, "citata".\nSeconda riga.')
        self.assertEqual(row["correzioni_sql"],"1")
        self.assertEqual(row["chiamate_llm_effettive"],"3")
        self.assertEqual(row["fonti"],'["AIFA AIC 045181017"]')
        self.assertEqual(row["snapshot_sha256"],"test-sha")
        self.assertIn("APP_UI_VERSION",WIDGET.read_text(encoding="utf-8"))
        self.assertIn('"Scarica CSV"',WIDGET.read_text(encoding="utf-8"))

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
