"""Gate strutturale di copertura del TAG: confronto tra ID nota, non tra risposte.

Il criterio non è il numero assoluto di documenti: se una SELECT ha escluso
note che menzionano lo stesso centro attraverso una JOIN con tabelle di centri
curate/parziali, la sua cardinalità non autorizza affermazioni di completezza.
La fase 2 rimane soggetta alla valutazione di intento del pianificatore.
"""
from __future__ import annotations

from sqlglot import exp, parse_one

from tesi.piano_documentale import (
    recovery_center_anchors, sql_from_document_plan,
)


def _sparse_center_join(sql):
    """Riconosce il rischio strutturale, non la terminologia clinica."""
    try:
        tree=parse_one(sql,read="sqlite")
    except Exception:
        return False
    if not isinstance(tree,exp.Select):
        return False
    if any(tree.args.get(part) is not None for part in (
            "with_","group","having","qualify","limit","offset","order")):
        return False
    source=tree.args.get("from_") or tree.args.get("from")
    if not source or not isinstance(source.this,exp.Table):
        return False
    if str(source.this.name).casefold()!="note":
        return False
    for join in tree.args.get("joins") or []:
        target=join.this
        if (not isinstance(target,exp.Table)
                or join.args.get("side") or join.args.get("kind")):
            continue
        if str(target.name).casefold() in {
            "centri_candidati","nota_centro_documentato"
        }:
            return True
    return False


def compare_center_coverage(db, sql, question, records, runner, validator):
    """Rileva un insieme di note escluse dal recupero documentale.

    Non dichiara pertinenti le note aggiuntive: abilita soltanto un secondo
    metodo che deve verificarle. Una query differenziale non può eliminare i
    vincoli richiesti dall'utente: il piano successivo li valuta e può
    rifiutare il percorso alternativo.

    Restituisce (issue, audit) e non modifica database, record o SQL originale.
    """
    audit={
        "sql_controllo_copertura":None,
        "documenti_controllo_copertura":None,
        "documenti_esclusi_primo_recupero":None,
        "controllo_copertura_troncato":False,
        "controllo_copertura_eseguito":False,
    }
    if not records or not _sparse_center_join(sql):
        return None,audit
    if any(r.get("nota_id") is None for r in records):
        return None,audit
    anchors=recovery_center_anchors(sql,question)
    if not anchors:
        return None,audit
    # In presenza di più ancore ambigue lasciamo al piano LLM il lavoro:
    # non deduciamo quale sede sia quella richiesta.
    if len(anchors)!=1:
        return None,audit
    query=validator(sql_from_document_plan({"centro":anchors[0]}))
    audit["sql_controllo_copertura"]=query
    audit["controllo_copertura_eseguito"]=True
    broad,truncated=runner(db,query)
    audit["documenti_controllo_copertura"]=len(broad)
    audit["controllo_copertura_troncato"]=bool(truncated)
    old_ids={str(x["nota_id"]) for x in records}
    broad_ids={str(x["nota_id"]) for x in broad
               if x.get("nota_id") is not None}
    missing=broad_ids-old_ids
    audit["documenti_esclusi_primo_recupero"]=len(missing)
    if truncated:
        # L'utente non deve ricevere un falso elenco esaustivo in presenza
        # di troncamento; il metodo alternativo potrà a sua volta astenersi.
        return "copertura_documentale_troncata",audit
    if missing:
        return "join_centri_documenti_potenzialmente_esclusi",audit
    return None,audit
