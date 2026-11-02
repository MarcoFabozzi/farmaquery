"""Prove senza LLM sulla completezza degli estratti per il TAG."""
import sqlite3
import unittest

from tesi.contesto_integrale import (
    AIC_RE, contesto_integrale,richiede_sezione_completa
)


class FullDocumentContextTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        CREATE TABLE gu_documenti(
          documento_id TEXT,codice TEXT,tipo_documento TEXT,
          url_fonte TEXT,sha256_testo TEXT,testo TEXT
        );
        CREATE TABLE gu_atti(codice TEXT);
        CREATE TABLE note(id TEXT,nome_file TEXT,anno INT,
          farmaco_candidato TEXT,percorso_zip TEXT,archivio_url TEXT);
        CREATE TABLE pagine(nota_id TEXT,numero_pagina INT,testo TEXT,metodo TEXT);
        """)
        body=(
            "Determina di esempio\nArt. 1\n"
            "Classificazione delle confezioni\n" +
            "A.I.C. n. 049883061/E 0,25 mg 1 penna, classe C\n" +
            "Testo" * 650 + "\n"+
            "A.I.C. n. 049883111/E 2,4 mg 3 penne, classe C\n"+
            "Art. 2\nAltra indicazione"
        )
        self.db.execute("INSERT INTO gu_atti VALUES (?)",("23A02767",))
        self.db.execute("INSERT INTO gu_documenti VALUES (?,?,?,?,?,?)",(
            "23A02767:atto","23A02767","ATTO","https://gu.test/23A02767",
            "hash",body))
        self.db.execute("INSERT INTO note VALUES (?,?,?,?,?,?)",(
            "nm","MEDICINALE CAMPIONE.pdf",2026,"MEDICINALE CAMPIONE",
            "2026/MEDICINALE CAMPIONE.pdf","https://regione.test/note.zip"))
        self.db.execute("INSERT INTO pagine VALUES (?,?,?,?)",(
            "nm",1,"Indicazione sintetica, non richiesta","TESTO"))
        self.table_page=(
            "Tabella 1 — centri per patologia ATTR-CM.\n"+
            "Intestazione ripetuta " * 200+
            "AO DEI COLLI\nAOU RUGGI\nAORN MOSCATI\n"+
            "AO SANT'ANNA\nAOU FEDERICO II\nAORN CARDARELLI")
        self.db.execute("INSERT INTO pagine VALUES (?,?,?,?)",(
            "nm",2,self.table_page,"OCR"))

    def tearDown(self):
        self.db.close()

    def test_gu_articolo_intero_con_lultimo_aic(self):
        q=("Quante confezioni sono nell'articolo 1 della determina "
           "23A02767? Riporta tutti gli AIC.")
        rows,complete=contesto_integrale(self.db,q,"MEDICINALE CAMPIONE")
        self.assertTrue(complete)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["aic_trovati_nel_testo"],
                         ["049883061/E","049883111/E"])
        self.assertIn("3 penne",rows[0]["testo"])
        self.assertNotIn("Altra indicazione",rows[0]["testo"])
        self.assertIn("Art. 1",rows[0]["testo"])
        self.assertEqual(len(AIC_RE.findall(rows[0]["testo"])),2)

    def test_regione_pagina_integrale_oltre_2150_caratteri(self):
        q=("Quali sono tutti i centri della Tabella 1, pagina 2, "
           "nota MEDICINALE CAMPIONE?")
        rows,complete=contesto_integrale(self.db,q,"MEDICINALE CAMPIONE")
        self.assertTrue(complete)
        self.assertEqual(len(rows),1)
        self.assertIn("AORN CARDARELLI",rows[0]["testo"])
        self.assertEqual(rows[0]["fonte"],
            "2026/MEDICINALE CAMPIONE.pdf#p2 | archivio: https://regione.test/note.zip")

    def test_pagina_specifica_non_enumerativa_recupera_originale(self):
        q=("Secondo la pagina 2 della nota MEDICINALE CAMPIONE, "
           "a quale scopo sono elencate le strutture?")
        self.assertTrue(richiede_sezione_completa(q))
        rows,complete=contesto_integrale(
            self.db,q,"MEDICINALE CAMPIONE")
        self.assertTrue(complete)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]["fonte"].endswith(
            "MEDICINALE CAMPIONE.pdf#p2 | archivio: https://regione.test/note.zip"))
        self.assertIn("AORN CARDARELLI",rows[0]["testo"])

    def test_troppo_lungo_non_dichiara_elenco_completo(self):
        q="Elenca tutti i centri della Tabella 1, pagina 2 per MEDICINALE CAMPIONE"
        rows,complete=contesto_integrale(
            self.db,q,"MEDICINALE CAMPIONE",max_chars=600)
        self.assertFalse(complete)
        self.assertTrue(rows)
        self.assertIn("TESTO TAGLIATO",rows[0]["testo"])
        self.assertFalse(rows[0]["integrale"])

    def test_non_modifica_domande_analitiche_senza_richiesta_integrale(self):
        self.assertFalse(richiede_sezione_completa(
            "Qual è la classe di PLUVICTO?"))
        self.assertTrue(richiede_sezione_completa(
            "Quali protocolli sono citati in CAMZYOS?"))
        self.assertTrue(richiede_sezione_completa(
            "Quante confezioni sono riportate nella determina?"))
        self.assertFalse(richiede_sezione_completa(
            "Qual è il numero di pazienti trattati in Campania?"))


if __name__=="__main__":
    unittest.main()
