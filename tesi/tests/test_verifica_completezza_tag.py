"""Regressioni del controllo di completezza, senza chiamate API reali."""
import unittest
from tesi.verifica_completezza_tag import (
    missing_identifiers,revise_if_needed,enumeration_warning,check_enumeration
)

class TagCompletionTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{
            "testo":"Art.1 AIC n. 123456789/E e AIC n. 123456790/E",
            "aic_trovati_nel_testo":["123456789/E","123456790/E"],
            "fonte":"GU TEST"
        }]

    def test_identifica_omissione_senza_risposte_predefinite(self):
        answer="Una confezione: 123456789/E"
        self.assertEqual(missing_identifiers(answer,self.rows),["123456790/E"])
        self.assertIn("2 identificativi",enumeration_warning(answer,self.rows))

    def test_fonte_integrale_con_autocorrezione_llm(self):
        calls=[]
        def fake(model,system,payload,**kw):
            calls.append((model,system,payload,kw))
            return ("Due confezioni: 123456789/E e 123456790/E",
                    {"token_input":23,"token_output":21,"costo_usd":0.003})
        answer,usage,done,status=revise_if_needed(
            "mock","Quali sono tutti gli AIC?","Una: 123456789/E",
            self.rows,True,fake)
        self.assertEqual(len(calls),1)
        self.assertTrue(done)
        self.assertEqual(status["aic_omessi_nella_risposta"],0)
        self.assertEqual(usage["token_input"],23)
        self.assertIn("123456790/E",answer)
        self.assertIn("fonte",str(calls[0][2]).lower())

    def test_sezione_parziale_non_genera_seconda_chiamata(self):
        def fake(*args,**kwargs):
            self.fail("Nessuna seconda chiamata su fonte parziale")
        answer,usage,done,status=revise_if_needed(
            "mock","Tutti gli AIC","123456789/E",self.rows,False,fake)
        self.assertFalse(done)
        self.assertIsNone(usage)
        self.assertEqual(status["aic_omessi_nella_risposta"],1)

    def test_astensione_con_fonte_integrale_attiva_revisione(self):
        rows=[{"testo":"Tabella centri: AOU ALFA e AOU BETA",
               "fonte":"n.pdf#p2"}]
        requests=[]
        def fake(*args,**kwargs):
            requests.append(args)
            return ("AOU ALFA e AOU BETA (pagina 2)",
                    {"token_input":10,"token_output":10,"costo_usd":0.0})
        answer,_,done,status=revise_if_needed(
            "mock","Elenca tutti i centri","Non documentato nello snapshot",
            rows,True,fake)
        self.assertEqual(len(requests),1)
        self.assertTrue(done)
        self.assertIn("BETA",answer)
        self.assertFalse(status["risposta_di_astensione"])

    def test_senza_omissione_non_consuma_seconda_chiamata(self):
        answer,usage,done,status=revise_if_needed(
            "mock","Tutti gli AIC","123456789/E, 123456790/E",
            self.rows,True,lambda *a,**k:self.fail("no retry"))
        self.assertFalse(done)
        self.assertIsNone(usage)
        self.assertEqual(status["aic_omessi_nella_risposta"],0)

if __name__=="__main__":
    unittest.main()