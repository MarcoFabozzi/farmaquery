"""Recupero progressivo SQL per TAG automatico, senza dizionari clinici.

Il fallback è deliberatamente conservativo: si attiva SOLO dopo zero righe
e SOLO per la forma documentale riconoscibile "centro in tabella curata"
AND "(termine in pagina OR termine in indicazione candidata)".
Non interpreta il significato di una patologia: conserva il riferimento
oggettivo alla struttura, e lascia la classificazione a LOTUS.
"""
from __future__ import annotations

import re

from sqlglot import exp, parse_one


def _unbox(node):
    """Rimuove parentesi e COLLATE prima di controllare un predicato."""
    while isinstance(node, (exp.Paren, exp.Collate)):
        node = node.this
    return node


def _from_note_with_pages(tree):
    """Restituisce alias di note, pagine e centri (solo SELECT semplice)."""
    if not isinstance(tree, exp.Select):
        return None
    if any(tree.args.get(key) is not None for key in (
            "with_", "group", "having", "qualify", "limit", "offset",
            "order", "windows", "connect", "intersect", "except")):
        return None
    if any(True for _ in tree.find_all(exp.Subquery)):
        return None
    source = tree.args.get("from_") or tree.args.get("from")
    if not source or not isinstance(source.this, exp.Table):
        return None
    if str(source.this.name).casefold() != "note":
        return None
    names = {"note": str(source.this.alias_or_name).casefold()}
    allowed = {"pagine", "nota_centro_documentato"}
    joins = tree.args.get("joins") or []
    if not joins:
        return None
    for join in joins:
        if not isinstance(join.this, exp.Table):
            return None
        name = str(join.this.name).casefold()
        if name not in allowed or name in names:
            return None
        names[name] = str(join.this.alias_or_name).casefold()
    if "pagine" not in names:
        return None
    return names


def _like(node):
    """Restituisce (alias, colonna, pattern) per un LIKE letterale."""
    node = _unbox(node)
    if not isinstance(node, exp.Like):
        return None
    column = _unbox(node.this)
    literal = _unbox(node.expression)
    if (not isinstance(column, exp.Column) or
            not isinstance(literal, exp.Literal) or not literal.is_string):
        return None
    return (str(column.table).casefold(), str(column.name).casefold(),
            str(literal.this))


def _and_clauses(node):
    node = _unbox(node)
    if isinstance(node, exp.And):
        return _and_clauses(node.this) + _and_clauses(node.expression)
    return [node]


def _is_clinical_like_pair(node, aliases):
    """Forma sintattica esplicita: (testo LIKE x OR indicazione LIKE x)."""
    node = _unbox(node)
    if not isinstance(node, exp.Or):
        return False
    left, right = _like(node.this), _like(node.expression)
    if left is None or right is None:
        return False
    page = (aliases["pagine"], "testo")
    indication = (aliases["note"], "indicazione_candidata")
    return (
        {left[:2], right[:2]} == {page, indication}
        and left[2].casefold() == right[2].casefold()
        and left[2].startswith("%") and left[2].endswith("%")
        and len(left[2].strip("%")) >= 4
    )


def normalize_document_note_id(sql):
    """Riconosce note.id come identificativo documentale, senza cambiare righe.

    Le note possono essere selezionate anche tramite centri_candidati, senza
    JOIN pagine. In quel caso la vecchia regola non riconosceva documento_id:
    LOTUS riceveva solo righe tabellari anziché i PDF. Verifichiamo che la
    proiezione sia proprio l'ID della tabella note (non un ID omonimo di altre
    tabelle). Non tocchiamo UNION, CTE o query annidate.
    """
    tree = parse_one(sql, read="sqlite")
    if not isinstance(tree, exp.Select):
        return sql, False
    if tree.args.get("with_") or any(tree.find_all(exp.Subquery)):
        return sql, False
    source = tree.args.get("from_") or tree.args.get("from")
    if not source or not isinstance(source.this, exp.Table):
        return sql, False
    if str(source.this.name).casefold() != "note":
        return sql, False
    alias = str(source.this.alias_or_name).casefold()
    if any(str(item.alias_or_name).casefold() == "nota_id"
           for item in tree.expressions):
        return sql, False
    for item in tree.expressions:
        if (isinstance(item, exp.Alias)
                and str(item.alias).casefold() == "documento_id"
                and isinstance(item.this, exp.Column)
                and str(item.this.name).casefold() == "id"
                and str(item.this.table).casefold() == alias):
            item.set("alias", exp.to_identifier("nota_id"))
            return tree.sql(dialect="sqlite"), True
    return sql, False


