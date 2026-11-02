"""Test recupero semantico preparatorio TAG, senza chiamate Gemini/LOTUS.

Verifica che i documenti siano reali e citabili nello SQLite, che i
riferimenti non diventino automaticamente autorizzazioni e che un
quesito per categoria non richieda il nome esplicito di un medicinale.
"""
import sqlite3
import unittest

from tesi.recupero_regionale import regional_candidates, categoria
from tesi.pilota_tag_vs_sql import evidence_candidates


class RegionalSemanticRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        CREATE TABLE note(
            id TEXT PRIMARY KEY, nome_file TEXT,percorso_zip TEXT,anno INT,
            farmaco_candidato TEXT,protocollo_candidato TEXT,
            archivio_url TEXT);
        CREATE TABLE pagine(nota_id TEXT,numero_pagina INT,testo TEXT,metodo TEXT);
        CREATE VIRTUAL TABLE pagine_fts USING fts5(nota_id UNINDEXED,
            numero_pagina UNINDEXED,testo);
        CREATE TABLE rimandi_candidati(nota_id TEXT,numero_pagina INT,
            riferimento TEXT,stato TEXT);
        CREATE TABLE aifa_confezioni(aic TEXT,nome TEXT,
            principio_attivo TEXT,descrizione TEXT,
            classe_a_h_snapshot TEXT,classe_a_h_data TEXT);
        CREATE TABLE ema_medicinali(ema_id TEXT,nome TEXT,
            principio_attivo TEXT,stato_ema TEXT,
            data_decisione_ue TEXT,indicazione_ema TEXT,url_ema TEXT);
        CREATE TABLE strutture_registri(id TEXT,medicinale TEXT,patologia TEXT,
            indicazione TEXT,struttura TEXT,data_riferimento TEXT,fonte_url TEXT);
        INSERT INTO note VALUES
            ('new','PLUVICTO-2026.pdf','2026/PLUVICTO-2026.pdf',2026,
             'PLUVICTO','PG/2026/0999999','https://regione.test/note2026.zip'),
            ('old','PLUVICTO-2024.pdf','2024/PLUVICTO-2024.pdf',2024,
             'PLUVICTO','PG/2024/0503681','https://regione.test/note2024.zip'),
            ('nm','MEDICINA-NEURO.pdf','2026/MEDICINA-NEURO.pdf',2026,
             'TERAPIA X','PG/2026/0000042','https://regione.test/note2026.zip'),
            ('onco','CARCINOMA.pdf','2026/CARCINOMA.pdf',2026,
             'TERAPIA Y','PG/2026/0000043','https://regione.test/note2026.zip');
        INSERT INTO pagine VALUES
            ('new',1,'Per PLUVICTO si richiamano i centri già individuati '
             || 'con la nota PG/2024/0503681.','TESTO'),
            ('old',1,'I centri PLUVICTO sono AOU Federico II e AORN Cardarelli.','TESTO'),
            ('nm',1,'TERAPIA X per miastenia gravis generalizzata.','TESTO'),
            ('nm',2,'Centro prescrittore: AOU Federico II di Napoli.','TESTO'),
            ('onco',1,'TERAPIA Y riguarda carcinoma della mammella.','TESTO');
        INSERT INTO pagine_fts
             SELECT nota_id,numero_pagina,testo FROM pagine;
        INSERT INTO rimandi_candidati VALUES
             ('new',1,'nota PG/2024/0503681','DA_VERIFICARE');
        INSERT INTO ema_medicinali VALUES
             ('EM1','PLUVICTO','X','Autorizzato',NULL,'Indicazione','https://ema.test');
        """)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_rimando_univoco_cita_entrambi_i_pdf(self):
        rows=regional_candidates(self.db,
           "In quali centri si prescrive PLUVICTO?", "pluvicto")
        files={r["fonte"].split("#p")[0] for r in rows}
        self.assertIn("2026/PLUVICTO-2026.pdf",files)
        self.assertIn("2024/PLUVICTO-2024.pdf",files)
        self.assertTrue(any("AOU Federico II" in r["testo"] for r in rows))
        self.assertTrue(any("corrispondenza identificativa" in r["testo"]
                            for r in rows))
        self.assertFalse(any("autorizzato dalla Regione" in r["testo"]
                             for r in rows))

    def test_categoria_implicita_legge_pagine_differenti(self):
        question="Quali farmaci per malattie neuromuscolari si prescrivono al Federico II?"
        self.assertEqual(categoria(question)[0],"neuromuscolar")
        evidence=regional_candidates(self.db,question,"neuromuscolari")
        self.assertTrue(evidence)
        texts=" ".join(r["testo"] for r in evidence)
        self.assertIn("miastenia gravis",texts)
        self.assertIn("Federico II",texts)
        self.assertTrue(all("#p" in r["fonte"] for r in evidence))
        full=evidence_candidates(self.db,question,max_rows=18)
        self.assertTrue(any(x["tipo"]=="REGIONE" for x in full))

    def test_citazioni_ciascuna_pagina_e_finestre_rilevanti(self):
        self.db.execute("UPDATE pagine SET testo=? "
                        "WHERE nota_id='nm' AND numero_pagina=2",
                        ("Intestazione ripetuta " * 110 +
                         "Centro prescrittore: AOU Federico II di Napoli."))
        self.db.execute(
            "DELETE FROM pagine_fts WHERE nota_id='nm' AND numero_pagina=2")
        self.db.execute(
            "INSERT INTO pagine_fts SELECT nota_id,numero_pagina,testo "
            "FROM pagine WHERE nota_id='nm' AND numero_pagina=2")
        q="Quali farmaci per malattie neuromuscolari si prescrivono al Federico II?"
        evidence=regional_candidates(self.db,q)
        self.assertEqual(len(evidence),1)
        doc=evidence[0]
        self.assertEqual(len(doc["fonti"]),2)
        self.assertTrue(all(" | archivio: " in x for x in doc["fonti"]))
        self.assertTrue(all(x.count("#p")==1 for x in doc["fonti"]))
        self.assertIn("miastenia",doc["testo"].lower())
        self.assertIn("Federico II",doc["testo"])
        self.assertIn("Federico II",doc["testo_selezione"])
        self.assertNotIn("Intestazione ripetuta Intestazione ripetuta "
                         "Intestazione ripetuta Intestazione ripetuta "
                         "Intestazione ripetuta",doc["testo_selezione"])

    def test_sclerosi_multipla_non_inserita_per_definizione(self):
        self.db.execute(
            "INSERT INTO note VALUES (?,?,?,?,?,?,?)",
            ('ms','KESIMPTA.pdf','2022/KESIMPTA.pdf',2022,
             'KESIMPTA',None,'https://regione.test/2022.zip'))
        self.db.execute("INSERT INTO pagine VALUES(?,?,?,?)",
                        ('ms',1,'Trattamento della sclerosi multipla presso '
                         'AOU Federico II','TESTO'))
        self.db.execute(
            "INSERT INTO pagine_fts SELECT nota_id,numero_pagina,testo "
            "FROM pagine WHERE nota_id='ms'")
        docs=regional_candidates(self.db,
            "Quali farmaci per malattie neuromuscolari si prescrivono al Federico II?")
        self.assertFalse(any("KESIMPTA" in d["testo"] for d in docs))
        self.assertTrue(any("miastenia" in d["testo"] for d in docs))

    def test_rimando_ambiguo_non_sceglie_documento_a_caso(self):
        self.db.execute(
           "INSERT INTO note VALUES(?,?,?,?,?,?,?)",
           ('another','DUPLICATO.pdf','2024/DUPLICATO.pdf',2024,
            'PLUVICTO','PG/2024/0503681','https://regione.test/note2024.zip'))
        self.db.execute("INSERT INTO pagine VALUES(?,?,?,?)",
                        ('another',1,'Contenuto duplicato','TESTO'))
        rows=regional_candidates(self.db,"Centri PLUVICTO","pluvicto")
        self.assertFalse(any("NOTA RICHIAMATA:" in x["testo"] for x in rows))

    def test_categoria_non_forza_il_nome_del_farmaco(self):
        q="Quali farmaci per malattie neuromuscolari si prescrivono al Federico II?"
        results=evidence_candidates(self.db,q,max_rows=22)
        self.assertTrue(results)
        self.assertTrue(all(row["tipo"]=="REGIONE" for row in results))
        self.assertTrue(any("miastenia" in row["testo"] for row in results))

    def test_assenza_documentale_non_inventa_fonti(self):
        self.assertEqual(regional_candidates(
            self.db,"Quali strutture per FARMACO SCONOSCIUTO?",
            "FARMACO SCONOSCIUTO"),[])


if __name__=="__main__":
    unittest.main()
