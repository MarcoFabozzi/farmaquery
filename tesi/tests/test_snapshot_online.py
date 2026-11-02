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
                db.row_factory=sqlite3.Row
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
                from tesi.recupero_gu import candidati_gu
                gu = candidati_gu(
                    db,"Secondo la determina GU 23A02767, quali AIC di WEGOVY "
                       "sono elencati e quale classe è attribuita?")
                self.assertTrue(gu, "WEGOVY non recuperato nel corpus GU reale")
                self.assertTrue(all(r["codice"]=="23A02767" for r in gu))
                self.assertTrue(any("WEGOVY" in r["testo"].upper() for r in gu))
                self.assertIn("gazzetta",info["fonti_ufficiali"])
                # Il nuovo recupero TAG funziona anche sul corpus regionale
                # reale, non solo sulle fixture sintetiche.
                from tesi.recupero_regionale import regional_candidates
                plu = regional_candidates(
                    db, "Quali centri sono riportati per PLUVICTO?", "pluvicto")
                self.assertTrue(plu, "Documento PLUVICTO non recuperato")
                self.assertTrue(all("#p" in r["fonte"] for r in plu))
                self.assertTrue(any("PLUVICTO" in r["testo"].upper()
                                    for r in plu))
                # Ricerca di categoria sul corpus regionale reale: fonte
                # verificabile per ciascuna pagina (non una lista concatenata).
                q=("Quali farmaci per malattie neuromuscolari "
                   "si prescrivono al Federico II?")
                docs=regional_candidates(db,q)
                self.assertTrue(docs, "Nessun documento candidato per categoria")
                self.assertTrue(all(
                    r["fonte"].count("#p")==1 and " | archivio: " in r["fonte"]
                    for r in docs))
                self.assertTrue(all(
                    len(r.get("fonti",[]))>=1 and
                    all(ref.count("#p")==1 for ref in r["fonti"])
                    for r in docs))
                self.assertTrue(all("testo_selezione" in r for r in docs))
                # Verifica di RICHIAMO sulle note presenti e già controllate:
                # un recupero top-k non deve perdere i documenti per Duchenne
                # e miastenia solo perché altre note hanno più occorrenze.
                file_names=" | ".join(
                    str(r["testo"]).split("; farmaco candidato:",1)[0]
                    for r in docs).upper()
                self.assertIn("DUVYZAT",file_names,
                              "Il recupero categoria ha escluso la nota DUVYZAT")
                self.assertIn("ULTOMIRIS",file_names,
                              "Il recupero categoria ha escluso la nota ULTOMIRIS")
                self.assertTrue(all("copertura_documenti" in r for r in docs))
                # Verifica TUTTO il passaggio allo strato TAG, non solo FTS.
                from tesi.pilota_tag_vs_sql import evidence_candidates
                from tesi.sintesi_tag import compact_category_evidence
                complete=evidence_candidates(db,q,max_rows=22)
                compact=compact_category_evidence(complete)
                combined=" | ".join(
                    str(d["documento_e_medicinale_candidato"])
                    for d in compact).upper()
                self.assertIn("DUVYZAT",combined,
                              "DUVYZAT perso tra recupero e sintesi TAG")
                self.assertIn("ULTOMIRIS",combined,
                              "ULTOMIRIS perso tra recupero e sintesi TAG")
                self.assertTrue(all(d.get("passaggi") for d in compact))
                print("Documenti recuperati per categoria:",len(docs),
                      "documenti consegnati alla sintesi:",len(compact),
                      "documenti nello snapshot:",docs[0]["copertura_documenti"])


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
