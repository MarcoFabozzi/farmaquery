"""Test della valutazione pilot: nessuna chiamata LLM e nessun giudizio clinico automatico."""
import json
from pathlib import Path
import unittest

from tesi.valuta_richiamo_medicinali import evaluate

ROOT = Path(__file__).resolve().parents[1]


class PilotNeuromuscolariTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = json.loads((ROOT / "riferimento_neuromuscolari_federico_ii_2026-11-03.json").read_text(encoding="utf-8"))
        cls.pilot = json.loads((ROOT / "pilota_neuromuscolari_2026-11-03.json").read_text(encoding="utf-8"))

    def test_core_e_sensibilita(self):
        out = evaluate(self.gold, self.pilot)
        tag = out["metodi"]["TAG"]["casi"]
        sql = out["metodi"]["Text-to-SQL"]["casi"]
        self.assertEqual((tag["core"]["corrispondenze_nomi"], tag["core"]["totale_gold"]), (7, 13))
        self.assertEqual((sql["core"]["corrispondenze_nomi"], sql["core"]["totale_gold"]), (4, 13))
        self.assertEqual((tag["core_senza_rinvii"]["corrispondenze_nomi"],tag["core_senza_rinvii"]["totale_gold"]), (7, 12))
        self.assertEqual((sql["core_senza_rinvii"]["corrispondenze_nomi"],sql["core_senza_rinvii"]["totale_gold"]), (4, 12))
        self.assertEqual((tag["esteso"]["corrispondenze_nomi"], tag["esteso"]["totale_gold"]), (7,14))
        self.assertEqual(out["confronto_core"]["non_riportati_da_nessuno"],
                         ["AMVUTTRA", "GAMTEN", "HIZENTRA", "WAINZUA"])
        self.assertEqual(out["confronto_core"]["vantaggio_tag_punti_percentuali"],23.08)
        self.assertFalse(out["validazione_esecuzioni_stesso_commit_e_snapshot"])

    def test_non_inventa_accuratezza_documentale(self):
        out = evaluate(self.gold, self.pilot)
        self.assertNotIn("accuratezza", out)
        self.assertEqual(out["metodi"]["Text-to-SQL"]["errori_documentali_verificati_nel_resoconto"][0]["medicinale"], "ULTOMIRIS")

    def test_blocca_hash_diverso_e_duplicati(self):
        p = json.loads(json.dumps(self.pilot))
        p["snapshot_sha256_riferimento"] = "sha-errato"
        with self.assertRaisesRegex(ValueError,"Hash"):
            evaluate(self.gold, p)
        p = json.loads(json.dumps(self.pilot))
        p["risultati"][0]["nomi_medicinali"].append("EVRYSDI")
        with self.assertRaisesRegex(ValueError,"duplicati"):
            evaluate(self.gold,p)


if __name__ == "__main__":
    unittest.main()
