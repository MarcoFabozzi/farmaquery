"""Test di sintesi TAG compatta senza consumare API Gemini."""
import json
import unittest

from tesi.sintesi_tag import (compact_category_evidence,CATEGORY_SYSTEM,
                              CATEGORY_RESPONSE_TIMEOUT_SECONDS,
                              missing_category_candidates,
                              revise_category_if_needed)
from tesi.pilota_tag_vs_sql import ask
from unittest.mock import patch


class CompactTagSynthesisTests(unittest.TestCase):
    def setUp(self):
        self.docs=[]
        for i in range(8):
            pages=[]
            for p in (1,2,3,4):
                pages.append("[pagina "+str(p)+"] "+("Documento "
                             +str(i)+" patologia miastenia centro Federico II. ")*25)
            self.docs.append({
                "chiave":"REGIONE:DOC:"+str(i),
                "tipo":"REGIONE",
                "testo":"Documento: TERAPIA "+str(i)+
                        "; farmaco candidato: TERAPIA "+str(i)+"; "+
                        " ".join(pages),
                "fonte":"2026/T"+str(i)+".pdf#p1 | archivio: https://regione.test/note.zip",
                "fonti":[
                    "2026/T"+str(i)+".pdf#p"+str(p)+
                    " | archivio: https://regione.test/note.zip"
                    for p in (1,2,3,4)],
            })

    def test_compressione_e_fonti(self):
        compact=compact_category_evidence(self.docs)
        self.assertEqual(len(compact),8)
        self.assertLess(len(json.dumps(compact,ensure_ascii=False)),24000)
        for i,doc in enumerate(compact):
            self.assertEqual(doc["chiave"],"REGIONE:DOC:"+str(i))
            self.assertEqual(len(doc["fonti"]),3)
            self.assertEqual([x["pagina"] for x in doc["passaggi"]],[1,2,3])
            self.assertTrue(all("Federico II" in x["estratto"]
                                for x in doc["passaggi"]))
            self.assertTrue(all("#p" in f for f in doc["fonti"]))

    def test_contesto_dedicato_non_certifica_candidati(self):
        self.assertIn("non è necessariamente",CATEGORY_SYSTEM)
        self.assertIn("medicinale",CATEGORY_SYSTEM)
        self.assertIn("centro",CATEGORY_SYSTEM)


    def test_revisione_categoria_non_promuove_candidati_senza_prova(self):
        # Un documento candidato non implica che la nota autorizzi il
        # medicinale per la patologia e struttura richieste.
        docs=[{
            "documento_e_medicinale_candidato":
                "Documento: ESEMPIO.pdf; farmaco candidato: ESEMPIO; ",
            "passaggi":[{"pagina":2,"estratto":
                         "Il centro è riferito a un'altra indicazione."}],
            "fonti":["2025/ESEMPIO.pdf#p2"]
        }]
        calls=[]
        def fake_ask(*args,**kwargs):
            calls.append(args)
            return "Nessuna associazione dimostrabile nello snapshot.",{
                "token_input":5,"token_output":5,"costo_usd":0.0}
        original="Non documentato nello snapshot."
        output,usage,revised,missing=revise_category_if_needed(
            "modello","Quali farmaci neuromuscolari al Federico II?",
            original,docs,fake_ask)
        self.assertTrue(revised)
        self.assertEqual(len(calls),1)
        self.assertEqual(output,original)
        self.assertEqual(missing,["ESEMPIO"])

    def test_non_richiede_revisione_se_tutti_i_documenti_sono_elencati(self):
        docs=[{
            "documento_e_medicinale_candidato":
                "Documento: ESEMPIO.pdf; farmaco candidato: ESEMPIO; ",
            "passaggi":[{"pagina":2,"estratto":"Miastenia e centro di esempio."}],
            "fonti":["2025/ESEMPIO.pdf#p2"]
        }]
        answer="Medicinale: ESEMPIO — indicazione, pagina 2."
        self.assertEqual(missing_category_candidates(answer,docs),[])
        def no_ask(*args,**kwargs):
            raise AssertionError("La seconda chiamata non è necessaria")
        output,usage,revised,missing=revise_category_if_needed(
            "modello","Quali farmaci neuromuscolari?",answer,docs,no_ask)
        self.assertFalse(revised)
        self.assertIsNone(usage)
        self.assertEqual(output,answer)

    def test_ask_timeout_e_limite_risposta_separati(self):
        class Usage:
            prompt_tokens=30
            completion_tokens=20
        class Message:
            content="Risposta breve."
        class Choice:
            message=Message()
        class Response:
            usage=Usage()
            choices=[Choice()]
        # Il workflow sperimentale non installa litellm: una finta libreria
        # controlla la chiamata senza richiedere provider né dipendenze extra.
        from types import SimpleNamespace
        from unittest.mock import Mock
        from unittest.mock import patch as patch_module
        import sys
        mocked=Mock(return_value=Response())
        fake=SimpleNamespace(completion=mocked,
                             completion_cost=Mock(return_value=0.0))
        with patch_module.dict(sys.modules,{"litellm":fake}):
            answer,usage=ask("mock-model","Sistema",{"domanda":"test"},
                             timeout=CATEGORY_RESPONSE_TIMEOUT_SECONDS,max_tokens=1100)
        self.assertEqual(answer,"Risposta breve.")
        self.assertEqual(usage["token_input"],30)
        kwargs=mocked.call_args.kwargs
        self.assertEqual(CATEGORY_RESPONSE_TIMEOUT_SECONDS,90)
        self.assertEqual(kwargs["timeout"],90)
        self.assertEqual(kwargs["max_tokens"],1100)
        self.assertEqual(kwargs["num_retries"],0)


if __name__=="__main__":
    unittest.main()
