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
    # Preserva il recupero via FTS per farmaci presenti solo nelle note.
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
    if not target:
        return []
    kind=_question_kind(question)
    rows=[]
    seen=set()

    def put(tipo,uid,description,source):
        if uid not in seen and len(rows)<max_rows:
            seen.add(uid)
            rows.append({"tipo":tipo,"chiave":uid,
                         "testo":str(description)[:2600],"fonte":source})

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
        for item in candidates(db,target,limit=5 if kind=="CENTRI" else 3):
            put("REGIONE",str(item["nota_id"])+"#p"+str(item["numero_pagina"]),
                str(item["testo"])[:1750],
                str(item["percorso_zip"])+"#p"+str(item["numero_pagina"])+
                " | archivio: "+str(item["archivio_url"]))

    def add_gu():
        for item in candidati_gu(db,question,limit=6):
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

    if kind=="GU":
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


def ask(model,system,payload):
    """LiteLLM con restituzione di token e costo quando disponibili."""
    from litellm import completion
    result=_in_phase("connessione LLM",completion,model=model,temperature=0,
        messages=[
            {"role":"system","content":system},
            {"role":"user","content":json.dumps(payload,ensure_ascii=False,default=str)}
        ],timeout=40,num_retries=0)
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


def tag(db,question,model):
    import pandas as pd
    import lotus
    from lotus.models import LM
    rows=evidence_candidates(db,question,max_rows=10)
    if not rows:
        return {"risposta":"Informazione non documentata nello snapshot consultato.",
                "fonti":[],"stato":"NESSUNA_EVIDENZA","token_input":0,
                "token_output":0,"costo_usd":0.0,"costo_completo":True}
    lm=_in_phase("inizializzazione TAG",LM,model=model,max_batch_size=4)
    _in_phase("inizializzazione TAG",lotus.settings.configure,lm=lm,enable_cache=False)
    frame=pd.DataFrame(rows)
    selected=_in_phase("selezione TAG",lambda: frame.sem_filter(
        "La riga {testo} è pertinente ad ALMENO UNA parte della domanda "
        +json.dumps(question,ensure_ascii=False)
        +". NON richiedere che la singola riga soddisfi tutte le parti: "
         "una riga EMA può indicare il tumore, AIFA la classe, una nota "
         "regionale i centri di prescrizione o somministrazione. "
         "Valuta anche le informazioni parziali documentate. "
         "Considera il nome commerciale esatto, non farmaci diversi "
         "che contengono lo stesso principio attivo; le strutture dei "
         "registri AIFA non sono automaticamente centri autorizzati."
    ).head(5 if len(_facets(question))>1 else 8))
    # L'assenza delle statistiche non deve annullare una risposta valida.
    selection_usage=getattr(getattr(lm,"stats",None),"physical_usage",None)
    prompt_tokens=getattr(selection_usage,"prompt_tokens",None)
    completion_tokens=getattr(selection_usage,"completion_tokens",None)
    selection_cost=getattr(selection_usage,"total_cost",None)
    # Conserviamo chiave e tipo per garantire copertura delle fonti senza
    # confondere una selezione semantica vuota con un database vuoto.
    semantic=selected[["tipo","chiave","testo","fonte"]].to_dict("records")
    evidence=_multisource_evidence(rows,semantic,question)
    if not evidence:
        return {"risposta":"Informazione non documentata nello snapshot consultato.",
                "fonti":[],"stato":"NESSUNA_EVIDENZA_SEMANTICA",
                "righe_recuperate":len(rows),
                "token_input":prompt_tokens,
                "token_output":completion_tokens,
                "costo_usd":selection_cost,"costo_completo":selection_cost is not None}
    answer,usage=ask(model,"Rispondi in italiano in modo breve e specifico, SOLO alla domanda. "
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
        "Per domande con più parti: rispondi separatamente a ciascuna, "
        "usando EMA per le indicazioni, AIFA per le classi delle confezioni "
        "le note regionali per i centri e gli atti GU per le determine. "
         "I testi GU possono essere parziali; non inferire lo stato vigente. "
         "NON rinunciare a rispondere alle "
        "parti documentate se manca la fonte di una sola parte. "
        "Non dichiarare un centro autorizzato soltanto dal registro AIFA "
        "e non dedurlo da una semplice menzione in un PDF. "
        "Indica le fonti pertinenti e per le parti non documentate scrivi "
        "'non documentato nello snapshot'.",
        {"domanda":question,"medicinale_o_sostanza_ricercata":_target_db(db, question),
         "intento":_question_kind(question),
         "parti_richieste":sorted(_facets(question)),
         "fonti_presenti":sorted({r["tipo"] for r in evidence}),
         "evidenze":evidence})
    input_tokens=(prompt_tokens+usage["token_input"]
                  if prompt_tokens is not None and usage["token_input"] is not None else None)
    output_tokens=(completion_tokens+usage["token_output"]
                   if completion_tokens is not None and usage["token_output"] is not None else None)
    full_cost=(selection_cost+usage["costo_usd"]
               if selection_cost is not None and usage["costo_usd"] is not None else None)
    return {"risposta":answer,"fonti":list(dict.fromkeys(x["fonte"] for x in evidence)),
            "stato":"OK","token_input":input_tokens,
            "token_output":output_tokens,"costo_usd":full_cost,
            "costo_completo":full_cost is not None,
            "righe_sem_filter":len(rows),
            "righe_selezionate_lotus":len(semantic),
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
        gu = row.get("gu_codice")
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


def sql_method(db,question,model):
    generated,first=_in_phase("generazione SQL",ask,model,
        "Genera SOLO UNA query SELECT SQLite eseguibile, senza Markdown. "
        "Usa esclusivamente le tabelle documentate; non generare DDL, DML, "
        "PRAGMA né più istruzioni. LIMIT 30. Per citazioni includi "
        "aic, ema_id oppure nota_id e numero_pagina nel risultato, "
         "e per GU codice AS gu_codice o documento_id, "
        "e archivio_url o fonte_url quando pertinenti. "
        "Per le classi usa: CASE WHEN classe_a_h_snapshot IN ('A','H') THEN classe_a_h_snapshot ELSE 'C (dedotta per esclusione)' END AS classe. Includi anche classe_a_h_snapshot e classe_a_h_data per distinguere fonte e deduzione.",
        {"schema":SCHEMA,"domanda":question})
    sql=_in_phase("validazione SQL",validate_sql,generated)
    start=time.monotonic()
    db.set_progress_handler(lambda:1 if time.monotonic()-start>12 else 0,10000)
    try:
        raw=_in_phase("esecuzione SQL",lambda:db.execute(sql).fetchmany(31))
        rows=[{key:(str(value)[:2500] if value is not None else None)
               for key,value in dict(r).items()} for r in raw[:30]]
    finally:
        db.set_progress_handler(None,0)
    citations=_sql_sources(db,rows)
    answer,second=_in_phase("sintesi SQL",ask,model,
        "Rispondi in italiano SOLO in base alle righe SELECT e alle fonti. "
        "Non interpretare un dato AIFA/EMA come autorizzazione regionale. "
        "Se la classe_a_h_snapshot è NULL, indica C solo come deduzione per esclusione dagli elenchi A/H, mai come classe ufficialmente attestata. Distingui data della lista A/H e data della determina. "
        "Se mancano dati o evidenze, scrivi 'non documentato nello snapshot'. "
        "Non inventare citazioni.",
        {"domanda":question,"righe_sql":rows,"fonti_recuperate":citations})
    total=_accumulate(first,second)
    return {"risposta":answer,"fonti":citations,"sql":sql,
            "righe_sql":len(rows),"stato":"OK",**total,"costo_completo":True}


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
