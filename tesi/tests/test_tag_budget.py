"""Test senza API per raggruppamento e classificazione quote TAG."""
import unittest

from errori_chatbot import EnginePhaseError,diagnose_error,label_error
from tesi.tag_budget import semantic_plan,expand_selected,selection_mode


class TagBudgetTests(unittest.TestCase):
    def setUp(self):
        self.rows=[
            {"chiave":"doc-"+str(i),"tipo":("REGIONE" if i<8 else "EMA"),
             "testo":"Contesto del documento "+str(i),
             "fonte":"PDF#p"+str(i)} for i in range(11)
        ]

    def test_raggruppa_senza_perdere_evidenze_o_fonti(self):
        plan,members=semantic_plan(self.rows,max_groups=3)
        self.assertEqual(len(plan),3)
        flattened=expand_selected(plan,members)
        self.assertEqual(len(flattened),len(self.rows))
        self.assertEqual({r["chiave"] for r in flattened},
                         {r["chiave"] for r in self.rows})
        self.assertEqual({r["fonte"] for r in flattened},
                         {r["fonte"] for r in self.rows})
        self.assertTrue(all("REGIONE" in p["testo"] or "EMA" in p["testo"]
                            for p in plan))

    def test_selezione_semantica_di_un_gruppo_non_inventa_fonti(self):
        plan,members=semantic_plan(self.rows,max_groups=3)
        selected=expand_selected([plan[0]],members)
        self.assertTrue(selected)
        self.assertTrue(all(r in self.rows for r in selected))
        self.assertLess(len(selected),len(self.rows))

    def test_modalita_legacy_per_confronto_qualita(self):
        plan,members=semantic_plan(self.rows,mode="righe")
        self.assertEqual(len(plan),len(self.rows))
        self.assertEqual(expand_selected(plan,members),self.rows)
        self.assertEqual(selection_mode({}),"raggruppata")
        self.assertEqual(selection_mode({"FARMAQUERY_TAG_SELECTION_MODE":"righe"}),"righe")
        with self.assertRaises(ValueError):
            selection_mode({"FARMAQUERY_TAG_SELECTION_MODE":"invalida"})

    def test_quote_non_sono_risposte_errate(self):
        class RateLimitError(Exception):
            status_code=429
        err=EnginePhaseError("selezione TAG",RateLimitError("PROVIDER_SECRETS"))
        classification=diagnose_error(err)
        self.assertEqual(classification["codice"],"QUOTA")
        self.assertEqual(classification["fase"],"selezione TAG")
        user_message=label_error(err)["risposta"]
        self.assertIn("QUOTA",user_message)
        self.assertNotIn("PROVIDER_SECRETS",user_message)

    def test_chiavi_e_testo_non_ritornano_dal_diagnostico(self):
        err=EnginePhaseError("connessione LLM",RuntimeError("NON_CONDIVIDERE_CHIAVE"))
        info=diagnose_error(err)
        self.assertEqual(info["codice"],"ALTRO")
        self.assertNotIn("NON_CONDIVIDERE_CHIAVE",str(info))


if __name__=="__main__":
    unittest.main()
