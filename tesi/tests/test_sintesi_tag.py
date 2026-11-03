"""Test di sintesi TAG compatta senza consumare API Gemini."""
import json
import unittest

from tesi.sintesi_tag import (compact_category_evidence,CATEGORY_SYSTEM,
                              CATEGORY_RESPONSE_TIMEOUT_SECONDS,
                              missing_category_candidates,
                              revise_category_if_needed)
from tesi.pilota_tag_vs_sql import ask
from tesi.revisione_categoria import verified_additions
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

    def test_revisione_rifiuta_fonti_inventate_e_pagine_errate(self):
        docs=[{
            "documento_e_medicinale_candidato":
                "Documento: TERAPIA X.pdf; farmaco candidato: TERAPIA X;",
            "passaggi":[{"pagina":3,"estratto":
                "Indicazione miastenia gravis generalizzata; "
                "Presidio AOU Federico II, Napoli."}],
            "fonti":["2024/TERAPIA X.pdf#p3 | archivio: esempio"]
        }]
        question="Quali farmaci neuromuscolari presso l'AOU Federico II?"
        valid={"nuove_voci":[{
            "confermato":True,"medicinale":"TERAPIA",
            "patologia":"Miastenia gravis",
            "indicazione":"Trattamento della miastenia",
            "pagina_indicazione":3,"pagina_centro":3,
            "citazione_indicazione":"Indicazione miastenia gravis generalizzata",
            "citazione_centro":"Presidio AOU Federico II, Napoli"
        }]}
        from tesi.sintesi_tag import _candidate_short_name
        additions=verified_additions(json.dumps(valid),docs,question,
                                     _candidate_short_name)
        self.assertEqual(len(additions),1)
        self.assertIn("pagina 3",additions[0])
        invalid=json.loads(json.dumps(valid))
        invalid["nuove_voci"][0]["pagina_centro"]=9
        self.assertEqual(verified_additions(
            json.dumps(invalid),docs,question,_candidate_short_name),[])
        invalid["nuove_voci"][0]["pagina_centro"]=3
        invalid["nuove_voci"][0]["citazione_centro"]="Centro non presente nello snapshot"
        self.assertEqual(verified_additions(
            json.dumps(invalid),docs,question,_candidate_short_name),[])
        invalid["nuove_voci"][0]["medicinale"]="MEDICINALE INVENTATO"
        self.assertEqual(verified_additions(
            json.dumps(invalid),docs,question,_candidate_short_name),[])

    def test_verifica_individuale_distingue_riscontri_e_rifiuti(self):
        def candidate(name,body):
            return {
                "documento_e_medicinale_candidato":
                    "Documento: "+name+".pdf; farmaco candidato: "+name+"; ",
                "passaggi":[{"pagina":2,"estratto":body}],
                "fonti":["2025/"+name+".pdf#p2 | archivio: prova"]
            }
        docs=[
            candidate("ALPHA",
                      "Indicazione miastenia gravis generalizzata. "
                      "Presidio AOU Federico II, Napoli."),
            candidate("BETA",
                      "Indicazione sclerosi multipla. "
                      "Presidio AOU Federico II, Napoli.")
        ]
        calls=[]
        def review(model,system,payload,**kwargs):
            name=payload["documenti_candidati_non_elencati"][0][
                "medicinale_candidato"]
            calls.append(name)
            if name=="ALPHA":
                content=json.dumps({"nuove_voci":[{
                    "confermato":True,"medicinale":name,
                    "patologia":"Miastenia gravis",
                    "indicazione":"Trattamento miastenia gravis",
                    "pagina_indicazione":2,"pagina_centro":2,
                    "citazione_indicazione":
                        "Indicazione miastenia gravis generalizzata",
                    "citazione_centro":"Presidio AOU Federico II, Napoli"
                }]})
            else:
                content=json.dumps({"nuove_voci":[]})
            return content,{"token_input":5,"token_output":4,
                            "costo_usd":0.002}
        audit=[]
        stats={}
        answer="Medicinale: GAMMA — già documentato.\n*Nota: verifica parziale."
        result,usage,revised,missing=revise_category_if_needed(
            "mock","Quali malattie neuromuscolari presso AOU Federico II?",
            answer,docs,review,audit=audit,stats=stats)
        self.assertEqual(calls,["ALPHA","BETA"])
        self.assertTrue(revised)
        self.assertIn("Medicinale: GAMMA",result)
        self.assertIn("Medicinale: ALPHA",result)
        self.assertNotIn("Medicinale: BETA",result)
        self.assertLess(result.index("Medicinale: ALPHA"),result.index("*Nota:"))
        self.assertEqual(stats["chiamate"],2)
        self.assertEqual(stats["accettati"],1)
        self.assertEqual(usage["token_input"],10)
        self.assertEqual([r["esito"] for r in audit],
                         ["accettato","non_proposto_dal_modello"])

    def test_citazioni_ocr_con_nome_ospedale_esteso(self):
        # Differenze innocue: abbreviazione di AOU, accenti e parole
        # interposte nel nome del centro realmente elencato.
        from tesi.sintesi_tag import _candidate_short_name
        source=("Presidi di riferimento regionale per la malattia rara "
                "Miastenia gravis generalizzata refrattaria (MGg). "
                "AOU UNIVERSITA' DEGLI STUDI DI NAPOLI FEDERICO II, "
                "NAPOLI - UOC di Neurologia.")
        candidate={
            "documento_e_medicinale_candidato":
                "Documento: MEDICINA DI PROVA.pdf; farmaco candidato: MEDICINA;",
            "passaggi":[{"pagina":3,"estratto":source}],
            "fonti":["2024/MEDICINA DI PROVA.pdf#p3"]
        }
        item={
            "confermato":True,"medicinale":"MEDICINA",
            "patologia":"Miastenia gravis generalizzata",
            "indicazione":"Trattamento della MGg refrattaria",
            "pagina_indicazione":3,"pagina_centro":3,
            "citazione_indicazione":
                "Trattamento della miastenia gravis generalizzata refrattaria",
            "citazione_centro":"AOU Federico II, Napoli"
        }
        audit=[]
        additions=verified_additions(
            json.dumps({"nuove_voci":[item]},ensure_ascii=False),
            [candidate],
            "Quali medicinali neuromuscolari prescritti presso l'AOU Federico II?",
            _candidate_short_name,diagnostics=audit)
        self.assertEqual(len(additions),1)
        self.assertEqual(audit[-1]["esito"],"accettato_con_ancore")
        self.assertIn("pagina 3",additions[0])
        self.assertIn("MEDICINA",additions[0])

    def test_ancore_non_convalidano_centri_o_diagnosi_assenti(self):
        from tesi.sintesi_tag import _candidate_short_name
        document={
            "documento_e_medicinale_candidato":
                "Documento: MEDICINA.pdf; farmaco candidato: MEDICINA;",
            "passaggi":[{"pagina":2,"estratto":
                "Indicazione per miastenia gravis generalizzata. "
                "Presidi: AORN Cardarelli, Napoli."}],
            "fonti":["2024/MEDICINA.pdf#p2"]
        }
        item={
            "confermato":True,"medicinale":"MEDICINA",
            "patologia":"Miastenia gravis",
            "indicazione":"Trattamento MGg",
            "pagina_indicazione":2,"pagina_centro":2,
            "citazione_indicazione":"Miastenia gravis generalizzata",
            "citazione_centro":"AOU Federico II, Napoli"
        }
        audit=[]
        self.assertEqual(verified_additions(
            json.dumps({"nuove_voci":[item]}),[document],
            "Medicinali neuromuscolari AOU Federico II",_candidate_short_name,
            diagnostics=audit),[])
        self.assertEqual(audit[-1]["esito"],"citazione_centro_non_trovata")
        # Una diagnosi presente in un'altra pagina non giustifica
        # un'associazione ricostruita con citazioni approssimative.
        doc2=dict(document)
        doc2["passaggi"]=[
            {"pagina":1,"estratto":"Miastenia gravis generalizzata refrattaria."},
            {"pagina":2,"estratto":
             "AOU UNIVERSITA DEGLI STUDI DI NAPOLI FEDERICO II."}
        ]
        doc2["fonti"]=["2024/MEDICINA.pdf#p1","2024/MEDICINA.pdf#p2"]
        item["pagina_indicazione"]=1
        item["citazione_indicazione"]=(
            "Trattamento della miastenia gravis generalizzata refrattaria")
        self.assertEqual(verified_additions(
            json.dumps({"nuove_voci":[item]}),[doc2],
            "Medicinali neuromuscolari AOU Federico II",_candidate_short_name),[])

    def test_rifiuto_di_citazione_mostra_testo_proposto(self):
        from tesi.sintesi_tag import _candidate_short_name
        doc={
            "documento_e_medicinale_candidato":
                "Documento: MEDICINA.pdf; farmaco candidato: MEDICINA;",
            "passaggi":[{"pagina":3,"estratto":
                         "Miastenia gravis. AOU Universita Federico II."}],
            "fonti":["2024/MEDICINA.pdf#p3"]
        }
        item={
            "confermato":True,"medicinale":"MEDICINA",
            "patologia":"Miastenia gravis",
            "indicazione":"Trattamento della miastenia",
            "pagina_indicazione":3,"pagina_centro":3,
            "citazione_indicazione":"Miastenia gravis",
            "citazione_centro":"AOU struttura inesistente"
        }
        audit=[]
        verified_additions(json.dumps({"nuove_voci":[item]}),[doc],
                           "Malattie neuromuscolari AOU Federico II",
                           _candidate_short_name,diagnostics=audit)
        self.assertEqual(audit[0]["esito"],"citazione_centro_non_pertinente")

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
