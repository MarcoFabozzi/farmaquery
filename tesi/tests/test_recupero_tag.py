"""Test del recupero TAG: il nome esatto prevale sulle combinazioni.

Nessuna chiave API, nessuna chiamata Gemini: misura le evidenze consegnate
a LOTUS, evitando di inquinare la risposta con farmaci non richiesti.
"""
import sqlite3
import unittest

from tesi.pilota_tag_vs_sql import (
    _question_kind,_search_aifa,_target,evidence_candidates,terms,
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
