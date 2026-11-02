"""Test del recupero TAG: il nome esatto prevale sulle combinazioni.

Nessuna chiave API, nessuna chiamata Gemini: misura le evidenze consegnate
a LOTUS, evitando di inquinare la risposta con farmaci non richiesti.
"""
import sqlite3
import unittest

from tesi.pilota_tag_vs_sql import (
    _question_kind,_search_aifa,_target,_facets,_multisource_evidence,
    evidence_candidates,terms,_target_db,
)


class TagRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        CREATE TABLE aifa_confezioni(
            aic TEXT,nome TEXT,principio_attivo TEXT,
            descrizione TEXT,classe_a_h_snapshot TEXT,classe_a_h_data TEXT
        );
        CREATE TABLE ema_medicinali(
            ema_id TEXT,nome TEXT,principio_attivo TEXT,
            stato_ema TEXT,data_decisione_ue TEXT,indicazione_ema TEXT,url_ema TEXT
        );
        CREATE TABLE note(id TEXT,percorso_zip TEXT,archivio_url TEXT);
        CREATE TABLE pagine(nota_id TEXT,numero_pagina INTEGER,
            testo TEXT,metodo TEXT);
        CREATE VIRTUAL TABLE pagine_fts USING fts5(
            nota_id UNINDEXED, numero_pagina UNINDEXED, testo);
        CREATE TABLE strutture_registri(
            id TEXT,medicinale TEXT,patologia TEXT,
            indicazione TEXT,struttura TEXT,data_riferimento TEXT,fonte_url TEXT
        );
        INSERT INTO aifa_confezioni VALUES
          ('001','ANTIREUMINA','ACIDO ACETILSALICILICO; CAFFEINA; PARACETAMOLO','Compresse',NULL,NULL),
          ('002','SARIDON','CAFFEINA; PARACETAMOLO; PROPIFENAZONE','Compresse',NULL,NULL),
          ('003','PARACETAMOLO','PARACETAMOLO','500 mg',NULL,NULL),
          ('004','TACHIPIRINA','PARACETAMOLO','500 mg compresse','A','2026-06-30'),
          ('005','TACHIPIRINA','PARACETAMOLO','1000 mg','C','2026-06-30'),
          ('006','TACHIPIRINA FLASHTAB','PARACETAMOLO','500 mg',NULL,NULL),
          ('007','BRUFEN','IBUPROFENE','600 mg compresse','A','2026-06-30');
        INSERT INTO ema_medicinali VALUES('EMA-PLU','PLUVICTO','LUTETIUM','Autorizzato','2022-12-01','Carcinoma prostatico metastatico resistente alla castrazione','https://ema.test/pluvicto');
        INSERT INTO aifa_confezioni VALUES('050419011','PLUVICTO','LUTETIUM','Soluzione','H','2026-06-30');
        INSERT INTO note VALUES('n1','note/DUVYZAT.pdf','https://campania.test/2026.zip');
        INSERT INTO pagine VALUES('n1',1,'I centri per DUVYZAT comprendono i presidi indicati','TESTO');
        INSERT INTO pagine_fts VALUES('n1',1,'I centri per DUVYZAT comprendono i presidi indicati');
        """)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_ignora_parole_generiche(self):
        self.assertEqual(_target("Qual è il principio attivo di Tachipirina?"),"tachipirina")
        self.assertEqual(_target("Che principio attivo ha paracetamolo?"),"paracetamolo")
        self.assertEqual(terms("Che principio attivo ha paracetamolo?"),["paracetamolo"])
        self.assertEqual(_question_kind("Che principio attivo ha paracetamolo?"),
                         "PRINCIPIO_ATTIVO")
        self.assertEqual(_target("Per quale malattia viene utilizzato Ozempic?"),
                         "ozempic")
        self.assertEqual(_target("Quali ospedali campani sono indicati per DUVYZAT?"),
                         "duvyzat")
        self.assertEqual(_target("Qualsiasi reparto di Neurologia in Campania "
                                 "può prescrivere ULTOMIRIS?"),"ultomiris")

    def test_pluvicto_riconosciuto_in_qualsiasi_posizione(self):
        questions = (
            "Per quale tumore è indicato PLUVICTO?",
            "Qual è la classe di rimborsabilità di PLUVICTO in Italia?",
            "Quali sono i centri autorizzati alla somministrazione di PLUVICTO in Campania?",
            "PLUVICTO: per quale tumore è indicato, quale classe ha in Italia?",
        )
        for question in questions:
            with self.subTest(question=question):
                self.assertEqual(_target_db(self.db, question), "pluvicto")
                found = evidence_candidates(self.db, question)
                self.assertTrue(found)
                self.assertIn("EMA", {r["tipo"] for r in found})
                self.assertIn("AIFA", {r["tipo"] for r in found})
        self.assertEqual(_question_kind(questions[0]), "EMA")

    def test_denominazione_composta(self):
        self.db.execute("INSERT INTO ema_medicinali VALUES "
                        "('EM-2','FARMACO PROVA','X','Autorizzato',NULL,"
                        "'Indicazione di test','https://example.test')")
        self.assertEqual(
            _target_db(self.db, "A cosa serve FARMACO PROVA?"), "farmaco prova")

    def test_esclude_specialita_composte_se_esiste_nome_esatto(self):
        rows=_search_aifa(self.db,"paracetamolo")
        self.assertTrue(rows)
        self.assertEqual({r["nome"] for r in rows},{"PARACETAMOLO"})
        evidence=evidence_candidates(self.db,"Che principio attivo ha paracetamolo?")
        self.assertTrue(evidence)
        self.assertTrue(all("ANTIREUMINA" not in r["testo"] and
                            "SARIDON" not in r["testo"] for r in evidence))
        self.assertTrue(any("principio attivo dichiarato: PARACETAMOLO"
                            in r["testo"] for r in evidence))

    def test_tachipirina_non_diventa_antireumina_o_saridon(self):
        evidence=evidence_candidates(self.db,"Qual è il principio attivo di Tachipirina?")
        self.assertTrue(evidence)
        aifa=[r for r in evidence if r["tipo"]=="AIFA"]
        self.assertTrue(aifa)
        self.assertTrue(all("Medicinale: TACHIPIRINA;" in r["testo"] for r in aifa))
        self.assertTrue(all("PARACETAMOLO" in r["testo"] for r in aifa))

    def test_pluvicto_domanda_multifonte_con_lotus_che_non_seleziona(self):
        domanda=("PLUVICTO: per quale tumore è indicato, quale classe "
                 "ha in Italia e dove è prevista la somministrazione in Campania?")
        self.assertEqual(_target(domanda),"pluvicto")
        self.assertEqual(_facets(domanda),{"EMA","AIFA","REGIONE"})
        righe=[
            {"tipo":"REGIONE","chiave":"n33#p2",
             "testo":"Nota regionale PLUVICTO con ospedali",
             "fonte":"Campania nota#p2"},
            {"tipo":"EMA","chiave":"EMA:pluvicto",
             "testo":"EMA PLUVICTO tumore della prostata",
             "fonte":"EMA 123"},
            {"tipo":"AIFA","chiave":"AIFA:123456789",
             "testo":"AIFA PLUVICTO confezione e classe H",
             "fonte":"AIFA 123456789"},
        ]
        # Filtro semantico che rifiuta le singole righe perché non
        # rispondono DA SOLE a tutte e tre le sottodomande.
        evidenze=_multisource_evidence(righe,[],domanda)
        self.assertEqual({r["tipo"] for r in evidenze},
                         {"REGIONE","EMA","AIFA"})
        # Se LOTUS seleziona già la riga EMA, conserva quella e
        # aggiunge le due parti restanti senza duplicati.
        evidenze=_multisource_evidence(righe,[righe[1]],domanda)
        self.assertEqual(len(evidenze),3)
        self.assertEqual(evidenze[0]["tipo"],"EMA")

    def test_pluvicto_parzialmente_documentato(self):
        domanda=("PLUVICTO: quale tumore, quale classe e dove "
                 "somministrato in Campania?")
        righe=[
            {"tipo":"EMA","chiave":"EMA:x","testo":"Indicazione",
             "fonte":"EMA"},
            {"tipo":"AIFA","chiave":"AIFA:y","testo":"Classe",
             "fonte":"AIFA"},
        ]
        evidenze=_multisource_evidence(righe,[],domanda)
        self.assertEqual({r["tipo"] for r in evidenze},{"EMA","AIFA"})
        # Non viene inventata una nota regionale inesistente.
        self.assertNotIn("REGIONE",{r["tipo"] for r in evidenze})

    def test_altro_medicinale_e_fonti_regionali(self):
        evidence=evidence_candidates(self.db,"Qual è il principio attivo di Brufen?")
        self.assertEqual([x["tipo"] for x in evidence],["AIFA"])
        self.assertIn("IBUPROFENE",evidence[0]["testo"])
        regional=evidence_candidates(
            self.db,"Quali centri campani sono indicati per DUVYZAT?")
        self.assertEqual(regional[0]["tipo"],"REGIONE")
        self.assertIn("DUVYZAT",regional[0]["testo"])
        self.assertIn("#p1",regional[0]["fonte"])


if __name__=="__main__":
    unittest.main()
