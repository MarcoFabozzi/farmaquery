"""Controlli del benchmark: Gold riferite ESCLUSIVAMENTE al database statico.

Non consulta fonti online, non corregge il testo OCR e non esegue LLM.
"""
import gzip
import hashlib
import json
import re
import sqlite3
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/"risultati/tesi_statico_20261102.sqlite.gz"
MANIFEST=ROOT/"risultati/tesi_statico_20261102.json"
CANDIDATES=ROOT/"tesi/FarmaQuery_Gold_35_20261109.json"

class SnapshotOnlyGoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=gzip.decompress(DB.read_bytes())
        expected=json.loads(MANIFEST.read_text(encoding="utf-8"))["sha256_sqlite"]
        assert hashlib.sha256(raw).hexdigest()==expected
        cls.db=sqlite3.connect(":memory:")
        cls.db.row_factory=sqlite3.Row
        cls.db.deserialize(raw)
        cls.gold=json.loads(CANDIDATES.read_text(encoding="utf-8"))["domande"]

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_questions_and_database_coverage(self):
        self.assertEqual(len(self.gold),35)
        self.assertEqual([q["id"] for q in self.gold],
                         [f"Q{i:02}" for i in range(1,36)])
        self.assertEqual({q["categoria"] for q in self.gold},
                         {"SEMPLICE","CATEGORIA_IMPLICITA","MULTIFONTE",
                          "NESSUNA_RISPOSTA","MULTIPLA"})

    def test_negative_gold_is_corpus_limited(self):
        names={r["name"] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        operational=("trattamenti","somministrazioni","pazienti",
                     "giacenze","ordini","fatture","pagamenti")
        self.assertFalse([n for n in names
                          if any(x in n.casefold() for x in operational)])
        for q in self.gold[25:30]:
            self.assertEqual(q["categoria"],"NESSUNA_RISPOSTA")
            self.assertRegex(q["risposta_gold"].casefold(),"non|manc")

    def test_regional_note_rystiggo_does_not_list_federico_in_extracted_text(self):
        rows=self.db.execute(
            "SELECT n.percorso_zip,p.numero_pagina,p.testo FROM note n "
            "JOIN pagine p ON p.nota_id=n.id "
            "WHERE n.nome_file='RYSTIGGO.pdf' ORDER BY p.numero_pagina"
        ).fetchall()
        self.assertEqual(len(rows),4)
        p3=rows[2]["testo"]
        self.assertIn("RYSTIGGO",p3)
        self.assertIn("prescrizione",p3.casefold())
        self.assertNotIn("federico",p3.casefold())
        aifa=self.db.execute(
            "SELECT struttura FROM strutture_registri "
            "WHERE UPPER(medicinale)='RYSTIGGO' "
            "AND LOWER(struttura) LIKE '%federico%'").fetchall()
        self.assertTrue(aifa)
        print("Q11: la Regione non riporta Federico nel testo estratto;"
              " AIFA lo riporta in tabella distinta. Non trasferire questo"
              " centro alla nota regionale.",flush=True)

    def test_ema_aifa_and_gu_structured_data(self):
        aifa=self.db.execute(
            "SELECT aic,classe_a_h_snapshot FROM aifa_confezioni "
            "WHERE UPPER(nome)='XEMBIFY' ORDER BY aic").fetchall()
        expected={
            "049488012":"H","049488024":"H","049488036":"H","049488048":"H",
            "049488051":None,"049488063":None,"049488075":None,
            "049488087":None,"049488099":None,
        }
        self.assertEqual({r["aic"]:r["classe_a_h_snapshot"] for r in aifa},
                         expected)
        siv={r["aic"]:r["classe_a_h_snapshot"] for r in self.db.execute(
            "SELECT aic,classe_a_h_snapshot FROM aifa_confezioni "
            "WHERE aic IN ('044020016','044020030')")}
        self.assertEqual(siv,{"044020016":"A","044020030":"H"})
        for name in ("WEGOVY","DUVYZAT","PLUVICTO"):
            self.assertTrue(self.db.execute(
                "SELECT 1 FROM ema_medicinali WHERE UPPER(nome)=?",
                (name,)).fetchone())
        gu=self.db.execute("SELECT documento_id,tipo_documento,LENGTH(testo) AS n "
                           "FROM gu_documenti WHERE codice='23A02767'").fetchall()
        print("WEGOVY_GU_DB_DOCUMENTS",[tuple(x) for x in gu],flush=True)
        seg=self.db.execute(
            "SELECT numero_segmento,substr(testo,1,6000) FROM gu_segmenti "
            "WHERE documento_id IN "
            "(SELECT documento_id FROM gu_documenti WHERE codice='23A02767')"
        ).fetchall()
        print("WEGOVY_GU_DB_SEGMENTS",[tuple(x) for x in seg][:5],flush=True)
        self.assertTrue(self.db.execute(
            "SELECT 1 FROM gu_atti WHERE codice='23A02767'").fetchone())

    def test_detailed_page_contents_for_review(self):
        # Stampa SOLO i blocchi gia' estratti dal database e associati al
        # questionario, per permettere di revisionare le risposte senza PDF.
        case_terms=[
            ("XEMBIFY","RNRL"),("XEMBIFY","MUP"),("KAYFANDA","File F"),
            ("KAYFANDA","SINFONIA"),("LIVMARLI Prot","SA.NI.A"),
            ("LIVMARLI Prot","03/11/2025"),("HYQVIA CIDP","HIZENTRA"),
            ("KIOVIG","Federico"),("KAFTRIO","Federico"),
            ("KALYDECO","Federico"),("ORKAMBI","Federico"),
            ("ALIFTREK","Federico"),("AGAMREE","Federico"),
            ("DUVYZAT","Federico"),("ZILBRYSQ","Federico"),
            ("AMVUTTRA Prot","Federico"),("DUPIXENT","BPCO"),
            ("PLUVICTO","Medicina Nucleare"),("HEMLIBRA","Piano Terapeutico"),
        ]
        for name,term in case_terms:
            docs=self.db.execute("SELECT id,percorso_zip FROM note "
                "WHERE nome_file LIKE ? COLLATE NOCASE ORDER BY anno DESC",
                ("%"+name+"%",)).fetchall()
            hits=[]
            for d in docs:
                pages=self.db.execute(
                    "SELECT numero_pagina,testo FROM pagine WHERE nota_id=?",
                    (d["id"],)).fetchall()
                for p in pages:
                    t=p["testo"]
                    at=t.casefold().find(term.casefold())
                    if at>=0:
                        excerpt=" ".join(t[max(0,at-160):at+330].split())
                        hits.append(d["percorso_zip"]+f'#p{p["numero_pagina"]} '+excerpt)
            print("GOLD_DB_ANCHOR",name,term,
                  json.dumps(hits[:4],ensure_ascii=False),flush=True)

if __name__=="__main__":
    unittest.main()
