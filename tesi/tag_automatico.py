"""TAG automatico: SQL generato dall'LLM, poi sem_filter LOTUS.

Nessuna espansione manuale di categorie cliniche, farmaci o ospedali.
Il recupero successivo delle pagine e' un JOIN per identificativo, non un filtro
semantico; mantiene la provenienza. Limiti e tagli sono sempre espliciti.
"""
from __future__ import annotations

import json
import re
import time

from tesi.contatore_llm import instrument_lotus, measured_engine
from tesi.tag_budget import sem_filter_controlled, expand_selected
from tesi.pilota_tag_vs_sql import (
    _accumulate, _in_phase, _source_previews, _sql_schema,
    _sql_sources, ask, validate_sql,
)

SQL_CANDIDATE_LIMIT = 240
MAX_NOTE_PAGES = 1200
MAX_LOTUS_GROUPS = 12
MAX_ANSWER_DOCUMENTS = 55
MAX_ANSWER_CHARS = 44000

SQL_PROMPT = (
    "Genera UNA sola query SQLite SELECT che recuperi candidati da far "
    "valutare successivamente a LOTUS, NON la risposta finale. Usa solo "
    "le tabelle e le colonne dello schema. Per le note regionali usa note "
    "JOIN pagine e seleziona DISTINCT note.id AS nota_id "
    "(e altri identificativi solo se utili). "
    "Filtra con SQL i vincoli OGGETTIVI espliciti nella domanda, come il "
    "nome di un medicinale, il nome di una struttura, un AIC o un protocollo. "
    "Se la domanda chiede una CATEGORIA CLINICA, NON tradurla in elenchi "
    "di patologie e NON filtrare per sinonimi o indicazioni cliniche: "
    "saranno valutati da LOTUS leggendo le note. "
    "Per una categoria clinica richiesta presso un ospedale, recupera "
    "tutte le note che menzionano l'ospedale, senza filtrare le patologie. "
    "Per un elenco di documenti NON usare LIMIT e NON aggregare le note "
    "prima del filtro semantico. Per dati tabellari seleziona le righe "
    "pertinenti e i relativi identificativi (aic, ema_id o documento_id). "
    "Non usare SQL per inferire autorizzazioni dalla sola menzione di un centro. "
    "Nessuna PRAGMA, DML, DDL, istruzioni multiple o spiegazioni. "
    "Restituisci esclusivamente il testo SQL."
)

SEMANTIC_PROMPT = (
    "Il seguente documento o gruppo di righe {testo} contiene elementi "
    "pertinenti alla domanda: {domanda}? Valuta il SIGNIFICATO clinico, "
    "le relazioni tra centri, indicazioni e farmaci e le prove documentali. "
    "Non assumere che la sola menzione di un ospedale sia un'autorizzazione. "
    "Non applicare un elenco precostituito di patologie o sinonimi. "
    "Se un gruppo contiene ALMENO una prova potenzialmente pertinente, "
    "selezionalo; la sintesi finale deve verificare i singoli documenti."
)

ANSWER_PROMPT = (
    "Rispondi in italiano usando ESCLUSIVAMENTE le evidenze recuperate. "
    "Per ogni elemento di un elenco controlla documento, indicazione, "
    "struttura e pagina. Una struttura menzionata non e' automaticamente "
    "autorizzata. Distingui i fatti verificati dalle sole menzioni. "
    "Se mancano dati, l'evidenza non e' completa o le fonti sono troncate, "
    "segnala chiaramente la parzialita' e non inventare. "
    "Cita nome del documento e pagina per le note; per EMA/AIFA cita "
    "l'identificativo. Non interpretare un'assenza nel database come "
    "l'assenza del fatto nel mondo reale."
)


def _run_generated_select(db, sql):
    """Esegue SELECT read-only con timeout e limite visibile; nessun retry."""
    started = time.monotonic()
    db.set_progress_handler(lambda: 1 if time.monotonic()-started > 12 else 0, 10000)
    try:
        cursor = db.execute(sql)
        records = cursor.fetchmany(SQL_CANDIDATE_LIMIT + 1)
    finally:
        db.set_progress_handler(None, 0)
    partial = len(records) > SQL_CANDIDATE_LIMIT or bool(re.search(r"\bLIMIT\s+\d+", sql, re.I))
    return [dict(row) for row in records[:SQL_CANDIDATE_LIMIT]], partial


