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
TAG_AUTO_REVISION = "2026-11-06-r3-relazioni-note"

SQL_PROMPT = (
    "Genera UNA sola query SQLite SELECT che recuperi candidati da far "
    "valutare successivamente a LOTUS, NON la risposta finale. Usa solo "
    "le tabelle e le colonne dello schema. Per le note regionali usa note "
    "JOIN pagine e seleziona DISTINCT note.id AS nota_id "
    "(e altri identificativi solo se utili). "
    "La JOIN deve collegare le chiavi: note.id = pagine.nota_id "
    "(o n.id = p.nota_id se usi alias). "
    "Per domande su quali NOTE MENZIONANO un medicinale, cerca il nome "
    "nel campo pagine.testo con LIKE e seleziona DISTINCT note.id AS nota_id; "
    "non limitarti a note.nome_file o note.farmaco_candidato, perché una nota "
    "può menzionare medicinali diversi da quello del titolo. "
    "Filtra con SQL i vincoli OGGETTIVI espliciti nella domanda, come il "
    "nome di un medicinale, il nome di una struttura, un AIC o un protocollo. "
    "Se la domanda chiede una CATEGORIA CLINICA, NON tradurla in elenchi "
    "di patologie e NON filtrare per sinonimi o indicazioni cliniche: "
    "saranno valutati da LOTUS leggendo le note. "
    "Per una categoria clinica richiesta presso un ospedale, recupera "
    "tutte le note che menzionano l'ospedale, senza filtrare le patologie. "
    "Per un elenco di documenti NON usare LIMIT e NON aggregare le note "
    "prima del filtro semantico. Per dati tabellari restituisci SEMPRE "
    "anche la denominazione del medicinale (nome), la colonna richiesta "
    "dalla domanda e gli identificativi disponibili (aic, ema_id o "
    "documento_id). Non restituire solo un valore privo del suo soggetto. "
    "Per confronti ESATTI sul nome dei medicinali usa COLLATE NOCASE "
    "(esempio: nome = 'Farmaco' COLLATE NOCASE); non usare confronti "
    "sensibili alle maiuscole. "
    "Se usi UNION, allinea esplicitamente gli alias delle colonne e "
    "non collocare aic ed ema_id nella stessa posizione con il medesimo "
    "alias: sono identificativi di fonti diverse. "
    "mantieni il nome del medicinale in ogni ramo. Per combinare AIFA ed EMA "
    "usa preferibilmente UNION ALL e una colonna fonte_origine con i valori "
    "AIFA o EMA. Non eliminare righe di fonti differenti. Non sostituire "
    "con NULL un identificativo esistente nella tabella di provenienza: "
    "AIFA deve riportare il VERO aic e EMA il VERO ema_id; usa NULL solo "
    "per la colonna inesistente nell\u0027altro ramo. "
    "Per collegamenti fra EMA e AIFA, quando la domanda riguarda uno "
    "specifico medicinale e il nome è disponibile in entrambe le fonti, "
    "usa anche la corrispondenza dei nomi con COLLATE NOCASE: "
    "una JOIN soltanto sul principio attivo può collegare marchi diversi. "
    "Non duplicare lo stesso collegamento con una UNION ALL del JOIN inverso; "
    "per un rapporto uno-a-molti usa una singola JOIN, senza UNION ridondante. "
    "Non usare SQL per inferire autorizzazioni dalla sola menzione di un centro. "
    "Nessuna PRAGMA, DML, DDL, istruzioni multiple o spiegazioni. "
    "Restituisci esclusivamente il testo SQL."
)

DOCUMENT_SEMANTIC_PROMPT = (
    "Il seguente gruppo di documenti {testo} contiene informazioni "
    "potenzialmente pertinenti alla domanda: {domanda}? Valuta il significato "
    "clinico e le relazioni effettivamente documentate fra medicinali, "
    "indicazioni e strutture. La mera menzione di un ospedale non prova "
    "un'autorizzazione. Non usare elenchi precostituiti di patologie. "
    "Se almeno un documento puo' essere pertinente, seleziona il gruppo: "
    "la risposta finale esaminera' i documenti singolarmente."
)

