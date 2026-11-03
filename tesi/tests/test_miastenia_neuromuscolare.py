"""Regressione della distinzione tra neuromuscolare e neurologia centrale."""
import unittest
from tesi.sintesi_tag import CATEGORY_SYSTEM


class NeuromuscularCategoryGuidanceTests(unittest.TestCase):
    def test_miastenia_non_esclusa_automaticamente(self):
        self.assertIn("miastenia gravis",CATEGORY_SYSTEM)
        self.assertIn("giunzione neuromuscolare",CATEGORY_SYSTEM)
        self.assertIn("NON va esclusa",CATEGORY_SYSTEM)
        self.assertIn("SPECIFICA indicazione",CATEGORY_SYSTEM)

    def test_restano_richieste_prove_documentali(self):
        self.assertIn("SOLO con informazioni esplicite",CATEGORY_SYSTEM)
        self.assertIn("centro richiesto",CATEGORY_SYSTEM)
        self.assertIn("PDF e pagina",CATEGORY_SYSTEM)


if __name__=="__main__":
    unittest.main()
