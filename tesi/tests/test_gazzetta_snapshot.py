"""Verifica import GU nello snapshot e recupero TAG, senza chiamate LLM."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tesi.gazzetta_snapshot import importa_gu, segmenta
from tesi.recupero_gu import candidati_gu, domanda_gu
from tesi.pilota_tag_vs_sql import validate_sql, _sql_sources


class GazzettaSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        folder = self.root / "risultati" / "gazzetta_testi"
        folder.mkdir(parents=True)
        self.body = ("DETERMINA WEGOVY. Classe di rimborsabilità C. " * 65)
        self.file = folder / "atto.txt"
        self.file.write_text(self.body, encoding="utf-8")
        self.digest = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.source = sqlite3.connect(":memory:")
        self.source.executescript("""
            CREATE TABLE gazzetta_atti (
              codice TEXT, data_pubblicazione TEXT, titolo TEXT, tipo TEXT,
              url_ufficiale TEXT, nominativi_campione TEXT, completezza TEXT,
              url_testo TEXT, testo_file TEXT, sha256_testo TEXT
            );
            CREATE TABLE gu_allegati (
              codice TEXT, url TEXT, testo_file TEXT, sha256 TEXT
            );
        """)
        self.source.execute("INSERT INTO gazzetta_atti VALUES (?,?,?,?,?,?,?,?,?,?)",
          ("23A02767", "2023-05-01", "WEGOVY", "DETERMINA",
           "https://www.gazzettaufficiale.it/eli/id/2023/05/01/23A02767/sg",
           json.dumps(["WEGOVY"]), "TESTO_NON_VERIFICATO",
           "https://www.gazzettaufficiale.it/atto", "gazzetta_testi/atto.txt",
           self.digest))
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row

    def tearDown(self):
        self.source.close()
        self.db.close()
        self.temp.cleanup()

    def test_importa_testi_e_query_fts(self):
        stats = importa_gu(self.db, self.source, self.root)
        self.assertEqual(stats["gu_atti"], 1)
        self.assertGreater(stats["gu_segmenti"], 1)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM gu_documenti").fetchone()[0], 1)
        self.assertTrue(domanda_gu("Cosa dice la determina GU 23A02767?"))
        matches = candidati_gu(self.db, "Secondo GU 23A02767 quale classe ha WEGOVY?")
        self.assertTrue(matches)
        self.assertEqual({r["codice"] for r in matches}, {"23A02767"})
        self.assertTrue(any("WEGOVY" in r["testo"] for r in matches))
        self.assertEqual(_sql_sources(self.db, [{"gu_codice":"23A02767"}]),
                         ["GU 23A02767 | https://www.gazzettaufficiale.it/eli/id/2023/05/01/23A02767/sg"])

    def test_tutti_segmenti_esplicito_senza_perdere_ultima_confezione(self):
        # Il nome del farmaco compare all'inizio, l'ultima confezione
        # solo nel segmento finale: FTS top-2 non basta.
        self.body=("WEGOVY classe C. " * 400 +
                   "AIC 049883111/E ultima confezione 3 penne")
        self.file.write_text(self.body,encoding="utf-8")
        self.digest=hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.source.execute("UPDATE gazzetta_atti SET sha256_testo=?",
                            (self.digest,))
        importa_gu(self.db,self.source,self.root)
        results=candidati_gu(
            self.db,
            "Quante confezioni elenca l'articolo 1 della determina 23A02767? "
            "Riporta tutti gli AIC.",limit=18)
        self.assertGreater(len(results),2)
        self.assertTrue(any("049883111/E" in item["testo"]
                            for item in results))
        self.assertEqual(len(results),self.db.execute(
            "SELECT COUNT(*) FROM gu_segmenti").fetchone()[0])

    def test_sql_sola_lettura_gu(self):
        q = validate_sql(
            "SELECT a.codice AS gu_codice, s.testo FROM gu_atti a "
            "JOIN gu_documenti d ON a.codice=d.codice "
            "JOIN gu_segmenti s ON s.documento_id=d.documento_id LIMIT 5")
        self.assertIn("gu_documenti", q)
        with self.assertRaises(ValueError):
            validate_sql("DROP TABLE gu_atti")

    def test_blocca_testo_manomesso(self):
        self.file.write_text("TESTO CAMBIATO", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            importa_gu(self.db, self.source, self.root)

    def test_segmentazione_copre_testo(self):
        text = "a" * 4100
        pieces = segmenta(text)
        self.assertTrue(pieces)
        self.assertLessEqual(max(map(len, pieces)), 1800)
        self.assertIn(text[-100:], pieces[-1])


if __name__ == "__main__":
    unittest.main()
