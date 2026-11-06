"""Verifiche offline della terza pipeline: nessuna API LLM coinvolta."""
from __future__ import annotations

import sqlite3
import sys
import types
import pandas as pd  # Import prima delle patch ai moduli, evita reimport numpy nei test.
import unittest
from unittest.mock import patch

from tesi import tag_automatico as auto


class TAGAutomaticoTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE note(
                id TEXT PRIMARY KEY, nome_file TEXT,
                anno INTEGER, protocollo_candidato TEXT, data_candidata TEXT,
                farmaco_candidato TEXT, indicazione_candidata TEXT,
                percorso_zip TEXT, archivio_url TEXT
            );
            CREATE TABLE pagine(
                nota_id TEXT, numero_pagina INTEGER, testo TEXT, metodo TEXT
            );
            INSERT INTO note VALUES
              ('n1','nota1.pdf',2022,'PROT/01','02/01/2022','MED-A','categoria clinica A','nota1.pdf','https://example.org/a.zip'),
              ('n2','nota2.pdf',2023,'PROT/02','03/02/2023','MED-B','categoria clinica B','nota2.pdf','https://example.org/b.zip');
            INSERT INTO pagine VALUES
              ('n1',1,'Menzione Federico II e descrizione documento A','TESTO'),
              ('n1',2,'Indicazione terapeutica del documento A','TESTO'),
              ('n2',1,'Menzione Federico II e descrizione documento B','TESTO');
        """)
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    @staticmethod
    def candidate_sql():
        return ("SELECT DISTINCT n.id AS nota_id FROM note n "
                "JOIN pagine p ON p.nota_id=n.id "
                "WHERE p.testo LIKE '%Federico%'")

    def test_retrieval_includes_every_page_of_candidate_notes(self):
        sql = self.candidate_sql()
        records, partial = auto._run_generated_select(self.db, sql)
        self.assertEqual(len(records), 2)
        self.assertFalse(partial)
        notes, page_partial = auto._note_candidates(self.db, records)
        self.assertFalse(page_partial)
        self.assertEqual(len(notes), 2)
        self.assertIn("[pagina 2]", notes[0]["testo_selezione"])
        self.assertIn("#p2", " ".join(notes[0]["fonti"]))
        groups, members = auto._lotus_plan(notes)
        self.assertEqual(sum(map(len, members.values())), 2)
        self.assertTrue(groups)

    def test_no_manual_clinical_expansion_in_prompt(self):
        self.assertNotIn("miastenia", auto.SQL_PROMPT.casefold())
        self.assertNotIn("neuromuscolar", auto.SQL_PROMPT.casefold())
        self.assertNotIn("distrofia", auto.SQL_PROMPT.casefold())

    def test_llm_sql_then_lotus_then_answer(self):
        messages = []
        def mock_ask(model,system,payload,**kwargs):
            messages.append(system)
            if system == auto.SQL_PROMPT:
                return self.candidate_sql(), {"token_input":2,"token_output":3,"costo_usd":0}
            return "Due note consultate, citando i documenti.", {"token_input":5,"token_output":6,"costo_usd":0}
        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_: None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_, **__: types.SimpleNamespace()
        with patch.dict(sys.modules, {"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(self.db,"Documenti del Federico II", "modello-fittizio")
        self.assertEqual(result["versione_tag"],"automatico-v1")
        self.assertEqual(result["righe_sql"],2)
        self.assertEqual(result["righe_recuperate"],2)
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(len(messages),2)
        self.assertTrue(any("#p2" in f for f in result["fonti"]))


    def test_scalar_attribute_sql_is_selected_by_lotus(self):
        """Regressione D01: il valore puo' essere senza nome nella SELECT."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni(aic TEXT, nome TEXT, principio_attivo TEXT);
            CREATE TABLE ema_medicinali(ema_id TEXT, nome TEXT, principio_attivo TEXT);
            INSERT INTO aifa_confezioni VALUES ('001','BEYONTTRA','sostanza-demo');
            INSERT INTO ema_medicinali VALUES ('EM-01','BEYONTTRA','sostanza-demo');
        """)
        self.db.execute("PRAGMA query_only=ON")
        sql = ("SELECT principio_attivo FROM aifa_confezioni "
               "WHERE nome LIKE '%BEYONTTRA%' "
               "UNION SELECT principio_attivo FROM ema_medicinali "
               "WHERE nome LIKE '%BEYONTTRA%'")
        seen = []
        called_system_prompts = []
        def mock_ask(model, system, payload, **kwargs):
            called_system_prompts.append(system)
            if system == auto.SQL_PROMPT:
                return sql, {"token_input":1,"token_output":1,"costo_usd":0}
            return "Principio attivo: sostanza-demo.", {
                "token_input":1,"token_output":1,"costo_usd":0
            }
        def fake_sem_filter(frame, instruction):
            seen.append(instruction)
            # Simula un filtro che passa i campi utili solo se trattati come
            # attributi tabellari, anziche' richiedere prove cliniche.
            if "RISULTATI SQL STRUTTURATI" in instruction and \
                    "sostanza-demo" in frame.iloc[0]["testo"]:
                return frame
            return frame.iloc[0:0]
        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_:None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",side_effect=fake_sem_filter):
            result=auto.automatic_tag(
                self.db,"Qual e' il principio attivo del medicinale BEYONTTRA?",
                "modello-fittizio"
            )
        self.assertEqual(result["stato"],"OK")
        self.assertIn("sostanza-demo",result["risposta"])
        self.assertEqual(result["righe_sql"],1)
        self.assertEqual(result["righe_selezionate_lotus"],1)
        self.assertIn("attributo",seen[0])
        self.assertEqual(called_system_prompts[-1],auto.TABULAR_ANSWER_PROMPT)

    def test_tabular_prompt_preserves_llm_sql_retrieval(self):
        self.assertIn("denominazione del medicinale (nome)",auto.SQL_PROMPT)
        self.assertIn("valore non vuoto",auto.TABULAR_SEMANTIC_PROMPT)
        self.assertNotIn("miastenia",auto.TABULAR_SEMANTIC_PROMPT.casefold())


    def test_identifier_provenance_is_grounded(self):
        """Il fallback trova solo codici realmente presenti nello SQLite."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni (
                aic TEXT, nome TEXT, principio_attivo TEXT
            );
            CREATE TABLE ema_medicinali (
                ema_id TEXT, nome TEXT, principio_attivo TEXT,
                url_ema TEXT
            );
            INSERT INTO aifa_confezioni VALUES
              ('050000111','BEYONTTRA','ACORAMIDIS'),
              ('050000222','BEYONTTRA','ACORAMIDIS');
            INSERT INTO ema_medicinali VALUES
              ('EMEA/H/C/006333','Beyonttra',
               'acoramidis hydrochloride','https://example.org/ema');
        """)
        self.db.execute("PRAGMA query_only=ON")
        rows = [
            {"nome":"BEYONTTRA","principio_attivo":"ACORAMIDIS",
             "aic":None,"ema_id":None,"fonte_origine":"AIFA"},
            {"nome":"Beyonttra","principio_attivo":"acoramidis hydrochloride",
             "aic":None,"ema_id":"EMEA/H/C/006333","fonte_origine":"EMA"},
        ]
        result = auto._tabular_candidates(self.db,rows)
        self.assertEqual(len(result),2)
        self.assertTrue(any("050000111" in src for src in result[0]["fonti"]))
        self.assertTrue(any("050000222" in src for src in result[0]["fonti"]))
        self.assertFalse(any("EMEA/" in src for src in result[0]["fonti"]))
        self.assertTrue(any("EMEA/H/C/006333" in src for src in result[1]["fonti"]))
        unknown = auto._verify_tabular_identifiers(
            self.db,{"nome":"BEYONTTRA",
                     "principio_attivo":"sostanza non presente",
                     "fonte_origine":"AIFA"})
        self.assertEqual(unknown,[])

    def test_sql_prompt_preserves_real_identifiers(self):
        self.assertIn("VERO aic", auto.SQL_PROMPT)
        self.assertIn("VERO ema_id", auto.SQL_PROMPT)
        self.assertIn("fonte_origine", auto.SQL_PROMPT)
        self.assertIn("NON richiedere numeri", auto.TABULAR_ANSWER_PROMPT)
        self.assertIn("differenza di denominazione", auto.TABULAR_ANSWER_PROMPT)
        self.assertIn("senza evidenze", auto.TABULAR_ANSWER_PROMPT)
        self.assertNotIn("BEYONTTRA", auto.TABULAR_ANSWER_PROMPT)
        self.assertIn("Cita nome del documento e pagina", auto.ANSWER_PROMPT)


    def test_union_different_identifiers_not_mislabelled_as_aic(self):
        """D03: UNION ALL deve conservare l'identità EMA, non un falso AIC."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni (
                aic TEXT, nome TEXT, principio_attivo TEXT
            );
            CREATE TABLE ema_medicinali (
                ema_id TEXT, nome TEXT, principio_attivo TEXT, url_ema TEXT
            );
            INSERT INTO aifa_confezioni VALUES
              ('050231012','VABYSMO','FARICIMAB'),
              ('050231024','VABYSMO','FARICIMAB');
            INSERT INTO ema_medicinali VALUES
              ('EMEA/H/C/005642','Vabysmo','Faricimab',
               'https://example.org/vabysmo');
        """)
        self.db.execute("PRAGMA query_only=ON")
        generated = (
            "SELECT aic, nome, principio_attivo FROM aifa_confezioni "
            "WHERE nome LIKE '%VABYSMO%' UNION ALL "
            "SELECT ema_id, nome, principio_attivo FROM ema_medicinali "
            "WHERE nome LIKE '%VABYSMO%'"
        )
        rows, partial = auto._run_generated_select(self.db, generated)
        self.assertFalse(partial)
        self.assertEqual(len(rows),3)
        candidates = auto._tabular_candidates(self.db,rows)
        self.assertEqual(sum(bool(x["provenienza_sql_riconciliata"]) for x in candidates),1)
        ema_row = next(x for x in candidates if "EMEA/H/C/005642" in x["testo"])
        self.assertIn('"aic": null',ema_row["testo"])
        self.assertIn('"ema_id": "EMEA/H/C/005642"',ema_row["testo"])
        self.assertEqual(ema_row["fonti"],[
            "EMA EMEA/H/C/005642 | https://example.org/vabysmo"
        ])
        self.assertFalse(any("AIFA AIC EMEA" in src
                             for item in candidates for src in item["fonti"]))

    def test_elrexfio_exact_name_case_insensitive(self):
        """D04: non considerare assente un medicinale per le maiuscole."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE ema_medicinali (
                ema_id TEXT, nome TEXT, data_decisione_ue TEXT
            );
            INSERT INTO ema_medicinali VALUES
              ('EMEA/H/C/005908','Elrexfio','2023-12-07');
        """)
        self.db.execute("PRAGMA query_only=ON")
        generated = ("SELECT ema_id,nome,data_decisione_ue "
                     "FROM ema_medicinali WHERE nome = 'ELREXFIO'")
        original, _ = auto._run_generated_select(self.db,generated)
        self.assertEqual(original,[])
        fixed = auto._normalize_exact_name_comparisons(generated)
        self.assertIn("COLLATE NOCASE",fixed)
        self.assertEqual(fixed,auto._normalize_exact_name_comparisons(fixed))
        records, partial = auto._run_generated_select(self.db,fixed)
        self.assertEqual(len(records),1)
        self.assertFalse(partial)
        self.assertEqual(records[0]["data_decisione_ue"],"2023-12-07")


    def test_full_pipeline_normalizes_exact_name_and_reports_revision(self):
        """D04/D05: query prodotta senza NOCASE, recupero completo e audit."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni(
                aic TEXT,nome TEXT,principio_attivo TEXT
            );
            CREATE TABLE ema_medicinali(
                ema_id TEXT,nome TEXT,data_decisione_ue TEXT,url_ema TEXT
            );
            INSERT INTO ema_medicinali VALUES
              ('EMA-DEMO','Elrexfio','data-snapshot-demo','https://example.org/ema');
        """)
        self.db.execute("PRAGMA query_only=ON")
        original = (
            "SELECT ema_id,nome,data_decisione_ue "
            "FROM ema_medicinali WHERE nome = 'ELREXFIO'"
        )
        seen = []
        def mock_ask(model,system,payload,**kwargs):
            seen.append(system)
            if system == auto.SQL_PROMPT:
                return original, {"token_input":1,"token_output":1,"costo_usd":0}
            return "Data: data-snapshot-demo", {
                "token_input":1,"token_output":1,"costo_usd":0
            }
        fake_lotus = types.ModuleType("lotus")
        fake_lotus.settings = types.SimpleNamespace(configure=lambda **_:None)
        fake_models = types.ModuleType("lotus.models")
        fake_models.LM = lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(
                self.db,"Data della decisione UE per ELREXFIO",
                "modello-fittizio"
            )
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["righe_sql"],1)
        self.assertIn("data-snapshot-demo",result["risposta"])
        self.assertIn("COLLATE NOCASE",result["sql"])
        self.assertNotIn("COLLATE NOCASE",result["sql_originale_llm"])
        self.assertTrue(result["sql_normalizzato_nome"])
        self.assertEqual(result["tag_auto_revision"],auto.TAG_AUTO_REVISION)
        self.assertEqual(len(seen),2)

    def test_full_pipeline_audits_misaligned_ema_id(self):
        """D03: controlla che l'etichetta falsa AIC non passi a LOTUS."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.executescript("""
            CREATE TABLE aifa_confezioni(
                aic TEXT,nome TEXT,principio_attivo TEXT
            );
            CREATE TABLE ema_medicinali(
                ema_id TEXT,nome TEXT,principio_attivo TEXT,url_ema TEXT
            );
            INSERT INTO aifa_confezioni VALUES
              ('AIC-DEMO','Medicinale-X','Principio-A');
            INSERT INTO ema_medicinali VALUES
              ('EMA-DEMO','Medicinale-X','Principio-A','https://example.org/ema');
        """)
        self.db.execute("PRAGMA query_only=ON")
        generated=(
            "SELECT aic,nome,principio_attivo FROM aifa_confezioni "
            "WHERE nome LIKE '%Medicinale-X%' UNION ALL "
            "SELECT ema_id,nome,principio_attivo FROM ema_medicinali "
            "WHERE nome LIKE '%Medicinale-X%'"
        )
        def mock_ask(model,system,payload,**kwargs):
            if system == auto.SQL_PROMPT:
                return generated,{"token_input":1,"token_output":1,"costo_usd":0}
            return "Principio-A",{"token_input":1,"token_output":1,"costo_usd":0}
        fake_lotus=types.ModuleType("lotus")
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        fake_models=types.ModuleType("lotus.models")
        fake_models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(
                self.db,"Principio attivo di Medicinale-X","modello-fittizio"
            )
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["identificativi_sql_riconciliati"],1)
        self.assertEqual(result["righe_sql"],2)
        self.assertTrue(any(src.startswith("EMA EMA-DEMO")
                            for src in result["fonti"]))
        self.assertFalse(any("AIFA AIC EMA-DEMO" in src
                             for src in result["fonti"]))


    def test_document_mentions_are_not_limited_to_filename(self):
        """La ricerca di menzioni include anche note con altri farmaci nel titolo."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.execute(
            "UPDATE pagine SET testo='La nota cita il prodotto MED-C, "
            "senza avere MED-C nel titolo.' "
            "WHERE nota_id='n2'"
        )
        self.db.execute("PRAGMA query_only=ON")
        sql = (
            "SELECT DISTINCT n.id AS nota_id FROM note n "
            "JOIN pagine p ON p.nota_id=n.id "
            "WHERE p.testo LIKE '%MED-C%'"
        )
        valid = auto.validate_sql(sql)
        rows, partial = auto._run_generated_select(self.db,valid)
        self.assertFalse(partial)
        self.assertEqual([r["nota_id"] for r in rows],["n2"])
        documents, doc_partial = auto._note_candidates(self.db,rows)
        self.assertFalse(doc_partial)
        self.assertEqual(len(documents),1)
        self.assertIn("MED-C",documents[0]["testo"])
        self.assertIn("pagine.testo",auto.SQL_PROMPT)
        self.assertIn("note.nome_file",auto.SQL_PROMPT)

    def test_sql_prompt_avoids_reversed_duplicated_join(self):
        """Una relazione uno-a-molti non necessita una UNION del JOIN inverso."""
        self.assertIn("UNION ridondante", auto.SQL_PROMPT)
        self.assertIn("JOIN soltanto sul principio attivo",auto.SQL_PROMPT)
        self.assertNotIn("LUMYKRAS",auto.SQL_PROMPT)
        self.assertNotIn("KEYTRUDA",auto.SQL_PROMPT)


    def test_all_seven_document_candidates_reach_synthesis_under_budget(self):
        """Nessuna nota viene persa perche' quelle prima sono piu' lunghe."""
        self.db.execute("PRAGMA query_only=OFF")
        # Ogni pagina resta sotto il taglio di 4200 caratteri, ma la somma
        # supera di molto il budget complessivo di 44000 caratteri.
        for i in range(1, 8):
            ident=f"nota-{i}"
            self.db.execute(
                "INSERT INTO note(id,nome_file,anno,protocollo_candidato,"
                "data_candidata,farmaco_candidato,indicazione_candidata,"
                "percorso_zip,archivio_url) VALUES (?,?,?,?,?,?,?,?,?)",
                (ident,f"nota-{i}.pdf",2020+i,f"PROT-{i}",
                 None,"Farmaco X",None,f"nota-{i}.pdf","https://example.org/regione.zip"))
            for page in range(1,4):
                self.db.execute(
                    "INSERT INTO pagine VALUES (?,?,?,?)",
                    (ident,page,f"Farmaco X e relazione documentata. "
                     + "dettaglio " * 350,"TESTO"))
        self.db.execute("PRAGMA query_only=ON")
        sql=("SELECT DISTINCT n.id AS nota_id FROM note n "
             "JOIN pagine p ON p.nota_id=n.id "
             "WHERE p.testo LIKE '%Farmaco X%'")
        captures=[]
        def mock_ask(model,system,payload,**kwargs):
            if system==auto.SQL_PROMPT:
                return sql,{"token_input":1,"token_output":1,"costo_usd":0}
            captures.append(payload)
            return "Sette note esaminate",{
                "token_input":1,"token_output":1,"costo_usd":0
            }
        fake_lotus=types.ModuleType("lotus")
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        fake_models=types.ModuleType("lotus.models")
        fake_models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(
                self.db,"Quali note menzionano Farmaco X? Indica anno e documento.",
                "modello-fittizio")
        self.assertEqual(result["righe_recuperate"],7)
        self.assertEqual(result["note_nell_indice"],7)
        self.assertEqual(result["note_nel_contesto"],7)
        self.assertEqual(len(captures),1)
        payload=captures[0]
        self.assertEqual(len(payload["indice_documentale"]),7)
        self.assertEqual(len(payload["evidenze"]),7)
        self.assertTrue(payload["risultati_parziali"])
        self.assertTrue(all(e["testo"].startswith("Identificativo interno nota:")
                            for e in payload["evidenze"]))
        self.assertLessEqual(sum(len(e["testo"]) for e in payload["evidenze"]),
                             auto.MAX_ANSWER_CHARS)
        for i in range(1,8):
            self.assertIn(f"nota-{i}",[x["nota_id"] for x
                                       in payload["indice_documentale"]])
            self.assertIn(f"nota-{i}.pdf",
                          "\n".join(x["testo"] for x in payload["evidenze"]))
            self.assertEqual(
                next(x["anno_archivio"] for x in payload["indice_documentale"]
                     if x["nota_id"]==f"nota-{i}"),2020+i)
        self.assertEqual(len(result["fonti"]),21)
        self.assertIn("alcuni testi di pagina sono abbreviati",result["risposta"])

    def test_balanced_context_does_not_drop_final_document(self):
        docs=[
            {"chiave":f"NOTA:{i}","testo":"ID "+str(i)+" "+("z"*20000),
             "fonte":f"note{i}#p1","fonti":[f"note{i}#p1"]}
            for i in range(7)
        ]
        chosen,partial=auto._balanced_answer_evidence(docs)
        self.assertTrue(partial)
        self.assertEqual(len(chosen),7)
        self.assertTrue(chosen[-1]["testo"].startswith("ID 6"))
        self.assertTrue(all(x["testo"] for x in chosen))


    def test_regional_scope_normalizer_removes_only_spurious_path_filter(self):
        """Un nome di archivio non certifica Campania: recupero preservato."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.execute("UPDATE pagine SET testo='MED-A citato nel testo' "
                        "WHERE nota_id='n1'")
        self.db.execute("UPDATE pagine SET testo='MED-B citato nel testo' "
                        "WHERE nota_id='n2'")
        self.db.execute("PRAGMA query_only=ON")
        sql=(
            "SELECT DISTINCT note.id AS nota_id FROM note "
            "JOIN pagine ON note.id=pagine.nota_id "
            "WHERE pagine.testo LIKE '%MED-A%' "
            "AND note.percorso_zip LIKE '%Campania%'"
        )
        original_rows,_=auto._run_generated_select(self.db,auto.validate_sql(sql))
        self.assertEqual(original_rows,[])
        fixed,changed=auto._normalize_regional_scope(
            auto.validate_sql(sql),
            "Quali note regionali della Campania menzionano MED-A?")
        self.assertTrue(changed)
        self.assertNotIn("LIKE '%Campania%'",fixed)
        self.assertIn("LIKE '%MED-A%'",fixed)
        records,partial=auto._run_generated_select(self.db,auto.validate_sql(fixed))
        self.assertFalse(partial)
        self.assertEqual([x["nota_id"] for x in records],["n1"])
        self.assertEqual(fixed,auto._normalize_regional_scope(
            fixed,"Quali note della Campania menzionano MED-A?")[0])

    def test_regional_scope_normalizer_handles_alias_and_or(self):
        """La regione non dipende da prefissi testuali del percorso."""
        sql=(
            "SELECT DISTINCT n.id AS nota_id FROM note n "
            "JOIN pagine p ON p.nota_id=n.id "
            "WHERE p.testo LIKE '%MED-A%' "
            "AND (n.percorso_zip LIKE '%Campania%' OR "
            "p.testo LIKE '%Campania%')"
        )
        normalized,changed=auto._normalize_regional_scope(
            auto.validate_sql(sql),
            "Quali note regionali della Campania menzionano MED-A?")
        self.assertTrue(changed)
        self.assertIn("LIKE '%MED-A%'",normalized)
        self.assertNotIn("n.percorso_zip LIKE '%Campania%'",normalized)
        self.assertTrue(auto.validate_sql(normalized))
        # Senza la regione nella domanda, il filtro viene lasciato invariato.
        unchanged,changed=auto._normalize_regional_scope(
            sql,"Quali note contengono MED-A?")
        self.assertFalse(changed)
        self.assertEqual(unchanged,sql)

    def test_regional_scope_preserves_explicit_path_queries(self):
        sql=(
            "SELECT id AS nota_id FROM note "
            "WHERE note.percorso_zip LIKE '%Campania%' "
            "AND note.anno=2026"
        )
        normalized,changed=auto._normalize_regional_scope(
            sql,"Quali percorsi archivio delle note Campania sono del 2026?")
        self.assertFalse(changed)
        self.assertEqual(normalized,sql)
        other,changed=auto._normalize_regional_scope(
            sql.replace("%Campania%","%2026%"),
            "Quali note regionali della Campania appartengono al 2026?")
        self.assertFalse(changed)
        self.assertIn("'%2026%'",other)

    def test_full_pipeline_audits_regional_scope_correction(self):
        """Nessun retry LLM; query origine conservata e note davvero recuperate."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.execute("UPDATE pagine SET testo='MED-A indicato nel documento' "
                        "WHERE nota_id='n1'")
        self.db.execute("PRAGMA query_only=ON")
        raw_sql=(
            "SELECT DISTINCT n.id AS nota_id FROM note n "
            "JOIN pagine p ON p.nota_id=n.id "
            "WHERE p.testo LIKE '%MED-A%' "
            "AND n.percorso_zip LIKE '%Campania%'"
        )
        responses=[]
        def mock_ask(model,system,payload,**kwargs):
            responses.append(system)
            if system == auto.SQL_PROMPT:
                return raw_sql,{"token_input":1,"token_output":1,"costo_usd":0}
            return "Documento n1 verificato.",{
                "token_input":1,"token_output":1,"costo_usd":0
            }
        fake_lotus=types.ModuleType("lotus")
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        fake_models=types.ModuleType("lotus.models")
        fake_models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(
                self.db,"Quali note regionali della Campania menzionano MED-A?",
                "modello-fittizio")
        self.assertEqual(result["stato"],"OK")
        self.assertTrue(result["sql_normalizzato_ambito_regione"])
        self.assertFalse(result["sql_normalizzato_nome"])
        self.assertEqual(result["sql_originale_llm"],auto.validate_sql(raw_sql))
        self.assertNotEqual(result["sql"],result["sql_originale_llm"])
        self.assertEqual(result["righe_sql"],1)
        self.assertEqual(result["note_nell_indice"],1)
        self.assertEqual(len(responses),2)


    def test_curated_inner_join_cannot_silently_remove_note_candidate(self):
        """Una nota non revisionata deve restare consultabile sul PDF."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.execute(
            "CREATE TABLE nota_centro_documentato("
            "id TEXT,nota_id TEXT,centro TEXT,numero_pagina INTEGER)"
        )
        self.db.execute("PRAGMA query_only=ON")
        original=(
            "SELECT DISTINCT note.id AS nota_id, note.farmaco_candidato, "
            "c.centro, c.numero_pagina FROM note "
            "JOIN nota_centro_documentato AS c ON note.id=c.nota_id "
            "WHERE note.farmaco_candidato='MED-A' COLLATE NOCASE"
        )
        empty,partial=auto._run_generated_select(
            self.db,auto.validate_sql(original))
        self.assertFalse(partial)
        self.assertEqual(empty,[])
        fixed,changed=auto._normalize_sparse_note_enrichment(
            auto.validate_sql(original))
        self.assertTrue(changed)
        self.assertIn("LEFT JOIN",fixed)
        rows,partial=auto._run_generated_select(self.db,auto.validate_sql(fixed))
        self.assertFalse(partial)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["nota_id"],"n1")
        self.assertIsNone(rows[0]["centro"])
        documents,_=auto._note_candidates(self.db,rows)
        self.assertEqual(len(documents),1)
        self.assertIn("nota1.pdf",documents[0]["testo"])
        self.assertEqual(
            fixed, auto._normalize_sparse_note_enrichment(fixed)[0])

    def test_curated_join_preserves_explicit_restriction(self):
        """Non allargare query che richiedono esplicitamente dati revisionati."""
        variants=[
            "SELECT note.id AS nota_id, c.centro FROM note "
            "JOIN nota_centro_documentato c ON note.id=c.nota_id "
            "WHERE c.centro LIKE '%Ospedale%'",
            "SELECT c.centro FROM note "
            "JOIN nota_centro_documentato c ON note.id=c.nota_id "
            "WHERE note.farmaco_candidato='MED-A'",
            "SELECT note.id AS nota_id FROM note "
            "LEFT JOIN nota_centro_documentato c ON note.id=c.nota_id "
            "WHERE note.farmaco_candidato='MED-A'",
        ]
        for raw in variants:
            with self.subTest(sql=raw):
                fixed,changed=auto._normalize_sparse_note_enrichment(
                    auto.validate_sql(raw))
                self.assertFalse(changed)
                self.assertEqual(fixed,auto.validate_sql(raw))

    def test_pipeline_can_read_note_without_curated_centers(self):
        """S02 generico: SQL LLM con JOIN sparsa, poi note e LOTUS."""
        self.db.execute("PRAGMA query_only=OFF")
        self.db.execute(
            "CREATE TABLE nota_centro_documentato("
            "id TEXT,nota_id TEXT,centro TEXT,numero_pagina INTEGER)"
        )
        self.db.execute("PRAGMA query_only=ON")
        raw=(
            "SELECT DISTINCT note.id AS nota_id, "
            "note.farmaco_candidato AS nome, c.centro "
            "FROM note JOIN nota_centro_documentato AS c "
            "ON note.id=c.nota_id "
            "WHERE note.farmaco_candidato='MED-A' COLLATE NOCASE"
        )
        calls=[]
        def mocked_ask(model,system,payload,**kwargs):
            calls.append((system,payload))
            if system==auto.SQL_PROMPT:
                return raw,{"token_input":1,"token_output":1,"costo_usd":0}
            return "Documento consultato con pagina.",{
                "token_input":1,"token_output":1,"costo_usd":0
            }
        fake_lotus=types.ModuleType("lotus")
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        fake_models=types.ModuleType("lotus.models")
        fake_models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mocked_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame):
            result=auto.automatic_tag(
                self.db,
                "Nella nota MED-A quali indicazioni e strutture sono "
                "esplicitamente collegate? Cita le pagine.",
                "modello-fittizio")
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["righe_sql"],1)
        self.assertEqual(result["righe_recuperate"],1)
        self.assertTrue(result["sql_normalizzato_join_documentali"])
        self.assertIn("LEFT JOIN",result["sql"])
        self.assertIn("JOIN nota_centro_documentato",result["sql_originale_llm"])
        self.assertEqual(len(calls),2)
        self.assertEqual(result["note_nel_contesto"],1)
        self.assertIn("[pagina 2]",calls[1][1]["evidenze"][0]["testo"])


    def test_absence_questions_retrieve_subject_context_not_missing_measure(self):
        """Dati operativi assenti non vanno inventati nel WHERE o nelle JOIN."""
        prompt=auto.SQL_PROMPT
        self.assertIn("DATO OPERATIVO",prompt)
        self.assertIn("STESSA pagina",prompt)
        self.assertIn("note.anno",prompt)
        self.assertIn("JOIN artificiali",prompt)
        self.assertNotIn("ALHEMO",prompt)
        self.assertNotIn("MYALEPTA",prompt)
        self.assertIn("PERTINENZA",auto.DOCUMENT_SEMANTIC_PROMPT)
        self.assertIn("non e' documentato NELLE FONTI CONSULTATE",
                      auto.ANSWER_PROMPT)

    def test_absence_answer_can_be_grounded_by_topically_relevant_notes(self):
        """Pipeline: il documento conta come evidenza anche senza dati clinici reali."""
        sql=("SELECT DISTINCT note.id AS nota_id FROM note "
             "WHERE note.farmaco_candidato='MED-A' COLLATE NOCASE")
        captured=[]
        def mock_ask(model,system,payload,**kwargs):
            if system==auto.SQL_PROMPT:
                return sql,{"token_input":1,"token_output":1,"costo_usd":0}
            captured.append((system,payload))
            return ("Le fonti consultate non indicano la data effettiva "
                    "del primo trattamento."),{
                       "token_input":1,"token_output":1,"costo_usd":0
                    }
        def filter_context(frame,instruction):
            self.assertIn("PERTINENZA",instruction)
            self.assertIn("MED-A",frame.iloc[0]["testo"])
            return frame
        fake_lotus=types.ModuleType("lotus")
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        fake_models=types.ModuleType("lotus.models")
        fake_models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=filter_context):
            result=auto.automatic_tag(
                self.db,"Qual e' la data effettiva del primo trattamento "
                "del paziente con MED-A?","modello-fittizio")
        self.assertEqual(result["stato"],"OK")
        self.assertEqual(result["righe_sql"],1)
        self.assertEqual(result["righe_recuperate"],1)
        self.assertEqual(result["note_nel_contesto"],1)
        self.assertIn("non indicano la data",result["risposta"])
        self.assertEqual(len(captured),1)
        self.assertEqual(captured[0][0],auto.ANSWER_PROMPT)
        self.assertEqual(len(captured[0][1]["indice_documentale"]),1)
        self.assertEqual(len(result["fonti"]),2)

    def test_no_semantic_selection_does_not_claim_absence(self):
        """LOTUS senza evidenze non autorizza un'asserzione di dato mancante."""
        sql=("SELECT DISTINCT note.id AS nota_id FROM note "
             "WHERE note.farmaco_candidato='MED-A' COLLATE NOCASE")
        responses=[]
        def mock_ask(model,system,payload,**kwargs):
            responses.append(system)
            return sql,{"token_input":1,"token_output":1,"costo_usd":0}
        fake_lotus=types.ModuleType("lotus")
        fake_lotus.settings=types.SimpleNamespace(configure=lambda **_:None)
        fake_models=types.ModuleType("lotus.models")
        fake_models.LM=lambda *_,**__:types.SimpleNamespace()
        with patch.dict(sys.modules,{"lotus":fake_lotus,"lotus.models":fake_models}), \
             patch.object(auto,"ask",side_effect=mock_ask), \
             patch.object(auto,"sem_filter_controlled",
                          side_effect=lambda frame,instruction:frame.iloc[:0]):
            result=auto.automatic_tag(
                self.db,"Quanto e' stato fatturato effettivamente per MED-A?",
                "modello-fittizio")
        self.assertEqual(result["stato"],"NESSUNA_SELEZIONE_SEMANTICA")
        self.assertIn("LOTUS non ha selezionato",result["risposta"])
        self.assertNotIn("non documentato",result["risposta"])
        self.assertEqual(len(responses),1)


if __name__ == "__main__":
    unittest.main()
