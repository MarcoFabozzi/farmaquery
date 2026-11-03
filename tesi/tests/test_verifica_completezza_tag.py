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

    def test_specificita_isotopo_estratta_dalla_fonte(self):
        rows=[{"testo":(
            "Il centro deve avere autorizzazione alla detenzione di "
            "Radioisotopo-177 per la somministrazione e l'abilitazione "
            "al registro della terapia."),"fonte":"nota#p2"}]
        usage={"token_input":5,"token_output":10,"costo_usd":0.0}
        revised=("È prevista autorizzazione alla detenzione "
                 "di Radioisotopo-177 e l'abilitazione al registro.")
        from tesi.verifica_completezza_tag import missing_requirement_cues
        omitted=missing_requirement_cues(
            "Quali requisiti sono richiesti?",
            "È prevista autorizzazione alla detenzione e registro.",rows)
        self.assertTrue(any("177" in x for x in omitted))
        answer,_,done,_=revise_if_needed(
            "mock","Quali requisiti sono richiesti?",
            "È prevista autorizzazione alla detenzione e registro.",
            rows,True,lambda *a,**kw:(revised,usage))
        self.assertTrue(done)
        self.assertIn("177",answer)

    def test_riesame_associazioni_terapeutiche_omesse(self):
        from tesi.verifica_completezza_tag import missing_therapy_associations
        rows=[{"testo":(
            "Tre indicazioni distinte: terapia A con X, terapia B con Y, "
            "terapia C con Z."),"fonte":"nota#p2"}]
        question="Quali tre indicazioni e rispettive combinazioni terapeutiche?"
        partial=("1. A: in associazione con X\n"
                 "2. B: in associazione con Y\n"
                 "3. C: indicazione presente nella nota")
        improved=("1. A: in associazione con X\n"
                  "2. B: in associazione con Y\n"
                  "3. C: in associazione con Z")
        self.assertTrue(missing_therapy_associations(question,partial,rows))
        self.assertFalse(missing_therapy_associations(question,improved,rows))
        result,_,done,_=revise_if_needed(
            "mock",question,partial,rows,True,
            lambda *a,**kw:(improved,
                {"token_input":5,"token_output":5,"costo_usd":0.0}))
        self.assertTrue(done)
        self.assertIn("con Z",result)

    def test_riesame_associazioni_senza_conteggio_esplicito(self):
        from tesi.verifica_completezza_tag import missing_therapy_associations
        rows=[{"testo":"Tre terapie distinte in diverse sezioni."}]
        q="Quali condizioni e associazioni terapeutiche per le nuove indicazioni?"
        answer="È previsto un trattamento in associazione con X."
        self.assertTrue(missing_therapy_associations(q,answer,rows))

    def test_nessuna_revisione_su_fonte_parziale(self):
        rows=[{"testo":"Associazioni diverse."}]
        answer,_,done,_=revise_if_needed(
            "mock","Quali tre indicazioni e combinazioni?",
            "In associazione a X",rows,False,
            lambda *a,**kw:self.fail("Non revisionare una fonte incompleta"))
        self.assertFalse(done)

if __name__=="__main__":
    unittest.main()