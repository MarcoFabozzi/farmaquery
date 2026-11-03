"""Diagnostica di recupero dello snapshot reale, senza Gemini."""
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
import tempfile
from tesi.prepara_snapshot_online import ROOT, build_snapshot
from tesi import pilota_tag_vs_sql as eng
from tesi.sintesi_tag import compact_category_evidence,missing_category_candidates
from tesi.recupero_regionale import regional_candidates

QUESTION=("Quali medicinali citati nelle note regionali della Campania per "
          "malattie neuromuscolari prevedono la prescrizione presso l'AOU Federico II? "
          "Indica per ciascuno il medicinale, la patologia, l'indicazione terapeutica "
          "e la pagina della nota.")
class DiagnoseCoverage(unittest.TestCase):
    def test_print_diagnostic_without_llm(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"snapshot.sqlite"
            build_snapshot(ROOT,f,Path(d)/"manifest.json")
            with closing(sqlite3.connect(f)) as db:
                db.row_factory=sqlite3.Row
                all_found=regional_candidates(db,QUESTION,limit=100)
                normal=eng.evidence_candidates(db,QUESTION,max_rows=32)
                compact=compact_category_evidence(normal)
                print("DIAGNOSI_TOT_CANDIDATI",len(all_found))
                print("DIAGNOSI_TOP_100",[(i+1,c["testo"].split("farmaco candidato: ",1)[-1].split(";",1)[0][:45]) for i,c in enumerate(all_found)])
                print("DIAGNOSI_32",[(i+1,c["documento_e_medicinale_candidato"][:135],[(p.get("pagina"),p["estratto"][:90]) for p in c["passaggi"]]) for i,c in enumerate(compact)])
                for term in ("GAMTEN","HIZENTRA","HYQVIA"):
                    print("DIAGNOSI_TERM",term,
                          [i+1 for i,c in enumerate(all_found) if term.casefold() in c["testo"].casefold()],
                          [i+1 for i,c in enumerate(normal) if term.casefold() in c["testo"].casefold()])
                for fname in ("HYQVIA CIDP.pdf","GAMTEN.pdf"):
                    source=db.execute("SELECT id FROM note WHERE nome_file=?",(fname,)).fetchone()
                    if source is None:
                        print("DIAGNOSI_PDF_ASSENTE",fname)
                        continue
                    for p in db.execute("SELECT numero_pagina,testo FROM pagine "
                                        "WHERE nota_id=? ORDER BY numero_pagina",
                                        (source["id"],)):
                        print("DIAGNOSI_DOC_PAGINA",fname,p["numero_pagina"],
                              " ".join((p["testo"] or "").split())[:5500])
                self.assertTrue(normal)

if __name__ == "__main__":
    unittest.main()
