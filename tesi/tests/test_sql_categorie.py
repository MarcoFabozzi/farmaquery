"""Regressioni Text-to-SQL su categorie implicite, senza chiamate API.

Non esiste una query SQL prestabilita in produzione: qui mock del modello.
Gli indizi di recupero sono condivisi con TAG; la risposta resta una
valutazione del modello su pagine e note originali.
"""
import sqlite3
import unittest
from unittest.mock import patch

from tesi.pilota_tag_vs_sql import sql_method
from tesi.sql_category_support import (
    category_sql_context,select_generation_guidance
)


class SqlCategoryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        CREATE TABLE note (
            id TEXT PRIMARY KEY, nome_file TEXT, percorso_zip TEXT,
            anno INT, farmaco_candidato TEXT, protocollo_candidato TEXT,
            data_candidata TEXT, indicazione_candidata TEXT,
            archivio_url TEXT
        );
        CREATE TABLE pagine (
            nota_id TEXT,numero_pagina INT,testo TEXT,metodo TEXT
        );
        CREATE TABLE strutture_registri (
            id TEXT,medicinale TEXT,patologia TEXT,indicazione TEXT,
            struttura TEXT,regione TEXT,data_riferimento TEXT,fonte_url TEXT
        );
        INSERT INTO note VALUES (
            'regional-1','NUOVO MEDICINALE.pdf',
            '2026/NUOVO MEDICINALE.pdf',2026,'TERAPIA ESEMPIO',NULL,
            NULL,NULL,'https://regione.test/note.zip'
        );
        INSERT INTO pagine VALUES
            ('regional-1',1,
             'TERAPIA ESEMPIO per miastenia gravis generalizzata','TESTO'),
            ('regional-1',2,
             'Presidi per miastenia gravis: AOU Federico II, Napoli','TESTO');
        """)
        self.question=(
            "Quali farmaci per malattie neuromuscolari "
            "si prescrivono al Federico II?"
        )

    def tearDown(self):
        self.db.close()

    def test_indizi_non_sono_nomi_di_farmaci_gold(self):
        category=category_sql_context(self.question)
        self.assertEqual(category["categoria_riconosciuta"],"neuromuscolar")
        self.assertIn("miastenia",category["indizi_di_ricerca_non_probatori"])
        prompt=select_generation_guidance(self.question)
        self.assertIn("pagine",prompt)
        self.assertIn("EXISTS",prompt)
        self.assertIn("categoria",prompt)
        self.assertIsNone(category_sql_context("Qual è la classe di PLUVICTO?"))

    def test_recupero_sql_tramite_seconda_select_generata(self):
        # Riproduce il falso negativo osservato: la prima SELECT cerca la
        # stringa astratta, la seconda il nome della patologia e il centro.
        first_sql=(
            "SELECT medicinale FROM strutture_registri "
            "WHERE patologia LIKE '%neuromuscolari%' LIMIT 80"
        )
        second_sql=(
            "SELECT n.id AS nota_id,p.numero_pagina,p.testo,"
            "n.nome_file,n.farmaco_candidato FROM note AS n "
            "JOIN pagine AS p ON p.nota_id=n.id "
            "WHERE EXISTS (SELECT 1 FROM pagine AS disease "
            "WHERE disease.nota_id=n.id "
            "AND disease.testo LIKE '%miastenia%') "
            "AND EXISTS (SELECT 1 FROM pagine AS center "
            "WHERE center.nota_id=n.id "
            "AND center.testo LIKE '%Federico II%') "
            "ORDER BY p.numero_pagina LIMIT 80"
        )
        usage={"token_input":12,"token_output":8,"costo_usd":0.002}
        with patch("tesi.pilota_tag_vs_sql.ask",
                   side_effect=[(first_sql,usage),(second_sql,usage),
                                ("TERAPIA ESEMPIO: miastenia gravis, "
                                 "AOU Federico II.",usage)]) as fake:
            result=sql_method(self.db,self.question,"mock-llm")
        self.assertEqual(fake.call_count,3)
        self.assertEqual(result["sql_tentativi"],2)
        self.assertIn("neuromuscolari",result["sql_iniziale"])
        self.assertIn("miastenia",result["sql"])
        self.assertEqual(result["righe_sql"],2)
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["token_input"],36)
        self.assertTrue(any("2026/NUOVO MEDICINALE.pdf#p1" in x
                            for x in result["fonti"]))
        self.assertTrue(any("2026/NUOVO MEDICINALE.pdf#p2" in x
                            for x in result["fonti"]))
        self.assertIn("TERAPIA ESEMPIO",result["risposta"])
        first_payload=fake.call_args_list[0].args[2]
        retry_payload=fake.call_args_list[1].args[2]
        self.assertIn("contesto_categoria",first_payload)
        self.assertIn("query_precedente_senza_righe",retry_payload)

    def test_sintassi_sql_errata_recuperata_senza_esecuzione(self):
        # Un ParseError non deve interrompere il benchmark quando il
        # modello può rigenerare una SELECT corretta e validata.
        bad_sql="SELECT FROM note WHERE"
        valid_sql=(
            "SELECT n.id AS nota_id,p.numero_pagina,p.testo,"
            "n.nome_file FROM note AS n JOIN pagine AS p "
            "ON n.id=p.nota_id LIMIT 80"
        )
        usage={"token_input":6,"token_output":4,"costo_usd":0.001}
        with patch("tesi.pilota_tag_vs_sql.ask",
                   side_effect=[(bad_sql,usage),(valid_sql,usage),
                                ("Documento: TERAPIA ESEMPIO.",usage)]) as fake:
            result=sql_method(self.db,self.question,"mock-llm")
        self.assertEqual(fake.call_count,3)
        self.assertTrue(result["sql_correzione_sintassi"])
        self.assertEqual(result["sql_tentativi"],2)
        self.assertIsNone(result["sql_iniziale"])
        self.assertEqual(result["righe_sql"],2)
        self.assertEqual(result["token_input"],18)
        retry_prompt=fake.call_args_list[1].args[1]
        retry_context=fake.call_args_list[1].args[2]
        self.assertIn("parser",retry_prompt)
        self.assertEqual(retry_context["query_sql_rifiutata_dal_parser"],
                         bad_sql)
        self.assertIn("SELECT",result["sql"])

    def test_seconda_query_malformata_resta_errore_sql(self):
        from errori_chatbot import EnginePhaseError
        usage={"token_input":4,"token_output":3,"costo_usd":None}
        with patch("tesi.pilota_tag_vs_sql.ask",
                   side_effect=[("SELECT FROM note WHERE",usage),
                                ("SELECT WHERE ORDER BY",usage)]) as fake:
            with self.assertRaises(EnginePhaseError) as caught:
                sql_method(self.db,self.question,"mock-llm")
        self.assertEqual(fake.call_count,2)
        self.assertEqual(caught.exception.phase,"validazione SQL")
        self.assertEqual(caught.exception.error_type,"ParseError")

    def test_operazione_sql_non_consentita_non_viene_ritentata(self):
        from errori_chatbot import EnginePhaseError
        usage={"token_input":4,"token_output":3,"costo_usd":None}
        with patch("tesi.pilota_tag_vs_sql.ask",
                   return_value=("DELETE FROM note",usage)) as fake:
            with self.assertRaises(EnginePhaseError) as caught:
                sql_method(self.db,self.question,"mock-llm")
        self.assertEqual(fake.call_count,1)
        self.assertEqual(caught.exception.error_type,"ValueError")

    def test_fallimento_due_select_non_diventa_assenza_documentale(self):
        sql=("SELECT medicinale FROM strutture_registri "
             "WHERE patologia LIKE '%categoria-inesistente%'")
        usage={"token_input":5,"token_output":4,"costo_usd":None}
        with patch("tesi.pilota_tag_vs_sql.ask",
                   side_effect=[(sql,usage),(sql,usage)]) as fake:
            result=sql_method(self.db,self.question,"mock-llm")
        self.assertEqual(fake.call_count,2)
        self.assertEqual(result["sql_tentativi"],2)
        self.assertEqual(result["righe_sql"],0)
        self.assertEqual(result["stato"],"NESSUNA_RIGA_SQL")
        self.assertIn("Non è una prova",result["risposta"])
        self.assertTrue(result["risultato_parziale"])


if __name__=="__main__":
    unittest.main()
