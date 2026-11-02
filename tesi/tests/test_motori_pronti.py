"""Test di completezza per il motore Text-to-SQL, senza API Gemini."""
import sqlite3
import unittest
from unittest.mock import patch

from tesi.pilota_tag_vs_sql import sql_method, _sql_context, SQL_ROW_LIMIT


class SQLReadinessTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        CREATE TABLE note(id TEXT, percorso_zip TEXT, archivio_url TEXT);
        CREATE TABLE pagine(nota_id TEXT, numero_pagina INT, testo TEXT);
        """)
        self.db.executemany(
            "INSERT INTO note VALUES (?, ?, ?)",
            [(str(i), "n"+str(i)+".pdf", "https://regione.test/note.zip")
             for i in range(110)]
        )

    def tearDown(self):
        self.db.close()

    def test_righe_sopra_limite_segnalate(self):
        sql=f"SELECT id FROM note ORDER BY CAST(id AS INT) LIMIT 100"
        mocked=[
            (sql, {"token_input":11,"token_output":5,"costo_usd":0.0}),
            ("Risposta di prova.", {"token_input":12,"token_output":6,"costo_usd":0.0}),
        ]
        with patch("tesi.pilota_tag_vs_sql.ask", side_effect=mocked) as llm:
            result=sql_method(self.db,"Quali note?", "mock-model")
        self.assertEqual(llm.call_count,2)
        self.assertEqual(result["stato"],"RISULTATI_PARZIALI")
        self.assertTrue(result["risultato_parziale"])
        self.assertEqual(result["righe_sql"],SQL_ROW_LIMIT)
        self.assertIn("non può essere considerato completo",result["risposta"])
        self.assertIn("ORDER BY",result["sql"])

    def test_query_vuota_non_spreca_seconda_chiamata(self):
        sql="SELECT id FROM note WHERE id='assente'"
        with patch("tesi.pilota_tag_vs_sql.ask",
                   return_value=(sql, {"token_input":11,"token_output":5,
                                       "costo_usd":None})) as llm:
            result=sql_method(self.db,"Nota assente?", "mock-model")
        self.assertEqual(llm.call_count,1)
        self.assertEqual(result["stato"],"NESSUNA_EVIDENZA")
        self.assertEqual(result["fonti"],[])
        self.assertEqual(result["righe_sql"],0)

    def test_limit_esatto_non_dichiarato_completo(self):
        sql="SELECT id FROM note ORDER BY id LIMIT 10"
        mocked=[
            (sql, {"token_input":11,"token_output":5,"costo_usd":None}),
            ("Dieci note.", {"token_input":12,"token_output":6,"costo_usd":None}),
        ]
        with patch("tesi.pilota_tag_vs_sql.ask",side_effect=mocked):
            result=sql_method(self.db,"Elenco delle note", "mock")
        self.assertTrue(result["risultato_parziale"])
        self.assertIn("parziali",result["risposta"])

    def test_cella_testo_troncata_segnalata(self):
        self.db.execute("INSERT INTO pagine VALUES ('1',1,?)",("A"*4000,))
        raw=self.db.execute("SELECT testo FROM pagine").fetchall()
        rows,cut=_sql_context(raw)
        self.assertTrue(cut)
        self.assertEqual(len(rows[0]["testo"]),2500)


if __name__=="__main__":
    unittest.main()
