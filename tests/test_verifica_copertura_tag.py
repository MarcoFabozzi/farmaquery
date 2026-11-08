"""Test del confronto copertura TAG, senza API esterne o diagnosi hardcoded."""
import gzip
import json
import sqlite3
from pathlib import Path
import unittest

from tesi import tag_automatico as auto
from tesi.recupero_progressivo import normalize_document_note_id
from tesi.verifica_copertura_tag import compare_center_coverage

QUESTION=(
    "Quali medicinali citati nelle note regionali della Campania "
    "per malattie neuromuscolari prevedono la prescrizione "
    "presso l'AOU Federico II? Indica documento e pagina."
)
SQL_R19=(
    "SELECT DISTINCT note.farmaco_candidato AS nome, "
    "note.indicazione_candidata AS indicazione, "
    "note.id AS documento_id, pagine.numero_pagina AS pagina_id "
    "FROM note JOIN pagine ON note.id=pagine.nota_id "
    "JOIN nota_centro_documentato ON "
    "note.id=nota_centro_documentato.nota_id "
    "AND pagine.numero_pagina=nota_centro_documentato.numero_pagina "
    "WHERE nota_centro_documentato.centro COLLATE NOCASE "
    "LIKE '%Federico II%'"
)
SQL_BROAD=(
    "SELECT DISTINCT n.id AS nota_id FROM note AS n "
    "JOIN pagine AS p ON p.nota_id=n.id "
    "WHERE p.testo LIKE '%Federico%'"
)


class CoverageGateTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
          CREATE TABLE note(id TEXT PRIMARY KEY,
            nome_file TEXT,anno INTEGER,protocollo_candidato TEXT,
            data_candidata TEXT,farmaco_candidato TEXT,
            indicazione_candidata TEXT,percorso_zip TEXT,archivio_url TEXT);
          CREATE TABLE pagine(nota_id TEXT,numero_pagina INTEGER,
            testo TEXT,metodo TEXT);
          CREATE TABLE nota_centro_documentato(
            nota_id TEXT,centro TEXT,numero_pagina INTEGER);
          INSERT INTO note VALUES
            ('a','a.pdf',2026,NULL,NULL,'MED-A','malattia alfa','a','u'),
            ('b','b.pdf',2026,NULL,NULL,'MED-B','malattia beta','b','u'),
            ('c','c.pdf',2026,NULL,NULL,'MED-C','altra','c','u');
          INSERT INTO pagine VALUES
            ('a',1,'MED-A indicazione alfa','TESTO'),
            ('a',2,'AOU Federico II centro prescrittore','TESTO'),
            ('b',1,'MED-B indicazione beta','TESTO'),
            ('b',2,'AOU Federico II centro prescrittore','TESTO'),
            ('c',1,'MED-C altra indicazione','TESTO'),
            ('c',2,'AOU Federico II centro prescrittore','TESTO');
          INSERT INTO nota_centro_documentato VALUES
            ('a','AOU Federico II',2);
        """)
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    def test_r19_1_su_3_attiva_controllo_copertura(self):
        sql,changed=normalize_document_note_id(SQL_R19)
        self.assertTrue(changed)
        first,partial=auto._run_generated_select(
            self.db,auto.validate_sql(sql))
        self.assertFalse(partial)
        self.assertEqual(len(first),1)
        reason,audit=compare_center_coverage(
            self.db,sql,QUESTION,first,
            auto._run_generated_select,auto.validate_sql
        )
        self.assertEqual(reason,"join_centri_documenti_potenzialmente_esclusi")
        self.assertEqual(audit["documenti_controllo_copertura"],3)
        self.assertEqual(audit["documenti_esclusi_primo_recupero"],2)
        self.assertTrue(audit["controllo_copertura_eseguito"])
        self.assertIn("LIKE '%Federico%'",audit["sql_controllo_copertura"])

    def test_primo_recupero_completo_non_attiva_altro_metodo(self):
        rows,partial=auto._run_generated_select(self.db,SQL_BROAD)
        self.assertFalse(partial)
        reason,audit=compare_center_coverage(
            self.db,SQL_BROAD,QUESTION,rows,
            auto._run_generated_select,auto.validate_sql
        )
        self.assertIsNone(reason)
        self.assertFalse(audit["controllo_copertura_eseguito"])

    def test_senza_centro_nella_domanda_non_amplia(self):
        sql,_=normalize_document_note_id(SQL_R19)
        first,_=auto._run_generated_select(self.db,sql)
        reason,audit=compare_center_coverage(
            self.db,sql,"Quali medicinali per una patologia?",
            first,auto._run_generated_select,auto.validate_sql
        )
        self.assertIsNone(reason)
        self.assertFalse(audit["controllo_copertura_eseguito"])

    def test_snapshot_r19_rileva_note_escluse_e_riferimento_incluso(self):
        base=Path(__file__).resolve().parents[1]
        dbfile=base/"risultati/tesi_statico_20261102.sqlite.gz"
        goldfile=base/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
        if not dbfile.is_file() or not goldfile.is_file():
            self.skipTest("Snapshot o riferimento non presenti")
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(dbfile.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            sql,_=normalize_document_note_id(SQL_R19)
            first,partial=auto._run_generated_select(
                db,auto.validate_sql(sql))
            self.assertFalse(partial)
            self.assertGreater(len(first),0)
            reason,audit=compare_center_coverage(
                db,sql,QUESTION,first,
                auto._run_generated_select,auto.validate_sql
            )
            self.assertEqual(
                reason,"join_centri_documenti_potenzialmente_esclusi")
            self.assertEqual(audit["documenti_controllo_copertura"],161)
            self.assertGreater(audit["documenti_esclusi_primo_recupero"],0)
            all_notes,_=auto._run_generated_select(
                db,auto.validate_sql(audit["sql_controllo_copertura"]))
            gold=json.loads(goldfile.read_text(encoding="utf-8"))
            source_ids={x["nota_id"] for x in all_notes}
            expected={x["sha256_pdf"] for x in gold["casi_positivi"]}
            self.assertTrue(expected<=source_ids)
            print("R20 SQL r19:",len({r["nota_id"] for r in first}),
                  "note nella SELECT, ",len(source_ids),
                  "nel controllo copertura, riferimento",len(expected))
        finally:
            db.close()


if __name__=="__main__":
    unittest.main()
