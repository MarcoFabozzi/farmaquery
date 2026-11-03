"""Controlli demo: documento, pagina e collegamenti verificabili."""
import unittest

from chatbot_widget import _citation_details


class CitationPresentationTests(unittest.TestCase):
    def test_pdf_in_zip_non_diventa_pdf_diretto_fittizio(self):
        ref=("note-regionali-2026/PLUVICTO.pdf#p2 | archivio: "
             "https://www.regione.campania.it/assets/archivio-2026.zip")
        info=_citation_details(ref)
        self.assertEqual(info["pagina"],2)
        self.assertTrue(info["archivio"])
        self.assertIn("pagina 2",info["titolo"])
        self.assertTrue(info["url"].endswith(".zip"))
        self.assertNotIn("#page=",info["url"])

    def test_pdf_diretto_aggiunge_pagina(self):
        ref=("note-regionali/nota.pdf#p3 | archivio: "
             "https://www.regione.campania.it/documents/nota.pdf")
        info=_citation_details(ref)
        self.assertFalse(info["archivio"])
        self.assertEqual(info["pagina"],3)
        self.assertTrue(info["url"].endswith("nota.pdf#page=3"))
        self.assertIn("pagina indicata",info["etichetta"])

    def test_link_ufficiale_ema_e_conservato(self):
        ref=("EMA EMEA/H/C/005483 | "
             "https://www.ema.europa.eu/en/medicines/human/EPAR/pluvicto")
        info=_citation_details(ref)
        self.assertIn("ema.europa.eu",info["url"])
        self.assertIsNone(info["pagina"])

    def test_url_esterno_non_viene_visualizzato(self):
        ref=("note/nota.pdf#p1 | archivio: "
             "https://www.regione.campania.it.example.net/nota.pdf")
        self.assertEqual(_citation_details(ref)["url"],"")
        self.assertEqual(_citation_details(ref)["pagina"],1)

    def test_url_con_credenziali_viene_bloccato(self):
        ref=("note/nota.pdf#p1 | archivio: "
             "https://utente:segreto@www.regione.campania.it/nota.pdf")
        self.assertEqual(_citation_details(ref)["url"],"")


if __name__=="__main__":
    unittest.main()
