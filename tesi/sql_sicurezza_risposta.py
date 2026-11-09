"""Controlli conservativi per il SOLO Text-to-SQL con auto-correzione.

Non modificano le righe SQL, non recuperano altre fonti e non usano LLM.
Una segnalazione non certifica l'assenza dell'informazione nel corpus.
"""
from __future__ import annotations

import re

from sqlglot import exp, parse_one


def _valore_costante(node):
    """Valore numerico letterale, oppure None se non e' una costante."""
    if not isinstance(node, exp.Literal) or node.is_string:
        return None
    try:
        return float(node.this)
    except (TypeError, ValueError):
        return None


def _booleano_costante(node):
    """Valuta solo predicati evidentemente costanti: mai quelli sulle colonne."""
    if isinstance(node, exp.Paren):
        return _booleano_costante(node.this)
    if isinstance(node, exp.Boolean):
        return bool(node.this)
    if isinstance(node, exp.EQ):
        left, right = _valore_costante(node.left), _valore_costante(node.right)
        if left is not None and right is not None:
            return left == right
    if isinstance(node, exp.NEQ):
        left, right = _valore_costante(node.left), _valore_costante(node.right)
        if left is not None and right is not None:
            return left != right
    if isinstance(node, exp.Not):
        value = _booleano_costante(node.this)
        return None if value is None else not value
    if isinstance(node, exp.And):
        left, right = _booleano_costante(node.left), _booleano_costante(node.right)
        if left is False or right is False:
            return False
        return True if left is True and right is True else None
    if isinstance(node, exp.Or):
        left, right = _booleano_costante(node.left), _booleano_costante(node.right)
        if left is True or right is True:
            return True
        return False if left is False and right is False else None
    return None


def motivo_select_non_probante(sql):
    """Rifiuta SELECT senza fonti o palesemente costruite per non produrre righe.

    Va chiamata DOPO la validazione SQL read-only esistente.
    Non conclude che il dato richiesto sia assente dallo snapshot.
    """
    parsed = parse_one(sql, read="sqlite")
    if not list(parsed.find_all(exp.Table)):
        return "SELECT_SENZA_TABELLE"
    for select in parsed.find_all(exp.Select):
        where = select.args.get("where")
        if where is not None and _booleano_costante(where.this) is False:
            return "PREDICATO_SEMPRE_FALSO"
        limit = select.args.get("limit")
        if limit is not None and _valore_costante(limit.expression) == 0:
            return "LIMIT_ZERO"
    return None


_QUANTITA = re.compile(
    r"\b(?:quanti|quante|quanto|quanta|numero|totale|volume|fatturato|ricavi|spesa)\b",
    re.I,
)
_EVENTO = re.compile(
    r"\b(?:pazient\w*|somministrazion\w*|prescrizion\w*|trattament\w*|"
    r"fatturat\w*|ricav\w*|erogazion\w*|acquist\w*|vendit\w*)\b", re.I
)
_EFFETTIVO = re.compile(
    r"\b(?:realment\w*|effettiv\w*|effettuat\w*|eseguit\w*|"
    r"trattat\w*|prodotto|prodott\w*|registrat\w*|pagat\w*)\b", re.I
)


def domanda_volume_operativo(question):
    """Conta attivita' realmente svolte, non record anagrafici/regolatori.

    Nel dataset regolatorio usato per la tesi non sono presenti flussi
    transazionali verificati di pazienti, somministrazioni o fatturato.
    Le SELECT sulle anagrafiche non possono diventare conteggi operativi.
    """
    return bool(
        _QUANTITA.search(question) and
        _EVENTO.search(question) and
        _EFFETTIVO.search(question)
    )


_NEGAZIONE_GLOBALE = (
    re.compile(r"\b(?:la query|la select|l.interrogazione)\b[^.!?\n]{0,110}"
               r"\b(?:non ha restituito|non restituisce|nessun risultato|zero righe)\b",
               re.I),
    re.compile(r"\bnon risultano\s+(?:note|confezioni|medicinali|record|"
               r"risultati|righe)\b", re.I),
    re.compile(r"\bnessun[ao]\s+(?:nota|confezione|documento|record|"
               r"risultato|riga)\b", re.I),
    re.compile(r"\binformazioni?\s+relativ[ea]\s+a\b[^.!?\n]{0,190}"
               r"\bnon\s+(?:sono|è|e')\s+documentat\w*\b", re.I),
    re.compile(r"\binformazione\s+non\s+documentata\s+"
               r"(?:nei\s+risultati|nello\s+snapshot)\b", re.I),
)


def sintesi_contraddittoria(rows, answer):
    """Segnala negazioni globali in presenza di righe con dati effettivi.

    E' un filtro prudente: non dichiara corrette le righe, ne' completa
    automaticamente un elenco. Le negazioni riferite SOLO a pagine o
    attributi non restituiti non vengono considerate negazioni globali.
    """
    if not rows or not any(
        value is not None and str(value).strip() != ""
        for row in rows for value in row.values()
    ):
        return False
    return any(p.search(answer) is not None for p in _NEGAZIONE_GLOBALE)


def anteprima_righe_non_validate(rows, max_rows=8):
    """Mostra soltanto identificativi candidati, senza qualificarli come Gold."""
    pieces = []
    keep = ("anno", "protocollo_candidato", "protocollo", "nome_file",
            "nota_id", "aic", "ema_id", "data_decisione_ue")
    for n, row in enumerate(rows[:max_rows], 1):
        selected = [f"{key}={str(row[key])[:100]}" for key in keep
                    if row.get(key) is not None and str(row[key]).strip()]
        if selected:
            pieces.append(f"Riga {n}: " + "; ".join(selected))
    return "\n".join(pieces)
