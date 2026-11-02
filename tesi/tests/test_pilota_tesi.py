import importlib.util
from pathlib import Path
import sqlite3
import unittest

FILE=Path(__file__).resolve().parents[1]/"pilota_tag_vs_sql.py"
spec=importlib.util.spec_from_file_location("pilota_tesi",FILE)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PilotaTests(unittest.TestCase):
    def test_solo_select(self):
        self.assertEqual(mod.validate_sql("SELECT nome_file FROM note LIMIT 2"),
                         "SELECT nome_file FROM note LIMIT 2")
        for sql in ("DELETE FROM note","DROP TABLE note",
                    "UPDATE note SET nome_file='x'",
                    "SELECT * FROM sqlite_master",
                    "SELECT * FROM main.note",
                    "SELECT 1; DELETE FROM note",
                    "SELECT load_extension('x') FROM note",
                    "SELECT * FROM pragma_database_list"):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                mod.validate_sql(sql)

    def test_fts_paginate(self):
        conn=sqlite3.connect(":memory:")
        conn.row_factory=sqlite3.Row
        conn.executescript("""
            CREATE TABLE note(id TEXT,percorso_zip TEXT,archivio_url TEXT);
            CREATE TABLE pagine(nota_id TEXT,numero_pagina INTEGER,testo TEXT,metodo TEXT);
            CREATE VIRTUAL TABLE pagine_fts USING fts5(nota_id UNINDEXED,numero_pagina UNINDEXED,testo);
        """)
        conn.execute("INSERT INTO note VALUES('n','archivio/TEST.pdf','https://www.regione.campania.it/archive.zip')")
        conn.execute("INSERT INTO pagine VALUES('n',1,'KEYTRUDA e centro prescrittore','TESTO')")
        conn.execute("INSERT INTO pagine_fts VALUES('n',1,'KEYTRUDA e centro prescrittore')")
        pages=mod.candidates(conn,"Quali centri sono previsti per KEYTRUDA?")
        self.assertEqual(len(pages),1)
        self.assertEqual(pages[0]["percorso_zip"],"archivio/TEST.pdf")
        conn.close()


if __name__=="__main__": unittest.main()
