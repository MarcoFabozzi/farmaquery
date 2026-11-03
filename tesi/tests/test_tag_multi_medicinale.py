"""Regressioni generiche: confronto multi-farmaco e richiamo neuromuscolare."""
import sqlite3
import unittest

from tesi.pilota_tag_vs_sql import (
    _comparison_medicines,_common_centres,evidence_candidates,
    SQL_GENERATION_PROMPT,
)
from tesi.recupero_regionale import regional_candidates,categoria


class MultiDrugAndCategoryRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
            CREATE TABLE note(
                id TEXT PRIMARY KEY,nome_file TEXT,percorso_zip TEXT,
                archivio_url TEXT,anno TEXT,farmaco_candidato TEXT,
                protocollo_candidato TEXT,data_candidata TEXT);
            CREATE TABLE pagine(
                nota_id TEXT,numero_pagina INTEGER,testo TEXT,metodo TEXT);
            CREATE VIRTUAL TABLE pagine_fts USING fts5(
                nota_id UNINDEXED,numero_pagina UNINDEXED,testo);
            CREATE TABLE nota_centro_documentato(
                id INTEGER,nota_id TEXT,centro TEXT,indicazione TEXT,
                numero_pagina INTEGER);
            CREATE TABLE ema_medicinali(
                ema_id TEXT,nome TEXT,principio_attivo TEXT,
                stato_ema TEXT,data_decisione_ue TEXT,
                indicazione_ema TEXT,url_ema TEXT);
            CREATE TABLE aifa_confezioni(
                aic TEXT,nome TEXT,principio_attivo TEXT,descrizione TEXT,
                classe_a_h_snapshot TEXT,classe_a_h_data TEXT);
            CREATE TABLE strutture_registri(
                id INTEGER,medicinale TEXT,patologia TEXT,
                indicazione TEXT,struttura TEXT,regione TEXT,
                data_riferimento TEXT,fonte_url TEXT);
        """)
        self._add_note("a","FARMACO ALFA",
                       "Indicazione per malattia alfa. Centro condiviso.",
                       "Centro condiviso, Struttura privata A")
        self._add_note("b","FARMACO BETA",
                       "Indicazione per malattia beta. Centro condiviso.",
                       "Centro condiviso, Struttura privata B")
        self.db.executemany(
            "INSERT INTO nota_centro_documentato VALUES (?,?,?,?,?)",[
                (1,"a","Centro condiviso","alfa",2),
                (2,"a","Struttura privata A","alfa",2),
                (3,"b","Centro condiviso","beta",2),
                (4,"b","Struttura privata B","beta",2)
            ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _add_note(self,uid,drug,indication,centers):
        self.db.execute(
            "INSERT INTO note VALUES (?,?,?,?,?,?,?,?)",
            (uid,f"{drug}.pdf",f"archivio/{drug}.pdf","https://test.invalid/zip",
             "2026",drug,"2026/1234567","03.11.2026"))
        for number,body in ((1,indication),(2,centers)):
            self.db.execute("INSERT INTO pagine VALUES (?,?,?,?)",
                            (uid,number,body,"TESTO"))
            self.db.execute("INSERT INTO pagine_fts VALUES (?,?,?)",
                            (uid,number,body))

    def test_recupera_entrambi_i_medicinali_e_centro_comune(self):
        question=("Quali strutture sanitarie ci sono tra i centri individuati "
                  "sia per FARMACO ALFA sia per FARMACO BETA?")
        drugs=_comparison_medicines(self.db,question)
        self.assertEqual(drugs,["farmaco alfa","farmaco beta"])
        overlaps=_common_centres(self.db,drugs)
        self.assertEqual(len(overlaps),1)
        self.assertIn("Centro condiviso",overlaps[0]["testo"])
        self.assertEqual(len(overlaps[0]["fonti"]),2)
        self.assertTrue(any("FARMACO ALFA.pdf#p2" in ref
                            for ref in overlaps[0]["fonti"]))
        self.assertTrue(any("FARMACO BETA.pdf#p2" in ref
                            for ref in overlaps[0]["fonti"]))
        evidence=evidence_candidates(self.db,question,max_rows=24)
        self.assertTrue(any("INTERSEZIONE" in row["testo"]
                            for row in evidence))
        self.assertTrue(any("FARMACO ALFA.pdf" in row["testo"]
                            for row in evidence))
        self.assertTrue(any("FARMACO BETA.pdf" in row["testo"]
                            for row in evidence))

    def test_senza_confronto_non_inventa_intersezione(self):
        q="Quali centri sono associati a FARMACO ALFA?"
        self.assertEqual(_comparison_medicines(self.db,q),[])
        self.assertEqual(_common_centres(self.db,["farmaco alfa"]),[])
        self.assertFalse(any("INTERSEZIONE" in x["testo"]
                             for x in evidence_candidates(self.db,q)))

    def test_senza_centro_comune_non_deduce_associazioni(self):
        self.db.execute(
            "DELETE FROM nota_centro_documentato WHERE centro='Centro condiviso'")
        q=("Confronta i centri di FARMACO ALFA e FARMACO BETA: "
           "quali sono in comune?")
        self.assertEqual(_common_centres(self.db,
                         _comparison_medicines(self.db,q)),[])

    def test_recupero_categoria_su_abbreviazioni_e_patologie(self):
        candidates=[
            ("n-cidp","MEDICINA GAMMA","La CIDP è una neuropatia cronica."),
            ("n-derm","MEDICINA DELTA","Trattamento della dermatomiosite attiva."),
            ("n-attr","MEDICINA EPSILON","Amiloidosi ereditaria da transtiretina.")
        ]
        for uid,drug,body in candidates:
            self._add_note(uid,drug,body,
                           "AOU Federico II - Centro di neurologia prescrittore.")
        question=("Quali medicinali per malattie neuromuscolari "
                  "presso l'AOU Federico II?")
        self.assertEqual(categoria(question)[0],"neuromuscolar")
        rows=regional_candidates(self.db,question,limit=32)
        labels=" ".join(x["testo"] for x in rows)
        for _,drug,_ in candidates:
            self.assertIn(drug,labels)
        self.assertIn("JOIN",SQL_GENERATION_PROMPT)
        self.assertIn("prodotti cartesiani",SQL_GENERATION_PROMPT)


if __name__=="__main__":
    unittest.main()
