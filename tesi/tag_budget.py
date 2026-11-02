"""Pianificazione trasparente del filtro semantico LOTUS per FarmaQuery.

La modalità raggruppata riduce il numero di elementi sottoposti al modello
conservando *tutte* le evidenze originali e le relative fonti. L'operatore
semantico è ancora LOTUS DataFrame.sem_filter; il raggruppamento influenza la
granularità della selezione, quindi l'esito va confrontato con 'righe'.
"""
from __future__ import annotations

import os

DEFAULT_GROUPS = 3
MAX_GROUPS = 5
EXCERPT_CHARS = 1150


def selection_mode(environ=None):
    env = os.environ if environ is None else environ
    mode = str(env.get("FARMAQUERY_TAG_SELECTION_MODE", "raggruppata")).strip().casefold()
    if mode not in {"raggruppata", "righe"}:
        raise ValueError("FARMAQUERY_TAG_SELECTION_MODE deve essere 'raggruppata' o 'righe'")
    return mode


def semantic_plan(rows, mode="raggruppata", max_groups=DEFAULT_GROUPS):
    """Restituisce (righe_per_LOTUS, mappa_chiave_verso_righe_originali).

    Non usa token, web o LLM; la sequenza è stabile e deterministica.
    Le righe originali sono sempre mantenute per la citazione finale.
    """
    if mode not in {"raggruppata", "righe"}:
        raise ValueError("Modalità TAG sconosciuta")
    if not 1 <= max_groups <= MAX_GROUPS:
        raise ValueError("Numero di gruppi fuori intervallo")
    if mode == "righe":
        return ([{"chiave":str(r["chiave"]), "testo":str(r["testo"])}
                 for r in rows],
                {str(r["chiave"]):[r] for r in rows})
    if not rows:
        return [], {}

    count = min(len(rows), max_groups)
    buckets=[[] for _ in range(count)]
    # Un tipo di fonte preferibilmente nello stesso gruppo. Fonti successive
    # sono distribuite sul gruppo con meno evidenze, senza perderne nessuna.
    assigned={}
    for row in rows:
        kind=str(row.get("tipo") or "ALTRO")
        if kind not in assigned:
            assigned[kind]=min(range(count),key=lambda i:(len(buckets[i]),i))
        buckets[assigned[kind]].append(row)

    # Unica fonte con molte pagine: ripartizione del carico per sem_filter.
    # Dopo la separazione per fonti, distribuiamo solo gruppi completamente
    # vuoti in modo da non lasciare gruppi inutilizzati.
    for idx in range(count):
        if not buckets[idx]:
            largest=max(range(count),key=lambda j:len(buckets[j]))
            if len(buckets[largest])>1:
                buckets[idx].append(buckets[largest].pop())

    planned=[]
    members={}
    for idx,bucket in enumerate(buckets,1):
        if not bucket:
            continue
        uid="LOTUS:GRUPPO:"+str(idx)
        textparts=[]
        for row in bucket:
            src=str(row.get("tipo") or "ALTRO")
            key=str(row["chiave"])
            piece=" ".join(str(row.get("testo") or "").split())
            if len(piece)>EXCERPT_CHARS:
                piece=piece[:EXCERPT_CHARS].rstrip()+" [ESTRATTO TRONCATO]"
            textparts.append("["+src+" | "+key+"] "+piece)
        planned.append({"chiave":uid, "testo":"\n".join(textparts)})
        members[uid]=bucket
    return planned,members


def expand_selected(selected, members):
    """Espande solo i gruppi selezionati, senza aggiungere altre fonti."""
    result=[]
    seen=set()
    for row in selected:
        for original in members.get(str(row.get("chiave")),()):
            key=original["chiave"]
            if key not in seen:
                result.append(original)
                seen.add(key)
    return result
