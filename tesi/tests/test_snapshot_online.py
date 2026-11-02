"""Controlli sperimentali su ultimo snapshot ufficiale online, senza web."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tesi.prepara_snapshot_online import ROOT, build_snapshot, load_sources, sha_file


class SnapshotOnlineTests(unittest.TestCase):
    def test_fonti_aggiornate_senza_vincolo_maggio(self):
        states, ah = load_sources(ROOT)
        self.assertEqual(
            ah["data_riferimento"],
            states["aifa_ah"]["statistiche"]["data_riferimento_ah"]
        )
        self.assertTrue(ah["classi"])
        self.assertTrue(states["ema"]["fonti"]["ema"]["sha256"])
        self.assertTrue(states["regione"]["fonti"])

    def test_snapshot_unico_con_riferimenti(self):
        with tempfile.TemporaryDirectory() as td:
            dbfile=Path(td)/"esperimento.sqlite"
            manifest=Path(td)/"manifest.json"
            info=build_snapshot(ROOT,dbfile,manifest)
            self.assertEqual(sha_file(dbfile),info["sha256_sqlite"])
            self.assertEqual(info["tipo"],"SNAPSHOT_ONLINE_FISSO_PER_ESPERIMENTO")
            self.assertEqual(json.loads(manifest.read_text())["sha256_sqlite"],
                             info["sha256_sqlite"])
            with sqlite3.connect(dbfile) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertGreater(db.execute("SELECT COUNT(*) FROM pagine_fts").fetchone()[0],100)
                self.assertGreater(db.execute("SELECT COUNT(*) FROM note").fetchone()[0],100)
                self.assertGreater(db.execute("SELECT COUNT(*) FROM strutture_registri").fetchone()[0],1000)
                self.assertGreater(db.execute("SELECT COUNT(*) FROM aifa_confezioni").fetchone()[0],100000)
                self.assertGreater(db.execute("SELECT COUNT(*) FROM ema_medicinali").fetchone()[0],1000)
                self.assertGreater(db.execute("SELECT COUNT(*) FROM gu_atti").fetchone()[0],10)
                self.assertGreater(db.execute("SELECT COUNT(*) FROM gu_segmenti_fts").fetchone()[0],10)
                self.assertGreater(
                    db.execute("SELECT COUNT(*) FROM gu_documenti "
                               "WHERE tipo_documento='ALLEGATO'").fetchone()[0],0
                )
                self.assertGreater(info["conteggi"]["gu_documenti"],10)
                self.assertIn("gazzetta",info["fonti_ufficiali"])
                # Lo snapshot scientifico NON attribuisce C per esclusione.
                self.assertGreater(
                    db.execute("SELECT COUNT(*) FROM aifa_confezioni "
                               "WHERE classe_a_h_snapshot IS NULL").fetchone()[0],0
                )
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM aifa_confezioni "
                               "WHERE classe_a_h_snapshot NOT IN ('A','H')").fetchone()[0],0
                )
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pagine "
                    "WHERE metodo IN ('TESTO','OCR')").fetchone()[0] +
                    db.execute("SELECT COUNT(*) FROM pagine "
                    "WHERE metodo NOT IN ('TESTO','OCR')").fetchone()[0],
                    info["conteggi"]["pagine"])
                self.assertGreater(
                    db.execute("SELECT COUNT(*) FROM fonti_snapshot").fetchone()[0],4
                )


if __name__ == "__main__":
    unittest.main()
