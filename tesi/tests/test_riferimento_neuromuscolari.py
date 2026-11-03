"""Verifiche automatiche del riferimento clinico-documentale.

I test controllano la tracciabilità su uno snapshot dato, non giudicano
da soli la classificazione clinica. Il database NON è modificato.
"""
from __future__ import annotations

from collections import Counter
import gzip
import json
from pathlib import Path
import sqlite3
import unittest


ROOT=Path(__file__).resolve().parents[2]
REFERENCE=ROOT/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
REGIONAL_DB=ROOT/"risultati/regione_campania.sqlite.gz"
STATUS=ROOT/"risultati/stato_fonti/regione_campania.json"


class NeuromuscularReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold=json.loads(REFERENCE.read_text(encoding="utf-8"))
        cls.status=json.loads(STATUS.read_text(encoding="utf-8"))
        cls.db=sqlite3.connect(":memory:")
        cls.db.deserialize(gzip.decompress(REGIONAL_DB.read_bytes()))
        cls.db.row_factory=sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_corpi_fonti_immutabili_e_archivi_ufficiali(self):
        self.assertEqual(cls_ref:=self.gold["snapshot_sha256"],
                         "bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53")
        sources={x["anno"]:x for x in self.status["fonti"]}
        for year in self.gold["archivi_verificati"]:
            self.assertEqual(year["sha256_zip"],
                             sources[year["anno"]]["sha256"])
        self.assertEqual(len(self.gold["casi_positivi"]),14)
        self.assertEqual(self.gold["conta_core"],13)
        self.assertEqual(self.gold["conta_esteso"],14)

    def test_pdf_hash_pagine_indicazione_e_centro(self):
        seen=set()
        for item in self.gold["casi_positivi"]:
            name=item["medicinale"]
            self.assertNotIn(name,seen)
            seen.add(name)
            doc=self.db.execute(
                "SELECT id,sha256_pdf,zip_url FROM documenti WHERE path_zip=?",
                (item["pdf"],)).fetchone()
            self.assertIsNotNone(doc,name)
            self.assertEqual(doc["sha256_pdf"],item["sha256_pdf"],name)
            self.assertEqual(doc["zip_url"],item["archivio_ufficiale"],name)
            for key in ("pagina_indicazione","pagina_centro"):
                page=self.db.execute(
                    "SELECT testo FROM pagine WHERE documento_id=? AND pagina=?",
                    (doc["id"],item[key])).fetchone()
                self.assertIsNotNone(page,(name,key))
                self.assertGreater(len(page["testo"]),70)
            central=self.db.execute(
                "SELECT testo FROM pagine WHERE documento_id=? AND pagina=?",
                (doc["id"],item["pagina_centro"])).fetchone()["testo"]
            self.assertIn("federico",central.casefold(),name)
            if name=="HIZENTRA":
                self.assertIn("HIZENTRA",central.upper())
                self.assertEqual(
                    item["relazione_prova"],
                    "RINVIO_ESPLICITO_AGGIORNAMENTO_STESSI_CENTRI")
            else:
                indication=self.db.execute(
                    "SELECT testo FROM pagine WHERE documento_id=? AND pagina=?",
                    (doc["id"],item["pagina_indicazione"])).fetchone()["testo"]
                self.assertIn(name,indication.upper(),name)
        self.assertEqual(len(seen),len(self.gold["casi_positivi"]))

    def test_non_promuove_falsi_positivi_nei_gold(self):
        positives={x["medicinale"] for x in self.gold["casi_positivi"]}
        excluded={x["medicinale"] for x in self.gold["esclusioni_esaminate"]}
        self.assertFalse(positives & excluded)
        self.assertEqual(
            Counter(x["perimetro"] for x in self.gold["casi_positivi"]),
            Counter({"core":13,"esteso":1}))
        self.assertIn("SKYCLARYS",positives)
        self.assertIn("HIZENTRA",positives)


if __name__=="__main__":
    unittest.main()