TABULAR_SEMANTIC_PROMPT = (
    "Questo gruppo di RISULTATI SQL STRUTTURATI {testo} contiene uno o piu' "
    "valori utili a rispondere alla domanda: {domanda}? Il database ha "
    "gia' applicato i filtri oggettivi della SELECT. Per una domanda su "
    "un attributo (ad esempio principio attivo, stato, data, AIC o classe), "
    "una riga con il nome della colonna richiesta e un valore non vuoto "
    "e' pertinente, anche quando il nome del medicinale non viene ripetuto "
    "nel risultato della query. Non richiedere prove cliniche, indicazioni "
    "o autorizzazioni in una domanda puramente anagrafica. "
    "Se ALMENO una riga contiene informazioni potenzialmente utili, "
    "seleziona il gruppo; le eventuali ambiguita' saranno esaminate "
    "nella risposta finale."
)

# Alias retrocompatibile per eventuali importazioni esterne.
SEMANTIC_PROMPT = DOCUMENT_SEMANTIC_PROMPT

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


TABULAR_ANSWER_PROMPT = (
    "Rispondi in italiano esclusivamente in base alle righe SQL strutturate. "
    "Per ogni attributo indica il medicinale. Se le fonti riportano "
    "denominazioni diverse per lo stesso attributo, descrivi precisamente "
    "la differenza di denominazione. Non affermare che si tratti di sostanze "
    "distinte, risultati incompatibili o equivalenti senza evidenze "
    "sufficienti nei dati recuperati. Evita formule come 'i principi attivi "
    "variano a seconda della fonte' se i soli dati mostrano nomi diversi. "
    "Per AIFA cita l'AIC, per EMA l'EMA ID, "
    "ma solo se presenti nei riferimenti verificabili. NON richiedere numeri "
    "di pagina: i dati EMA/AIFA provengono da tabelle, non da pagine PDF. "
    "Evita 'p. non specificata' e non inventare pagine o identificativi. "
    "Se mancano dati sufficienti, dichiaralo."
)


_NOME_UGUALE_RE = re.compile(
    r"""(?<![\w])(?P<col>(?:[A-Za-z_]\w*\.)?"?nome"?)\s*=\s*"""
    r"""(?P<value>'(?:''|[^'])*')(?!\s+COLLATE\s+\w+)""",
    re.IGNORECASE,
)


def _normalize_exact_name_comparisons(sql):
    """Confronti nome = stringa non sensibili al case, senza query aggiuntive.

    Normalizzazione SQL generale e riproducibile, prima di rieseguire il
    validatore read-only. Non inserisce nomi di medicinali o sinonimi clinici.
    """
    return _NOME_UGUALE_RE.sub(
        lambda m: m.group("col") + " = " + m.group("value") +
        " COLLATE NOCASE", sql
    )


def _canonicalize_tabular_identifier(db, row):
    """Riconcilia identificativi disallineati dalle UNION per POSIZIONE.

    SQLite usa i nomi delle colonne della prima SELECT anche nelle righe
    successive. Verifichiamo l'ID contro lo schema e il nome del medicinale:
    non aggiungiamo contenuti né nuovi candidati e non usiamo parole cliniche.
    """
    data = dict(row)
    name = str(data.get("nome") or "").strip()
    if not name:
        return data, False
    aic = str(data.get("aic") or "").strip()
    ema = str(data.get("ema_id") or "").strip()
    if aic and not ema:
        src_ema = db.execute(
            "SELECT 1 FROM ema_medicinali WHERE ema_id=? "
            "AND nome=? COLLATE NOCASE LIMIT 1", (aic, name)
        ).fetchone()
        if src_ema:
            src_aifa = db.execute(
                "SELECT 1 FROM aifa_confezioni WHERE aic=? LIMIT 1", (aic,)
            ).fetchone()
            if not src_aifa:
                data["ema_id"], data["aic"] = aic, None
                data["fonte_origine"] = "EMA"
                return data, True
    if ema and not aic:
        src_aifa = db.execute(
            "SELECT 1 FROM aifa_confezioni WHERE aic=? "
            "AND nome=? COLLATE NOCASE LIMIT 1", (ema, name)
        ).fetchone()
        if src_aifa:
            src_ema = db.execute(
                "SELECT 1 FROM ema_medicinali WHERE ema_id=? LIMIT 1", (ema,)
            ).fetchone()
            if not src_ema:
                data["aic"], data["ema_id"] = ema, None
                data["fonte_origine"] = "AIFA"
                return data, True
    return data, False


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
        corrected, normalized = _canonicalize_tabular_identifier(db, row)
        source = _sql_sources(db, [corrected])
        if not source:
            source = _verify_tabular_identifiers(db, corrected)
        candidates.append({"chiave": "SQL:"+str(idx), "tipo": "SQL",
                           "testo": json.dumps(corrected, ensure_ascii=False, default=str)[:3600],
                           "fonte": source[0] if source else "Riga SQL "+str(idx+1),
                           "fonti": source,
                           "provenienza_sql_riconciliata": normalized})
    return candidates