def propose_empty_category_fallback(sql, question):
    """Proponi SQL ampliato soltanto per due vincoli riconoscibili e sicuri.

    Nessuna modifica ad altri vincoli, UNION, sottoquery o SELECT tabellari.
    Poiché è presente una JOIN alla tabella dei centri revisionati, il
    recupero ampliato cerca la medesima stringa nel testo di TUTTE le note.
    La menzione non prova autorizzazione: LOTUS e sintesi verificano le pagine.
    """
    tree = parse_one(sql, read="sqlite")
    aliases = _from_note_with_pages(tree)
    if not aliases or "nota_centro_documentato" not in aliases:
        return None, "struttura_sql_non_supportata"
    where = tree.args.get("where")
    if where is None:
        return None, "nessun_filtro"
    clauses = _and_clauses(where.this)
    if len(clauses) != 2:
        return None, "filtri_aggiuntivi_non_rimuovibili"
    center = None
    clinical = False
    for clause in clauses:
        candidate = _like(clause)
        if (candidate and candidate[:2] ==
                (aliases["nota_centro_documentato"], "centro")):
            if center is not None:
                return None, "piu_centri"
            center = candidate[2]
        elif _is_clinical_like_pair(clause, aliases):
            clinical = True
        else:
            return None, "predicato_non_riconosciuto"

    if not center or not clinical:
        return None, "ancora_oggettiva_o_categoria_mancante"
    if not (center.startswith("%") and center.endswith("%")):
        return None, "confronto_centro_non_generico"
    core = center[1:-1]
    if (len(core.strip()) < 4 or "%" in core or "_" in core
            or core.casefold() not in question.casefold()):
        return None, "centro_non_verificabile_nella_domanda"

    # L'ancora testuale viene riportata SENZA ALTERARE il pattern SQL originale.
    # String literal SQLGlot (escaping incluso), non interpolazione di input.
    literal = exp.Literal.string(center).sql(dialect="sqlite")
    candidate_sql = (
        "SELECT DISTINCT n.id AS nota_id FROM note AS n "
        "JOIN pagine AS p ON p.nota_id = n.id "
        "WHERE p.testo LIKE " + literal + " COLLATE NOCASE"
    )
    return candidate_sql, "categoria_semantica_da_valutare_con_lotus"


def _column_is(node, table, name):
    node = _unbox(node)
    return (isinstance(node, exp.Column)
            and str(node.table).casefold() == table
            and str(node.name).casefold() == name)


def _weak_candidate_status(node, alias):
    """Accetta solo la guardia (stato IS NULL OR stato NOT IN esclusi).

    Altri stati, inclusi filtri di autorizzazione esplicita, non vengono
    mai rilassati. I due valori rappresentano flag della tabella candidata,
    NON classi di farmaci o dizionari di patologie.
    """
    node = _unbox(node)
    if not isinstance(node, exp.Or):
        return False

    def is_unreviewed(part):
        part = _unbox(part)
        return (isinstance(part, exp.Is) and
                _column_is(part.this, alias, "stato") and
                isinstance(_unbox(part.expression), exp.Null))

    def is_not_rejected(part):
        part = _unbox(part)
        if not isinstance(part, exp.Not):
            return False
        inner = _unbox(part.this)
        if not isinstance(inner, exp.In):
            return False
        if not _column_is(inner.this, alias, "stato"):
            return False
        values = inner.expressions
        return (len(values) == 2 and
                all(isinstance(v, exp.Literal) and v.is_string for v in values)
                and {str(v.this).casefold() for v in values} ==
                    {"escluso", "falso"})

    return ((is_unreviewed(node.this) and is_not_rejected(node.expression))
            or (is_unreviewed(node.expression) and is_not_rejected(node.this)))


