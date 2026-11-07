import sqlite3
import tempfile
from hashlib import sha256
from pathlib import Path
import unittest

from analisi_provvedimenti_llm import (
    verifica_analisi, leggi_testo, estratto_per_modello
)


class TestAnalisiProvvedimenti(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute("CREATE TABLE aifa_confezioni (aic TEXT PRIMARY KEY, nome TEXT)")
        self.con.execute("CREATE TABLE link_verificati (aic TEXT, ema_id TEXT)")
        self.con.execute("INSERT INTO aifa_confezioni VALUES (?,?)",
                         ("012345678", "Farmaco dimostrativo"))
        self.con.execute("INSERT INTO link_verificati VALUES (?,?)",
                         ("012345678", "EMEA/H/C/001234"))
        self.passage = "La confezione AIC 012345678 è classificata in classe H."
        self.fonti = {"atto": {"testo": self.passage,
                               "sha256": "abc",
                               "parziale": False,
                               "url": "https://www.gazzettaufficiale.it/test"}}

    def tearDown(self):
        self.con.close()

    def proposta(self, citazione=None, classe="H", aic="012345678"):
        return {"sintesi": "Bozza", "evidenze": [{
            "aic": aic, "classe": classe, "azione": "CLASSIFICAZIONE",
            "fonte_id": "atto", "citazione": citazione or self.passage,
            "spiegazione": "Descrizione da verificare",
        }]}

    def test_citazione_documentata(self):
        result = verifica_analisi(self.proposta(), self.fonti, self.con)
        self.assertEqual(len(result["evidenze_con_citazione_verificata"]), 1)
        self.assertEqual(result["evidenze_con_citazione_verificata"][0]["ema_id_documentati"],
                         ["EMEA/H/C/001234"])
        self.assertEqual(result["evidenze_con_citazione_verificata"][0]["stato"],
                         "DA_REVISIONARE_MANUALMENTE")

    def test_citazione_inventata(self):
        result = verifica_analisi(self.proposta(
            citazione="La confezione AIC 012345678 non è autorizzata."), self.fonti, self.con)
        self.assertEqual(result["evidenze_con_citazione_verificata"], [])
        self.assertEqual(result["evidenze_scartate"], 1)

    def test_aic_non_nel_testo(self):
        result = verifica_analisi(self.proposta(aic="099999999"), self.fonti, self.con)
        self.assertEqual(result["evidenze_con_citazione_verificata"], [])

    def test_classe_non_documentata(self):
        result = verifica_analisi(self.proposta(classe="C(nn)"), self.fonti, self.con)
        self.assertEqual(result["evidenze_con_citazione_verificata"], [])

    def test_percorso_e_hash(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            (base / "gazzetta_testi").mkdir()
            (base / "gazzetta_testi" / "atto.txt").write_text(self.passage, encoding="utf-8")
            hash_ = sha256(self.passage.encode()).hexdigest()
            value = leggi_testo(base, "gazzetta_testi/atto.txt", hash_, 15000)
            self.assertEqual(value["sha256"], hash_)
            with self.assertRaises(ValueError):
                leggi_testo(base, "gazzetta_testi/atto.txt", "wrong", 15000)
            with self.assertRaises(ValueError):
                leggi_testo(base, "../segreto.txt", hash_, 15000)

    def test_taglio_testo_lungo(self):
        testo, truncated = estratto_per_modello("x" * 24000, 15000)
        self.assertTrue(truncated)
        self.assertIn("[PARTE INTERMEDIA OMESSA]", testo)


if __name__ == "__main__":
    unittest.main()
