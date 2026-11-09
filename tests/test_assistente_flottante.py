"""Verifica che FarmaQuery abbia un chatbot flottante senza domande precompilate."""
from pathlib import Path
import unittest
import csv
from io import StringIO
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
        self.assertIn('if mostra_dettagli:',src)
        self.assertIn('Esporta risposte integrali e metriche (JSON)',src)
        self.assertIn("answer_question(db,question,method,model)",src)
        self.assertIn("st.form_submit_button",src)
        self.assertNotIn("FARMAQUERY_CHAT_PASSWORD",src)
        self.assertNotIn("domande_utente_35.csv",src)
        self.assertNotIn("domande_della_tesi",src)

    def test_screenshot_cleanup_preserves_full_raw_error(self):
        import chatbot_widget as widget
        item={"role":"assistant",
              "text":"Query non eseguibile. (fase: esecuzione SQL; codice: SQL; tipo: OperationalError).",
              "stato":"ERRORE"}
        self.assertEqual(widget._visible_message(item,False),"Query non eseguibile.")
        self.assertEqual(widget._visible_message(item,True),item["text"])
        self.assertIn("codice: SQL",item["text"])


    def test_csv_export_preserves_full_responses_and_errors(self):
        import chatbot_widget as widget
        full_answer="Risposta integrale, senza tagli; prova con accenti è e nuove righe\nDocumento pag. 2"
        groups={
            "esportazione_utc":"2026-11-09T20:00:00+00:00",
            "modello":"gemini/test","snapshot_sha256":"sha256_test",
            "metodi":[
                {"metodo":"Text-to-SQL con auto-correzione","etichetta":"Text-to-SQL",
                 "messaggi":[
                     {"role":"user","text":"Domanda 1?"},
                     {"role":"assistant","text":full_answer,"stato":"OK",
                      "fonti":["AIFA AIC 000"],"secondi":2.5,
                      "correzioni_sql":1,"sql_tentativi":2,
                      "chiamate_llm_effettive":3,"token_input":123,
                      "sql":"SELECT * FROM aifa_confezioni","sql_proposte":["SQL errato","SQL valido"]}
                 ]},
                {"metodo":"TAG automatico","etichetta":"TAG",
                 "messaggi":[
                     {"role":"user","text":"Domanda 2?"},
                     {"role":"assistant","text":"Errore SQL","stato":"ERRORE_SQL",
                      "codice_errore":"SQL","sql_tentativi":3}
                 ]}
            ]}
        csv_bytes=widget._export_csv(groups)
        self.assertTrue(csv_bytes.startswith(b"\\xef\\xbb\\xbf"))
        rows=list(csv.DictReader(StringIO(csv_bytes.decode("utf-8-sig")),delimiter=";"))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["domanda"],"Domanda 1?")
        self.assertEqual(rows[0]["risposta_completa"],full_answer)
        self.assertEqual(rows[0]["sql_tentativi"],"2")
        self.assertEqual(rows[0]["chiamate_llm_effettive"],"3")
        self.assertIn("SQL errato",rows[0]["sql_proposte"])
        self.assertEqual(rows[1]["metodo"],"TAG")
        self.assertEqual(rows[1]["stato"],"ERRORE_SQL")
        self.assertEqual(rows[1]["codice_errore"],"SQL")

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