def propose_partial_center_expansion(sql, question):
    """Amplia una SELECT su centri_candidati senza perdere i risultati originali.

    SOLO pattern documentale non aggregato con join chiave nota-id e filtri:
    menzione del centro + stato non escluso/non revisionato. Il singolo token
    usato per il recall deriva dalla stringa di centro dell'LLM, verificata
    anche nella domanda, mai da sinonimi clinici scritti dal programmatore.
    UNION conserva tutte le note del primo recupero; la seconda SELECT legge
    pagine nel loro contesto e LOTUS verifica indicazioni e autorizzazioni.
    """
    tree = parse_one(sql, read="sqlite")
    if not isinstance(tree, exp.Select):
        return None, "non_select_documentale"
    if (tree.args.get("with_") or tree.args.get("group") or
            tree.args.get("having") or tree.args.get("limit") or
            tree.args.get("order") or tree.args.get("qualify") or
            any(tree.find_all(exp.Subquery))):
        return None, "select_complessa"
    source = tree.args.get("from_") or tree.args.get("from")
    if not source or not isinstance(source.this, exp.Table):
        return None, "nessuna_nota"
    if str(source.this.name).casefold() != "note":
        return None, "nessuna_nota"
    note_alias = str(source.this.alias_or_name).casefold()
    joins = tree.args.get("joins") or []
    if len(joins) != 1 or not isinstance(joins[0].this, exp.Table):
        return None, "join_non_riconosciute"
    if str(joins[0].this.name).casefold() != "centri_candidati":
        return None, "fonte_centro_non_candidata"
    c_alias = str(joins[0].this.alias_or_name).casefold()
    on = _unbox(joins[0].args.get("on"))
    if not isinstance(on, exp.EQ):
        return None, "join_chiave_non_verificata"
    pair = {
        (note_alias, "id"), (c_alias, "nota_id")
    }
    if not (isinstance(_unbox(on.this), exp.Column) and
            isinstance(_unbox(on.expression), exp.Column) and
            {(str(_unbox(on.this).table).casefold(),
              str(_unbox(on.this).name).casefold()),
             (str(_unbox(on.expression).table).casefold(),
              str(_unbox(on.expression).name).casefold())} == pair):
        return None, "join_chiave_non_verificata"
    where = tree.args.get("where")
    if where is None:
        return None, "nessun_filtro"
    clauses = _and_clauses(where.this)
    if len(clauses) != 2:
        return None, "vincoli_extra_non_ampliabili"
    mentioned = None
    weak_status = False
    for clause in clauses:
        pred = _like(clause)
        if pred and pred[:2] == (c_alias, "menzione"):
            mentioned = pred[2]
        elif _weak_candidate_status(clause, c_alias):
            weak_status = True
        else:
            return None, "vincoli_extra_non_ampliabili"
    if not (mentioned and weak_status and
            mentioned.startswith("%") and mentioned.endswith("%")):
        return None, "centro_o_stato_non_riconosciuto"
    label = mentioned[1:-1]
    if (not label or "%" in label or "_" in label or
            label.casefold() not in question.casefold()):
        return None, "denominazione_centro_non_verificata"
    tokens = re.findall(r"[^\W\d_]{5,}", label, flags=re.UNICODE)
    if not tokens:
        return None, "nessun_token_discriminante"
    token = sorted(tokens, key=lambda x: (-len(x), x.casefold()))[0]
    # Preserva le condizioni originali per tutti i documenti già recuperabili.
    original = tree.copy()
    original.set(
        "expressions",
        [exp.alias_(exp.column("id", table=note_alias), "nota_id")]
    )
    original.set("distinct", exp.Distinct())
    # String literal SQLGlot: niente interpolazione non protetta.
    token_literal = exp.Literal.string("%" + token + "%").sql(dialect="sqlite")
    broad = (
        "SELECT DISTINCT n.id AS nota_id FROM note AS n "
        "JOIN pagine AS p ON p.nota_id=n.id "
        "WHERE p.testo LIKE " + token_literal + " COLLATE NOCASE"
    )
    return original.sql(dialect="sqlite") + " UNION " + broad, (
        "ampliamento_centro_documentale_senza_classificazione_clinica"
    )


def _eq_columns(node):
    """Restituisce la coppia non ordinata di colonne di un'uguaglianza."""
    node = _unbox(node)
    if not isinstance(node, exp.EQ):
        return None
    left, right = _unbox(node.this), _unbox(node.expression)
    if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
        return None
    return frozenset({
        (str(left.table).casefold(), str(left.name).casefold()),
        (str(right.table).casefold(), str(right.name).casefold()),
    })


