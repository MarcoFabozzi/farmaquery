#!/usr/bin/env python3
"""Motori sperimentali TAG (LOTUS) e Text-to-SQL su un unico SQLite online.

Solo SELECT e database in read-only. Nessuna chiamata remota alla sola
importazione del modulo. I dati regolatori sono datati: non dedurre
rimborsabilita' vigente o autorizzazione dei centri da una semplice menzione.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import time

from errori_chatbot import EnginePhaseError
from tesi.recupero_gu import domanda_gu, candidati_gu
from tesi.recupero_regionale import regional_candidates, categoria
from tesi.contesto_integrale import contesto_integrale,richiede_sezione_completa,AIC_RE
from tesi.verifica_completezza_tag import revise_if_needed,enumeration_warning
from tesi.sql_category_support import (category_sql_context,
                                      select_generation_guidance,CATEGORY_RETRY_RULES,
                                      SQL_SYNTAX_REPAIR_RULES,
                                      CATEGORY_DIVERSITY_RETRY_RULES)
from tesi.tag_budget import (selection_mode,semantic_plan,expand_selected,
                             sem_filter_controlled,preserve_category_recall)
from tesi.sintesi_tag import (CATEGORY_SYSTEM, compact_category_evidence,
                              CATEGORY_RESPONSE_TIMEOUT_SECONDS,
                              revise_category_if_needed,
                              expand_review_pages)


SCHEMA = """Tabelle disponibili (SQLite, SOLA LETTURA):
aifa_confezioni(aic, nome, principio_attivo, descrizione, classe_a_h_snapshot, classe_a_h_data)
ema_medicinali(ema_id, nome, principio_attivo, stato_ema, data_decisione_ue, indicazione_ema, url_ema)
note(id, nome_file, percorso_zip, anno, farmaco_candidato, protocollo_candidato, data_candidata, indicazione_candidata, archivio_url)
pagine(nota_id, numero_pagina, testo, metodo)
strutture_registri(id, medicinale, patologia, indicazione, struttura, regione, data_riferimento, fonte_url)
centri_candidati(nota_id, numero_pagina, menzione, stato)
rimandi_candidati(nota_id, numero_pagina, riferimento, stato)
gu_atti(codice, data_pubblicazione, titolo, tipo, url_ufficiale, nominativi_campione, completezza)
gu_documenti(documento_id, codice, tipo_documento, url_fonte, sha256_testo, testo)
gu_segmenti(documento_id, numero_segmento, testo)
gu_segmenti_fts(documento_id, numero_segmento, testo) -- FTS5
fonti_snapshot(fonte, url, sha256, data_riferimento)
pagine_fts(nota_id, numero_pagina, testo) -- FTS5, opzionale.

