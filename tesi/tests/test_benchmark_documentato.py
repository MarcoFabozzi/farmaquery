"""Il benchmark non inventa mai gold e mantiene lo stesso snapshot."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from tesi.crea_benchmark_documentato import generate
from tesi.prepara_snapshot_online import ROOT, build_snapshot


class DocumentedBenchmarkTests(unittest.TestCase):
    def test_36_question_and_evidence_provenance(self):
        with tempfile.TemporaryDirectory() as work:
            folder=Path(work)
            db=folder/"esperimento.sqlite"
            man=folder/"manifest.json"
            build_snapshot(ROOT,db,man)
            out=folder/"domande.csv"
            evidence=folder/"evidenze.jsonl"
            report=folder/"report.json"
            summary=generate(db,man,out,evidence,report)
            self.assertEqual(summary["categorie"],
                             {v:9 for v in ("DIRETTE","SEMANTICHE","RIMANDI","NEGATIVE")})
            with out.open(encoding="utf-8-sig",newline="") as fh:
                rows=list(csv.DictReader(fh,delimiter=";"))
            self.assertEqual(len(rows),36)
            self.assertEqual(len({r["id"] for r in rows}),36)
            self.assertTrue(all(r["stato_validazione"]=="DA_VERIFICARE" for r in rows))
            self.assertTrue(all(not r["risposta_gold"] and not r["fonti_gold"]
                                for r in rows))
            self.assertEqual(
                len(evidence.read_text(encoding="utf-8").splitlines()),36
            )
            first=json.loads(evidence.read_text(encoding="utf-8").splitlines()[0])
            self.assertTrue(first["file_pdf"])
            self.assertTrue(first["pagine_da_controllare"])
            self.assertEqual(summary["snapshot_sha256"],
                             json.loads(man.read_text(encoding="utf-8"))["sha256_sqlite"])
            bad=folder/"bad.json"
            broken=json.loads(man.read_text(encoding="utf-8"))
            broken["sha256_sqlite"]="0"*64
            bad.write_text(json.dumps(broken),encoding="utf-8")
            with self.assertRaises(ValueError):
                generate(db,bad,out,evidence,report)


if __name__=="__main__":
    unittest.main()
