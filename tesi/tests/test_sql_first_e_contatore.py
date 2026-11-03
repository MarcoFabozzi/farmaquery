"""Test SQL-first sullo snapshot e regressione conteggio delle chiamate LLM."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from tesi.prepara_snapshot_online import ROOT,build_snapshot
from tesi.recupero_sql_first import retrieve_category_sql_first
from tesi import pilota_tag_vs_sql as engine
from tesi.contatore_llm import measure_requests,direct_attempt,instrument_lotus


QUESTION=("Quali medicinali citati nelle note regionali della Campania "
          "per malattie neuromuscolari prevedono la prescrizione presso "
          "l'AOU Federico II? Indica medicinale, indicazione e pagina.")


class SqlFirstSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.sqlite=Path(cls.tmp.name)/"static.sqlite"
        build_snapshot(ROOT,cls.sqlite,Path(cls.tmp.name)/"manifest.json")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sql_recupera_tutte_le_note_prima_della_preselezione(self):
        with closing(sqlite3.connect(self.sqlite)) as db:
            db.row_factory=sqlite3.Row
            rows,meta=retrieve_category_sql_first(db,QUESTION,max_rows=180)
            sql_ids={r[0] for r in db.execute(
                "SELECT DISTINCT nota_id FROM pagine "
                "WHERE testo LIKE '%federico%' AND metodo IN ('TESTO','OCR')")}
        self.assertTrue(meta["applicabile"])
        self.assertEqual(meta["tipo"],"SQL_PRIMA_DEL_TESTO")
        self.assertEqual(meta["note_con_centro_sql"],len(sql_ids))
        self.assertEqual(meta["note_con_centro_sql"],161)
        self.assertEqual(len(rows),17)
        self.assertFalse(meta["preselezione_troncata"])
        self.assertTrue(all(x["fonti"] and x["passaggi_sintesi"]
                            and x["farmaco_sql"] for x in rows))
        names={x["farmaco_sql"] for x in rows}
        self.assertIn("GAMTEN",names)
        self.assertIn("HYQVIA CIDP",names)

    def test_produzione_evidenze_unificata_per_lotus(self):
        with closing(sqlite3.connect(self.sqlite)) as db:
            db.row_factory=sqlite3.Row
            rows=engine.evidence_candidates(db,QUESTION,max_rows=180)
        self.assertTrue(any(r.get("note_sql_esaminate")==161 for r in rows))
        self.assertTrue(all(r["tipo"]=="REGIONE" for r in rows))
        self.assertTrue(any("GAMTEN" in r["testo"] for r in rows))

    def test_limite_segnalato_non_dichiarato_esaustivo(self):
        with closing(sqlite3.connect(self.sqlite)) as db:
            db.row_factory=sqlite3.Row
            rows,info=retrieve_category_sql_first(db,QUESTION,max_rows=4)
        self.assertEqual(len(rows),4)
        self.assertTrue(info["preselezione_troncata"])
        self.assertTrue(all(r["documenti_troncati"] for r in rows))

    def test_senza_categoria_non_modifica_text_to_sql(self):
        with closing(sqlite3.connect(self.sqlite)) as db:
            db.row_factory=sqlite3.Row
            rows,info=retrieve_category_sql_first(
                db,"Qual è la classe AIFA di BRUKINSA?")
        self.assertEqual(rows,[])
        self.assertFalse(info["applicabile"])


class CallsMeasurementTests(unittest.TestCase):
    def test_conta_due_chiamate_dirette_isolate(self):
        with measure_requests() as counter:
            direct_attempt()
            direct_attempt()
            self.assertEqual(counter.payload()["chiamate_llm_effettive"],2)
        with measure_requests() as second:
            self.assertEqual(second.payload()["chiamate_llm_effettive"],0)

    def test_lotus_conta_messaggi_trasmessi_e_non_batch(self):
        class FakeLotusLM:
            def _process_uncached_messages(self,data,*args,**kwargs):
                return [{"text":"ok"}]*len(data)
        lm=FakeLotusLM()
        with measure_requests() as counter:
            self.assertTrue(instrument_lotus(lm))
            lm._process_uncached_messages([1,2,3],{},False,"test")
            direct_attempt()
            self.assertEqual(counter.payload()["chiamate_llm_lotus"],3)
            self.assertEqual(counter.payload()["chiamate_llm_effettive"],4)

    def test_quando_non_si_puo_contare_lotus_non_inventa_zero(self):
        with measure_requests() as counter:
            self.assertFalse(instrument_lotus(object()))
            direct_attempt()
            stats=counter.payload()
            self.assertFalse(stats["conteggio_llm_completo"])
            self.assertIsNone(stats["chiamate_llm_effettive"])


if __name__=="__main__":
    unittest.main()
