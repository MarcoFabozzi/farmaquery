"""Text-to-SQL standard: una sola SELECT, senza recupero semantico o retry."""
import sqlite3
import unittest
from unittest.mock import patch

from errori_chatbot import EnginePhaseError
from tesi.pilota_tag_vs_sql import sql_method, SQL_GENERATION_PROMPT


class StandardSqlTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
          CREATE TABLE ema_medicinali (
            ema_id TEXT,nome TEXT,principio_attivo TEXT,stato_ema TEXT,
            data_decisione_ue TEXT,indicazione_ema TEXT,url_ema TEXT
          );
          CREATE TABLE note(
            id TEXT,nome_file TEXT,percorso_zip TEXT,archivio_url TEXT
          );
          CREATE TABLE pagine(
            nota_id TEXT,numero_pagina INTEGER,testo TEXT,metodo TEXT
          );
          INSERT INTO ema_medicinali VALUES (
            'EMA-001','FARMACO X','sostanza a','Authorised','2026-06-01',
            'Indicazione documentata', 'https://www.ema.europa.eu/example');
          INSERT INTO note VALUES(
            'r1','FARMACO X.pdf','2026/FARMACO X.pdf',
            'https://www.regione.campania.it/note.zip');
          INSERT INTO pagine VALUES(
            'r1',1,'Indicazione documentata per la terapia A','TESTO');
        """)
        self.usage={"token_input":10,"token_output":5,"costo_usd":0.001}

    def tearDown(self):
        self.db.close()

    def test_ema_strutturato_risponde_con_una_select(self):
        query=("SELECT ema_id,nome,stato_ema,indicazione_ema "
               "FROM ema_medicinali WHERE nome='FARMACO X'")
        with patch("tesi.pilota_tag_vs_sql.ask",side_effect=[
            (query,self.usage),
            ("La scheda EMA indica una terapia documentata.",self.usage),
        ]) as llm:
            answer=sql_method(self.db,"Quale indicazione di FARMACO X?","mock")
        self.assertEqual(llm.call_count,2)
        self.assertEqual(answer["sql_tentativi"],1)
        self.assertEqual(answer["righe_sql"],1)
        self.assertEqual(answer["stato"],"OK")
        self.assertEqual(answer["versione_text_to_sql"],"standard-v1")
        self.assertEqual(answer["token_input"],20)
        self.assertTrue(any("EMA-001" in x for x in answer["fonti"]))
        self.assertEqual(llm.call_args_list[0].args[2],
                         {"schema":__import__("tesi.pilota_tag_vs_sql",
                                            fromlist=["SCHEMA"]).SCHEMA,
                          "domanda":"Quale indicazione di FARMACO X?"})

    def test_zero_righe_non_riprova_ne_sintetizza(self):
        query="SELECT nome FROM ema_medicinali WHERE nome='INESISTENTE'"
        with patch("tesi.pilota_tag_vs_sql.ask",
                   return_value=(query,self.usage)) as llm:
            answer=sql_method(self.db,"Quale farmaco inesistente?","mock")
        self.assertEqual(llm.call_count,1)
        self.assertEqual(answer["righe_sql"],0)
        self.assertEqual(answer["stato"],"NESSUNA_EVIDENZA")
        self.assertIn("non ha restituito risultati",answer["risposta"])

    def test_categoria_implicita_non_ha_indizi_ne_seconda_query(self):
        question="Quali medicinali per malattie neuromuscolari?"
        query=("SELECT nome_file FROM note "
               "WHERE nome_file LIKE '%neuromuscolari%'")
        with patch("tesi.pilota_tag_vs_sql.ask",
                   return_value=(query,self.usage)) as llm:
            answer=sql_method(self.db,question,"mock")
        self.assertEqual(llm.call_count,1)
        self.assertNotIn("contesto_categoria",
                         llm.call_args_list[0].args[2])
        self.assertNotIn("miastenia",SQL_GENERATION_PROMPT.casefold())
        self.assertEqual(answer["sql_tentativi"],1)
        self.assertEqual(answer["stato"],"NESSUNA_EVIDENZA")

    def test_nota_legge_testo_solo_se_select_lo_recupera(self):
        query=("SELECT n.id AS nota_id,p.numero_pagina,p.testo "
               "FROM note AS n JOIN pagine AS p ON p.nota_id=n.id "
               "WHERE n.nome_file LIKE '%FARMACO X%'")
        with patch("tesi.pilota_tag_vs_sql.ask",side_effect=[
            (query,self.usage),("Documento: pagina 1.",self.usage)
        ]) as llm:
            answer=sql_method(self.db,"Che cosa dice la nota X?","mock")
        self.assertEqual(llm.call_count,2)
        self.assertTrue(any("2026/FARMACO X.pdf#p1" in x
                            for x in answer["fonti"]))
        self.assertEqual(answer["righe_sql"],1)

    def test_sql_non_valido_non_si_rigenera(self):
        with patch("tesi.pilota_tag_vs_sql.ask",
                   return_value=("DELETE FROM note",self.usage)) as llm:
            with self.assertRaises(EnginePhaseError) as err:
                sql_method(self.db,"Cancella le note","mock")
        self.assertEqual(llm.call_count,1)
        self.assertEqual(err.exception.phase,"validazione SQL")

    def test_errore_sintattico_non_si_rigenera(self):
        with patch("tesi.pilota_tag_vs_sql.ask",
                   return_value=("SELECT FROM note WHERE",self.usage)) as llm:
            with self.assertRaises(EnginePhaseError) as err:
                sql_method(self.db,"Quali note?","mock")
        self.assertEqual(llm.call_count,1)
        self.assertEqual(err.exception.phase,"validazione SQL")

    def test_errore_operativo_non_si_rigenera(self):
        with patch("tesi.pilota_tag_vs_sql.ask",
                   return_value=("SELECT colonna_assente FROM note",self.usage)) as llm:
            with self.assertRaises(EnginePhaseError) as err:
                sql_method(self.db,"Quali note?","mock")
        self.assertEqual(llm.call_count,1)
        self.assertEqual(err.exception.phase,"esecuzione SQL")


if __name__=="__main__":
    unittest.main()
