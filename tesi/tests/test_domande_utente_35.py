"""Verifica il set di 35 domande reali senza effettuare chiamate AI."""
import csv
from collections import Counter
from pathlib import Path
import unittest

from tesi.esegui_benchmark import load_questions

ROOT=Path(__file__).resolve().parents[2]
QUESTIONS=ROOT/"tesi"/"domande_utente_35.csv"


class DomandeUtenteTests(unittest.TestCase):
    def test_trentacinque_domande_benchmark(self):
        questions=load_questions(QUESTIONS)
        self.assertEqual(len(questions),35)
        self.assertEqual([q["id"] for q in questions],
                         [f"Q{i:02d}" for i in range(1,36)])
        self.assertEqual(Counter(q["categoria"] for q in questions),
                         {"AIFA":13,"EMA":9,"REGIONE":9,"MULTIFONTE":4})
        self.assertIn("Eutirox",questions[6]["domanda"])
        self.assertIn("CEVEDALO",questions[20]["domanda"])
        with QUESTIONS.open(encoding="utf-8-sig",newline="") as fd:
            rows=list(csv.DictReader(fd,delimiter=";"))
        self.assertEqual(len(rows),35)
        self.assertTrue(all(r["stato_validazione"]=="DA_VERIFICARE"
                            and not r["risposta_gold"]
                            and not r["fonti_gold"] for r in rows))
        self.assertTrue(all(q["domanda"].endswith("?") for q in questions))


if __name__=="__main__":
    unittest.main()
