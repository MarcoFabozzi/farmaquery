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
from tesi.piano_documentale import (
    PLAN_PROMPT, document_center_anchors, validated_document_plan,
    sql_from_document_plan,
)
from tesi.tag_budget import sem_filter_controlled, expand_selected, preserve_category_recall
from tesi.raffinamento_documentale import (
    MIN_DOCS_FOR_REFINEMENT, REFINEMENT_PROMPT,
    refinement_payload, parse_refinement_result, refinement_batches,
)
from tesi.recupero_progressivo import (
    normalize_document_note_id, propose_empty_category_fallback,
    propose_partial_center_expansion,
    propose_empty_crosspage_category_fallback,
    propose_empty_note_page_semantic_fallback,
    propose_partial_crosspage_center_expansion,
)
from tesi.pilota_tag_vs_sql import (
    _accumulate, _in_phase, _source_previews, _sql_schema,
    _sql_sources, ask, validate_sql,
)

SQL_CANDIDATE_LIMIT = 240
MAX_NOTE_PAGES = 1200
MAX_LOTUS_GROUPS = 12
MAX_ANSWER_DOCUMENTS = 55
MAX_ANSWER_CHARS = 44000
TAG_AUTO_REVISION = "2026-11-07-r17-piano-documentale-strutturato"