AIFA: A/H sono attestate dalle liste datate. Se classe_a_h_snapshot e' NULL, C e' solo una classe convenzionale dedotta per esclusione e NON una certificazione AIFA.
Regione: centri_candidati e strutture_registri non certificano autorizzazione
per una indicazione, senza testo esplicito della nota regionale.
Per citare, seleziona aic per AIFA; ema_id per EMA;
nota_id e numero_pagina per le note (con join su pagine).
Per GU includi gu_codice (alias del codice) o documento_id. I testi GU
possono essere parziali e richiedono validazione documentale."""

ALLOWED = {"aifa_confezioni","ema_medicinali","note","pagine",
           "strutture_registri","centri_candidati","rimandi_candidati",
           "fonti_snapshot","pagine_fts","gu_atti","gu_documenti",
           "gu_segmenti","gu_segmenti_fts"}
STOP = {"quali","quale","quali","della","delle","nelle","degli","sono",
        "questa","questo","regione","campania","farmaco","farmaci",
        "medicinale","medicinali","centri","centro","prescrive",
        "prescrivere","prescritto","indicazioni","indicazione",
        "terapeutiche","terapeutica","classe","aifa","ema","europea",
        "autorizzato","autorizzata","rimborsato","rimborsata",
        "invece","dopo","secondo","presso","farmacista","medico",
        "posso","quale","quando","nota","italia","disponibile",
        "esiste","delle","essere","sulle","della","dalla","paziente",
        "principio","principi","attivo","attivi","quali","quale",
        "come","perche","attualmente","sostanza","sostanze",
        "formulazione","formulazioni","confezione","confezioni",
        "formato","formati","compresse","bustine","flaconcino",
         "tumore","rimborsabilita","rimborsabilità","alla","dove",
        "ospedali","reparti","reparto","strutture","possibile","prevista",
        "previsto","previsti","prescrizione","somministrazione","nelle",
        "negli","agli","campani","campane","indicato","indicati",
        "indicata","indicate","malattia","malattie","patologia",
        "patologie","utilizzato","utilizzata","utilizzati","viene",
        "vengono","qualsiasi","persone","pazienti","trattati",
        "trattate","trattamento","terapia","condizioni","controllo",
        "oncologici","servizi","neurologia","possono","potrebbe",
        "prescrittori","autorizzazione","autorizzati","ricevuto",
        "stessi","stesse","impiegato","farmaci","quale","europea",
        "qual","quell","quello","quella","queste","questi",
        "prescrivono","prescritta","prescritti","prescritte",
        "prescrittive","possiamo","rientrano","stadio","avanzato"}


def read_only(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def terms(question):
    words=[word.casefold() for word in re.findall(r"[A-Za-zÀ-ÿ0-9-]{4,}",question)]
    return list(dict.fromkeys(w for w in words if w not in STOP))[:8]


def _like(term):
    return "%"+term.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"


def candidates(db,question,limit=12):
    """Pagine FTS deterministiche; compatibile con i test precedenti."""
    tokens=terms(question)
    if not tokens:
        return []
    pattern=" OR ".join('"'+token.replace('"','')+'"' for token in tokens[:6])
    sql="""SELECT n.percorso_zip,n.archivio_url,p.nota_id,p.numero_pagina,p.testo
           FROM pagine_fts f
           JOIN pagine p ON p.nota_id=f.nota_id
             AND p.numero_pagina=f.numero_pagina
           JOIN note n ON n.id=p.nota_id
           WHERE pagine_fts MATCH ? AND p.metodo IN ('TESTO','OCR')
           ORDER BY bm25(pagine_fts) LIMIT ?"""
    return [dict(r) for r in db.execute(sql,(pattern,limit))]


def _question_kind(question):
    """Instrada il recupero verso la fonte più utile, senza LLM."""
    q=question.casefold()
    if domanda_gu(question):
        return "GU"
    if "principio attivo" in q or "principi attivi" in q:
        return "PRINCIPIO_ATTIVO"
    if any(word in q for word in ("centri", "centro prescritt",
                                  "ospedal", "repart", "campania",
                                  "somministrazion", "servizi oncologici")):
        return "CENTRI"
    if any(word in q for word in ("classe", "confezion", "formato",
                                  "compresse", "flaconcin", "bustine",
                                  "rimbors")):
        return "AIFA"
    if any(word in q for word in ("indicazion", "indicat", "tumore", "patologia",
                                  "malattia", "autorizzazion",
                                  "europe", "pazienti", "quale età",
                                  "quali condizioni")):
        return "EMA"
    return "GENERICA"


def _facets(question):
    """Fonti necessarie per rispondere alle parti della domanda.

    Le domande miste richiedono più fonti indipendenti: un'unica riga
    AIFA non può attestare anche l'indicazione EMA e i centri regionali.
    """
    q=question.casefold()
    requested=set()
    if domanda_gu(question):
        requested.add("GU")
    if any(x in q for x in ("indicaz", "tumore", "patologia", "malatt",
                            "autorizz", "terapi", "trattament", "pazient",
                            "duchenne", "emofilia", "primo linea")):
        requested.add("EMA")
    if any(x in q for x in ("classe", "confezion", "formato", "rimbors",
                            "compresse", "bustine", "flaconcin")):
        requested.add("AIFA")
    if any(x in q for x in ("campania", "campani", "centri", "ospedal",
                            "prescrittor", "somministrazion", "repart")):
        requested.add("REGIONE")
    # Una determina GU può citare classe e indicazioni senza richiedere
    # automaticamente una seconda fonte AIFA o EMA.
    if domanda_gu(question):
        if "aifa" not in q and "elench" not in q:
            requested.discard("AIFA")
        if "ema" not in q and "europe" not in q and "decisione ue" not in q:
            requested.discard("EMA")
    if categoria(question)[0] and "ema" not in q and "europe" not in q:
        requested.discard("EMA")
        requested.add("REGIONE")
    return requested


def _multisource_evidence(rows,semantic_rows,question,limit=8):
    """Mantiene le righe selezionate da LOTUS e la copertura delle fonti.

    Per una domanda che richiede EMA+AIFA+Regione ogni fonte soddisfa
    un sottoquesito diverso. Se LOTUS rifiuta una fonte perché non
    risponde alla domanda intera, conserviamo la prima evidenza con
    corrispondenza diretta al medicinale recuperato (mai inventata).
    L'eventuale assenza di una fonte resta esplicita nella risposta.
    """
    facets=_facets(question)
    evidence=[]
    seen=set()
    for row in semantic_rows:
        uid=row.get("chiave")
        if uid not in seen:
            evidence.append(row)
            seen.add(uid)
    if len(facets)>1:
        for tipo in ("EMA","AIFA","REGIONE","GU"):
            if tipo not in facets or any(e["tipo"]==tipo for e in evidence):
                continue
            for row in rows:
                if row["tipo"]==tipo and row["chiave"] not in seen:
                    evidence.append(row)
                    seen.add(row["chiave"])
                    break
    return evidence[:limit]


def _target(question):
    """Prima entità significativa, non parole della domanda come 'attivo'.

    Funziona con nomi commerciali e sostanze, evitando che 'principio'
    diventi la prima keyword della ricerca e produca risultati casuali.
    """
    meaningful=terms(question)
    return meaningful[0] if meaningful else ""


def _target_db(db, question):
    """Riconosce il nome presente nella domanda tramite le tabelle dello snapshot.

    Non assume che il farmaco sia la prima parola significativa e supporta
    denominazioni di più parole. Usa solo SELECT parametrizzate.
    """
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+(?:[-'][A-Za-zÀ-ÿ0-9]+)*", question)
    phrases = {}
    for start in range(len(words)):
        for length in range(1, min(5, len(words) - start) + 1):
            part = words[start:start + length]
            if not any(len(w) >= 4 and w.casefold() not in STOP for w in part):
                continue
            phrase = " ".join(part).casefold()
            phrases.setdefault(phrase, (start, length))

    if not phrases:
        return _target(question)

    placeholders = ",".join("?" for _ in phrases)
    params = tuple(phrases)
    matches = set()
    for table, column in (
        ("ema_medicinali", "nome"),
        ("aifa_confezioni", "nome"),
        ("aifa_confezioni", "principio_attivo"),
    ):
        query = (f"SELECT DISTINCT {column} FROM {table} "
                 f"WHERE {column} COLLATE NOCASE IN ({placeholders})")
        for row in db.execute(query, params):
            name = str(row[0] or "").casefold()
            if name in phrases:
                matches.add(name)

    if matches:
        return min(matches, key=lambda name: (-phrases[name][1], phrases[name][0]))
    # Le fixture minime possono non avere questa colonna.
    note_columns={r[1] for r in db.execute("PRAGMA table_info(note)")}
    if "farmaco_candidato" in note_columns:
        for row in db.execute(
            "SELECT DISTINCT farmaco_candidato FROM note "
            "WHERE farmaco_candidato IS NOT NULL"):
            name=str(row[0]).strip()
            if name and re.search(r"(?<!\w)"+re.escape(name)+r"(?!\w)",
                                  question,re.I):
                return name
    return _target(question)


def _search_aifa(db,target,limit=6):
    """Prima marchio esatto, poi prefisso; sostanza come ripiego.

    I match parziali di un principio attivo (es. combinazioni con
    paracetamolo) sono ammessi solo se NON esistono riscontri più precisi.
    """
    if not target:
        return []
    columns=("SELECT aic,nome,principio_attivo,descrizione,"
             "classe_a_h_snapshot,classe_a_h_data FROM aifa_confezioni")
    query_templates=[
        (f"{columns} WHERE nome = ? COLLATE NOCASE ORDER BY aic LIMIT ?",(target,limit)),
        (f"{columns} WHERE nome LIKE ? ESCAPE '\\' COLLATE NOCASE "
         "ORDER BY nome,aic LIMIT ?",(_like(target)+"",limit)),
        (f"{columns} WHERE principio_attivo = ? COLLATE NOCASE "
         "ORDER BY nome,aic LIMIT ?",(target,limit)),
        (f"{columns} WHERE nome LIKE ? ESCAPE '\\' COLLATE NOCASE "
         "ORDER BY nome,aic LIMIT ?",(_like(target),limit)),
        (f"{columns} WHERE principio_attivo LIKE ? ESCAPE '\\' COLLATE NOCASE "
         "ORDER BY nome,aic LIMIT ?",(_like(target),limit)),
    ]
    # Prefix match, not contains: '%TACHIPIRINA%' would admit other brand names.
    prefix=target.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
    query_templates[1]=(query_templates[1][0],(prefix,limit))
    for statement,values in query_templates:
        rows=[dict(r) for r in db.execute(statement,values)]
        if rows:
            return rows
    return []


def _search_ema(db,target,limit=3):
    if not target:
        return []
    columns=("SELECT ema_id,nome,principio_attivo,stato_ema,data_decisione_ue,"
             "indicazione_ema,url_ema FROM ema_medicinali")
    prefix=target.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
    for suffix,value in (
        ("nome = ? COLLATE NOCASE",target),
        ("nome LIKE ? ESCAPE '\\' COLLATE NOCASE",prefix),
        ("principio_attivo = ? COLLATE NOCASE",target),
        ("nome LIKE ? ESCAPE '\\' COLLATE NOCASE",_like(target)),
        ("principio_attivo LIKE ? ESCAPE '\\' COLLATE NOCASE",_like(target)),
    ):
        records=[dict(r) for r in db.execute(
            f"{columns} WHERE {suffix} ORDER BY nome LIMIT ?",(value,limit))]
        if records:
            return records
    return []


def evidence_candidates(db,question,max_rows=18):
    """Recupero con entità precisa e priorità della fonte, prima di LOTUS.

    LOTUS rimane il selettore semantico fra evidenze pertinenti.
    Un match solo nel campo 'principio_attivo' di un medicinale composto
    NON deve prevalere sul nome esatto del medicinale chiesto.
    """
    target=_target_db(db, question)
    category_question=bool(categoria(question)[0])
    if not target and not category_question:
        return []
    if category_question:
        target=""
    kind=_question_kind(question)
    rows=[]
    seen=set()

    def put(tipo,uid,description,source,sources=None,selection_text=None,
            passages=None,document_count=None,documents_truncated=False):
        if uid not in seen and len(rows)<max_rows:
            seen.add(uid)
            row={"tipo":tipo,"chiave":uid,
                 "testo":str(description)[:6000],"fonte":source}
            if sources:
                row["fonti"]=list(dict.fromkeys(sources))
            if selection_text:
                row["testo_selezione"]=selection_text
            if passages:
                row["passaggi_sintesi"]=passages
            if document_count is not None:
                row["copertura_documenti"]=document_count
                row["documenti_troncati"]=documents_truncated
            rows.append(row)

    aifa_limit=7 if kind=="AIFA" else 4
    aifa_data=_search_aifa(db,target,limit=aifa_limit)
    ema_data=_search_ema(db,target,limit=4 if kind=="EMA" else 2)

    def add_aifa():
        for item in aifa_data:
            uid="AIFA:"+str(item["aic"])
            desc=("Medicinale: "+str(item["nome"])
                  +"; AIC: "+str(item["aic"])
                  +"; principio attivo dichiarato: "+str(item["principio_attivo"])
                  +"; confezione: "+str(item["descrizione"])
                  +"; classe: "+str(item["classe_a_h_snapshot"] or "C (dedotta per esclusione da A/H; non attestata come classe ufficiale)")
                  +"; data elenco A/H: "+str(item["classe_a_h_data"]))
            put("AIFA",uid,desc,"AIFA AIC "+str(item["aic"]))

    def add_ema():
        for item in ema_data:
            uid="EMA:"+str(item["ema_id"])
            desc=("Medicinale: "+str(item["nome"])+
                  "; principio attivo: "+str(item["principio_attivo"])+
                  "; stato autorizzazione: "+str(item["stato_ema"])+
                  "; decisione UE: "+str(item["data_decisione_ue"])+
                  "; indicazione: "+str(item["indicazione_ema"]))
            put("EMA",uid,desc,
                "EMA "+str(item["ema_id"])+" | "+str(item["url_ema"]))

    def add_regione():
        if kind=="PRINCIPIO_ATTIVO":
            return
        # Se il documento nominativo esiste, carica tutte le pagine
        # leggibili (entro limiti controllati) e gli eventuali protocolli
        # richiamati. Per categorie implicite interroga più note e LOTUS
        # deciderà semanticamente, non una tabella di risposte predefinite.
        expanded=regional_candidates(db,question,target,limit=min(22,max_rows))
        if expanded:
            for item in expanded:
                put(item["tipo"],item["chiave"],item["testo"],item["fonte"],
                    sources=item.get("fonti"),
                    selection_text=item.get("testo_selezione"),
                    passages=item.get("passaggi_sintesi"),
                    document_count=item.get("copertura_documenti"),
                    documents_truncated=item.get("documenti_troncati",False))
            return
        # Compatibilità con fixture minime e con vecchie sorgenti.
        for item in candidates(db,target,limit=5 if kind=="CENTRI" else 3):
            put("REGIONE",str(item["nota_id"])+"#p"+str(item["numero_pagina"]),
                str(item["testo"])[:1750],
                str(item["percorso_zip"])+"#p"+str(item["numero_pagina"])+
                " | archivio: "+str(item["archivio_url"]))

    def add_gu():
        for item in candidati_gu(db,question,limit=min(18,max_rows) if re.search(r"\b(?:tutt[ieo]|quante confezioni|quanti aic|elenco completo)\b",question,re.I) else 6):
            uid=("GU:"+str(item["documento_id"])+"#s"+
                 str(item["numero_segmento"]))
            text=("GU "+str(item["codice"])+"; pubblicazione: "+
                  str(item["data_pubblicazione"])+"; tipo: "+
                  str(item["tipo_documento"])+"; stato del testo: "+
                  str(item["completezza"])+"; estratto: "+
                  str(item["testo"])[:1800])
            source=("GU "+str(item["codice"])+" | "+
                    str(item["url_fonte"])+"#segmento-"+
                    str(item["numero_segmento"]))
            put("GU",uid,text,source)

    def add_registri():
        if kind!="CENTRI":
            return
        pattern=_like(target)
        for item in db.execute(
            "SELECT id,medicinale,patologia,indicazione,struttura,"
            "data_riferimento,fonte_url FROM strutture_registri "
            "WHERE medicinale LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "ORDER BY medicinale,struttura LIMIT 3",(pattern,)):
            put("REGISTRO_AIFA","REGISTRO:"+str(item["id"]),
                "Medicinale: "+str(item["medicinale"])+
                "; patologia: "+str(item["patologia"])+
                "; indicazione: "+str(item["indicazione"])+
                "; struttura: "+str(item["struttura"])+
                "; data: "+str(item["data_riferimento"]),
                "AIFA strutture abilitate ai registri | "+str(item["fonte_url"]))

    if category_question:
        add_regione()
    elif kind=="GU":
        add_gu()
        add_ema()
        add_aifa()
        add_regione()
    elif kind=="CENTRI":
        add_regione()
        add_ema()
        add_aifa()
        add_registri()
    elif kind=="EMA":
        add_ema()
        add_aifa()
        add_regione()
    else:
        add_aifa()
        add_ema()
        add_regione()
    return rows[:max_rows]


def _in_phase(phase,func,*args,**kwargs):
    try:
        return func(*args,**kwargs)
    except EnginePhaseError:
        raise
    except Exception as exc:
        raise EnginePhaseError(phase,exc) from exc


def ask(model,system,payload,*,timeout=40,max_tokens=None):
    """LiteLLM con restituzione di token e costo quando disponibili."""
    from litellm import completion
    request={"model":model,"temperature":0,
             "messages":[{"role":"system","content":system},
                         {"role":"user","content":json.dumps(
                             payload,ensure_ascii=False,default=str)}],
             "timeout":timeout,"num_retries":0}
    if max_tokens is not None:
        request["max_tokens"]=max_tokens
    result=_in_phase("connessione LLM",completion,**request)
    usage=getattr(result,"usage",None)
    data={
        "token_input":getattr(usage,"prompt_tokens",None),
        "token_output":getattr(usage,"completion_tokens",None),
        "costo_usd":None,
    }
    try:
        from litellm import completion_cost
        data["costo_usd"]=float(completion_cost(completion_response=result))
    except (ValueError,TypeError,KeyError,AttributeError):
        pass
    return str(result.choices[0].message.content or ""),data


def _accumulate(a,b):
    return {key:(a.get(key) or 0)+(b.get(key) or 0)
            if a.get(key) is not None and b.get(key) is not None else None
            for key in ("token_input","token_output","costo_usd")}


def _source_previews(evidence, limit=16):
    """Estratti verificabili delle righe effettivamente consegnate al modello.

    Non sono citazioni letterali validate: l'interfaccia indica un estratto
    della riga recuperata, insieme alla fonte da cui proviene.
    """
    found=[]
    seen=set()
    for row in evidence:
        source=str(row.get("fonte") or "")
        if not source or source in seen:
            continue
        seen.add(source)
        raw=str(row.get("testo") or "")
        for marker in ("; testo: ", "; estratto: ", "; passaggio: "):
            if marker in raw:
                raw=raw.split(marker,1)[1]
                break
        raw=" ".join(raw.split())
        if len(raw)>420:
            raw=raw[:417].rstrip()+"..."
        found.append({"fonte":source,"tipo":row.get("tipo",""),
                      "estratto":raw})
        if len(found)>=limit:
            break
    return found


def tag(db,question,model):
    import pandas as pd
    import lotus
    from lotus.models import LM
    category_question=bool(categoria(question)[0])
    complete_request=bool(re.search(
        r"\b(?:tutti|tutte|elenco completo|lista completa|quali farmaci|quali centri|quali strutture|quante confezioni|quanti aic)\b",
        question.casefold()))
    region_request=category_question or complete_request or _question_kind(question)=="CENTRI"
    rows=evidence_candidates(db,question,max_rows=22 if region_request else 12)
    if not rows:
        return {"risposta":"Informazione non documentata nello snapshot consultato.",
                "fonti":[],"stato":"NESSUNA_EVIDENZA","token_input":0,
                "token_output":0,"costo_usd":0.0,"costo_completo":True}
    mode=selection_mode()
    # Nessuna fonte viene eliminata per ridurre il costo: la selezione
    # raggruppata valuta più evidenze in un solo elemento semantico.
    planned,members=semantic_plan(
        rows,mode=mode,max_groups=4 if category_question else 3)
    # Le categorie implicite attivano più valutazioni semantiche;
    # ridurre le richieste contemporanee evita burst inutili verso Gemini.
    lm=_in_phase("inizializzazione TAG",LM,model,
                 max_batch_size=2 if category_question else 4)
    _in_phase("inizializzazione TAG",lotus.settings.configure,lm=lm,enable_cache=False)
    frame=pd.DataFrame(planned)
    selected=_in_phase("selezione TAG",lambda: sem_filter_controlled(frame,
        "La riga {testo} è pertinente ad ALMENO UNA parte della domanda "
        +json.dumps(question,ensure_ascii=False)
        +". NON richiedere che la singola riga soddisfi tutte le parti: "
         "una riga EMA può indicare il tumore, AIFA la classe, un atto GU "
          "le condizioni di una determina, una nota "
         "regionale i centri di prescrizione o somministrazione. "
         "Valuta anche le informazioni parziali documentate. "
         "Considera il nome commerciale esatto, non farmaci diversi "
         "che contengono lo stesso principio attivo; le strutture dei "
         "registri AIFA non sono automaticamente centri autorizzati."
    ).head(12 if region_request else (6 if len(_facets(question))>1 else 8)))
    # L'assenza delle statistiche non deve annullare una risposta valida.
    selection_usage=getattr(getattr(lm,"stats",None),"physical_usage",None)
    prompt_tokens=getattr(selection_usage,"prompt_tokens",None)
    completion_tokens=getattr(selection_usage,"completion_tokens",None)
    selection_cost=getattr(selection_usage,"total_cost",None)
    # Conserviamo chiave e tipo per garantire copertura delle fonti senza
    # confondere una selezione semantica vuota con un database vuoto.
    selected_groups=selected[["chiave"]].to_dict("records")
    semantic=expand_selected(selected_groups,members)
    ids={r["chiave"] for r in rows}
    semantic=[r for r in semantic if r.get("chiave") in ids]
    if complete_request and _question_kind(question)=="GU":
        evidence=preserve_category_recall(rows,semantic)
    elif category_question:
        # sem_filter valuta e ORDINA i documenti, ma un gruppo escluso
        # non prova che le altre note siano irrilevanti: per una domanda
        # elenco, non trasformare il filtro approssimativo in esclusione.
        evidence=preserve_category_recall(rows,semantic)
    else:
        evidence=_multisource_evidence(rows,semantic,question,
                                     limit=18 if region_request else 10)
    # Una lista di centri richiesta come completa non può essere generata
    # da una sola pagina selezionata: includiamo tutte le pagine della nota
    # già recuperate e verificate come leggibili. Non dichiariamo esaustive
    # ricerche trasversali a categorie con corpus troncato.
    if complete_request and not category_question:
        seen={r["chiave"] for r in evidence}
        for row in rows:
            if row["tipo"]=="REGIONE" and row["chiave"] not in seen and len(evidence)<18:
                evidence.append(row)
                seen.add(row["chiave"])
    # LOTUS puo' rigettare tutti i gruppi anche quando una pagina
    # esplicitamente richiesta esiste e risulta leggibile nello SQLite.
    # Recupero documentale diretto: non sostituisce il filtro, ma impedisce
    # che la sua astensione diventi una falsa assenza di fonti.
    integral,integral_complete=contesto_integrale(
        db,question,_target_db(db,question))
    fallback_pagina_integrale=bool(
        not evidence and integral and not category_question)
    if fallback_pagina_integrale:
        evidence=list(integral)
    if not evidence:
        return {"risposta":(
                    "Il filtro semantico LOTUS non ha selezionato evidenze "
                    "tra le fonti recuperate. Questo NON dimostra che "
                    "l'informazione sia assente nello snapshot."),
                "fonti":[],"stato":"NESSUNA_SELEZIONE_SEMANTICA",
                "righe_recuperate":len(rows),
                "righe_sem_filter":len(planned),
                "righe_selezionate_lotus":len(selected_groups),
                "modalita_selezione":mode,
                "chiamate_semantiche_stimate":len(planned),
                "chiamate_llm_stimate":len(planned),
                "token_input":prompt_tokens,
                "token_output":completion_tokens,
                "costo_usd":selection_cost,"costo_completo":selection_cost is not None}
    system_tag=("Rispondi in italiano in modo breve e specifico, SOLO alla domanda. "
        "La denominazione di un principio attivo non va trattata come il nome "
        "di un medicinale che lo contiene: ad esempio, se si chiede il principio "
        "attivo di una sostanza, spiega che la sostanza stessa è già un principio "
        "attivo. Se viene chiesto il principio attivo di un medicinale, cita SOLO "
        "le righe in cui il medicinale corrisponde al nome commerciale richiesto; "
        "NON elencare altre specialità né combinazioni diverse. "
        "Non aggiungere dettagli EMA, classi o liste di confezioni non richiesti. "
        "Distingui autorizzazione europea EMA, classe A/H di una confezione AIFA "
        "e centri prescrittori di specifiche note campane. "
        "Classifica ogni confezione in A se compare nella lista A, H se compare nella lista H; altrimenti indica C come deduzione per esclusione e non come classificazione ufficialmente verificata. "
        "Quando la GU attesta C o C(nn), riportala come classe descritta "
        "in quello specifico provvedimento, non come inferenza dalle liste. "
        "Per domande con più parti: rispondi separatamente a ciascuna, "
        "usando EMA per le indicazioni, AIFA per le classi delle confezioni, "
        "le note regionali per i centri e gli atti GU per le determine. "
         "I testi GU possono essere parziali; non inferire lo stato vigente. "
         "NON rinunciare a rispondere alle "
        "parti documentate se manca la fonte di una sola parte. "
        "Non dichiarare un centro autorizzato soltanto dal registro AIFA "
        "e non dedurlo da una semplice menzione in un PDF. "
        "Per categorie implicite considera ogni nota separatamente: "
        "collega il medicinale alla patologia e alla specifica struttura "
        "indicata nei passaggi delle pagine, riportando soltanto le "
        "associazioni effettivamente verificabili. Se una nota contiene "
        "solo il nome della patologia ma non il centro, non aggiungerla. "
        "Le intestazioni con nomi di ospedali non bastano da sole. "
        "Per una categoria implicita (es. neuromuscolare), verifica la "
        "patologia e il centro direttamente nel testo di ogni nota; i "
        "termini di ricerca NON certificano che il farmaco appartenga "
        "alla categoria e i registri AIFA NON attestano autorizzazioni "
        "regionali. Per i rimandi cita sia la nota che richiama sia "
        "quella richiamata: non scambiare un richiamo per abrogazione. "
        "Se l'elenco richiesto non è verificabilmente completo, dichiara "
        "espressamente che è parziale e non inventare elementi. "
        "Indica PDF, pagina e passo rilevante per ogni conclusione. "
        "Indica le fonti pertinenti e per le parti non documentate scrivi "
        "'non documentato nello snapshot'.")
    payload={"domanda":question,"medicinale_o_sostanza_ricercata":_target_db(db, question),
         "intento":_question_kind(question),
         "parti_richieste":sorted(_facets(question)),
         "fonti_presenti":sorted({r["tipo"] for r in evidence}),
         "evidenze":evidence}
    if integral:
        # Il filtro semantico LOTUS ha già selezionato i documenti. Per una
        # domanda esaustiva su una pagina o un articolo nominato, invece
        # dell'incipit OCR passiamo alla sintesi il TESTO INTEGRALE della
        # sezione effettiva sullo stesso SQLite. Non è una risposta gold.
        system_tag += (" Per un elenco completo controlla TUTTE le righe "
                       "del testo originale della sezione, comprese "
                       "confezioni con dosaggio identico ma formato diverso. "
                       "Non dichiarare un elenco esaustivo senza averlo "
                       "riconciliato con tutti gli identificativi elencati "
                       "nel documento. Distingui testo estratto e "
                       "autorizzazione regolatoria. Se la domanda attribuisce "
                       "alla pagina un riferimento non presente nel testo, "
                       "segnala che non vi compare; non inventare collegamenti. ")
        payload["evidenze"]=integral
        payload["sezione_integralmente_disponibile"]=integral_complete
        payload["origine_evidenze"]="pagine/atti dello stesso SQLite, non gold"
        if not integral_complete:
            payload["avviso"]="Fonte più lunga del contesto: elenco NON esaustivo"

    category_revised=False
    category_missing=[]
    category_audit=[]
    category_review_stats={}
    if category_question:
        # LOTUS seleziona; la sintesi riesamina tutti i documenti candidati.
        # La verifica successiva NON promuove automaticamente candidati a fatti.
        system_tag=CATEGORY_SYSTEM
        compact=compact_category_evidence(evidence)
        payload={"domanda":question,
                 "evidenze":compact,
                 "copertura_documentale":(
                     "Documenti recuperati: "+str(len(rows))+
                     "; documenti aggiuntivi rispetto a LOTUS: "+
                     str(len(evidence)-len(semantic))+
                     ". I documenti non selezionati da LOTUS sono "
                     "solo candidati da verificare, non negativi accertati."),
                 "copertura_limitata":any(r.get("documenti_troncati")
                                          for r in evidence)}
        answer,usage=ask(model,system_tag,payload,
                         timeout=CATEGORY_RESPONSE_TIMEOUT_SECONDS,
                         max_tokens=1400)
        review_context=expand_review_pages(db,question,answer,compact)
        answer,extra_category_usage,category_revised,category_missing=(
            revise_category_if_needed(
                model,question,answer,review_context,ask,
                audit=category_audit,stats=category_review_stats))
        if extra_category_usage is not None:
            usage=_accumulate(usage,extra_category_usage)
    else:
        answer,usage=ask(model,system_tag,payload)
    answer,extra_usage,revised,validation=revise_if_needed(
        model,question,answer,integral,integral_complete,ask)
    if extra_usage is not None:
        usage=_accumulate(usage,extra_usage)
    missing_aic=validation["aic_omessi_nella_risposta"]
    answer+=enumeration_warning(answer,integral)
    if integral and not integral_complete:
        answer+=("\n\nAvvertenza: la sezione richiesta supera il "
                 "limite di contesto, pertanto la lista non può essere "
                 "considerata completa.")
    input_tokens=(prompt_tokens+usage["token_input"]
                  if prompt_tokens is not None and usage["token_input"] is not None else None)
    output_tokens=(completion_tokens+usage["token_output"]
                   if completion_tokens is not None and usage["token_output"] is not None else None)
    full_cost=(selection_cost+usage["costo_usd"]
               if selection_cost is not None and usage["costo_usd"] is not None else None)
    if (complete_request and not (integral and integral_complete) and
        (len(rows)>=22 or any("ESTRATTO PARZIALE" in r["testo"]
                                for r in evidence))):
        answer+=("\n\nAvvertenza: almeno una pagina della fonte è stata "
                 "troncata per limiti di contesto; l'elenco va verificato "
                 "sul PDF integrale e non può essere considerato completo.")
    if category_question and any(r.get("documenti_troncati") for r in rows):
        answer+=("\n\nAttenzione: la ricerca documentale è stata "
                 "limitata; ulteriori note candidate possono non "
                 "essere state analizzate.")
    if category_question and not re.search(
        r"parzial|non esaustiv|non documentat|non verificabil",
        answer.casefold()):
        answer += ("\n\nCopertura: risultati candidati ricavati dalle note "
                   "recuperate; non è garantito un elenco esaustivo dei medicinali.")
    citations=list(dict.fromkeys(
        source for item in (integral or evidence)
        for source in (item.get("fonti") or [item["fonte"]])
    ))
    return {"risposta":answer,"fonti":citations,
            "evidenze_fonti":_source_previews(integral or evidence),
            "stato":"RISULTATI_PARZIALI" if (integral and (not integral_complete or missing_aic)) else "OK",
            "contesto_integrale":bool(integral),
            "contesto_integrale_completo":bool(integral and integral_complete),
            "aic_mancanti_rispetto_al_testo":missing_aic,
            "aic_nel_testo_integrale":validation["aic_nel_testo"],
            "revisione_completezza_llm":revised or category_revised,
            "revisione_categoria_llm":category_revised,
            "candidati_categoria_da_ricontrollare":category_missing,
            "diagnostica_revisione_categoria":category_audit,
            "statistiche_revisione_categoria":category_review_stats,
            "fallback_pagina_integrale":fallback_pagina_integrale,
            "verifica_contesto":(
                "integrale" if integral and integral_complete else
                "parziale" if integral else "non_recuperato"),
            "versione_tag":"verifica-integrale-v2",
            "token_input":input_tokens,
            "token_output":output_tokens,"costo_usd":full_cost,
            "costo_completo":full_cost is not None,
            "righe_sem_filter":len(planned),
            "righe_recuperate":len(rows),
            "righe_selezionate_lotus":len(selected_groups),
            "righe_evidenze_da_lotus":len(semantic),
            "modalita_selezione":mode,
            "chiamate_semantiche_stimate":len(planned),
            "chiamate_llm_stimate":len(planned)+1+int(revised)+
                                    category_review_stats.get("chiamate",0),
            "fonti_recuperate":sorted({r["tipo"] for r in rows}),
            "fonti_usate":sorted({r["tipo"] for r in evidence}),
            "fonti_mancanti":sorted(_facets(question)-{r["tipo"] for r in evidence})}


def validate_sql(text):
    """Accetta una sola SELECT, niente istruzioni PRAGMA, DDL, DML o funzioni rischiose."""
    import sqlglot
    from sqlglot import exp
    cleaned=re.sub(r"^\s*"+chr(96)*3+r"(?:sql)?\s*|\s*"+chr(96)*3+r"\s*$","",text.strip(),flags=re.I)
    instructions=sqlglot.parse(cleaned,read="sqlite")
    if len(instructions)!=1 or not isinstance(instructions[0],(exp.Select,exp.Union)):
        raise ValueError("Sono consentite solo SELECT")
    root=instructions[0]
    blocked=tuple(getattr(exp,name) for name in
                  ("Insert","Update","Delete","Drop","Create","Alter","Command",
                   "Pragma","Attach","Detach") if hasattr(exp,name))
    for banned in blocked:
        if root.find(banned):
            raise ValueError("SQL non consentito")
    for table in root.find_all(exp.Table):
        ctes={c.alias for c in root.find_all(exp.CTE)}
        if (table.name not in ALLOWED|ctes or table.db or table.catalog):
            raise ValueError("Tabella o schema non consentito: "+table.name)
    deny_names={"load_extension","readfile","writefile","fts5_tokenize",
                "sqlite_compileoption_get","sqlite_compileoption_used"}
    for item in root.find_all(exp.Func):
        if getattr(item,"name","").lower() in deny_names:
            raise ValueError("Funzione SQL non consentita")
    # Limita anche le funzioni non nominate/collateralmente pericolose.
    if re.search(r"\b(load_extension|readfile|writefile|randomblob)\s*\(",
                 cleaned,re.I):
        raise ValueError("Funzione SQL non consentita")
    return root.sql(dialect="sqlite")


def _sql_sources(db,rows):
    found=[]
    for row in rows:
        note=row.get("nota_id")
        page=row.get("numero_pagina")
        if note and page:
            src=db.execute("SELECT percorso_zip,archivio_url FROM note WHERE id=?",
                           (note,)).fetchone()
            if src:
                found.append(str(src["percorso_zip"])+"#p"+str(page)+
                             " | archivio: "+str(src["archivio_url"]))
        aic=row.get("aic")
        if aic:
            found.append("AIFA AIC "+str(aic)+" | snapshot elenchi ufficiali A/H")
        ema=row.get("ema_id")
        if ema:
            src=db.execute("SELECT url_ema FROM ema_medicinali WHERE ema_id=?",
                           (ema,)).fetchone()
            found.append("EMA "+str(ema)+(" | "+str(src["url_ema"]) if src else ""))
        gu = row.get("gu_codice") or row.get("codice")
        if not gu and row.get("documento_id"):
            found_gu = db.execute(
                "SELECT codice FROM gu_documenti WHERE documento_id=?",
                (row["documento_id"],)).fetchone()
            gu = found_gu["codice"] if found_gu else None
        if gu:
            source = db.execute(
                "SELECT url_ufficiale FROM gu_atti WHERE codice=?", (gu,)
            ).fetchone()
            if source:
                found.append("GU " + str(gu) + " | " + str(source["url_ufficiale"]))
        if row.get("fonte_url"):
            found.append(str(row["fonte_url"]))
        if row.get("url"):
            found.append(str(row["url"]))
    return list(dict.fromkeys(found))


SQL_ROW_LIMIT = 80
SQL_CONTEXT_CHARS = 24000


def _limit_from_sql(sql):
    hit=re.search(r"\bLIMIT\s+([0-9]+)\b",sql,re.I)
    return int(hit.group(1)) if hit else None


def _category_excerpt(value,question,max_chars=1350):
    """Finestre testuali con posizione, non prove cliniche preconfezionate.

    Raccoglie contesto iniziale e passi attorno a parole della domanda e
    alle espansioni di categoria condivise; non inventa né salda fonti.
    """
    value=str(value)
    if len(value)<=max_chars:
        return value
    from tesi.recupero_regionale import categoria
    _,terms=categoria(question or "")
    facility=re.search(r"\b(?:AOU|AORN|IRCCS)\s+([A-Za-zÀ-ÿ]{4,})",
                       question or "",re.I)
    named=facility.group(1).casefold() if facility else ""
    anchors=([named] if named else [])+list(terms)
    windows=[(0,min(230,len(value)))]
    lowered=value.casefold()
    # La struttura viene cercata per prima; un indizio clinico diverso
    # compare in un'altra finestra, se presente.
    budget=max_chars-260
    for word in anchors:
        if not word:
            continue
        found=lowered.find(word.casefold())
        if found<0:
            continue
        lo=max(0,found-190)
        hi=min(len(value),found+430)
        if any(lo<end and hi>start for start,end in windows):
            continue
        size=min(hi-lo,max(0,budget))
        if size<90:
            break
        windows.append((lo,lo+size))
        budget-=size+8
        if len(windows)>=3:
            break
    windows.sort()
    excerpts=[]
    for start,end in windows:
        excerpts.append(value[start:end])
    return " [...] ".join(excerpts)[:max_chars]


def _sql_context(raw,category=False,question=""):
    """Contesto citabile e limitato, bilanciato per documenti nelle categorie."""
    output=[]
    consumed=0
    cut=False
    for record in raw:
        original=dict(record)
        row={}
        for key,value in original.items():
            if value is None:
                row[key]=None
                continue
            text=str(value)
            if category and key=="testo" and len(text)>1350:
                row[key]=_category_excerpt(text,question)
                cut=True
            else:
                limit=1800 if category else 2500
                row[key]=text[:limit]
                if len(text)>limit:
                    cut=True
        size=len(json.dumps(row,ensure_ascii=False))
        if consumed+size>SQL_CONTEXT_CHARS:
            cut=True
            break
        output.append(row)
        consumed+=size
    return output,cut


def _balanced_category_rows(records):
    """Riduce la moltiplicazione dovuta a JOIN 1:N e alterna le note.

    Per una domanda sulle note regionali l'unità documentale è la pagina
    (nota_id, numero_pagina), non la confezione AIFA. Nessun nome di
    medicinale o autorizzazione viene dedotto durante questa operazione.
    """
    groups={}
    seen=set()
    duplicates=0
    for item in records:
        row=dict(item)
        note=str(row.get("nota_id") or row.get("nome_file") or
                 row.get("medicinale") or "NON_IDENTIFICATA")
        page=row.get("numero_pagina")
        if row.get("nota_id") is not None and page is not None:
            key=("REGIONE",str(row["nota_id"]),str(page))
        else:
            key=("RIGA",json.dumps(row,sort_keys=True,ensure_ascii=False,
                                   default=str))
        if key in seen:
            duplicates+=1
            continue
        seen.add(key)
        groups.setdefault(note,[]).append(row)
    balanced=[]
    while any(groups.values()):
        for group in groups.values():
            if group:
                balanced.append(group.pop(0))
    return balanced,duplicates


def _category_note_count(rows):
    return len({str(row.get("nota_id") or row.get("nome_file") or
                    row.get("medicinale") or "")
                for row in rows if row})


def _needs_category_coverage_retry(sql,rows,truncated):
    if not rows:
        return False
    docs=_category_note_count(rows)
    # Una ricerca dominata da una singola nota non può essere
    # considerata esaustiva se ha esaurito il limite o usa una JOIN
    # che moltiplica le confezioni. Non forziamo sempre il retry.
    repeated_join=bool(re.search(
        r"\bJOIN\s+aifa_confezioni\b",sql,re.I))
    # Il taglio rende impossibile attestare l'assenza di ulteriori note,
    # anche se le prime righe contengono già molti documenti diversi.
    return truncated or (docs<=2 and repeated_join)


def _combine_category_context(first,second,question=""):
    combined,_=_balanced_category_rows([*first,*second])
    return _sql_context(combined,category=True,question=question)


def _execute_generated_select(db,sql,category=False,question=""):
    """Esegue una SELECT validata con gli stessi limiti per tutti i tentativi."""
    start=time.monotonic()
    db.set_progress_handler(lambda:1 if time.monotonic()-start>12 else 0,10000)
    try:
        raw=_in_phase("esecuzione SQL",
                      lambda:db.execute(sql).fetchmany(SQL_ROW_LIMIT+1))
        selected=( _balanced_category_rows(raw[:SQL_ROW_LIMIT])[0]
                   if category else raw[:SQL_ROW_LIMIT])
        rows,context_cut=_sql_context(selected,category=category,question=question)
        query_limit=_limit_from_sql(sql)
        truncated=(len(raw)>SQL_ROW_LIMIT or context_cut or
                   (query_limit is not None and len(raw)>=query_limit))
    finally:
        db.set_progress_handler(None,0)
    return rows,truncated


def _absolute_negative_on_partial_sql(answer,rows,truncated,category):
    """Blocca conclusioni di assenza globale da un sottoinsieme SQL.

    Non trasforma candidati in fatti: distingue un risultato incompleto
    dall'affermazione ingiustificata che non esistano medicinali.
    """
    if not (category and truncated and rows):
        return False
    statement=str(answer or "")
    if re.search(r"(?im)^\s*(?:[-*]\s*)?medicinale\s*:",statement):
        return False
    return bool(re.search(
        r"(?:non\s+(?:sono|risultano)\s+presenti\s+(?:medicinali|farmaci)"
        r"|nessun\s+(?:medicinale|farmaco)"
        r"|non\s+(?:esistono|vi\s+sono)\s+(?:medicinali|farmaci)"
        r"|(?:l['’]?)?informazione\s+richiesta\s+non\s+[eè]\s+documentata"
        r"|non\s+[eè]\s+documentata\s+nello\s+snapshot)",
        statement,flags=re.I))


def sql_method(db,question,model):
    category_context=category_sql_context(question)
    request={"schema":SCHEMA,"domanda":question}
    if category_context:
        request["contesto_categoria"]=category_context
    generated,first=_in_phase("generazione SQL",ask,model,
                              select_generation_guidance(question),request)
    attempts=1
    syntax_repair=False
    try:
        sql=_in_phase("validazione SQL",validate_sql,generated)
    except EnginePhaseError as exc:
        # Recupero soltanto da SQL sintatticamente non parsabile: le
        # query non autorizzate continuano a essere respinte senza retry.
        if exc.error_type!="ParseError":
            raise
        retry_request={
            "schema":SCHEMA,
            "domanda":question,
            "query_sql_rifiutata_dal_parser":generated[:12000],
            "contesto_categoria":category_context,
        }
        regenerated,retry_usage=_in_phase(
            "correzione sintassi SQL",ask,model,
            SQL_SYNTAX_REPAIR_RULES,retry_request)
        sql=_in_phase("validazione SQL",validate_sql,regenerated)
        first=_accumulate(first,retry_usage)
        attempts+=1
        syntax_repair=True

    first_sql=sql
    rows,truncated=_execute_generated_select(db,sql,category=bool(category_context),
                                             question=question)
    zero_row_retry=False

    if category_context and not rows:
        # Un'altra SELECT è ammessa solo per lo ZERO-righe, mai per
        # aggirare i controlli di sola lettura su una query rifiutata.
        retry_payload={
            "schema":SCHEMA,
            "domanda":question,
            "contesto_categoria":category_context,
            "query_precedente_senza_righe":first_sql,
            "righe_primo_tentativo":0
        }
        regenerated,retry_usage=_in_phase(
            "revisione SQL",ask,model,CATEGORY_RETRY_RULES,retry_payload)
        revised=_in_phase("validazione SQL",validate_sql,regenerated)
        attempts+=1
        zero_row_retry=True
        first=_accumulate(first,retry_usage)
        sql=revised
        rows,truncated=_execute_generated_select(db,sql,category=bool(category_context),
                                             question=question)

    # Un risultato non vuoto può essere comunque dominato da ripetizioni
    # di una sola nota; una seconda SELECT, sempre generata dal modello,
    # cerca una maggiore varietà documentale. Le evidenze restano distinte.
    coverage_retry=False
    coverage_retry_status="non_necessario"
    sql_evidence_queries=[sql]
    if (category_context and rows and
            _needs_category_coverage_retry(sql,rows,truncated)):
        coverage_retry=True
        previous_sql=sql
        retry_payload={
            "schema":SCHEMA,
            "domanda":question,
            "contesto_categoria":category_context,
            "query_precedente_con_copertura_limitata":previous_sql,
            "note_distinte_prima_riprova":_category_note_count(rows),
            "risultato_troncato":truncated
        }
        try:
            alternative_sql_raw,extra_usage=_in_phase(
                "miglioramento copertura SQL",ask,model,
                CATEGORY_DIVERSITY_RETRY_RULES,retry_payload)
            attempts+=1
            first=_accumulate(first,extra_usage)
            alternative_sql=_in_phase(
                "validazione SQL",validate_sql,alternative_sql_raw)
            other_rows,other_cut=_execute_generated_select(
                db,alternative_sql,category=True,question=question)
            sql_evidence_queries.append(alternative_sql)
            if other_rows:
                previous_count=_category_note_count(rows)
                merged,merge_cut=_combine_category_context(rows,other_rows,question=question)
                rows=merged
                # Anche la prima SELECT può essere stata troncata: non
                # nascondere il limite dopo aver unito più query.
                truncated=truncated or other_cut or merge_cut
                sql=alternative_sql
                coverage_retry_status=(
                    "nuove_note" if _category_note_count(rows)>previous_count
                    else "nessuna_nuova_nota")
            else:
                coverage_retry_status="seconda_query_senza_righe"
        except EnginePhaseError as exc:
            # La seconda query è facoltativa: se il modello fallisce o
            # genera SQL vietato, conserva la prima SELECT già validata.
            coverage_retry_status="rifiutata_o_non_eseguibile"
            if exc.phase=="miglioramento copertura SQL":
                attempts+=1

    citations=_sql_sources(db,rows)
    metadata={"sql_tentativi":attempts,
              "sql_iniziale":first_sql if zero_row_retry or coverage_retry else None,
              "sql_correzione_sintassi":syntax_repair,
              "sql_riprova_copertura":coverage_retry,
              "sql_esito_riprova_copertura":coverage_retry_status,
              "sql_query_fonti":sql_evidence_queries,
              "note_distinte_sql":_category_note_count(rows) if category_context else None,
              "categoria_implicita":bool(category_context)}
    if not rows:
        # Zero righe NON equivale ad assenza documentale: può essere un
        # falso negativo della query, soprattutto per categorie astratte.
        return {
            "risposta":("Nessuna riga restituita dalle query Text-to-SQL "
                       "per questa categoria. Non è una prova che "
                       "l'informazione sia assente nello snapshot."
                       if category_context else
                       "Informazione non documentata nello snapshot consultato."),
            "fonti":[],"sql":sql,"righe_sql":0,
            "stato":"NESSUNA_RIGA_SQL" if category_context else "NESSUNA_EVIDENZA",
            "risultato_parziale":bool(category_context),
            **first,"costo_completo":first.get("costo_usd") is not None,
            **metadata
        }

    answer,second=_in_phase("sintesi SQL",ask,model,
        "Rispondi in italiano SOLO in base alle righe SELECT e alle fonti. "
        "Non interpretare un dato AIFA/EMA come autorizzazione regionale. "
        "Se la classe_a_h_snapshot è NULL, indica C solo come deduzione per esclusione dagli elenchi A/H, mai come classe ufficialmente attestata. Distingui data della lista A/H e data della determina. "
        "Per categorie implicite non confondere il termine clinico generale "
        "con il nome letterale della patologia e, se la query restituisce "
        "pagine diverse della stessa nota, distingui la sezione con "
        "l'indicazione dalla tabella del centro. La co-occorrenza "
        "non certifica l'autorizzazione. "
        "Se mancano dati o evidenze, scrivi 'non documentato nello snapshot'. "
        "Non inventare citazioni; se i risultati sono parziali "
        "non dichiarare una lista completa E NON dire che non esistono "
        "medicinali: il contesto è un campione di pagine candidate. "
        "Se non puoi verificare l'associazione centro-indicazione, "
        "scrivi che la prova è insufficiente, senza dedurre assenza. "
        "Se più SELECT concorrono "
        "alle evidenze, esamina tutte le note senza considerare i "
        "candidati automaticamente autorizzati.",
        {"domanda":question,"righe_sql":rows,"fonti_recuperate":citations,
         "righe_limite":SQL_ROW_LIMIT,"risultati_parziali":truncated,
         "note_distinte":metadata["note_distinte_sql"],
         "query_eseguite":sql_evidence_queries})
    total=_accumulate(first,second)
    incorrect_absence=_absolute_negative_on_partial_sql(
        answer,rows,truncated,bool(category_context))
    original_answer=answer if incorrect_absence else None
    if incorrect_absence:
        answer=(
            "Le query Text-to-SQL hanno restituito "+str(len(rows))+
            " righe di evidenza da "+str(_category_note_count(rows))+
            " note candidate, ma i risultati sono parziali. "
            "Dalle righe disponibili non è stata verificata una "
            "corrispondenza sufficiente tra indicazione e centro "
            "prescrittore per produrre un elenco attendibile. "
            "Non è corretto concludere che non esistano medicinali "
            "pertinenti nello snapshot: occorre verificare le "
            "sezioni originali delle note.")
    if truncated:
        answer+=("\n\nAvvertenza: risultati SQL parziali per limite di "
                 "righe, limite della query o di contesto. L'elenco non "
                 "può essere considerato completo.")
    sql_evidence=[{"tipo":"SQL","fonte":"Riga "+str(ix+1),
                   "testo":str(record.get("testo") or record.get("indicazione_ema")
                               or record.get("descrizione") or "")}
                  for ix,record in enumerate(rows) if
                  (record.get("testo") or record.get("indicazione_ema")
                   or record.get("descrizione"))]
    return {"risposta":answer,"fonti":citations,"sql":sql,
            "evidenze_fonti":_source_previews(sql_evidence),
            "righe_sql":len(rows),
            "stato":("RISPOSTA_NON_VERIFICATA" if incorrect_absence else
                     "RISULTATI_PARZIALI" if truncated else "OK"),
            "negazione_non_supportata_sql":incorrect_absence,
            "risposta_modello_originale_sql":original_answer,
            "risultato_parziale":truncated,**total,
            "costo_completo":total["costo_usd"] is not None,**metadata}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--method",choices=["TAG","Text-to-SQL"],required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--question",required=True)
    p.add_argument("--out",type=Path)
    p.add_argument("--conferma-chiamate",action="store_true")
    a=p.parse_args()
    if not a.conferma_chiamate:
        p.error("Le API LLM consumano quote: aggiungi --conferma-chiamate")
    start=time.monotonic()
    with closing(read_only(a.db)) as db:
        result=tag(db,a.question,a.model) if a.method=="TAG" else sql_method(db,a.question,a.model)
    record={"metodo":a.method,"modello":a.model,"domanda":a.question,
            "secondi":round(time.monotonic()-start,3),**result}
    payload=json.dumps(record,ensure_ascii=False,indent=2)
    print(payload)
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(payload+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
