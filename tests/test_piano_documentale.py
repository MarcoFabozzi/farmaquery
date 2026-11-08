"""Piano documentale tipizzato senza tassonomie cliniche manuali.

Test offline: SQL LLM della r16 con filtri artificiali, recupero
di pagine e controesempi con vincoli oggettivi reali.
"""
import gzip
import json
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd  # Evita re-import NumPy durante mock LOTUS.

from tesi import tag_automatico as auto
from tesi.recupero_due_fasi import DISCOVER_PROMPT, VERIFY_PROMPT
from tesi.piano_documentale import (
    PLAN_PROMPT, document_center_anchors, validated_document_plan,
    sql_from_document_plan,
)

QUESTION=(
    "Quali medicinali citati nelle note regionali della Campania "
    "per malattie neuromuscolari prevedono la prescrizione presso "
    "l'AOU Federico II? Per ciascuno indica il medicinale, "
    "la patologia o indicazione, il documento e la pagina "
    "in cui e' individuato il centro prescrittore."
)
SQL_LLM=(
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "n.indicazione_candidata AS indicazione, n.id AS nota_id, "
    "p.numero_pagina AS numero_pagina FROM note AS n "
    "JOIN pagine AS p ON n.id = p.nota_id "
    "JOIN centri_candidati AS c "
    "ON p.nota_id = c.nota_id AND p.numero_pagina = c.numero_pagina "
    "WHERE c.menzione LIKE '%Federico II%' "
    "AND c.stato = 'attivo' "
    "AND (n.farmaco_candidato LIKE '%neuromuscolari%' "
    "OR p.testo LIKE '%neuromuscolari%')"
)
VALID_PLAN=json.dumps({
    "applicabile":True, "centro":"Federico II",
    "criterio_semantico":"malattie neuromuscolari",
    "vincoli_oggettivi_aggiuntivi":[]
})


class StructuredPlanTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
          CREATE TABLE note(
            id TEXT PRIMARY KEY, nome_file TEXT, anno INTEGER,
            protocollo_candidato TEXT, data_candidata TEXT,
            farmaco_candidato TEXT, indicazione_candidata TEXT,
            percorso_zip TEXT, archivio_url TEXT
          );
          CREATE TABLE pagine(
            nota_id TEXT, numero_pagina INTEGER,
            testo TEXT, metodo TEXT
          );
          CREATE TABLE centri_candidati(
            nota_id TEXT, numero_pagina INTEGER,
            menzione TEXT, stato TEXT
          );
          INSERT INTO note VALUES
            ('a','a.pdf',2026,NULL,NULL,'MED-A',
             'Malattia neurologica specifica','a.pdf','https://example.org/a.zip'),
            ('b','b.pdf',2026,NULL,NULL,'MED-B',
             'Altra indicazione','b.pdf','https://example.org/b.zip');
          INSERT INTO pagine VALUES
            ('a',1,'Trattamento della condizione neurologica specifica','TESTO'),
            ('a',2,'AOU Federico II centro prescrittore','TESTO'),
            ('b',1,'Altro ospedale in regione','TESTO');
          INSERT INTO centri_candidati VALUES
            ('a',2,'AOU Federico II',NULL);
        """)
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    def test_estrazione_ancore_da_query_arbitraria_non_prende_categoria(self):
        anchors=document_center_anchors(SQL_LLM,QUESTION)
        self.assertIn("Federico II",anchors)
        self.assertNotIn("neuromuscolari",anchors)
        self.assertNotIn("attivo",anchors)

    def test_piano_tipizzato_compila_select_deterministica(self):
        anchors=document_center_anchors(SQL_LLM,QUESTION)
        plan,reason=validated_document_plan(VALID_PLAN,anchors,QUESTION)
        self.assertEqual(reason,"ok")
        sql=sql_from_document_plan(plan)
        self.assertNotIn("neuromuscolari",sql)
        self.assertNotIn("attivo",sql)
        self.assertNotIn("centri_candidati",sql)
        self.assertIn("LIKE '%Federico%'",sql)
        initial,partial=auto._run_generated_select(
            self.db,auto.validate_sql(SQL_LLM))
        self.assertEqual(initial,[])
        self.assertFalse(partial)
        rows,partial=auto._run_generated_select(
            self.db,auto.validate_sql(sql))
        self.assertFalse(partial)
        self.assertEqual([r["nota_id"] for r in rows],["a"])
        docs,more=auto._note_candidates(self.db,rows)
        self.assertFalse(more)
        self.assertIn("[pagina 2]",docs[0]["testo"])

    def test_piano_non_autorizza_vincoli_extra_o_ospedali_non_richiesti(self):
        anchors=document_center_anchors(SQL_LLM,QUESTION)
        for data in [
            {"applicabile":True,"centro":"Federico II",
             "criterio_semantico":"neuromuscolari",
             "vincoli_oggettivi_aggiuntivi":["anno 2026"]},
            {"applicabile":True,"centro":"Ospedale diverso",
             "criterio_semantico":"neuromuscolari",
             "vincoli_oggettivi_aggiuntivi":[]},
            {"applicabile":True,"centro":"Federico II",
             "criterio_semantico":"neuromuscolari",
             "vincoli_oggettivi_aggiuntivi":"nessuno"},
            {"applicabile":False,"centro":None,
             "criterio_semantico":None,
             "vincoli_oggettivi_aggiuntivi":[]},
        ]:
            parsed,why=validated_document_plan(
                json.dumps(data),anchors,QUESTION)
            self.assertIsNone(parsed,why)
        for raw in ["prosa","[]",'{"applicabile":"true"}']:
            parsed,why=validated_document_plan(raw,anchors,QUESTION)
            self.assertIsNone(parsed,why)

    def test_una_query_non_documentale_non_attiva_il_piano(self):
        for sql in [
            "SELECT nome FROM confezioni_aifa WHERE classe = 'A'",
            "SELECT * FROM note n WHERE n.anno=2026",
            "SELECT * FROM note n JOIN pagine p ON n.id=p.nota_id "
            "WHERE p.testo LIKE '%Ospedale diverso%'",
            SQL_LLM+" LIMIT 5",
            SQL_LLM+" UNION SELECT 1,2,3,4",
        ]:
            self.assertEqual(document_center_anchors(sql,QUESTION),[])

    def test_end_to_end_con_sql_aleatoria_controllo_indice_pdf(self):
        calls=[]
        def ask_mock(model,system,payload,**kwargs):
            calls.append((system,payload))
            if system==auto.SQL_PROMPT:
                return SQL_LLM,{
                    "token_input":10,"token_output":3,"costo_usd":0
                }
            if system==PLAN_PROMPT:
                return VALID_PLAN,{
                    "token_input":6,"token_output":2,"costo_usd":0
                }
            if system==DISCOVER_PROMPT:
                return '{"indici":[0],"incerto":false}',{
                    "token_input":5,"token_output":5,"costo_usd":0
                }
            if system==VERIFY_PROMPT:
                return json.dumps({"verificati":[{
                    "documento_indice":0,"medicinale":"MED-A",
                    "indicazione":"Malattia neurologica specifica",
                    "pagina_indicazione":1,"pagina_centro":2
                }],"incerto":False}),{
                    "token_input":5,"token_output":5,"costo_usd":0
                }
            raise AssertionError("Chiamata inattesa")
        lotus=types.ModuleType("lotus")
        lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        models=types.ModuleType("lotus.models")
        models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{
                "lotus":lotus,"lotus.models":models}), \
             patch.object(auto,"ask",side_effect=ask_mock), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(self.db,QUESTION,"mock")
        self.assertTrue(result["piano_documentale_usato"])
        self.assertEqual(result["piano_documentale_esito"],"ok")
        self.assertEqual(result["piano_documentale_centro"],"Federico II")
        self.assertEqual(result["chiamate_piano_documentale"],1)
        self.assertTrue(result["recupero_progressivo_usato"])
        self.assertEqual(result["strategia_tag"],"due_fasi")
        self.assertEqual(result["righe_sql_primo_tentativo"],0)
        self.assertEqual(result["sql_tentativi"],3)
        self.assertEqual(result["documenti_fase1"],1)
        self.assertEqual(result["documenti_fase2"],1)
        self.assertEqual(result["coppie_documentate"],1)
        self.assertEqual(result["righe_sql"],1)
        self.assertEqual(result["note_nell_indice"],1)
        self.assertEqual(len(calls),4)
        self.assertIn("note",result["sql"])
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-08-r18-recupero-due-fasi")

    def test_piano_non_applicabile_non_inventa_fonti(self):
        calls=[]
        def ask_mock(model,system,payload,**kwargs):
            calls.append(system)
            if system==auto.SQL_PROMPT:
                return SQL_LLM,{"token_input":1,"token_output":1,"costo_usd":0}
            if system==PLAN_PROMPT:
                return '{"applicabile":false,"centro":null,"criterio_semantico":null,"vincoli_oggettivi_aggiuntivi":["farmaco preciso"]}',{
                    "token_input":1,"token_output":1,"costo_usd":0}
            raise AssertionError("Non deve sintetizzare senza prove")
        lotus=types.ModuleType("lotus")
        lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        models=types.ModuleType("lotus.models")
        models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{
                "lotus":lotus,"lotus.models":models}), \
             patch.object(auto,"ask",side_effect=ask_mock):
            result=auto.automatic_tag(self.db,QUESTION,"mock")
        self.assertFalse(result["piano_documentale_usato"])
        self.assertEqual(result["chiamate_piano_documentale"],1)
        self.assertEqual(result["righe_sql"],0)
        self.assertEqual(result["stato"],"NESSUNA_EVIDENZA")

    def test_snapshot_20261102_piano_copre_riferimento(self):
        base=Path(__file__).resolve().parents[1]
        frozen=base/"risultati/tesi_statico_20261102.sqlite.gz"
        reference=base/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
        if not frozen.is_file() or not reference.is_file():
            self.skipTest("Snapshot o riferimento non disponibili")
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(frozen.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            before,partial=auto._run_generated_select(
                db,auto.validate_sql(SQL_LLM))
            self.assertFalse(partial)
            self.assertEqual(before,[])
            anchors=document_center_anchors(SQL_LLM,QUESTION)
            plan,why=validated_document_plan(VALID_PLAN,anchors,QUESTION)
            self.assertIsNotNone(plan,why)
            sql=sql_from_document_plan(plan)
            records,partial=auto._run_generated_select(
                db,auto.validate_sql(sql))
            self.assertFalse(partial)
            gold=json.loads(reference.read_text(encoding="utf-8"))
            wanted={x["sha256_pdf"] for x in gold["casi_positivi"]}
            found={x["nota_id"] for x in records}
            self.assertTrue(wanted<=found)
            self.assertEqual(len(found),161)
            print("Piano strutturato: da 0 a",len(found),
                  "note candidate; riferimento PDF",len(wanted))
        finally:
            db.close()


if __name__=="__main__":
    unittest.main()
