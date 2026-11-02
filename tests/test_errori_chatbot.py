"""Test di diagnosi e risposta senza consumare quote di Gemini."""
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from errori_chatbot import EnginePhaseError,label_error
from chatbot_farmaquery import verify_provider
from tesi import pilota_tag_vs_sql as core


class DiagnosticTests(unittest.TestCase):
    def test_quota_senza_fuga_di_credenziali(self):
        class RateLimitError(Exception): pass
        password="nonmostrare_questa_chiave_123"
        failure=EnginePhaseError("selezione TAG",RateLimitError(password))
        result=label_error(failure)
        self.assertEqual(result["codice_errore"],"QUOTA")
        self.assertNotIn(password,result["risposta"])
        self.assertIn("selezione TAG",result["risposta"])

    def test_fasi_e_errori_sql(self):
        class ParseError(Exception): pass
        with self.assertRaises(EnginePhaseError) as caught:
            core._in_phase("validazione SQL",lambda: (_ for _ in ()).throw(ParseError("bad")))
        result=label_error(caught.exception)
        self.assertEqual(result["codice_errore"],"SQL")
        self.assertEqual(result["fase_errore"],"validazione SQL")

    def test_prova_minima_gemini_senza_rete(self):
        fake=MagicMock()
        fake.choices[0].message.content="OK"
        with patch("litellm.completion",return_value=fake) as mocked:
            self.assertTrue(verify_provider("gemini/gemini-3.5-flash-lite"))
            self.assertEqual(mocked.call_args.kwargs["model"],"gemini/gemini-3.5-flash-lite")
            self.assertEqual(mocked.call_args.kwargs["max_tokens"],12)

    def test_text_to_sql_usa_veramente_le_righe(self):
        db=sqlite3.connect(":memory:")
        db.row_factory=sqlite3.Row
        db.execute("CREATE TABLE aifa_confezioni(aic TEXT,nome TEXT,principio_attivo TEXT)")
        db.execute("INSERT INTO aifa_confezioni VALUES('123456789','TACHIPIRINA','PARACETAMOLO')")
        answers=[
            ("SELECT aic,nome,principio_attivo FROM aifa_confezioni WHERE nome='TACHIPIRINA' LIMIT 30",
             {"token_input":10,"token_output":12,"costo_usd":None}),
            ("Il principio attivo di Tachipirina è il paracetamolo.",
             {"token_input":10,"token_output":12,"costo_usd":None}),
        ]
        with patch.object(core,"ask",side_effect=answers):
            result=core.sql_method(db,"Qual è il principio attivo di Tachipirina?","fake-model")
        db.close()
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["righe_sql"],1)
        self.assertIn("paracetamolo",result["risposta"])
        self.assertIn("AIFA AIC 123456789",result["fonti"][0])


if __name__=="__main__":
    unittest.main()
