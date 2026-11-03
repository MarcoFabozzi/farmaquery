"""Regressioni offline: falsi negativi e retry sicuri nei due motori.

I documenti sono fittizi, nessun modello o provider viene chiamato.
"""
import sqlite3
import unittest
from unittest.mock import patch

from errori_chatbot import EnginePhaseError
from tesi.pilota_tag_vs_sql import sql_method
from tesi.contesto_integrale import richiede_sezione_completa, contesto_integrale
from tesi.sql_category_support import select_generation_guidance


class DocumentRepairTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
            CREATE TABLE note (
              id TEXT PRIMARY KEY, nome_file TEXT, percorso_zip TEXT,
              anno INTEGER, farmaco_candidato TEXT,
              protocollo_candidato TEXT, data_candidata TEXT,
              indicazione_candidata TEXT, archivio_url TEXT
            );
            CREATE TABLE pagine (
              nota_id TEXT, numero_pagina INTEGER, testo TEXT, metodo TEXT
            );
            INSERT INTO note VALUES
              ('k','TERAPIA ALFA Prot.N.0116205-2026.pdf',
               'archivio-2026/TERAPIA ALFA Prot.N.0116205-2026.pdf',
               2026,'TERAPIA ALFA','0116205-2026',NULL,NULL,'https://test.invalid/2026.zip'),
              ('c','TERAPIA BETA Prot.N.0655032-2025.pdf',
               'archivio-2025/TERAPIA BETA Prot.N.0655032-2025.pdf',
               2025,'TERAPIA BETA','0655032-2025',NULL,NULL,'https://test.invalid/2025.zip');
            INSERT INTO pagine VALUES
              ('k',2,'Tre indicazioni distinte, terapia A+B, C+D e E+F.','TESTO'),
              ('k',3,'Il documento presenta una tabella di combinazioni.','TESTO'),
              ('c',3,'Si richiama la nota PG/2024/0503681 per SINFONIA.','TESTO');
        """)
        self.usage={"token_input":10,"token_output":5,"costo_usd":0.002}

    def tearDown(self):
        self.db.close()

    def test_zero_righe_protocollo_non_blocca_documento(self):
        q=("Quali tre indicazioni e combinazioni terapeutiche della nota "
           "TERAPIA ALFA 0116205/2026?")
        bad=("SELECT n.id AS nota_id,p.numero_pagina,p.testo FROM note n "
             "JOIN pagine p ON p.nota_id=n.id "
             "WHERE n.nome_file LIKE '%0116205/2026%' LIMIT 80")
        repaired=("SELECT n.id AS nota_id,p.numero_pagina,p.testo "
                  "FROM note n JOIN pagine p ON p.nota_id=n.id "
                  "WHERE n.nome_file LIKE '%TERAPIA ALFA%' LIMIT 80")
        with patch("tesi.pilota_tag_vs_sql.ask",side_effect=[
            (bad,self.usage),(repaired,self.usage),
            ("Tre indicazioni nella fonte.",self.usage)
        ]) as model:
            result=sql_method(self.db,q,"mock")
        self.assertEqual(result["sql_tentativi"],2)
        self.assertTrue(result["sql_riprova_documentale"])
        self.assertFalse(result["sql_correzione_operativa"])
        self.assertEqual(result["righe_sql"],2)
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["token_input"],30)
        self.assertIn("0116205/2026",result["sql_iniziale"])
        prompt=model.call_args_list[1].args[1]
        self.assertIn("ZERO RIGHE",prompt)
        hints=model.call_args_list[1].args[2]["metadati_note_candidate"]
        self.assertTrue(any(x["anno"]==2026 for x in hints))
        self.assertIn("TERAPIA ALFA",hints[0]["nome_file"])
        self.assertTrue(any("#p2" in ref for ref in result["fonti"]))

    def test_anno_della_nota_richiamata_non_elimina_la_citante(self):
        q=("Quale nota del 2024 richiama TERAPIA BETA nel 2025 "
           "per SINFONIA, e questo rimando annulla la precedente?")
        bad=("SELECT n.id AS nota_id,p.numero_pagina,p.testo "
             "FROM note n JOIN pagine p ON p.nota_id=n.id "
             "WHERE n.anno=2024 AND n.nome_file LIKE '%TERAPIA BETA%' LIMIT 80")
        repaired=("SELECT n.id AS nota_id,p.numero_pagina,p.testo "
                  "FROM note n JOIN pagine p ON p.nota_id=n.id "
                  "WHERE n.nome_file LIKE '%TERAPIA BETA%' LIMIT 80")
        with patch("tesi.pilota_tag_vs_sql.ask",side_effect=[
            (bad,self.usage),(repaired,self.usage),
            ("Richiamo operativo alla nota precedente.",self.usage)
        ]) as model:
            result=sql_method(self.db,q,"mock")
        hints=model.call_args_list[1].args[2]["metadati_note_candidate"]
        self.assertEqual(hints[0]["anno"],2025)
        self.assertTrue(result["sql_riprova_documentale"])
        self.assertEqual(result["righe_sql"],1)

    def test_operational_error_riparato_da_select_alla_stessa_fonte(self):
        q="Quale nota del 2023 è richiamata dalla nota TERAPIA ALFA 2026?"
        bad=("SELECT p.campo_inesistente,p.numero_pagina,n.id AS nota_id "
             "FROM note n JOIN pagine p ON p.nota_id=n.id "
             "WHERE n.nome_file LIKE '%TERAPIA ALFA%'")
        repaired=("SELECT n.id AS nota_id,p.numero_pagina,p.testo "
                  "FROM note n JOIN pagine p ON p.nota_id=n.id "
                  "WHERE n.nome_file LIKE '%TERAPIA ALFA%' LIMIT 80")
        with patch("tesi.pilota_tag_vs_sql.ask",side_effect=[
            (bad,self.usage),(repaired,self.usage),
            ("Testo della nota.",self.usage)
        ]) as model:
            result=sql_method(self.db,q,"mock")
        self.assertTrue(result["sql_correzione_operativa"])
        self.assertEqual(result["sql_tentativi"],2)
        self.assertIn("campo_inesistente",result["sql_iniziale"])
        self.assertEqual(result["righe_sql"],2)
        self.assertEqual(
            model.call_args_list[1].args[2]["tipo_errore_sql"],
            "COLONNA_NON_PRESENTE")

    def test_errore_della_seconda_query_non_causa_retry_infinito(self):
        q="Quale nota del 2024 richiama TERAPIA BETA nel 2025?"
        bad="SELECT p.colonna_assente FROM pagine p LIMIT 80"
        with patch("tesi.pilota_tag_vs_sql.ask",
                   side_effect=[(bad,self.usage),(bad,self.usage)]) as model:
            with self.assertRaises(EnginePhaseError) as caught:
                sql_method(self.db,q,"mock")
        self.assertEqual(model.call_count,2)
        self.assertEqual(caught.exception.phase,"esecuzione SQL")

    def test_selezione_vuota_non_diventa_assenza_provata(self):
        q="Quali indicazioni nella nota TERAPIA ALFA 2026?"
        bad=("SELECT n.id AS nota_id FROM note n "
             "WHERE n.nome_file LIKE '%file-sconosciuto%' LIMIT 80")
        with patch("tesi.pilota_tag_vs_sql.ask",
                   side_effect=[(bad,self.usage),(bad,self.usage)]) as model:
            result=sql_method(self.db,q,"mock")
        self.assertEqual(model.call_count,2)
        self.assertEqual(result["righe_sql"],0)
        self.assertEqual(result["stato"],"NESSUNA_RIGA_SQL")
        self.assertIn("NON dimostra",result["risposta"])
        self.assertTrue(result["risultato_parziale"])

    def test_guida_sql_non_usa_percorso_campania_e_tratta_protocolli(self):
        prompt=select_generation_guidance(
            "Quali centri della nota TERAPIA ALFA in Campania?")
        self.assertIn("trattini",prompt)
        self.assertIn("INNER JOIN",prompt)
        self.assertIn("Campania",prompt)


class IntegralNoteTests(unittest.TestCase):
    def test_domande_note_documentali_richiedono_contesto(self):
        questions=(
            "Quali tre indicazioni e rispettive combinazioni terapeutiche "
            "distingue la nota regionale TERAPIA ALFA 0116205/2026?",
            "Quali condizioni e associazioni terapeutiche distingue "
            "la nota regionale TERAPIA BETA 0403588/2026?",
            "Quale nota del 2023 è richiamata dalla nota TERAPIA ALFA "
            "2026 e come cambiano i canali?",
            "In relazione all'EGPA, quale nota precedente è richiamata "
            "da TERAPIA ALFA 2026?",
        )
        for q in questions:
            with self.subTest(q=q):
                self.assertTrue(richiede_sezione_completa(q))
        self.assertFalse(richiede_sezione_completa(
            "Qual è la classe AIFA di TERAPIA ALFA?"))

    def test_legge_tutte_le_pagine_della_nota_nominata(self):
        db=sqlite3.connect(":memory:")
        db.row_factory=sqlite3.Row
        db.executescript("""
          CREATE TABLE note(id TEXT,nome_file TEXT,anno INTEGER,
            farmaco_candidato TEXT,percorso_zip TEXT,archivio_url TEXT);
          CREATE TABLE pagine(nota_id TEXT,numero_pagina INTEGER,
            testo TEXT,metodo TEXT);
          INSERT INTO note VALUES('k','TERAPIA ALFA 0116205-2026.pdf',
            2026,'TERAPIA ALFA','2026/TERAPIA ALFA.pdf','https://test.invalid.zip');
          INSERT INTO pagine VALUES
            ('k',1,'Introduzione', 'TESTO'),
            ('k',2,'Indicazione 1 e combinazione A', 'TESTO'),
            ('k',3,'Indicazione 2 e combinazione B', 'TESTO');
        """)
        q=("Quali indicazioni e combinazioni distingue la nota "
           "TERAPIA ALFA 0116205/2026?")
        rows,complete=contesto_integrale(db,q,"TERAPIA ALFA")
        self.assertTrue(complete)
        self.assertEqual({x["fonte"].split("#p")[1][0] for x in rows},
                         {"1","2","3"})
        db.close()


if __name__=="__main__":
    unittest.main()