def propose_empty_crosspage_category_fallback(sql, question):
    """Fallback generico per categoria semantica cercata sulla STESSA pagina.

    Si usa solo se la prima SELECT non trova righe e la forma SQL è nota:
    note -> pagine -> centri_candidati, vincolo ospedaliero LIKE
    diretto oppure OR su menzione/testo e filtro di categoria OR. Richiede esplicitamente le tre
    relazioni di chiave e non rimuove mai altri vincoli. Recupera come
    candidati le note che contengono un termine della denominazione del
    centro, lasciando a LOTUS la lettura completa delle pagine e
    la valutazione del significato clinico. Nessun dizionario di patologie.
    """
    tree = parse_one(sql, read="sqlite")
    if not isinstance(tree, exp.Select):
        return None, "selezione_non_semplice"
    if any(tree.args.get(k) is not None for k in (
            "with_", "group", "having", "qualify", "limit", "offset",
            "order", "windows")) or any(tree.find_all(exp.Subquery)):
        return None, "selezione_aggregata_o_limitata"
    source = tree.args.get("from_") or tree.args.get("from")
    if not source or not isinstance(source.this, exp.Table):
        return None, "nessuna_tabella_note"
    if str(source.this.name).casefold() != "note":
        return None, "nessuna_tabella_note"
    n = str(source.this.alias_or_name).casefold()
    joins = tree.args.get("joins") or []
    if len(joins) != 2:
        return None, "join_non_riconosciute"
    if any(not isinstance(j.this, exp.Table) or
           j.args.get("side") or j.args.get("kind") for j in joins):
        return None, "join_non_interne"
    if ([str(j.this.name).casefold() for j in joins] !=
            ["pagine", "centri_candidati"]):
        return None, "join_sorgenti_non_riconosciute"
    p = str(joins[0].this.alias_or_name).casefold()
    c = str(joins[1].this.alias_or_name).casefold()
    key_note = frozenset({(n, "id"), (p, "nota_id")})
    key_center = frozenset({(p, "nota_id"), (c, "nota_id")})
    key_page = frozenset({(p, "numero_pagina"), (c, "numero_pagina")})
    if _eq_columns(joins[0].args.get("on")) != key_note:
        return None, "relazione_nota_pagine_non_verificata"
    center_joins = _and_clauses(joins[1].args.get("on"))
    if len(center_joins) != 2 or {
            _eq_columns(j) for j in center_joins} != {key_center, key_page}:
        return None, "relazione_pagina_centro_non_verificata"
    where = tree.args.get("where")
    if where is None:
        return None, "nessun_filtro"
    clauses = _and_clauses(where.this)
    if len(clauses) != 2:
        return None, "vincoli_aggiuntivi_non_rimovibili"
    center_pattern = None
    category_pattern = None
    for clause in clauses:
        clause = _unbox(clause)
        # L'LLM puo' ancorare il centro con una sola menzione indicizzata,
        # senza OR sul testo della pagina. Si tratta sempre dello stesso
        # vincolo OGGETTIVO, non di una nuova tassonomia clinica.
        simple_center = _like(clause)
        if simple_center is not None:
            if (simple_center[:2] not in
                    {(c, "menzione"), (p, "testo")}
                    or center_pattern is not None):
                return None, "filtro_centro_semplice_non_supportato"
            center_pattern = simple_center[2]
            continue
        if not isinstance(clause, exp.Or):
            return None, "assenza_coppia_semantica"
        first, second = _like(clause.this), _like(clause.expression)
        if not first or not second or first[2].casefold() != second[2].casefold():
            return None, "pattern_distinti"
        pair = {first[:2], second[:2]}
        if pair == {(c, "menzione"), (p, "testo")}:
            if center_pattern is not None:
                return None, "centro_duplicato"
            center_pattern = first[2]
        elif pair == {(n, "indicazione_candidata"), (p, "testo")}:
            if category_pattern is not None:
                return None, "categoria_duplicata"
            category_pattern = first[2]
        else:
            return None, "filtro_non_supportato"
    if not center_pattern or not category_pattern:
        return None, "centro_o_categoria_mancante"
    if not (center_pattern.startswith("%") and center_pattern.endswith("%")
            and category_pattern.startswith("%") and category_pattern.endswith("%")):
        return None, "ricerca_non_generica"
    label = center_pattern[1:-1]
    category = category_pattern[1:-1]
    if not (len(label.strip()) >= 5 and len(category.strip()) >= 4
            and "%" not in label and "_" not in label
            and "%" not in category and "_" not in category
            and label.casefold() in question.casefold()
            and category.casefold() in question.casefold()):
        return None, "vincoli_non_verificabili_nella_domanda"
    words = re.findall(r"[^\W\d_]{5,}", label, flags=re.UNICODE)
    if not words:
        return None, "denominazione_centro_troppo_breve"
    token = sorted(words, key=lambda word: (-len(word), word.casefold()))[0]
    literal = exp.Literal.string("%" + token + "%").sql(dialect="sqlite")
    # Solo candidati: la presenza del centro NON equivale ad autorizzazione.
    broad = (
        "SELECT DISTINCT n.id AS nota_id FROM note AS n "
        "JOIN pagine AS p ON p.nota_id = n.id "
        "WHERE p.testo LIKE " + literal + " COLLATE NOCASE"
    )
    return broad, "categoria_clinica_e_join_stessa_pagina_ampliati"


