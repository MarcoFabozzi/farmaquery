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
from tesi.contatore_llm import direct_attempt
from tesi.recupero_due_fasi import (
    DISCOVER_PROMPT, VERIFY_PROMPT, semantic_filter_warning,
    sql_second_stage,verified_document_pairs,final_verification_batches,
)
from tesi.piano_documentale import (
    PLAN_PROMPT, sql_from_document_plan, document_center_anchors,
    recovery_center_anchors, question_center_anchors,
)
from errori_chatbot import EnginePhaseError
from tesi.raffinamento_documentale import refinement_batches

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
SQL_R18_REAL = (
    "SELECT DISTINCT n.farmaco_candidato AS nome, "
    "COALESCE(n.indicazione_candidata, 'Malattie neuromuscolari') "
    "AS patologia_o_indicazione, n.id AS documento_id, c.numero_pagina "
    "FROM note AS n JOIN nota_centro_documentato AS c "
    "ON n.id = c.nota_id "
    "WHERE (c.centro COLLATE NOCASE LIKE '%Federico II%' "
    "OR c.centro COLLATE NOCASE LIKE '%AOU%') "
    "AND (n.farmaco_candidato COLLATE NOCASE LIKE '%neuromuscolar%' "
    "OR n.indicazione_candidata COLLATE NOCASE LIKE '%neuromuscolar%' "
    "OR n.farmaco_candidato COLLATE NOCASE IN "
    "(SELECT DISTINCT medicinale FROM strutture_registri "
    "WHERE patologia COLLATE NOCASE LIKE '%neuromuscolar%'))"
)

SQL_UNKNOWN_TABLE=(
    "SELECT n.id AS nota_id FROM note AS n "
    "JOIN centri_prescrittori_inventati AS c ON c.nota_id=n.id "
    "WHERE c.centro LIKE '%Federico II%'"
)

SQL_R19_REAL = (
    "SELECT DISTINCT note.farmaco_candidato AS nome, "
    "note.indicazione_candidata AS indicazione, note.id AS documento_id, "
    "pagine.numero_pagina AS pagina_id FROM note "
    "JOIN pagine ON note.id = pagine.nota_id "
    "JOIN nota_centro_documentato ON note.id = nota_centro_documentato.nota_id "
    "AND pagine.numero_pagina = nota_centro_documentato.numero_pagina "
    "WHERE nota_centro_documentato.centro COLLATE NOCASE "
    "LIKE '%Federico II%'"
)

