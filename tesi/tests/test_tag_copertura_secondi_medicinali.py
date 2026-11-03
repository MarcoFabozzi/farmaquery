"""Regressione TAG: farmaci impliciti in note regionali e miopatie.

Le denominazioni attese sono SOLO nei test, mai nella logica di recupero.
Il test opera sullo stesso snapshot SQLite; nessuna chiamata al provider.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from tesi.prepara_snapshot_online import ROOT,build_snapshot
from tesi.pilota_tag_vs_sql import evidence_candidates
from tesi.sintesi_tag import (
    compact_category_evidence,secondary_medicine_candidates,
    missing_category_candidates,expand_review_pages,
    _candidate_short_name,
)
from tesi.revisione_categoria import verified_additions

QUESTION=("Quali medicinali citati nelle note regionali della Campania "
          "per malattie neuromuscolari prevedono la prescrizione presso "
          "l'AOU Federico II? Indica per ciascuno il medicinale, "
          "la patologia, l'indicazione terapeutica e la pagina della nota.")


class CandidateReviewOnSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        cls.sqlite=Path(cls.folder.name)/"snapshot.sqlite"
        build_snapshot(ROOT,cls.sqlite,
                       Path(cls.folder.name)/"manifest.json")

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def _documents(self, db):
        rows=evidence_candidates(db,QUESTION,max_rows=32)
        return compact_category_evidence(rows)

    def test_source_of_missing_primary_is_retrieved(self):
        with closing(sqlite3.connect(self.sqlite)) as db:
            db.row_factory=sqlite3.Row
            docs=self._documents(db)
            present={_candidate_short_name(d) for d in docs}
            self.assertIn("GAMTEN",present)
            note=next(d for d in docs if _candidate_short_name(d)=="GAMTEN")
            self.assertTrue(any("GAMTEN.pdf#p2" in str(p)
                                for p in note["fonti"]))

    def test_secondary_candidate_from_explicit_center_update(self):
        with closing(sqlite3.connect(self.sqlite)) as db:
            db.row_factory=sqlite3.Row
            docs=self._documents(db)
            secondary=secondary_medicine_candidates(db,QUESTION,docs)
        names={_candidate_short_name(d) for d in secondary}
        self.assertIn("HIZENTRA",names)
        candidate=next(d for d in secondary
                       if _candidate_short_name(d)=="HIZENTRA")
        self.assertTrue(any("#p2" in src and "HYQVIA" in src
                            for src in candidate["fonti"]))
        page2=next(p["estratto"] for p in candidate["passaggi"]
                   if p["pagina"]==2)
        self.assertIn("HIZENTRA",page2)
        self.assertIn("Federico II",page2)
        self.assertIn("centri prescrittori",page2)

    def test_secondary_is_missing_and_needs_evidence_review(self):
        with closing(sqlite3.connect(self.sqlite)) as db:
            db.row_factory=sqlite3.Row
            docs=self._documents(db)
            secondary=secondary_medicine_candidates(db,QUESTION,docs)
        # Il modello non deve aggiungerlo per solo riconoscimento lessicale:
        # resta una voce da verificare, non una risposta automatica.
        result=missing_category_candidates(
            "Medicinale: HYQVIA\n- Patologia: CIDP",secondary)
        self.assertIn("HIZENTRA",{_candidate_short_name(d) for d in result})

    def test_verified_positive_examples_use_exact_source_pages(self):
        with closing(sqlite3.connect(self.sqlite)) as db:
            db.row_factory=sqlite3.Row
            docs=self._documents(db)
            primary=expand_review_pages(db,QUESTION,"Nessun elenco",docs,
                                        max_docs=16)
            secondary=secondary_medicine_candidates(db,QUESTION,docs)
        by_name={_candidate_short_name(d):d for d in primary+secondary}

        # Le due citazioni letterali di ogni voce sono ricavate da PDF
        # e sono convalidate dalla funzione che governa la sintesi finale.
        examples=[
            ("GAMTEN",1,2,
             "Immunomodulazione in adulti affetti da Dermatomiosite in fase attiva",
             "Azienda Ospedaliera Universitaria Federico II, Napoli",
             "Dermatomiosite","Immunomodulazione nella dermatomiosite attiva"),
            ("HIZENTRA",2,2,
             "sono aggiornati i centri prescrittori del farmaco HIZENTRA",
             "A.O.U. Federico II - Napoli",
             "CIDP","Aggiornamento centri per CIDP"),
        ]
        for name,p_ind,p_ctr,ind,ctr,illness,indication in examples:
            with self.subTest(name=name):
                doc=by_name[name]
                proposal={"nuove_voci":[{
                    "confermato":True,"medicinale":name,
                    "patologia":illness,"indicazione":indication,
                    "pagina_indicazione":p_ind,
                    "pagina_centro":p_ctr,
                    "citazione_indicazione":ind,
                    "citazione_centro":ctr,
                }]}
                diagnostic=[]
                additions=verified_additions(json.dumps(proposal),
                                            [doc],QUESTION,
                                            _candidate_short_name,
                                            diagnostics=diagnostic)
                self.assertEqual(len(additions),1,diagnostic)
                self.assertIn("Medicinale: "+name,additions[0])

if __name__=="__main__":
    unittest.main()
