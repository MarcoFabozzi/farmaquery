"""Test demo: estrazione locale di una sola pagina da PDF in archivio."""
import io
import unittest
from zipfile import ZipFile

from demo_fonti_pdf import extract_cited_pdf, _validated_regional_archive


def build_zip(files):
    b=io.BytesIO()
    with ZipFile(b,"w") as z:
        for path,data in files.items():
            z.writestr(path,data)
    return b.getvalue()


class PDFArchiveTests(unittest.TestCase):
    def test_documento_dalla_cartella_originale(self):
        blob=build_zip({"archivio2025/PLUVICTO.pdf":b"%PDF-1.6\ntest",
                        "altro.pdf":b"%PDF-1.7\nextra"})
        self.assertEqual(
            extract_cited_pdf(blob,"archivio2025/PLUVICTO.pdf"),
            b"%PDF-1.6\ntest")

    def test_cartella_non_correlata_ma_nome_pdf_unico(self):
        blob=build_zip({"dentro/sottocartella/FASENRA.pdf":b"%PDF-1.7\ntest"})
        self.assertEqual(
            extract_cited_pdf(blob,"2026/FASENRA.pdf"),
            b"%PDF-1.7\ntest")

    def test_nome_ambiguo_non_estende_collegamento_arbitrario(self):
        blob=build_zip({"a/FASENRA.pdf":b"%PDF-1.7\na",
                        "b/FASENRA.pdf":b"%PDF-1.7\nb"})
        with self.assertRaisesRegex(ValueError,"univocamente"):
            extract_cited_pdf(blob,"2026/FASENRA.pdf")

    def test_altri_formati_non_trattati_come_pdf(self):
        blob=build_zip({"nota.pdf":b"HTML non PDF"})
        with self.assertRaisesRegex(ValueError,"non disponibile"):
            extract_cited_pdf(blob,"nota.pdf")

    def test_url_ufficiale_e_zip_obbligatori(self):
        url="https://www.regione.campania.it/assets/documents/note.zip"
        self.assertEqual(_validated_regional_archive(url),url)
        for malicious in ("https://invalid.example/note.zip",
                          "http://www.regione.campania.it/note.zip",
                          "https://www.regione.campania.it.evil.test/note.zip",
                          "https://user:pass@www.regione.campania.it/note.zip",
                          "https://www.regione.campania.it/nota.pdf"):
            with self.subTest(url=malicious):
                with self.assertRaises(ValueError):
                    _validated_regional_archive(malicious)


if __name__=="__main__":
    unittest.main()
