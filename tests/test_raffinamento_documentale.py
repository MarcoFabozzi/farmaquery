"""Test offline del raffinamento documentale TAG (nessuna API esterna)."""
import gzip
import json
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd  # Importa NumPy prima dei mock di sys.modules.

from tesi import tag_automatico as auto
from tesi.raffinamento_documentale import (
    REFINEMENT_PROMPT, refinement_payload, parse_refinement_result,
    refinement_batches, REFINEMENT_BATCH_SIZE, _evidence_excerpt
)


class DocumentRefinementTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
            CREATE TABLE note (
                id TEXT PRIMARY KEY, nome_file TEXT, anno INTEGER,
                protocollo_candidato TEXT, data_candidata TEXT,
                farmaco_candidato TEXT, indicazione_candidata TEXT,
                percorso_zip TEXT, archivio_url TEXT
            );
            CREATE TABLE pagine (
                nota_id TEXT, numero_pagina INTEGER,
                testo TEXT, metodo TEXT
            );
        """)
        self.db.execute("PRAGMA query_only=OFF")
        for i in range(25):
            doc=f"doc-{i:02d}"
            self.db.execute("INSERT INTO note VALUES (?,?,?,?,?,?,?,?,?)",
                (doc, f"{doc}.pdf",2026,None,None,
                 f"MEDICINALE-{i}",None,f"{doc}.pdf",
                 "https://www.regione.campania.it/demo.zip"))
            pages=[
                "Indicazione terapeutica: patologia generica "+("A"*2100),
                "Elenco centri prescrittori: ospedale generico "+("B"*1850)
            ]
            for page, text in enumerate(pages,1):
                self.db.execute("INSERT INTO pagine VALUES (?,?,?,?)",
                                (doc,page,text,"TESTO"))
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    def _run(self, sql, selected, doc_count=25, bad_offset=None):
        seen=[]
        def fake_ask(model, system, payload, **kwargs):
            seen.append((system,payload))
            if system == auto.SQL_PROMPT:
                return sql,{"token_input":2,"token_output":2,"costo_usd":0}
            if system == REFINEMENT_PROMPT:
                offset=payload["indice_globale_inizio"]
                size=len(payload["documenti"])
                if offset==bad_offset:
                    return "JSON non valido",{
                        "token_input":3,"token_output":3,"costo_usd":0}
                local=[item-offset for item in selected
                       if offset<=item<offset+size]
                return json.dumps({"indici":local,"incerto":False}),{
                    "token_input":3,"token_output":3,"costo_usd":0}
            return "Risposta documentale verificabile.",{
                "token_input":5,"token_output":5,"costo_usd":0}
        fake_lotus=types.ModuleType("lotus")
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        fake_models=types.ModuleType("lotus.models")
        fake_models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{
                "lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=fake_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(
                self.db,"Quali medicinali hanno un centro prescrittore?",
                "modello-fittizio")
        return result, seen

    def test_risposta_seleziona_singoli_documenti_non_interi_gruppi(self):
        sql="SELECT id AS nota_id FROM note"
        res, calls=self._run(sql,[3,17])
        self.assertEqual(res["stato"],"RISULTATI_PARZIALI")
        self.assertEqual(res["tag_auto_revision"],
                         "2026-11-08-r19-ancore-documentali-robuste")
        self.assertTrue(res["raffinamento_documentale_usato"])
        self.assertEqual(res["documenti_candidati_raffinamento"],25)
        self.assertEqual(res["documenti_selezionati_raffinamento"],2)
        self.assertEqual(res["note_nel_contesto"],2)
        self.assertEqual(res["note_nell_indice"],2)
        self.assertEqual(len(calls),4)  # SQL + 2 lotti + sintesi
        self.assertEqual(calls[1][0],REFINEMENT_PROMPT)
        self.assertEqual(calls[2][0],REFINEMENT_PROMPT)
        self.assertEqual(calls[1][1]["indice_globale_inizio"],0)
        self.assertEqual(calls[2][1]["indice_globale_inizio"],20)
        self.assertEqual(res["lotti_raffinamento"],2)
        self.assertEqual(res["lotti_raffinamento_completati"],2)
        self.assertEqual(res["lotti_raffinamento_non_validi"],0)
        self.assertEqual(len(calls[-1][1]["evidenze"]),2)
        docs={d["nota_id"] for d in calls[-1][1]["indice_documentale"]}
        self.assertEqual(len(docs),2)
        self.assertTrue(docs<=
            {f"doc-{i:02d}" for i in range(25)})
        self.assertTrue(all("#p2" in " ".join(e["fonti"])
                            for e in calls[-1][1]["evidenze"]))

    def test_lotto_malformato_resta_dichiaratamente_incompleto(self):
        res,calls=self._run("SELECT id AS nota_id FROM note",
                            [3,17,21],bad_offset=20)
        self.assertTrue(res["raffinamento_documentale_usato"])
        self.assertEqual(res["lotti_raffinamento"],2)
        self.assertEqual(res["lotti_raffinamento_completati"],1)
        self.assertEqual(res["lotti_raffinamento_non_validi"],1)
        self.assertEqual(res["documenti_selezionati_raffinamento"],2)
        self.assertEqual(res["note_nell_indice"],2)
        self.assertEqual(res["chiamate_dirette_raffinamento"],2)
        self.assertEqual(len(calls),4)
        self.assertEqual(res["stato"],"RISULTATI_PARZIALI")
        self.assertIn("lotto/i",res["risposta"])
        self.assertIn("non e' garantito",res["risposta"])

    def test_risposta_invalid_json_non_presenta_elenco_come_accertato(self):
        sql="SELECT id AS nota_id FROM note"
        with patch("tesi.raffinamento_documentale.parse_refinement_result",
                   wraps=parse_refinement_result):
            # Validazione del parser direttamente, per non simulare 25 API.
            for bad in ('{"indici":[999],"incerto":false}',
                        '{"indici":[1,1],"incerto":false}',
                        '{"indici":[true],"incerto":false}',
                        '{"indici":[]}', "prosa libera"):
                with self.assertRaises(ValueError):
                    parse_refinement_result(bad,25,10)

    def test_preserva_tutte_le_pagine_in_contesto_bilanciato(self):
        raw=("Identificativo interno nota: 1; documento: prova.pdf\n"+
             "[pagina 1] Indicazione terapeutica " + "A"*3300 +
             "[pagina 2] Prescrizione e centro: " + "B"*3100)
        excerpt, partial=auto._balanced_page_excerpt(raw,1700)
        self.assertTrue(partial)
        self.assertLessEqual(len(excerpt),1700)
        self.assertIn("[pagina 1]",excerpt)
        self.assertIn("[pagina 2]",excerpt)
        self.assertIn("Indicazione terapeutica",excerpt)
        self.assertIn("Prescrizione e centro",excerpt)

    def test_indice_selezione_contiene_due_pagine(self):
        text=("Identificativo interno nota: 1; documento: x.pdf\n"
              "[pagina 1] Indicazione terapeutica disturbo periferico "+
              "A"*1000+"[pagina 2] Centro prescrittore indicato "+
              "B"*1000)
        summary=_evidence_excerpt(text)
        self.assertIn("[pagina 1]",summary)
        self.assertIn("[pagina 2]",summary)
        self.assertIn("Indicazione terapeutica",summary)
        self.assertIn("Centro prescrittore",summary)

    def test_payload_non_contiene_dizionari_patologie(self):
        sql="SELECT id AS nota_id FROM note"
        records, partial=auto._run_generated_select(self.db,sql)
        self.assertFalse(partial)
        docs, _=auto._note_candidates(self.db,records)
        payload,reason=refinement_payload(
            docs,"Quali medicinali per determinate patologie?",55)
        self.assertEqual(reason,"ok")
        self.assertEqual(len(payload["documenti"]),25)
        self.assertNotIn("neuromuscolar",
                         json.dumps(payload).casefold())

    def test_23_documenti_generano_due_lotti_senza_omissioni(self):
        docs=[{"chiave":f"NOTA:{i}","nome_file":f"{i}.pdf",
               "testo":"[pagina 1] indicazione [pagina 2] centro"}
              for i in range(23)]
        batches=refinement_batches(docs)
        self.assertEqual([(offset,len(part)) for offset,part in batches],
                         [(0,20),(20,3)])
        self.assertEqual([item["chiave"] for _,part in batches for item in part],
                         [item["chiave"] for item in docs])
        with self.assertRaises(ValueError):
            refinement_batches(docs,21)

    def test_lotti_molteplici_non_usano_i_medici_come_etichette_fisse(self):
        doc={"chiave":"NOTA:aaa","nome_file":"prova.pdf",
             "testo":"[pagina 1] Sindrome rara in trattamento "
                     "[pagina 2] Centro prescrittore ospedaliero"}
        payload,reason=refinement_payload([doc],
            "Quali medicinali per questa condizione?",1,20)
        self.assertEqual(reason,"ok")
        self.assertEqual(payload["indice_globale_inizio"],20)
        self.assertIn("[pagina 2]",payload["documenti"][0]["passaggi"])
        self.assertNotIn("neuromuscolar",json.dumps(payload).casefold())

    def test_snapshot_161_documenti_puo_essere_sottoposto_a_raffinamento(self):
        root=Path(__file__).resolve().parents[1]
        source=root/"risultati/tesi_statico_20261102.sqlite.gz"
        if not source.is_file():
            self.skipTest("Snapshot statico mancante")
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(source.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            rows,_=auto._run_generated_select(
                db,"SELECT DISTINCT n.id AS nota_id "
                "FROM note n JOIN pagine p ON n.id=p.nota_id "
                "WHERE p.testo LIKE '%Federico%' COLLATE NOCASE")
            docs,partial=auto._note_candidates(db,rows)
            # Alcune pagine del vero snapshot superano il budget: e'
            # corretto registrarlo, non dichiararle integralmente lette.
            self.assertTrue(partial)
            self.assertEqual(len(docs),161)
            batches=refinement_batches(docs)
            self.assertEqual(len(batches),9)
            self.assertEqual([len(chunk) for _,chunk in batches],
                             [20]*8+[1])
            self.assertEqual([offset for offset,_ in batches],
                             [0,20,40,60,80,100,120,140,160])
            self.assertEqual(sum(len(chunk) for _,chunk in batches),161)
            for offset,chunk in batches:
                payload,reason=refinement_payload(
                    chunk,"Quali patologie presso la struttura indicata?",
                    len(chunk),offset)
                self.assertIsNotNone(payload,reason)
                self.assertEqual(len(payload["documenti"]),len(chunk))
        finally:
            db.close()


if __name__=="__main__":
    unittest.main()