PLAN_WITH_FULL_CENTER=json.dumps({
    "applicabile":True,
    "centro":"AOU Federico II",
    "criterio_semantico":"malattie neuromuscolari",
    "vincoli_oggettivi_aggiuntivi":[],
})

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
           CREATE TABLE nota_centro_documentato(
               nota_id TEXT,centro TEXT,numero_pagina INTEGER
           );
           CREATE TABLE strutture_registri(
               medicinale TEXT,patologia TEXT
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
                     lotus_selected=True,question=QUESTION):
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
        verification_call=[0]
        def mock_ask(model,system,payload,**kwargs):
            direct_attempt()
            called.append((system,payload))
            if system==auto.SQL_PROMPT:
                value=sql
            elif system==PLAN_PROMPT:
                value=plan
            elif system==DISCOVER_PROMPT:
                value=json.dumps(discover) if isinstance(discover,dict) else discover
            elif system==VERIFY_PROMPT:
                if isinstance(verify,list):
                    value=verify[verification_call[0]]
                    verification_call[0]+=1
                else:
                    value=verify
                value=json.dumps(value) if isinstance(value,dict) else value
            else:
                raise AssertionError("Chiamata inattesa: "+str(system)[:45])
            if isinstance(value,Exception):
                raise value
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
            result=auto.automatic_tag(self.db,question,"mock")
        return result,called

    def _aggiungi_due_note_con_centro(self):
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executemany(
            "INSERT INTO note VALUES (?,?,?,?,?,?,?,?,?)",[
                ("n4","MED-D.pdf",2026,None,None,"MED-D",
                 "Disturbo neuromuscolare delta","note/d.pdf",
                 "https://example.org/d.zip"),
                ("n5","MED-E.pdf",2026,None,None,"MED-E",
                 "Disturbo neuromuscolare epsilon","note/e.pdf",
                 "https://example.org/e.zip"),
            ]
        )
        self.db.executemany(
            "INSERT INTO pagine VALUES (?,?,?,?)",[
                ("n4",1,"MED-D per disturbo neuromuscolare delta","TESTO"),
                ("n4",2,"AOU Federico II centro prescrittore MED-D","TESTO"),
                ("n5",1,"MED-E per disturbo neuromuscolare epsilon","TESTO"),
                ("n5",2,"AOU Federico II centro prescrittore MED-E","TESTO"),
            ]
        )
        self.db.commit()
        self.db.execute("PRAGMA query_only=ON")

    def test_suddivisione_finale_13_documenti_non_perde_id(self):
        items=list(range(13))
        chunks=final_verification_batches(items)
        self.assertEqual(len(chunks),5)
        self.assertEqual([len(chunk) for _,chunk in chunks],[3,3,3,3,1])
        self.assertEqual(
            [item for _,chunk in chunks for item in chunk],items
        )
        self.assertEqual(len(final_verification_batches(list(range(55)))),8)
        with self.assertRaises(ValueError):
            final_verification_batches([])
        with self.assertRaises(ValueError):
            final_verification_batches(list(range(56)))

    def test_verifica_due_lotti_indici_locali_nessuna_omissione(self):
        self._aggiungi_due_note_con_centro()
        first={"verificati":[
            {"documento_indice":0,"medicinale":"MED-A",
             "indicazione":"Disturbo muscolare alfa",
             "pagina_indicazione":1,"pagina_centro":2},
            {"documento_indice":1,"medicinale":"MED-B",
             "indicazione":"Malattia neurologica beta",
             "pagina_indicazione":1,"pagina_centro":2},
            {"documento_indice":2,"medicinale":"MED-C",
             "indicazione":"Melanoma cutaneo",
             "pagina_indicazione":1,"pagina_centro":2},
        ],"incerto":False}
        # Indici 0/1 del SECONDO lotto si riferiscono a n4/n5,
        # non a n1/n2.
        second={"verificati":[
            {"documento_indice":0,"medicinale":"MED-D",
             "indicazione":"Disturbo neuromuscolare delta",
             "pagina_indicazione":1,"pagina_centro":2},
            {"documento_indice":1,"medicinale":"MED-E",
             "indicazione":"Disturbo neuromuscolare epsilon",
             "pagina_indicazione":1,"pagina_centro":2},
        ],"incerto":False}
        result,calls=self.run_pipeline(
            discover={"indici":[0,1,2,3,4],"incerto":False},
            verify=[first,second]
        )
        self.assertEqual(result["strategia_tag"],"due_fasi")
        self.assertEqual(result["documenti_fase2"],5)
        self.assertEqual(result["lotti_verifica_finale"],2)
        self.assertEqual(result["lotti_verifica_conclusi"],2)
        self.assertEqual(result["lotti_verifica_non_validi"],0)
        self.assertEqual(result["documenti_inviati_verifica"],5)
        self.assertEqual(result["note_nel_contesto"],5)
        self.assertEqual(result["asserzioni_verifica_proposte"],5)
        self.assertEqual(result["asserzioni_verifica_accettate"],4)
        self.assertEqual(result["asserzioni_verifica_respinte"],1)
        self.assertEqual(result["coppie_documentate"],4)
        self.assertEqual(len(result["fonti"]),4)
        self.assertEqual(len(calls),5)
        self.assertEqual(result["chiamate_llm_dirette"],5)
        self.assertIn("MED-D",result["risposta"])
        self.assertIn("MED-E",result["risposta"])
        self.assertNotIn("MED-C",result["risposta"])
        self.assertEqual(result["documenti_senza_associazione_verificata"],
                         ["MED-C.pdf"])
        verify_requests=[data for prompt,data in calls
                         if prompt==VERIFY_PROMPT]
        self.assertEqual([len(x["documenti"]) for x in verify_requests],
                         [3,2])
        self.assertEqual(verify_requests[1]["documenti"][0]["documento_indice"],0)

    def test_quota_lotto_finale_conserva_prova_prima_del_guasto(self):
        self._aggiungi_due_note_con_centro()
        good={"verificati":[{
            "documento_indice":0,"medicinale":"MED-A",
            "indicazione":"Disturbo muscolare alfa",
            "pagina_indicazione":1,"pagina_centro":2,
        }],"incerto":False}
        class RateLimitError(Exception):
            pass
        error=EnginePhaseError(
            "connessione LLM",RateLimitError("errore fittizio")
        )
        result,calls=self.run_pipeline(
            discover={"indici":[0,1,2,3,4],"incerto":False},
            verify=[good,error]
        )
        self.assertEqual(result["stato"],"RISULTATI_PARZIALI")
        self.assertEqual(result["lotti_verifica_finale"],2)
        self.assertEqual(result["lotti_verifica_conclusi"],1)
        self.assertEqual(result["lotti_verifica_non_validi"],1)
        self.assertEqual(result["lotto_verifica_interrotto"],2)
        self.assertEqual(result["codice_errore_due_fasi"],"QUOTA")
        self.assertEqual(result["tipo_errore_due_fasi"],"RateLimitError")
        self.assertEqual(result["coppie_documentate"],1)
        self.assertEqual(result["documenti_inviati_verifica"],5)
        self.assertEqual(len(result["fonti"]),1)
        self.assertIn("MED-A",result["risposta"])
        self.assertIn("errore tecnico del modello",result["risposta"])
        self.assertEqual(len(calls),5)
        self.assertEqual(result["chiamate_llm_dirette"],5)

    def test_guasto_al_primo_lotto_si_astiene_con_diagnostica(self):
        class ServiceUnavailableError(Exception):
            pass
        error=EnginePhaseError(
            "connessione LLM",ServiceUnavailableError("fittizio")
        )
        result,calls=self.run_pipeline(verify=error)
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["motivo_astensione"],
                         "errore_llm_verifica_finale")
        self.assertEqual(result["documenti_fase1"],3)
        self.assertEqual(result["documenti_fase2"],2)
        self.assertEqual(result["lotti_fase1_validi"],1)
        self.assertEqual(result["lotti_verifica_finale"],1)
        self.assertEqual(result["lotto_verifica_interrotto"],1)
        self.assertEqual(result["codice_errore_due_fasi"],"SERVIZIO")
        self.assertEqual(result["lotti_verifica_conclusi"],0)
        self.assertEqual(result["fonti"],[])
        self.assertEqual(len(calls),4)

    def test_guasto_classificazione_prima_fase_preserva_metriche_sql(self):
        class RateLimitError(Exception):
            pass
        error=EnginePhaseError(
            "connessione LLM",RateLimitError("fittizio")
        )
        result,calls=self.run_pipeline(discover=error)
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["motivo_astensione"],"errore_llm_o_servizio")
        self.assertEqual(result["documenti_fase1"],3)
        self.assertEqual(result["lotti_fase1"],1)
        self.assertEqual(result["lotti_fase1_validi"],0)
        self.assertEqual(result["codice_errore_due_fasi"],"QUOTA")
        self.assertEqual(result["fase_errore_due_fasi"],"connessione LLM")
        self.assertEqual(result["tipo_errore_due_fasi"],"RateLimitError")
        self.assertIsNotNone(result["sql_fase1"])
        self.assertIsNone(result["sql_fase2"])
        self.assertEqual(result["fonti"],[])
        self.assertEqual(len(calls),3)

    def test_un_lotto_json_invalido_non_cancella_lotto_valido(self):
        self._aggiungi_due_note_con_centro()
        accepted={"verificati":[
            {"documento_indice":0,"medicinale":"MED-D",
             "indicazione":"Disturbo neuromuscolare delta",
             "pagina_indicazione":1,"pagina_centro":2},
        ],"incerto":False}
        result,calls=self.run_pipeline(
            discover={"indici":[0,1,2,3,4],"incerto":False},
            verify=["non JSON",accepted]
        )
        self.assertEqual(result["stato"],"RISULTATI_PARZIALI")
        self.assertEqual(result["lotti_verifica_finale"],2)
        self.assertEqual(result["lotti_verifica_non_validi"],1)
        self.assertEqual(result["lotti_verifica_conclusi"],1)
        self.assertEqual(result["coppie_documentate"],1)
        self.assertEqual(result["motivi_rifiuto_verifica"],
                         {"contratto_json_non_valido":1})
        self.assertIn("uno o piu' lotti",result["risposta"])
        self.assertIn("MED-D",result["risposta"])
        self.assertEqual(len(calls),5)

    def test_tabella_inesistente_avvia_automaticamente_due_select(self):
        # La SQL inventata NON viene eseguita. Il centro viene recuperato
        # dalla domanda e confermato con le pagine nello snapshot.
        self.assertEqual(question_center_anchors(self.db,QUESTION),
                         ["AOU Federico II"])
        executed=[]
        self.db.set_trace_callback(executed.append)
        try:
            result,calls=self.run_pipeline(
                sql=SQL_UNKNOWN_TABLE,plan=PLAN_WITH_FULL_CENTER
            )
        finally:
            self.db.set_trace_callback(None)
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-08-r24-errore-lotti-diagnosticabile")
        self.assertEqual(result["strategia_tag"],"due_fasi")
        self.assertEqual(result["errore_sql_iniziale"],"tabella_non_consentita")
        self.assertFalse(result["sql_iniziale_validata"])
        self.assertIsNone(result["sql_primo_tentativo"])
        self.assertEqual(result["sql_originale_llm"],SQL_UNKNOWN_TABLE)
        self.assertEqual(result["sql_tentativi_due_fasi"],2)
        self.assertEqual(result["sql_tentativi"],2)
        self.assertEqual(result["documenti_fase1"],3)
        self.assertEqual(result["documenti_fase2"],2)
        self.assertEqual(result["coppie_documentate"],2)
        self.assertEqual(result["chiamate_piano_documentale"],1)
        self.assertEqual(result["chiamate_llm_dirette"],4)
        self.assertEqual(len(calls),4)
        self.assertIn("MED-A",result["risposta"])
        self.assertIn("MED-B",result["risposta"])
        self.assertEqual(len(result["fonti"]),2)
        self.assertTrue(all("centri_prescrittori_inventati" not in q
                            for q in executed))

    def test_sql_tabella_inventata_senza_centro_documentato_si_astiene(self):
        question=("Quali medicinali hanno un principio attivo? "
                  "Indica le confezioni AIFA.")
        result,calls=self.run_pipeline(
            sql=SQL_UNKNOWN_TABLE,question=question
        )
        self.assertEqual(result["stato"],"ASTENSIONE_SQL_NON_VALIDA")
        self.assertEqual(result["chiamate_piano_documentale"],0)
        self.assertEqual(result["sql_tentativi"],0)
        self.assertEqual(len(calls),1)
        self.assertFalse(result["fonti"])
        self.assertEqual(result["piano_documentale_esito"],
                         "nessuna_ancora_documentale_verificata")

    def test_sql_tabella_inventata_piano_non_applicabile_si_astiene(self):
        rejected=json.dumps({
            "applicabile":False,"centro":None,
            "criterio_semantico":None,
            "vincoli_oggettivi_aggiuntivi":["vincolo oggettivo"]
        })
        result,calls=self.run_pipeline(
            sql=SQL_UNKNOWN_TABLE,plan=rejected
        )
        self.assertEqual(result["stato"],"ASTENSIONE_SQL_NON_VALIDA")
        self.assertEqual(result["piano_documentale_esito"],
                         "piano_non_applicabile")
        self.assertEqual(result["chiamate_piano_documentale"],1)
        self.assertEqual(result["sql_tentativi"],0)
        self.assertEqual(len(calls),2)
        self.assertFalse(result["fonti"])

    def test_sql_dml_o_multipla_resta_bloccata_senza_fallback(self):
        for query in (
            "DELETE FROM note",
            "SELECT id FROM note; DROP TABLE note",
            "SELECT * FROM note JOIN pagine",
        ):
            with self.assertRaises(EnginePhaseError):
                self.run_pipeline(sql=query)

    def test_r18_sql_vuoto_due_query_e_conferma_pagine(self):
        result,calls=self.run_pipeline()
        self.assertEqual(result["tag_auto_revision"],
                         "2026-11-08-r24-errore-lotti-diagnosticabile")
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

    def test_sql_esatta_r18_con_centro_revisionato_e_sottoquery(self):
        # SQL originale del test nell'app: prima recupero vuoto,
        # quindi PLAN + SQL1 + classificazione + SQL2 + LOTUS.
        original,partial=auto._run_generated_select(
            self.db,auto.validate_sql(SQL_R18_REAL))
        self.assertFalse(partial)
        self.assertEqual(original,[])
        self.assertEqual(document_center_anchors(SQL_R18_REAL,QUESTION),[])
        self.assertEqual(recovery_center_anchors(SQL_R18_REAL,QUESTION),
                         ["Federico II"])
        result,calls=self.run_pipeline(sql=SQL_R18_REAL)
        self.assertEqual(result["strategia_tag"],"due_fasi")
        self.assertEqual(result["motivo_due_fasi"],"sql_vuoto")
        self.assertEqual(result["documenti_fase1"],3)
        self.assertEqual(result["documenti_fase2"],2)
        self.assertEqual(result["coppie_documentate"],2)
        self.assertEqual(result["chiamate_piano_documentale"],1)
        self.assertEqual(result["sql_tentativi_due_fasi"],2)
        self.assertEqual(result["chiamate_llm_dirette"],4)
        self.assertEqual(len(calls),4)
        self.assertIn("MED-A",result["risposta"])
        self.assertTrue(all("#p2" in url for url in result["fonti"]))

    def test_ancore_generiche_non_prendono_filtri_clinici_della_sottoquery(self):
        # La query scelta dall'LLM puo' contenere sottoquery semantiche
        # irrilevanti. Non diventano mai un'ancora di struttura.
        self.assertNotIn("neuromuscolar",
                         recovery_center_anchors(SQL_R18_REAL,QUESTION))
        altered=SQL_R18_REAL.replace(
            "c.centro COLLATE NOCASE LIKE '%Federico II%'",
            "n.farmaco_candidato COLLATE NOCASE LIKE '%Federico II%'"
        ).replace(
            "c.centro COLLATE NOCASE LIKE '%AOU%'",
            "n.indicazione_candidata COLLATE NOCASE LIKE '%AOU%'"
        )
        self.assertEqual(recovery_center_anchors(altered,QUESTION),[])
        self.assertEqual(recovery_center_anchors(
            SQL_R18_REAL,QUESTION.replace("Federico II","altra struttura")),
            [])

    def _abilita_relazione_curata_per_r19(self):
        # Fixture della sola SELECT r19: non alterare la prova r18,
        # che richiede un risultato iniziale davvero vuoto.
        self.db.execute("PRAGMA query_only=OFF")
        self.db.execute(
            "INSERT INTO nota_centro_documentato "
            "(nota_id,centro,numero_pagina) VALUES (?,?,?)",
            ("n1","AOU Federico II",2)
        )
        self.db.execute("PRAGMA query_only=ON")

    def test_sql_reale_r19_con_righe_attiva_due_fasi_per_copertura(self):
        """Una SELECT con 1 nota non prova completezza sui 3 PDF del centro."""
        self._abilita_relazione_curata_per_r19()
        original, partial=auto._run_generated_select(
            self.db,auto.validate_sql(SQL_R19_REAL))
        self.assertFalse(partial)
        self.assertEqual(len(original),1)
        result,calls=self.run_pipeline(sql=SQL_R19_REAL)
        self.assertEqual(result["righe_sql_primo_tentativo"],1)
        self.assertEqual(result["strategia_tag"],"due_fasi")
        self.assertEqual(result["motivo_due_fasi"],
                         "join_centri_documenti_potenzialmente_esclusi")
        self.assertTrue(result["controllo_copertura_eseguito"])
        self.assertEqual(result["documenti_controllo_copertura"],3)
        self.assertEqual(result["documenti_esclusi_primo_recupero"],2)
        self.assertIn("p.testo LIKE",result["sql_controllo_copertura"])
        self.assertEqual(result["documenti_fase1"],3)
        self.assertEqual(result["documenti_fase2"],2)
        self.assertEqual(result["coppie_documentate"],2)
        self.assertEqual(result["sql_tentativi"],4)  # SQL, gate, SQL1, SQL2
        self.assertEqual(result["chiamate_llm_dirette"],4)
        self.assertEqual(len(calls),4)
        self.assertIn("MED-A",result["risposta"])
        self.assertIn("MED-B",result["risposta"])

    def test_copertura_ristretta_senza_piano_valido_resta_segnalata(self):
        """Non si sopprime la diagnosi anche se il piano e' rifiutato."""
        self._abilita_relazione_curata_per_r19()
        rejected=json.dumps({"applicabile":False,"centro":None,
            "criterio_semantico":None,
            "vincoli_oggettivi_aggiuntivi":["filtro oggettivo"]})
        # L'LLM di sintesi normale riceve una risposta simulata: non
        # dev'essere spacciata per risultato esaustivo.
        call=[]
        def fake_ask(model,system,payload,**kwargs):
            direct_attempt()
            call.append(system)
            if system==auto.SQL_PROMPT:
                value=SQL_R19_REAL
            elif system==PLAN_PROMPT:
                value=rejected
            else:
                value="MED-A documentato."
            return value,{"token_input":1,"token_output":1,"costo_usd":0}
        lotus=types.ModuleType("lotus")
        lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        models=types.ModuleType("lotus.models")
        models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":lotus,"lotus.models":models}), \
             patch.object(auto,"ask",side_effect=fake_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(self.db,QUESTION,"mock")
        self.assertEqual(result["strategia_tag"],"normale")
        self.assertTrue(result["risultato_parziale"])
        self.assertEqual(result["stato"],"RISULTATI_PARZIALI")
        self.assertIn("copertura della risposta",result["risposta"])
        self.assertEqual(result["documenti_esclusi_primo_recupero"],2)

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
        self.assertEqual(result["motivi_rifiuto_verifica"],{
            "La pagina indicata non menziona la struttura":1
        })
        self.assertEqual(result["asserzioni_verifica_respinte"],1)

    def test_associazione_falsa_non_elimina_quella_verificata(self):
        mixed={
            "verificati":[{
                "documento_indice":0,"medicinale":"MED-A",
                "indicazione":"Disturbo muscolare alfa",
                "pagina_indicazione":1,"pagina_centro":2
            },{
                "documento_indice":1,"medicinale":"MED-B",
                "indicazione":"Melanoma cutaneo",
                "pagina_indicazione":1,"pagina_centro":2
            }],
            "incerto":False,
        }
        result,calls=self.run_pipeline(verify=mixed)
        self.assertEqual(result["stato"],"RISULTATI_PARZIALI")
        self.assertEqual(result["strategia_tag"],"due_fasi")
        self.assertEqual(result["coppie_documentate"],1)
        self.assertEqual(result["asserzioni_verifica_proposte"],2)
        self.assertEqual(result["asserzioni_verifica_accettate"],1)
        self.assertEqual(result["asserzioni_verifica_respinte"],1)
        self.assertEqual(result["motivi_rifiuto_verifica"],{
            "Indicazione non supportata dalla pagina citata":1})
        self.assertEqual(len(result["documenti_candidati_verifica"]),2)
        self.assertEqual(result["documenti_fase2"],2)
        self.assertEqual(len(calls),4)
        self.assertEqual(result["chiamate_llm_dirette"],4)
        self.assertEqual(len(result["fonti"]),1)
        self.assertIn("MED-A",result["risposta"])
        self.assertNotIn("MED-B",result["risposta"])
        self.assertNotIn("Melanoma",result["risposta"])
        self.assertIn("associazioni proposte",result["risposta"])

    def test_verifica_json_non_valido_registra_causa(self):
        result,calls=self.run_pipeline(verify="testo libero anziche JSON")
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["motivo_astensione"],
                         "verifica_strutturata_non_valida")
        self.assertEqual(result["motivi_rifiuto_verifica"],
                         {"contratto_json_non_valido":1})
        self.assertFalse(result["fonti"])
        self.assertEqual(len(calls),4)

    def test_indicazione_inventata_non_supera_verifica(self):
        forged={
            "verificati":[{
                "documento_indice":0,"medicinale":"MED-A",
                "indicazione":"Melanoma cutaneo",
                "pagina_indicazione":1,"pagina_centro":2
            }],"incerto":False
        }
        result,_=self.run_pipeline(verify=forged)
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["motivo_astensione"],
                         "verifica_strutturata_non_valida")
        self.assertEqual(result["coppie_documentate"],0)
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
        self.assertEqual(result["stato"],"ASTENSIONE_DUE_FASI")
        self.assertEqual(result["chiamate_piano_documentale"],1)
        self.assertEqual(len(calls),2)

    def test_snapshot_fase1_tutti_pdf_gold_senza_dizionario(self):
        root=Path(__file__).resolve().parents[1]
        dbfile=root/"risultati/tesi_statico_20261102.sqlite.gz"
        goldfile=root/"tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json"
        if not dbfile.is_file() or not goldfile.is_file():
            self.skipTest("Snapshot statico o riferimento non disponibile")
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(dbfile.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            sql=sql_from_document_plan({"centro":"Federico II"})
            self.assertNotIn("neuromuscolari",sql.casefold())
            records,partial=auto._run_generated_select(
                db,auto.validate_sql(sql))
            self.assertFalse(partial)
            self.assertEqual(len(records),161)
            docs,partial_notes=auto._note_candidates(db,records)
            self.assertEqual(len(docs),161)
            batches=refinement_batches(docs)
            self.assertEqual(len(batches),9)
            self.assertEqual(sum(len(part) for _,part in batches),161)
            expected=json.loads(goldfile.read_text(encoding="utf-8"))
            expected_ids={c["sha256_pdf"] for c in expected["casi_positivi"]}
            found_ids={c["nota_id"] for c in docs}
            self.assertTrue(expected_ids<=found_ids)
            self.assertEqual(len(expected_ids),13)
            print("R18 fase 1:",len(docs),
                  "documenti, lotti",len(batches),
                  "PDF distinti del riferimento",len(expected_ids))
        finally:
            db.close()

    def test_seconda_sql_usa_solo_identificativi_validi(self):
        sql=sql_second_stage(["a' OR 1=1 --","b"])
        self.assertIn("''",sql)
        self.assertNotIn("centri_candidati",sql)
        with self.assertRaises(ValueError):
            sql_second_stage([])
        with self.assertRaises(ValueError):
            sql_second_stage([""])

    def test_audit_gold_strutturato_holdout_20261108(self):
        """Audit read-only sul DB congelato, branch temporaneo senza merge."""
        root=Path(__file__).resolve().parents[1]
        frozen=root/"risultati/tesi_statico_20261102.sqlite.gz"
        db=sqlite3.connect(":memory:")
        try:
            db.deserialize(gzip.decompress(frozen.read_bytes()))
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            print("=== GOLD-SQL-BLOCK ===")
            for name in ("KAYFANDA","BESREMI","VOXZOGO"):
                rows=db.execute(
                    "SELECT ema_id,nome,principio_attivo,"
                    "stato_ema,data_decisione_ue,indicazione_ema "
                    "FROM ema_medicinali WHERE UPPER(nome)=? "
                    "ORDER BY ema_id",(name,)
                ).fetchall()
                print("EMA",name,
                      [dict(row) for row in rows])
            for name in ("EMGALITY","PROCYSBI","HEMLIBRA"):
                rows=db.execute(
                    "SELECT aic,nome,principio_attivo,descrizione,"
                    "classe_a_h_snapshot,classe_a_h_data "
                    "FROM aifa_confezioni WHERE UPPER(nome)=? "
                    "ORDER BY aic",(name,)
                ).fetchall()
                print("AIFA",name,"COUNT",len(rows),
                      "ROWS",[dict(row) for row in rows])
            for keyword in ("BIMZELX","EPIDYOLEX"):
                rows=db.execute(
                    "SELECT nome_file,percorso_zip,anno,protocollo_candidato "
                    "FROM note WHERE UPPER(nome_file) LIKE ? "
                    "ORDER BY anno,nome_file",("%"+keyword+"%",)
                ).fetchall()
                print("REGIONE",keyword,"COUNT",len(rows),
                      "ROWS",[dict(row) for row in rows])
            print("=== END-GOLD-SQL-BLOCK ===")
        finally:
            db.close()



if __name__=="__main__":
    unittest.main()
