"""Test offline per la terza baseline, senza chiamate a Gemini."""
import unittest
from unittest.mock import patch, Mock

from errori_chatbot import EnginePhaseError
from tesi.sql_autocorrezione import sql_autocorrezione
from tesi import pilota_tag_vs_sql as p

USAGE={"token_input":10,"token_output":5,"costo_usd":0.001}


class SQLAutoCorrezioneTests(unittest.TestCase):
    def test_corrects_once_and_generates_full_answer(self):
        ask_results=[
            ("SELECT sbagliata",USAGE),
            ("SELECT aic,descrizione FROM aifa_confezioni",USAGE),
            ("Risposta completa",USAGE),
        ]
        with patch.object(p,"_sql_schema",return_value="schema"),\
             patch.object(p,"ask",side_effect=ask_results) as ask,\
             patch.object(p,"validate_sql",side_effect=[
                 ValueError("Tabella o schema non consentito: sbagliata"),
                 "SELECT aic,descrizione FROM aifa_confezioni"]),\
             patch.object(p,"_execute_generated_select",
                          return_value=([{"aic":"049883061","descrizione":"Penna"}],False)),\
             patch.object(p,"_sql_sources",return_value=["AIFA"]),\
             patch.object(p,"_source_previews",return_value=[]):
            result=sql_autocorrezione(Mock(),"Quali confezioni?","test-model")
        self.assertEqual(result["risposta"],"Risposta completa")
        self.assertEqual(result["correzioni_sql"],1)
        self.assertEqual(result["sql_tentativi"],2)
        self.assertEqual(len(result["errori_sql_tentativi"]),1)
        self.assertEqual(ask.call_count,3)

    def test_empty_valid_query_is_not_rewritten(self):
        with patch.object(p,"_sql_schema",return_value="schema"),\
             patch.object(p,"ask",return_value=("SELECT * FROM note",USAGE)) as ask,\
             patch.object(p,"validate_sql",return_value="SELECT * FROM note"),\
             patch.object(p,"_execute_generated_select",return_value=([],False)),\
             patch.object(p,"_sql_sources",return_value=[]):
            result=sql_autocorrezione(Mock(),"Cosa manca?","test-model")
        self.assertEqual(result["sql_tentativi"],1)
        self.assertEqual(result["correzioni_sql"],0)
        self.assertEqual(ask.call_count,1)

    def test_stops_after_exactly_two_corrections(self):
        responses=[("SELECT a",USAGE),("SELECT b",USAGE),("SELECT c",USAGE)]
        with patch.object(p,"_sql_schema",return_value="schema"),\
             patch.object(p,"ask",side_effect=responses) as ask,\
             patch.object(p,"validate_sql",
                          side_effect=ValueError("Tabella o schema non consentito")):
            result=sql_autocorrezione(Mock(),"Domanda","test-model")
        self.assertEqual(result["stato"],"ERRORE_SQL")
        self.assertEqual(result["correzioni_sql"],2)
        self.assertEqual(result["sql_tentativi"],3)
        self.assertEqual(ask.call_count,3)

    def test_does_not_retry_provider_failure(self):
        with patch.object(p,"_sql_schema",return_value="schema"),\
             patch.object(p,"ask",
                          side_effect=EnginePhaseError("connessione LLM",RuntimeError("503"))) as ask:
            with self.assertRaises(EnginePhaseError):
                sql_autocorrezione(Mock(),"Domanda","test-model")
        self.assertEqual(ask.call_count,1)


if __name__=="__main__":
    unittest.main()
