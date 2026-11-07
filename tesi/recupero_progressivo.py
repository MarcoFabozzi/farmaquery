"""Recupero progressivo SQL per TAG automatico, senza dizionari clinici.

Il fallback è deliberatamente conservativo: si attiva SOLO dopo zero righe
e SOLO per la forma documentale riconoscibile "centro in tabella curata"
AND "(termine in pagina OR termine in indicazione candidata)".
Non interpreta il significato di una patologia: conserva il riferimento
oggettivo alla struttura, e lascia la classificazione a LOTUS.
"""
from __future__ import annotations

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
