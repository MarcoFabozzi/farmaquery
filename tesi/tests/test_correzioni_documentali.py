"""Test del recupero integrale TAG su note fittizie senza API esterne."""
import sqlite3
import unittest
from tesi.contesto_integrale import richiede_sezione_completa, contesto_integrale


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