SQL_PROMPT = (
    "Genera UNA sola query SQLite SELECT che recuperi candidati da far "
    "valutare successivamente a LOTUS, NON la risposta finale. Usa solo "
    "le tabelle e le colonne dello schema. Per le note regionali usa note "
    "JOIN pagine e seleziona DISTINCT note.id AS nota_id "
    "(e altri identificativi solo se utili). "
    "La JOIN deve collegare le chiavi: note.id = pagine.nota_id "
    "(o n.id = p.nota_id se usi alias). "
    "Per domande su indicazioni e centri NELLE NOTE, prima individua "
    "i documenti da note e pagine (seleziona note.id AS nota_id), "
    "poi il motore recupererà i testi completi delle pagine. "
    "Tabelle curate come nota_centro_documentato e "
    "nota_metadati_revisionati sono parziali: includono solo note "
    "già revisionate. NON usare INNER JOIN verso queste tabelle "
    "come requisito per trovare il documento, perché una nota "
    "senza relazione revisionata non deve scomparire. "
    "Anche centri_candidati contiene MENZIONI e puo' essere incompleta: "
    "non usarla come unica condizione per una ricerca DOCUMENTALE "
    "esaustiva su una categoria, e non confondere menzione e abilitazione. "
    "Se ti servono valori aggiuntivi da tabelle curate e non vi "
    "applichi filtri obbligatori, usa LEFT JOIN; in assenza di "
    "relazione la nota resta candidata e il PDF fornisce l'evidenza. "
    "Per domande su quali NOTE MENZIONANO un medicinale, cerca il nome "
    "nel campo pagine.testo con LIKE e seleziona DISTINCT note.id AS nota_id; "
    "non limitarti a note.nome_file o note.farmaco_candidato, perché una nota "
    "può menzionare medicinali diversi da quello del titolo. "
    "La tabella note è già l'archivio delle note REGIONALI della Campania: "
    "NON aggiungere predicati su note.percorso_zip o note.nome_file "
    "con LIKE '%Campania%' per riconoscere la regione. "
    "Questi campi rappresentano nomi e percorsi dei file e NON attributi "
    "geografici; il percorso può non contenere la parola Campania. "
    "Quando servono menzioni testuali, filtra pagine.testo per il "
    "medicinale richiesto, senza condizioni extra di appartenenza regionale. "
    "Filtra con SQL i vincoli OGGETTIVI espliciti nella domanda, come il "
    "nome di un medicinale, il nome di una struttura, un AIC o un protocollo. "
    "Se viene richiesto un DATO OPERATIVO non presente come colonna nello "
    "schema (ad esempio eventi realmente avvenuti, conteggi di trattamenti, "
    "date di inizio effettivo, ricavi), NON costruire JOIN artificiali, "
    "non inventare colonne e non cercare una cifra inesistente con LIKE. "
    "Recupera invece le note o i record pertinenti al medicinale o alla "
    "fonte, per permettere alla sintesi di verificare e motivare "
    "un'eventuale assenza documentale. "
    "Per domande sull'intero DOCUMENTO non imporre che medicinali, anni, "
    "strutture e altre parole compaiano tutti nella STESSA pagina di testo; "
    "una condizione su pagine.testo vale solo sulla singola pagina. "
    "Preferisci identificare il documento tramite note.farmaco_candidato "
    "o note.nome_file, usare note.anno per l'anno di archivio se richiesto, "
    "e poi lasciare che siano consultate tutte le sue pagine. "
    "Usa solo JOIN fra tabelle con una reale relazione di chiave "
    "esplicitata nello schema; non collegare tabelle senza legame "
    "per cercare misure che non esistono. "
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
    "La selezione riguarda la PERTINENZA del documento rispetto al "
    "soggetto della domanda, non la presenza garantita del dato richiesto. "
    "Anche per domande su valori non documentati (numero reale di pazienti, "
    "date di somministrazione, ricavi, eventi), conserva il gruppo se "
    "contiene note del medicinale o un contesto direttamente pertinente: "
    "la sintesi potra' verificare che manca la misura e astenersi "
    "citando il documento. "
    "Non selezionare gruppi totalmente estranei alla domanda."
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
    "Non limitarti al medicinale nel nome del PDF: se una nota cita "
    "ulteriori medicinali pertinenti, controlla separatamente nel suo testo "
    "se per ciascuno risulta il legame con l'indicazione e con la struttura. "
    "Non dedurre l'abilitazione dalla sola menzione di un altro medicinale. "
    "Se mancano dati, l'evidenza non e' completa o le fonti sono troncate, "
    "segnala chiaramente la parzialita' e non inventare. "
    "Per elenchi di note regionali, considera ogni scheda dell'indice "
    "documentale e verifica la pertinenza con le evidenze disponibili; "
    "non omettere note pertinenti solo perché il testo di alcune è lungo. "
    "Indica sempre anno, nome file e protocollo REGIONALE soltanto se "
    "documentato; non confondere il protocollo di una nota regionale "
    "con il numero della determina AIFA richiamata nel testo. "
    "I protocolli classificati come candidati richiedono verifica; "
    "non inventare date o completare date OCR illeggibili. "
    "Se la domanda richiede un dato su eventi realmente avvenuti, "
    "quantita' di pazienti, ricavi o date effettive, non desumerlo "
    "da un'autorizzazione, una previsione o un registro. "
    "Quando i documenti consultati non riportano il dato, rispondi "
    "esplicitamente che non e' documentato NELLE FONTI CONSULTATE; "
    "cita le note e le pagine pertinenti senza attribuire un valore "
    "zero o affermare che l'evento non sia mai avvenuto. "
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


def _normalize_regional_scope(sql, question):
    """Elimina un falso vincolo regionale sul percorso dei documenti.

    La tabella note è interamente regionale per costruzione dello snapshot.
    Un filtro sul percorso con LIKE '%Campania%' non verifica quindi
    l'appartenenza alla regione e può annullare risultati pertinenti.

    Si interviene SOLO se la domanda riguarda le note della Campania,
    non chiede esplicitamente percorsi/archivi, e il confronto letterale
    riguarda note.percorso_zip (anche con alias). SQL originale preservato,
    nessun retry o altra chiamata LLM. Le altre condizioni restano intatte.
    """
    lower_question = question.casefold()
    if ("campania" not in lower_question or
            not re.search(r"\bnot[ae]\b",lower_question) or
            re.search(r"\b(percorso|percorsi|archivio|archivi|zip)\b",
                      lower_question)):
        return sql, False

    from sqlglot import parse_one, exp
    tree = parse_one(sql, read="sqlite")
    note_aliases = {
        str(table.alias_or_name).casefold()
        for table in tree.find_all(exp.Table)
        if str(table.name).casefold() == "note"
    }
    if not note_aliases:
        return sql, False

    changed = False
    for predicate in list(tree.find_all(exp.Like)):
        field, pattern = predicate.this, predicate.expression
        if not isinstance(field, exp.Column) or not isinstance(pattern, exp.Literal):
            continue
        if (str(field.name).casefold() != "percorso_zip" or
                str(field.table).casefold() not in note_aliases or
                not pattern.is_string):
            continue
        if str(pattern.this).casefold() != "%campania%":
            continue
        predicate.replace(exp.Boolean(this=True))
        changed = True
    return (tree.sql(dialect="sqlite"), True) if changed else (sql, False)


_SPARSE_NOTE_ENRICHMENT_TABLES = frozenset({
    "nota_centro_documentato", "nota_metadati_revisionati",
    "nota_aifa_corrispondenze", "nota_struttura_aifa_corrispondenze",
    "nota_rimando_revisionato", "revisione_relazioni_manuale_v2",
    "revisione_collegamenti_aifa_v2",
})


def _normalize_sparse_note_enrichment(sql):
    """Non perdere note per INNER JOIN a relazioni revisionate incompletamente.

    Regola generale di schema, non dipendente da farmaci o domande:
    soltanto SELECT da note che restituiscono nota_id, JOIN di
    arricchimento con ON e nessun filtro sull'alias curato nel WHERE/HAVING.
    La JOIN rimane auditabile nello SQL originale e non vengono ricercate
    note aggiuntive né fatte chiamate LLM.
    """
    from sqlglot import parse_one, exp
    tree = parse_one(sql, read="sqlite")
    changed = False
    for select in tree.find_all(exp.Select):
        source = select.args.get("from_") or select.args.get("from")
        if not source or not isinstance(source.this, exp.Table):
            continue
        if str(source.this.name).casefold() != "note":
            continue
        has_note_id = any(
            str(getattr(item, "alias_or_name", "") or "").casefold() == "nota_id"
            for item in select.expressions
        )
        if not has_note_id:
            continue
        for join in select.args.get("joins") or []:
            target = join.this
            if not isinstance(target, exp.Table):
                continue
            if str(target.name).casefold() not in _SPARSE_NOTE_ENRICHMENT_TABLES:
                continue
            if (str(join.args.get("side") or "").upper() or
                    str(join.args.get("kind") or "").upper()):
                continue
            if join.args.get("on") is None:
                continue
            alias = str(target.alias_or_name).casefold()
            # Se la condizione WHERE/HAVING/QUALIFY filtra davvero su una
            # tabella revisionata, NON ampliamo i risultati implicitamente.
            filtered = False
            for restriction in ("where", "having", "qualify"):
                node = select.args.get(restriction)
                if node and any(
                    str(col.table).casefold() == alias
                    for col in node.find_all(exp.Column)
                ):
                    filtered = True
                    break
            if filtered:
                continue
            join.set("side", "LEFT")
            changed = True
    return (tree.sql(dialect="sqlite"), True) if changed else (sql, False)


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
            "SELECT id,nome_file,anno,protocollo_candidato,data_candidata,"
            "farmaco_candidato,indicazione_candidata,"
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
        prefix = ("Identificativo interno nota: " + note_id +
                  "; documento: " + str(notes["nome_file"]) +
                  "; anno archivio: " + str(notes.get("anno") or "n.d.") +
                  "; protocollo regionale candidato (NON verificato): " +
                  str(notes.get("protocollo_candidato") or "non estratto") +
                  "; data candidata (NON verificata): " +
                  str(notes.get("data_candidata") or "non estratta") +
                  "; farmaco candidato: " + str(notes.get("farmaco_candidato") or "") +
                  "; indicazione candidata da verificare: " +
                  str(notes.get("indicazione_candidata") or ""))
        rows.append({"chiave": "NOTA:" + note_id, "tipo": "REGIONE",
                     "testo": prefix + "\n" + "\n".join(answer_parts),
                     "testo_selezione": prefix + "\n" + "\n".join(selection_parts),
                     "fonte": sources[0] if sources else str(notes["percorso_zip"]),
                     "fonti": sources, "nota_id": note_id,
                     "nome_file": notes["nome_file"],
                     "anno": notes.get("anno"),
                     "protocollo_candidato": notes.get("protocollo_candidato"),
                     "data_candidata": notes.get("data_candidata")})
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


def _balanced_page_excerpt(raw, allowance):
    """Mantiene evidenze da OGNI pagina anche quando un PDF va abbreviato.

    Non stabilisce quali pagine siano clinicamente pertinenti: il testo
    resta fedele ai passaggi originali e ogni taglio e' segnalato.
    """
    raw = str(raw)
    if len(raw) <= allowance:
        return raw, False
    if allowance <= 0:
        return "", True
    parts = re.split(r"(?=\[pagina \d+\])", raw)
    marker = " [ESTRATTO TRONCATO]"
    if len(parts) < 2:
        keep = max(0, allowance - len(marker))
        return raw[:keep] + marker[:allowance-keep], True
    head = parts[0][:min(len(parts[0]), max(100, allowance//7))]
    pages = parts[1:]
    remaining = max(0, allowance - len(head) - len(pages)*len(marker))
    base = remaining // max(1,len(pages))
    more = remaining % max(1,len(pages))
    excerpts = [head]
    for idx,page in enumerate(pages):
        quota = base + (1 if idx < more else 0)
        if len(page) <= quota:
            excerpts.append(page)
            continue
        if quota < 20:
            excerpts.append(page[:quota])
        else:
            # Inizio e fine pagina, piu' contesto di una sezione generica
            # se presente. Non vengono inserite parole cliniche ad hoc.
            label = re.match(r"\[pagina \d+\]",page)
            label_text = label.group(0) if label else ""
            usable = max(0, quota - len(label_text) - 7)
            cue = re.search(
                r"indicazion\w*|prescri\w*|centri\b|centro\b",
                page[len(label_text):], re.I)
            main = page[:min(len(page),max(len(label_text)+30, quota//3))]
            if cue and usable > 90:
                start = len(label_text) + cue.start()
                middle = page[max(len(main),start-30):
                              max(len(main),start-30)+max(35,usable//3)]
            else:
                middle = ""
            tail_len = max(0, quota-len(main)-len(middle)-7)
            excerpts.append((main + " […] " + middle + page[-tail_len:]
                             if tail_len else main + " […] " + middle)[:quota])
    return ("".join(excerpts))[:allowance], True


def _balanced_answer_evidence(selected):
    """Distribuisce il contesto su tutte le evidenze scelte, non solo sulle prime.

    Il modello riceve un indice completo dei documenti ammessi nel budget.
    LOTUS resta l'unico filtro semantico: qui non si cercano sinonimi né
    si aggiungono o scartano note in base alla domanda.
    """
    eligible = list(selected[:MAX_ANSWER_DOCUMENTS])
    truncated = len(selected) > len(eligible)
    if not eligible:
        return [], truncated

    # Allocazione fair-share: i documenti brevi cedono il budget non usato
    # ai successivi. Un documento lungo non puo' oscurare gli altri.
    budget = MAX_ANSWER_CHARS
    chosen = []
    for index, item in enumerate(eligible):
        still_to_consider = len(eligible) - index
        allowance = max(0, budget // still_to_consider)
        raw = str(item["testo"])
        trimmed, clipped = _balanced_page_excerpt(raw, allowance)
        truncated = truncated or clipped
        budget -= len(trimmed)
        chosen.append({"chiave": item["chiave"],
                       "testo": trimmed,
                       "fonti": item.get("fonti") or [item["fonte"]]})
    return chosen, truncated


def _document_index(selected):
    """Indice delle note effettivamente selezionate, non prova di pertinenza."""
    return [{
        "nota_id": item["nota_id"],
        "nome_file": item.get("nome_file"),
        "anno_archivio": item.get("anno"),
        "protocollo_candidato_da_verificare": item.get("protocollo_candidato"),
        "data_candidata_da_verificare": item.get("data_candidata"),
        "fonte": item.get("fonte"),
    } for item in selected if item.get("nota_id") is not None]


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
    sql_with_name = _normalize_exact_name_comparisons(sql_originale_llm)
    sql_with_scope, scope_changed = _in_phase(
        "normalizzazione ambito regionale TAG automatico",
        _normalize_regional_scope, sql_with_name, question
    )
    sql_with_joins, note_join_changed = _in_phase(
        "normalizzazione JOIN documentali TAG automatico",
        _normalize_sparse_note_enrichment, sql_with_scope
    )
    sql_with_id, note_id_changed = _in_phase(
        "normalizzazione identificativo nota TAG automatico",
        normalize_document_note_id, sql_with_joins
    )
    sql_initial = _in_phase(
        "normalizzazione SQL TAG automatico", validate_sql, sql_with_id
    )
    records, sql_partial = _in_phase(
        "esecuzione SQL TAG automatico", _run_generated_select, db, sql_initial
    )
    initial_rows = len(records)
    sql, fallback_sql, fallback_reason = sql_initial, None, "non_necessario"
    sql_attempts = 1
    fallback_used = False
    # Le tabelle di centri candidati non costituiscono un indice esaustivo.
    # Se la SELECT li usa come unica fonte per elencare note relative a un
    # centro, preserviamo i risultati originali e ampliamo con il TESTO dei
    # PDF, senza liste manuali di malattie e senza ulteriori chiamate LLM.
    expansion, expansion_reason = _in_phase(
        "analisi copertura centri candidati TAG automatico",
        propose_partial_center_expansion, sql_initial, question
    )
    if not expansion:
        expansion, expansion_reason = _in_phase(
            "analisi copertura centro su pagine diverse TAG automatico",
            propose_partial_crosspage_center_expansion, sql_initial, question
        )
    if expansion:
        fallback_sql = _in_phase(
            "validazione SQL centri ampliati TAG automatico",
            validate_sql, expansion
        )
        sql_attempts = 2
        expanded_rows, expanded_partial = _in_phase(
            "esecuzione recupero progressivo centri TAG automatico",
            _run_generated_select, db, fallback_sql
        )
        old_ids = {str(row["nota_id"]) for row in records
                   if row.get("nota_id") is not None}
        new_ids = {str(row["nota_id"]) for row in expanded_rows
                   if row.get("nota_id") is not None}
        if new_ids - old_ids:
            records, sql_partial = expanded_rows, expanded_partial
            sql = fallback_sql
            fallback_reason = expansion_reason
            fallback_used = True
        else:
            fallback_reason = "nessun_nuovo_documento_da_centri"
    if not records and not expansion:
        suggestion, fallback_reason = _in_phase(
            "analisi recupero SQL vuoto TAG automatico",
            propose_empty_category_fallback, sql_initial, question
        )
        if not suggestion:
            suggestion, fallback_reason = _in_phase(
                "analisi categoria e centro su pagine distinte TAG automatico",
                propose_empty_crosspage_category_fallback,
                sql_initial, question
            )
        if not suggestion:
            suggestion, fallback_reason = _in_phase(
                "analisi categoria testuale senza join ai centri TAG automatico",
                propose_empty_note_page_semantic_fallback,
                sql_initial, question
            )
        if suggestion:
            fallback_sql = _in_phase(
                "validazione SQL recupero progressivo", validate_sql, suggestion
            )
            # Nessuna nuova generazione LLM: seconda SELECT sempre read-only.
            sql_attempts = 2
            fallback_rows, fallback_partial = _in_phase(
                "esecuzione recupero SQL progressivo TAG automatico",
                _run_generated_select, db, fallback_sql
            )
            if fallback_rows:
                records, sql_partial = fallback_rows, fallback_partial
                sql = fallback_sql
                fallback_used = True
            else:
                fallback_reason = "fallback_senza_risultati"
    # Rete di sicurezza architetturale quando la SQL inventa filtri e le
    # regole AST non riescono a riconoscere un recupero documentale valido.
    # L'LLM formula solo un PIANO tipizzato; la SELECT e' costruita in Python.
    # In una domanda con altri vincoli oggettivi (anno, protocollo, farmaco
    # specifico, stato esplicitamente richiesto) il piano viene rifiutato.
    plan_used = False
    plan_center = None
    plan_reason = "non_necessario"
    plan_llm_calls = 0
    if not fallback_used and not expansion:
        anchors = _in_phase(
            "individuazione ancore documentali piano TAG automatico",
            document_center_anchors, sql_initial, question
        )
        if anchors:
            plan_text, plan_usage = _in_phase(
                "pianificazione strutturata recupero TAG automatico",
                ask, model, PLAN_PROMPT,
                {"domanda": question, "centri_candidati_sql": anchors,
                 "sql_generato": sql_initial}
            )
            generation_usage = _accumulate(generation_usage, plan_usage)
            plan_llm_calls = 1
            plan, plan_reason = _in_phase(
                "validazione piano documentale TAG automatico",
                validated_document_plan, plan_text, anchors, question
            )
            if plan:
                plan_center = plan["centro"]
                document_sql = _in_phase(
                    "compilazione SQL piano documentale TAG automatico",
                    sql_from_document_plan, plan
                )
                document_sql = _in_phase(
                    "validazione SELECT piano documentale TAG automatico",
                    validate_sql, document_sql
                )
                # Solo due SELECT in totale: quella dell'LLM e la forma
                # verificata su note/pagine. Non modifica lo snapshot.
                sql_attempts = 2
                plan_rows, plan_partial = _in_phase(
                    "esecuzione piano documentale TAG automatico",
                    _run_generated_select, db, document_sql
                )
                old_ids = {str(row["nota_id"]) for row in records
                           if row.get("nota_id") is not None}
                new_ids = {str(row["nota_id"]) for row in plan_rows
                           if row.get("nota_id") is not None}
                if plan_rows and (not records or old_ids <= new_ids):
                    records, sql_partial = plan_rows, plan_partial
                    sql, fallback_sql = document_sql, document_sql
                    fallback_reason = "piano_strutturato_centro_e_categoria"
                    fallback_used = True
                    plan_used = True
                else:
                    plan_reason = ("nessun_documento_nel_piano"
                                   if not plan_rows else
                                   "piano_non_contiene_candidati_originali")
    base = {"sql":sql, "sql_originale_llm":sql_originale_llm,
            "sql_primo_tentativo":sql_initial,
            "sql_fallback":fallback_sql,
            "recupero_progressivo_usato":fallback_used,
            "motivo_recupero_progressivo":fallback_reason,
            "piano_documentale_usato":plan_used,
            "piano_documentale_centro":plan_center,
            "piano_documentale_esito":plan_reason,
            "chiamate_piano_documentale":plan_llm_calls,
            "righe_sql_primo_tentativo":initial_rows,
            "sql_normalizzato_nota_id":note_id_changed,
            "sql_normalizzato_nome":sql_with_name != sql_originale_llm,
            "sql_normalizzato_ambito_regione":scope_changed,
            "sql_normalizzato_join_documentali":note_join_changed,
            "tag_auto_revision":TAG_AUTO_REVISION,
            "versione_tag":"automatico-v1",
            "recupero":"LLM-SQL-progressivo" if fallback_used else "LLM-SQL",
            "sql_tentativi":sql_attempts, "righe_sql":len(records)}
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
    refinement_used = False
    refinement_uncertain = False
    refinement_skipped_reason = ""
    refinement_pool_count = 0
    refinement_batch_count = 0
    refinement_batch_completed = 0
    refinement_batch_invalid = 0
    refinement_batch_calls = 0
    direct_usage = generation_usage
    # LOTUS considera gruppi eterogenei e NON prova la pertinenza di ogni
    # singolo documento. Nei recuperi ampi esaminiamo TUTTI i candidati
    # in piccoli lotti senza escludere i gruppi non scelti da LOTUS.
    if (len(candidates) >= MIN_DOCS_FOR_REFINEMENT
            and all(item.get("nota_id") is not None for item in candidates)):
        pool = preserve_category_recall(candidates, selected)
        refinement_pool_count = len(pool)
        chunks = _in_phase(
            "organizzazione lotti documentali TAG automatico",
            refinement_batches, pool
        )
        refinement_batch_count = len(chunks)
        accepted = set()
        refinement_used = True
        for start, documents in chunks:
            payload, why = _in_phase(
                "preparazione lotto documentale TAG automatico",
                refinement_payload, documents, question,
                len(documents), start
            )
            if payload is None:
                refinement_batch_invalid += 1
                refinement_uncertain = True
                refinement_skipped_reason = why
                continue
            response, usage = _in_phase(
                "raffinamento lotto documentale TAG automatico",
                ask, model, REFINEMENT_PROMPT, payload,
                timeout=75, max_tokens=1400
            )
            refinement_batch_calls += 1
            direct_usage = _accumulate(direct_usage, usage)
            try:
                indices, uncertain = parse_refinement_result(
                    response, len(documents), len(documents)
                )
            except ValueError:
                # Il lotto non verificabile NON autorizza a scartare come
                # irrilevanti le sue note. Segnaliamo esplicitamente
                # omissioni potenziali e conserviamo gli altri lotti validi.
                refinement_batch_invalid += 1
                refinement_uncertain = True
                refinement_skipped_reason = "risposta_json_lotto_non_valida"
                continue
            refinement_batch_completed += 1
            refinement_uncertain |= uncertain
            accepted.update(start + index for index in indices)
        # Ordine stabile nell'indice originale; deduplica sempre per nota.
        selected = [pool[index] for index in sorted(accepted)]
        if refinement_batch_invalid == 0:
            refinement_skipped_reason = "nessuno"
    prior_usage = direct_usage
    if not selected:
        # Mantieni la diagnostica storica se e' stato LOTUS a non
        # selezionare alcun gruppo (senza raffinamento successivo).
        missing_message = (
            "LOTUS non ha selezionato evidenze fra i candidati. "
            "Questo non dimostra che l'informazione sia assente."
            if not refinement_used else
            "Il raffinamento delle note non ha selezionato evidenze "
            "sufficientemente pertinenti. Questo non dimostra "
            "l'assenza delle informazioni."
        )
        return {
            **base,
            "risposta":missing_message,
            "fonti":[], "stato":"NESSUNA_SELEZIONE_SEMANTICA",
            "raffinamento_documentale_usato":refinement_used,
            "documenti_candidati_raffinamento":refinement_pool_count,
            "lotti_raffinamento":refinement_batch_count,
            "lotti_raffinamento_completati":refinement_batch_completed,
            "lotti_raffinamento_non_validi":refinement_batch_invalid,
            "righe_recuperate":len(candidates),
            "righe_sem_filter":len(planned),
            "righe_selezionate_lotus":len(selected_groups),
            **prior_usage
        }

    chosen, truncated_answer = _balanced_answer_evidence(selected)
    index_notes = _document_index(selected[:MAX_ANSWER_DOCUMENTS])
    # La selezione semantica per nota richiede una verifica indipendente.
    partial = (sql_partial or page_partial or truncated_answer
               or refinement_used or refinement_uncertain
               or bool(refinement_skipped_reason
                   and refinement_skipped_reason not in ("nessuno", "")))
    answer_prompt = (ANSWER_PROMPT if any(
        item.get("nota_id") is not None for item in candidates
    ) else TABULAR_ANSWER_PROMPT)
    answer, answer_usage = _in_phase(
        "sintesi TAG automatico", ask, model, answer_prompt,
        {"domanda":question,"evidenze":chosen,"indice_documentale":index_notes,
         "risultati_parziali":partial},
        timeout=65, max_tokens=2400
    )
    if sql_partial or page_partial or len(selected)>MAX_ANSWER_DOCUMENTS:
        answer += ("\n\nAvvertenza: recupero di note o pagine non completo; "
                   "l'elenco non e' garantito esaustivo.")
    elif truncated_answer:
        answer += ("\n\nAvvertenza: alcuni testi di pagina sono abbreviati "
                   "per limiti di contesto; verificare i dettagli sui documenti originali.")
    if refinement_used:
        answer += ("\n\nAvvertenza: la selezione dei singoli documenti "
                   "e' stata effettuata semanticamente dall'LLM; "
                   "la completezza richiede validazione indipendente.")
    if refinement_batch_invalid:
        answer += ("\n\nAvvertenza: "+str(refinement_batch_invalid)+
                   " lotto/i di documenti non hanno superato la verifica "
                   "della selezione. Alcune note potrebbero mancare.")
    if refinement_uncertain:
        answer += ("\n\nAvvertenza: il raffinamento documentale ha "
                   "segnalato incertezza sulla pertinenza; "
                   "verificare i documenti originali.")
    if refinement_skipped_reason not in ("", "nessuno"):
        answer += ("\n\nAvvertenza: raffinamento documentale non eseguito; "
                   "l'elenco non e' garantito esaustivo.")
    sources = list(dict.fromkeys(src for item in chosen for src in item["fonti"]))
    return {**base, "risposta":answer, "fonti":sources[:80],
            "evidenze_fonti":_source_previews(selected),
            "note_nell_indice":len(index_notes),
            "note_nel_contesto":sum(1 for r in chosen if r["chiave"].startswith("NOTA:")),
            "stato":"RISULTATI_PARZIALI" if partial else "OK",
            "risultato_parziale":partial,
            "righe_recuperate":len(candidates),"righe_sem_filter":len(planned),
            "righe_selezionate_lotus":len(selected_groups),
            "modalita_selezione":"gruppi neutri + singole note"
                if refinement_used else "gruppi neutri",
            "raffinamento_documentale_usato":refinement_used,
            "raffinamento_documentale_incerto":refinement_uncertain,
            "raffinamento_documentale_non_eseguito":refinement_skipped_reason,
            "documenti_candidati_raffinamento":refinement_pool_count,
            "documenti_selezionati_raffinamento":len(selected)
                if refinement_used else None,
            "lotti_raffinamento":refinement_batch_count,
            "lotti_raffinamento_completati":refinement_batch_completed,
            "lotti_raffinamento_non_validi":refinement_batch_invalid,
            "chiamate_dirette_raffinamento":refinement_batch_calls,
            "chiamate_llm_stimate":len(planned)+2+refinement_batch_calls,
            **_accumulate(prior_usage,answer_usage)}


# La misurazione delle chiamate usa lo stesso contatore degli altri motori.
automatic_tag = measured_engine(automatic_tag)