def _note_candidates(db, records):
    """Espande TUTTE le note candidate nelle rispettive pagine, senza filtri clinici."""
    ids = list(dict.fromkeys(str(row["nota_id"]) for row in records
                             if row.get("nota_id") is not None))
    if not ids:
        return [], False
    rows = []
    page_count = 0
    partial = False
    for note_id in ids:
        note = db.execute(
            "SELECT id,nome_file,farmaco_candidato,indicazione_candidata,"
            "percorso_zip,archivio_url FROM note WHERE id=?", (note_id,)
        ).fetchone()
        if note is None:
            continue
        pages = db.execute(
            "SELECT numero_pagina,testo FROM pagine WHERE nota_id=? "
            "AND metodo IN ('TESTO','OCR') ORDER BY numero_pagina", (note_id,)
        ).fetchall()
        if page_count + len(pages) > MAX_NOTE_PAGES:
            partial = True
            break
        page_count += len(pages)
        notes = dict(note)
        sources = [str(notes["percorso_zip"]) + "#p" + str(p["numero_pagina"]) +
                   " | archivio: " + str(notes["archivio_url"]) for p in pages]
        # Preparazione neutrale: incipit e fine di OGNI pagina, senza sinonimi
        # o preferenze verso malattie fissate nel codice.
        selection_parts = []
        answer_parts = []
        for p in pages:
            raw = " ".join(str(p["testo"] or "").split())
            if len(raw) > 4200:
                partial = True
            # Conserva un campione di OGNI pagina, anche se la nota e' lunga.
            per_page = max(70, min(420, 1050 // max(1, len(pages))))
            if len(raw) > per_page:
                before = max(30, per_page // 2)
                preview = raw[:before] + " [...] " + raw[-(per_page-before):]
            else:
                preview = raw
            selection_parts.append("[pagina " + str(p["numero_pagina"]) + "] " + preview)
            answer_parts.append("[pagina " + str(p["numero_pagina"]) + "] " + raw[:4200] +
                                (" [TESTO PAGINA TRONCATO]" if len(raw) > 4200 else ""))
        prefix = ("Documento: " + str(notes["nome_file"]) +
                  "; farmaco candidato: " + str(notes.get("farmaco_candidato") or "") +
                  "; indicazione candidata da verificare: " +
                  str(notes.get("indicazione_candidata") or ""))
        rows.append({"chiave": "NOTA:" + note_id, "tipo": "REGIONE",
                     "testo": prefix + "\n" + "\n".join(answer_parts),
                     "testo_selezione": prefix + "\n" + "\n".join(selection_parts),
                     "fonte": sources[0] if sources else str(notes["percorso_zip"]),
                     "fonti": sources, "nota_id": note_id})
    return rows, partial


def _tabular_candidates(db, records):
    """Righe SQL senza regole per patologie, con identificativi e fonti."""
    candidates = []
    for idx, row in enumerate(records):
        source = _sql_sources(db, [row])
        candidates.append({"chiave": "SQL:"+str(idx), "tipo": "SQL",
                           "testo": json.dumps(row, ensure_ascii=False, default=str)[:3600],
                           "fonte": source[0] if source else "Riga SQL "+str(idx+1),
                           "fonti": source})
    return candidates


def _lotus_plan(candidates):
    """Raggruppa SOLO per budget, senza classificare patologie o scegliere note."""
    groups = min(MAX_LOTUS_GROUPS, max(1, (len(candidates)+11)//12))
    bundles = [[] for _ in range(groups)]
    for idx, row in enumerate(candidates):
        bundles[idx % groups].append(row)
    frames, members = [], {}
    for idx, group in enumerate(bundles):
        uid = "GRUPPO:" + str(idx+1)
        content = "\n".join("["+r["chiave"]+"] " +
                            str(r.get("testo_selezione") or r["testo"])[:1600]
                            for r in group)
        frames.append({"chiave":uid,"testo":content})
        members[uid] = group
    return frames, members


def automatic_tag(db, question, model):
    """LLM -> SQL -> DB -> LOTUS sem_filter -> LLM; niente dizionari clinici."""
    import pandas as pd
    import lotus
    from lotus.models import LM

    generated, generation_usage = _in_phase(
        "generazione SQL TAG automatico", ask, model, SQL_PROMPT,
        {"schema": _sql_schema(db), "domanda": question}
    )
    sql = _in_phase("validazione SQL TAG automatico", validate_sql, generated)
    records, sql_partial = _in_phase(
        "esecuzione SQL TAG automatico", _run_generated_select, db, sql
    )
    base = {"sql":sql, "versione_tag":"automatico-v1",
            "recupero":"LLM-SQL", "sql_tentativi":1, "righe_sql":len(records)}
    if not records:
        return {**base, "risposta":"La query SQL non ha restituito righe. "
                "Questo non dimostra che l'informazione sia assente dalle fonti.",
                "fonti":[],"stato":"NESSUNA_EVIDENZA",**generation_usage}
    if any("nota_id" in r and r["nota_id"] is not None for r in records):
        candidates, page_partial = _in_phase(
            "recupero pagine TAG automatico", _note_candidates, db, records)
    else:
        candidates = _tabular_candidates(db, records)
        page_partial = False
    if not candidates:
        return {**base, "risposta":"La SELECT ha trovato identificativi, "
                "ma non sono disponibili testi consultabili per il filtro LOTUS.",
                "fonti":[], "stato":"NESSUNA_EVIDENZA", **generation_usage}

    lm = _in_phase("inizializzazione TAG automatico", LM, model, max_batch_size=3)
    instrument_lotus(lm)
    _in_phase("inizializzazione TAG automatico", lotus.settings.configure,
              lm=lm, enable_cache=False)
    planned, members = _lotus_plan(candidates)
    filtered = _in_phase("selezione LOTUS TAG automatico", sem_filter_controlled,
                         pd.DataFrame(planned),
                         SEMANTIC_PROMPT.format(testo="{testo}",domanda=json.dumps(question,ensure_ascii=False)))
    selected_groups = filtered[["chiave"]].to_dict("records")
    selected = expand_selected(selected_groups, members)
    if not selected:
        return {**base, "risposta":"LOTUS non ha selezionato evidenze fra "
                "i candidati. Questo non dimostra che l'informazione sia assente.",
                "fonti":[], "stato":"NESSUNA_SELEZIONE_SEMANTICA",
                "righe_recuperate":len(candidates), "righe_sem_filter":len(planned),
                "righe_selezionate_lotus":0, **generation_usage}

    chosen = []
    used_chars = 0
    truncated_answer = False
    for item in selected:
        if len(chosen) >= MAX_ANSWER_DOCUMENTS:
            truncated_answer = True
            break
        text = str(item["testo"])
        remaining = MAX_ANSWER_CHARS-used_chars
        if remaining <= 0:
            truncated_answer = True
            break
        if len(text)>remaining:
            text=text[:remaining]+" [EVIDENZA TRONCATA]"
            truncated_answer = True
        used_chars += len(text)
        chosen.append({"chiave":item["chiave"],"testo":text,
                       "fonti":item.get("fonti") or [item["fonte"]]})
    partial = sql_partial or page_partial or truncated_answer
    answer, answer_usage = _in_phase(
        "sintesi TAG automatico", ask, model, ANSWER_PROMPT,
        {"domanda":question,"evidenze":chosen,"risultati_parziali":partial},
        timeout=65, max_tokens=2400
    )
    if partial:
        answer += "\n\nAvvertenza: recupero o contesto parziale; l'elenco non e' esaustivo."
    sources = list(dict.fromkeys(src for item in chosen for src in item["fonti"]))
    return {**base, "risposta":answer, "fonti":sources[:80],
            "evidenze_fonti":_source_previews(selected),
            "stato":"RISULTATI_PARZIALI" if partial else "OK",
            "risultato_parziale":partial,
            "righe_recuperate":len(candidates),"righe_sem_filter":len(planned),
            "righe_selezionate_lotus":len(selected_groups),
            "modalita_selezione":"gruppi neutri",
            "chiamate_llm_stimate":len(planned)+2,
            **_accumulate(generation_usage,answer_usage)}


# La misurazione delle chiamate usa lo stesso contatore degli altri motori.
automatic_tag = measured_engine(automatic_tag)
