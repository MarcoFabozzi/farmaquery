"""Controlli sul benchmark revisione relatore, senza chiamate API."""
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from tesi.audit_benchmark_regolatorio import CATEGORIES, load_benchmark
from tesi.esegui_benchmark import execute, load_questions

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmark_regolatorio_30.csv"
FROZEN = "bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53"


class BenchmarkRelatoreTests(unittest.TestCase):
    def test_categorie_fotografia_e_solo_gold_gia_verificati(self):
        records = load_benchmark(BENCHMARK)
        self.assertEqual(Counter(x["categoria"] for x in records), CATEGORIES)
        self.assertEqual({x["snapshot_sha256"] for x in records}, {FROZEN})
        validated = {x["id"] for x in records if x["stato_validazione"] == "VALIDATO"}
        self.assertEqual(validated, {"Q01", "Q05", "Q06", "Q07", "Q08",
                                     "Q09", "Q21", "Q28", "Q29"})
        q01=next(x for x in records if x["id"]=="Q01")
        self.assertEqual(q01["fonti_gold"],"EMA:EMEA/H/C/005483")
        self.assertIn("PSMA-positivo",q01["risposta_gold"])
        self.assertIn("taxani",q01["risposta_gold"])
        self.assertTrue(all(x["stato_validazione"] == "DA_VERIFICARE"
                            for x in records if x["categoria"] == "NEGATIVA"))
        self.assertTrue(all(not x["risposta_gold"] and not x["fonti_gold"]
                            for x in records if x["stato_validazione"] != "VALIDATO"))
        self.assertEqual(len(load_questions(BENCHMARK)), 30)

    def test_non_accepta_risposta_gold_non_verificata(self):
        rows = load_benchmark(BENCHMARK)
        pending=next(x for x in rows if x["stato_validazione"]=="DA_VERIFICARE")
        pending["risposta_gold"] = "Risposta non verificata"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "invalid.csv"
            with path.open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter=";")
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ValueError):
                load_benchmark(path)

    def test_runner_non_interroga_altra_fotografia_o_gold_non_validato(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            db = folder / "test.sqlite"
            db.write_bytes(b"snapshot-di-test")
            actual = sha256(db.read_bytes()).hexdigest()
            manifest = folder / "manifest.json"
            manifest.write_text(json.dumps({"sha256_sqlite": actual}), encoding="utf-8")
            out = folder / "risposte.csv"
            # La fotografia non coincide: interrompe prima del modello, anche in anteprima.
            with self.assertRaisesRegex(ValueError, "diverso snapshot"):
                execute(db, manifest, BENCHMARK, out, max_questions=1)
            questions = folder / "questions.csv"
            questions.write_text(
                "id;categoria;domanda;snapshot_sha256;stato_validazione\n"
                f"Q01;CONTROLLO;Qual è il risultato?;{actual};DA_VERIFICARE\n",
                encoding="utf-8",
            )
            self.assertEqual(
                execute(db, manifest, questions, out, max_questions=1)["esito"],
                "ANTEPRIMA_SENZA_CHIAMATE",
            )
            # Anche se il modello è fittizio, il test non deve avviare un esperimento.
            with self.assertRaisesRegex(ValueError, "gold non validati"):
                execute(db, manifest, questions, out,
                        model="model/test", max_questions=1, confirm=True)


if __name__ == "__main__":
    unittest.main()