def propose_partial_crosspage_center_expansion(sql, question):
    """Recall documentale per query note-pagine-centri_candidati non vuota.

    Se il centro viene richiesto con una JOIN sulla STESSA pagina, aggiunge
    note che lo menzionano su altre pagine senza filtri clinici. I risultati
    originali restano inclusi mediante UNION. Non attribuisce autorizzazioni
    né usa elenchi di medicinali, patologie o strutture.
    """
    tree = parse_one(sql, read="sqlite")
    if not isinstance(tree, exp.Select):
        return None, "selezione_non_semplice"
    if any(tree.args.get(k) is not None for k in (
            "with_", "group", "having", "qualify", "limit", "offset",
            "order", "windows")) or any(tree.find_all(exp.Subquery)):
        return None, "selezione_aggregata_o_limitata"
    source = tree.args.get("from_") or tree.args.get("from")
    if not source or not isinstance(source.this, exp.Table):
        return None, "nessuna_tabella_note"
    if str(source.this.name).casefold() != "note":
        return None, "nessuna_tabella_note"
    n = str(source.this.alias_or_name).casefold()
    joins = tree.args.get("joins") or []
    if len(joins) != 2:
        return None, "join_non_riconosciute"
    if any(not isinstance(j.this, exp.Table) or
           j.args.get("side") or j.args.get("kind") for j in joins):
        return None, "join_non_interne"
    if ([str(j.this.name).casefold() for j in joins] !=
            ["pagine", "centri_candidati"]):
        return None, "join_sorgenti_non_riconosciute"
    p = str(joins[0].this.alias_or_name).casefold()
    c = str(joins[1].this.alias_or_name).casefold()
    if _eq_columns(joins[0].args.get("on")) != frozenset({
            (n, "id"), (p, "nota_id")}):
        return None, "relazione_nota_pagine_non_verificata"
    expected = {
        frozenset({(p, "nota_id"), (c, "nota_id")}),
        frozenset({(p, "numero_pagina"), (c, "numero_pagina")})
    }
    jc = _and_clauses(joins[1].args.get("on"))
    if len(jc) != 2 or {_eq_columns(j) for j in jc} != expected:
        return None, "relazione_pagina_centro_non_verificata"
    where = tree.args.get("where")
    if where is None:
        return None, "nessun_filtro"
    center_clause = _unbox(where.this)
    if not isinstance(center_clause, exp.Or):
        return None, "filtro_aggiuntivo_o_non_supportato"
    first, second = _like(center_clause.this), _like(center_clause.expression)
    if not first or not second or first[2].casefold() != second[2].casefold():
        return None, "valori_centro_non_uguali"
    if {first[:2], second[:2]} != {(c, "menzione"), (p, "testo")}:
        return None, "filtro_centro_non_riconosciuto"
    pattern = first[2]
    if not (pattern.startswith("%") and pattern.endswith("%")):
        return None, "ricerca_non_generica"
    label = pattern[1:-1]
    if (len(label.strip()) < 5 or "%" in label or "_" in label
            or label.casefold() not in question.casefold()):
        return None, "centro_non_richiesto_nella_domanda"
    words = re.findall(r"[^\W\d_]{5,}", label, flags=re.UNICODE)
    if not words:
        return None, "centro_senza_token_significativo"
    token = sorted(words, key=lambda w: (-len(w),w.casefold()))[0]
    original = tree.copy()
    original.set("expressions", [
        exp.alias_(exp.column("id", table=n), "nota_id")
    ])
    original.set("distinct",exp.Distinct())
    literal = exp.Literal.string("%"+token+"%").sql(dialect="sqlite")
    broad = (
        "SELECT DISTINCT n.id AS nota_id FROM note AS n "
        "JOIN pagine AS p ON p.nota_id=n.id "
        "WHERE p.testo LIKE "+literal+" COLLATE NOCASE"
    )
    return original.sql(dialect="sqlite")+" UNION "+broad, (
        "recupero_centro_tra_pagine_documentali"
    )


