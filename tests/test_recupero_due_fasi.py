"""Regressioni TAG automatico r18: un tentativo normale, poi due SQL.

Nessuna chiamata a provider reali. Le pagine e i farmaci sono simulati per
verificare che i risultati non si inventino e che il costo sia misurato.
"""
from __future__ import annotations

import gzip
import json
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from tesi import tag_automatico as auto
from tesi.recupero_due_fasi import (
    DISCOVER_PROMPT, VERIFY_PROMPT, semantic_filter_warning,
    sql_second_stage,verified_document_pairs,
)
from tesi.piano_documentale import PLAN_PROMPT

QUESTION=(
    "Quali medicinali citati nelle note regionali della Campania "
    "per malattie neuromuscolari prevedono prescrizione presso "
    "l'AOU Federico II? Indica medicinale, indicazione, documento e pagina."
)
SQL_EMPTY=(
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "n.indicazione_candidata AS indicazione, n.id AS nota_id, "
    "p.numero_pagina FROM note AS n "
    "JOIN pagine AS p ON n.id=p.nota_id "
    "JOIN centri_candidati AS c "
    "ON c.nota_id=p.nota_id AND c.numero_pagina=p.numero_pagina "
    "WHERE c.menzione LIKE '%Federico II%' "
    "AND c.stato='attivo' "
    "AND (n.farmaco_candidato LIKE '%neuromuscolari%' "
    "OR p.testo LIKE '%neuromuscolari%')"
)
SQL_PARTIAL=(
    "SELECT DISTINCT n.id AS nota_id FROM note n "
    "JOIN pagine p ON n.id=p.nota_id "
    "WHERE p.testo LIKE '%Federico II%' "
    "AND n.indicazione_candidata LIKE '%neuromuscolari%'"
)
PLAN=json.dumps({
    "applicabile":True,
    "centro":"Federico II",
    "criterio_semantico":"malattie neuromuscolari",
    "vincoli_oggettivi_aggiuntivi":[],
})


class TwoStageTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
           CREATE TABLE note(
               id TEXT PRIMARY KEY,nome_file TEXT,anno INTEGER,
               protocollo_candidato TEXT,data_candidata TEXT,
               farmaco_candidato TEXT,indicazione_candidata TEXT,
               percorso_zip TEXT,archivio_url TEXT
           );
           CREATE TABLE pagine(
               nota_id TEXT,numero_pagina INTEGER,testo TEXT,metodo TEXT
           );
           CREATE TABLE centri_candidati(
               nota_id TEXT,numero_pagina INTEGER,menzione TEXT,stato TEXT
           );
           INSERT INTO note VALUES
             ('n1','MED-A.pdf',2026,NULL,NULL,'MED-A',
              'neuromuscolari, disturbo muscolare alfa',
              'note/med-a.pdf','https://example.org/notes.zip'),
             ('n2','MED-B.pdf',2026,NULL,NULL,'MED-B',
              'Disturbo neurologico beta',
              'note/med-b.pdf','https://example.org/notes.zip'),
             ('n3','MED-C.pdf',2026,NULL,NULL,'MED-C',
              'Dermatologia',
              'note/med-c.pdf','https://example.org/notes.zip');
           INSERT INTO pagine VALUES
             ('n1',1,'MED-A: terapia del disturbo muscolare alfa','TESTO'),
             ('n1',2,'AOU Federico II, Napoli - Centro prescrittore MED-A','TESTO'),
             ('n2',1,'MED-B: trattamento della malattia neurologica beta','TESTO'),
             ('n2',2,'AOU Federico II centro prescrittore MED-B','TESTO'),
             ('n3',1,'MED-C per dermatologia','TESTO'),
             ('n3',2,'AOU Federico II centro prescrittore MED-C','TESTO');
           INSERT INTO centri_candidati VALUES
             ('n1',2,'AOU Federico II','sospeso');
        """)
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    def run_pipeline(self,sql=SQL_EMPTY,discover=None,verify=None,plan=PLAN,
                     lotus_selected=True):
        called=[]
        if discover is None:
            discover={"indici":[0,1],"incerto":False}
        if verify is None:
            verify={
                "verificati":[{
                    "documento_indice":0,"medicinale":"MED-A",
                    "indicazione":"Disturbo muscolare alfa",
                    "pagina_indicazione":1,"pagina_centro":2
                },{
                    "documento_indice":1,"medicinale":"MED-B",
                    "indicazione":"Malattia neurologica beta",
                    "pagina_indicazione":1,"pagina_centro":2
                }],
                "incerto":False
            }
        def mock_ask(model,system,payload,**kwargs):
            called.append((system,payload))
            if system==auto.SQL_PROMPT:
                value=sql
            elif system==PLAN_PROMPT:
                value=plan
            elif system==DISCOVER_PROMPT:
                value=json.dumps(discover) if isinstance(discover,dict) else discover
            elif system==VERIFY_PROMPT:
                value=json.dumps(verify) if isinstance(verify,dict) else verify
            else:
                raise AssertionError("Chiamata inattesa: "+str(system)[:45])
            return value,{"token_input":1,"token_output":1,"costo_usd":0}
        lotus=types.ModuleType("lotus")
        lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        models=types.ModuleType("lotus.models")
        models.LM=lambda *_,**__:types.SimpleNamespace()
        def mock_filter(frame,instruction):
            return frame if lotus_selected else frame.iloc[0:0]
        with patch.dict(sys.modules,{
                "lotus":lotus,"lotus.models":models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",side_effect=mock_filter):
            result=auto.automatic_tag(self.db,QUESTION,"mock")
        return result,called

    def test_r18_sql_vuoto_due_query_e_conferma_pagine(self):
        result,calls=self.run_pipeline()
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-08-r18-recupero-due-fasi")
        self.assertEqual(result["strategia_tag"],"due_fasi")
        self.assertEqual(result["motivo_due_fasi"],"sql_vuoto")
        self.assertEqual(result["documenti_fase1"],3)
        self.assertEqual(result["documenti_fase2"],2)
        self.assertEqual(result["coppie_documentate"],2)
        self.assertEqual(result["lotti_fase1_validi"],1)
        self.assertEqual(result["sql_tentativi_due_fasi"],2)
        self.assertEqual(result["sql_tentativi"],3)
        self.assertIn("MED-A",result["risposta"])
        self.assertIn("MED-B",result["risposta"])
        self.assertNotIn("MED-C",result["risposta"])
        self.assertIn("pagina del centro prescrittore **2**",result["risposta"])
        self.assertEqual(len(result["fonti"]),2)
        self.assertTrue(all("#p2" in source for source in result["fonti"]))
        self.assertNotIn("c.stato",result["sql_fase1"])
        self.assertNotIn("neuromuscolari",result["sql_fase1"])
        self.assertIn("'n1'",result["sql_fase2"])
        self.assertIn("'n2'",result["sql_fase2"])
        self.assertNotIn("'n3'",result["sql_fase2"])
        self.assertEqual(len(calls),4)
        self.assertEqual([system for system,_ in calls],
                         [auto.SQL_PROMPT,PLAN_PROMPT,DISCOVER_PROMPT,VERIFY_PROMPT])
        self.assertEqual(result["chiamate_llm_dirette"],4)

    def test_query_parziale_attiva_secondo_metodo(self):
        self.assertEqual(
            semantic_filter_warning(SQL_PARTIAL,QUESTION),
            "filtro_lessicale_non_esaustivo_su_documenti"
        )
        result,calls=self.run_pipeline(sql=SQL_PARTIAL)
        self.assertEqual(result["righe_sql_primo_tentativo"],1)
        self.assertEqual(result["strategia_tag"],"due_fasi")
        self.assertEqual(result["documenti_fase1"],3)
        self.assertEqual(result["coppie_documentate"],2)

    def test_lotus_seconda_fase_vuoto_si_astiene(self):
        result,calls=self.run_pipeline(lotus_selected=False)
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["motivo_astensione"],
                         "nessuna_relazione_selezionata_da_lotus")
        self.assertFalse(result["fonti"])
        self.assertFalse(any(system==VERIFY_PROMPT for system,_ in calls))

    def test_nessuna_malattia_selezionata_si_astiene(self):
        result,_=self.run_pipeline(discover={"indici":[],"incerto":False})
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["motivo_astensione"],
                         "nessuna_nota_pertinente_alla_categoria")
        self.assertIsNone(result["sql_fase2"])
        self.assertFalse(result["fonti"])

    def test_verifica_documentale_manca_centro_su_pagina_si_astiene(self):
        invalid={
            "verificati":[{
                "documento_indice":0,"medicinale":"MED-A",
                "indicazione":"Disturbo alfa",
                "pagina_indicazione":1,"pagina_centro":1,
            }],"incerto":False
        }
        result,_=self.run_pipeline(verify=invalid)
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["motivo_astensione"],
                         "verifica_strutturata_non_valida")
        self.assertFalse(result["fonti"])

    def test_json_malformato_si_astiene_senza_citazioni(self):
        result,_=self.run_pipeline(discover="RISPOSTA LIBERA")
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["lotti_fase1_non_validi"],1)
        self.assertEqual(result["motivo_astensione"],
                         "classificazione_prima_fase_non_completa")
        self.assertFalse(result["fonti"])

    def test_piano_non_applicabile_non_elimina_vincoli_oggettivi(self):
        p=json.dumps({"applicabile":False,"centro":None,
                      "criterio_semantico":None,
                      "vincoli_oggettivi_aggiuntivi":["farmaco preciso"]})
        result,calls=self.run_pipeline(plan=p)
        self.assertNotEqual(result.get("strategia_tag"),"due_fasi")
        self.assertEqual(result["stato"],"NESSUNA_EVIDENZA")
        self.assertEqual(result["chiamate_piano_documentale"],1)
        self.assertEqual(len(calls),2)

    def test_seconda_sql_usa_solo_identificativi_validi(self):
        sql=sql_second_stage(["a' OR 1=1 --","b"])
        self.assertIn("''",sql)
        self.assertNotIn("centri_candidati",sql)
        with self.assertRaises(ValueError):
            sql_second_stage([])
        with self.assertRaises(ValueError):
            sql_second_stage([""])


if __name__=="__main__":
    unittest.main()