def _verify_tabular_identifiers(db, row):
    """Trova esclusivamente riferimenti collegati a nome+valore esatti.

    Passo deterministico di provenienza: non aggiunge nuovi candidati,
    non usa categorie cliniche e non altera il recupero SQL generato.
    """
    name = str(row.get("nome") or "").strip()
    active = str(row.get("principio_attivo") or "").strip()
    if not name or not active:
        return []
    origin = str(row.get("fonte_origine") or "").strip().casefold()
    if origin not in ("", "aifa", "ema"):
        return []
    found = []
    if origin in ("", "aifa") and not row.get("aic") and not row.get("ema_id"):
        entries = db.execute(
            "SELECT DISTINCT aic FROM aifa_confezioni "
            "WHERE nome = ? COLLATE NOCASE "
            "AND principio_attivo = ? COLLATE NOCASE "
            "AND aic IS NOT NULL ORDER BY aic LIMIT 21", (name, active)
        ).fetchall()
        # In caso di molte confezioni non affermare una provenienza esaustiva.
        if 0 < len(entries) <= 20:
            found.extend(
                "AIFA AIC " + str(entry["aic"]) +
                " | snapshot elenchi ufficiali A/H"
                for entry in entries
            )
    if origin in ("", "ema") and not row.get("ema_id") and not row.get("aic"):
        entries = db.execute(
            "SELECT DISTINCT ema_id, url_ema FROM ema_medicinali "
            "WHERE nome = ? COLLATE NOCASE "
            "AND principio_attivo = ? COLLATE NOCASE "
            "AND ema_id IS NOT NULL LIMIT 2", (name, active)
        ).fetchall()
        if len(entries) == 1:
            entry = entries[0]
            found.append("EMA " + str(entry["ema_id"]) +
                         (" | " + str(entry["url_ema"])
                          if entry["url_ema"] else ""))
    return found


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
    sql_originale_llm = _in_phase(
        "validazione SQL TAG automatico", validate_sql, generated
    )
    sql = _in_phase(
        "normalizzazione SQL TAG automatico", validate_sql,
        _normalize_exact_name_comparisons(sql_originale_llm)
    )
    records, sql_partial = _in_phase(
        "esecuzione SQL TAG automatico", _run_generated_select, db, sql
    )
    base = {"sql":sql, "sql_originale_llm":sql_originale_llm,
            "sql_normalizzato_nome":sql != sql_originale_llm,
            "tag_auto_revision":TAG_AUTO_REVISION,
            "versione_tag":"automatico-v1",
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
    base["identificativi_sql_riconciliati"] = sum(
        bool(item.get("provenienza_sql_riconciliata")) for item in candidates
    )
    if not candidates:
        return {**base, "risposta":"La SELECT ha trovato identificativi, "
                "ma non sono disponibili testi consultabili per il filtro LOTUS.",
                "fonti":[], "stato":"NESSUNA_EVIDENZA", **generation_usage}

    lm = _in_phase("inizializzazione TAG automatico", LM, model, max_batch_size=3)
    instrument_lotus(lm)
    _in_phase("inizializzazione TAG automatico", lotus.settings.configure,
              lm=lm, enable_cache=False)
    planned, members = _lotus_plan(candidates)
    semantic_instruction = (DOCUMENT_SEMANTIC_PROMPT if any(
        item.get("nota_id") is not None for item in candidates
    ) else TABULAR_SEMANTIC_PROMPT)
    filtered = _in_phase("selezione LOTUS TAG automatico", sem_filter_controlled,
                         pd.DataFrame(planned),
                         semantic_instruction.format(
                             testo="{testo}",domanda=json.dumps(question,ensure_ascii=False)))
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
    answer_prompt = (ANSWER_PROMPT if any(
        item.get("nota_id") is not None for item in candidates
    ) else TABULAR_ANSWER_PROMPT)
    answer, answer_usage = _in_phase(
        "sintesi TAG automatico", ask, model, answer_prompt,
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