def propose_empty_note_page_semantic_fallback(sql, question):
    """Fallback per SELECT documentale note JOIN pagine, senza tabelle curate.

    Se due soli predicati sono riconoscibili come:
      (1) denominazione del centro in pagine.testo;
      (2) categoria semantica in (pagine.testo OR note.indicazione_candidata),
    l'LLM ha chiesto la presenza letterale di una categoria clinica sulla
    stessa pagina. Dopo zero righe, recuperiamo invece TUTTE le note che
    menzionano il centro, da sottoporre al TAG/LOTUS. Nessun lessico clinico
    manuale, nessuna modifica alle note o ai vincoli extra.
    """
    tree = parse_one(sql, read="sqlite")
    if not isinstance(tree, exp.Select):
        return None, "query_non_select_semplice"
    if any(tree.args.get(k) is not None for k in (
            "with_", "group", "having", "qualify", "limit", "offset",
            "order", "windows", "connect", "intersect", "except")):
        return None, "query_aggregata_o_limitata"
    if any(tree.find_all(exp.Subquery)):
        return None, "sottoquery_non_ammesse"
    source = tree.args.get("from_") or tree.args.get("from")
    if not source or not isinstance(source.this, exp.Table):
        return None, "tabella_iniziale_mancante"
    if str(source.this.name).casefold() != "note":
        return None, "fonte_non_documentale"
    n = str(source.this.alias_or_name).casefold()
    joins = tree.args.get("joins") or []
    if len(joins) != 1:
        return None, "numero_join_non_supportato"
    join = joins[0]
    if (not isinstance(join.this, exp.Table)
            or str(join.this.name).casefold() != "pagine"
            or join.args.get("side") or join.args.get("kind")):
        return None, "join_pagine_non_interna"
    p = str(join.this.alias_or_name).casefold()
    if _eq_columns(join.args.get("on")) != frozenset({
            (n, "id"), (p, "nota_id")}):
        return None, "join_documentale_non_verificata"
    where = tree.args.get("where")
    if where is None:
        return None, "vincoli_assenti"
    clauses = _and_clauses(where.this)
    if len(clauses) != 2:
        return None, "vincoli_aggiuntivi_non_rimovibili"
    center_pattern = None
    category_pattern = None
    for clause in clauses:
        node = _unbox(clause)
        exact = _like(node)
        if exact is not None:
            if exact[:2] != (p, "testo") or center_pattern is not None:
                return None, "ancora_centro_non_riconosciuta"
            center_pattern = exact[2]
            continue
        if not isinstance(node, exp.Or):
            return None, "categoria_semantica_non_riconosciuta"
        left, right = _like(node.this), _like(node.expression)
        if left is None or right is None:
            return None, "predicati_categoria_non_letterali"
        if (left[2].casefold() != right[2].casefold()
                or {left[:2], right[:2]} != {
                    (p, "testo"), (n, "indicazione_candidata")}
                or category_pattern is not None):
            return None, "categoria_non_equivalente"
        category_pattern = left[2]
    if not center_pattern or not category_pattern:
        return None, "centro_o_categoria_mancanti"
    if not all(v.startswith("%") and v.endswith("%")
               for v in (center_pattern, category_pattern)):
        return None, "pattern_like_non_supportati"
    center, category = center_pattern[1:-1], category_pattern[1:-1]
    if (len(center.strip()) < 5 or len(category.strip()) < 4
            or any(ch in center+category for ch in ("%","_"))
            or center.casefold() not in question.casefold()
            or category.casefold() not in question.casefold()):
        return None, "termini_non_presenti_nella_domanda"
    tokens = re.findall(r"[^\W\d_]{5,}", center, re.UNICODE)
    if not tokens:
        return None, "centro_senza_token_utile"
    token = sorted(tokens, key=lambda w: (-len(w), w.casefold()))[0]
    literal = exp.Literal.string("%"+token+"%").sql(dialect="sqlite")
    candidate_sql = (
        "SELECT DISTINCT n.id AS nota_id FROM note AS n "
        "JOIN pagine AS p ON p.nota_id = n.id "
        "WHERE p.testo LIKE " + literal + " COLLATE NOCASE"
    )
    return candidate_sql, "categoria_clinica_letterale_esclusa_da_note_pagine"
