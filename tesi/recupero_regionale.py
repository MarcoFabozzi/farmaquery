"""Recupero documentale regionale per il TAG sperimentale FarmaQuery.

Questa fase è DETERMINISTICA: cerca pagine effettivamente presenti nel DB
congelato. LOTUS valuta poi il significato del testo. Le parole di espansione
servono solo al recupero (non sono fatti su indicazioni/centri).
Nessun riferimento o centro candidato viene dichiarato autorizzato.
"""
from __future__ import annotations

import re

# Espansioni di recupero pubbliche e indipendenti da medicinali/ospedali.
# Servono a trovare testi per i quali il termine ombrello non compare nel PDF.
ESPANSIONI = {
    "neuromuscolar": ("miastenia", "muscolare", "spinale", "sclerosi",
                      "duchenne", "atrofia"),
    "oncol": ("carcinoma", "tumore", "neoplasia", "linfoma"),
    "autoimmun": ("miastenia", "artrite", "sclerosi", "lupus"),
    "cardiomiopat": ("cardiomiopatia", "amiloidosi", "attr"),
}
STOP_RICERCA = {"quali","quale","farmaci","farmaco","malattie","patologie",
                 "sono","presso","della","degli","delle","centri",
                 "centro","regione","campania","prescrivere","prescrivono",
                 "autorizzati","strutture","domanda","risposta"}
PROTOCOL = re.compile(
    r"(?:PG\s*[/.\-]\s*20\d{2}\s*[/.\-]\s*\d{5,9}|"
    r"(?:prot(?:ocollo)?\.?\s*(?:n\.?\s*)?)\d{5,10}|"
    r"\b20\d{2}\s*[/.\-]\s*\d{5,9}\b)", re.I
)
CENTRI = re.compile(r"centr[io]|prescritt|somministr|struttur|abilitat|ospedal|A\.O\.U|AORN|IRCCS",re.I)
MAX_PER_DOC = 8


def _tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(db, table):
    return {r[1] for r in db.execute("PRAGMA table_info(" + table + ")")}


def _key(s):
    # Protocollo confrontato in modo conservativo: tutti i numeri, incluso anno.
    return "".join(re.findall(r"\d+", str(s or "")))


def _tokens(q):
    return list(dict.fromkeys(
        word.casefold() for word in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", q)
        if word.casefold() not in STOP_RICERCA))[:8]


def categoria(q):
    s=q.casefold()
    for stem, words in ESPANSIONI.items():
        if stem in s:
            return stem, words
    return None, ()


def _sql_fts(db, word, limit=35):
    if not re.fullmatch(r"[\wÀ-ÿ-]{3,60}", word, re.U):
        return []
    return db.execute(
        """SELECT p.nota_id,p.numero_pagina,p.testo,n.farmaco_candidato,
                  n.nome_file,n.percorso_zip,n.archivio_url
           FROM pagine_fts
           JOIN pagine p ON p.nota_id=pagine_fts.nota_id
                        AND p.numero_pagina=pagine_fts.numero_pagina
           JOIN note n ON n.id=p.nota_id
           WHERE pagine_fts MATCH ? AND p.metodo IN ('TESTO','OCR')
           ORDER BY bm25(pagine_fts) LIMIT ?""",
        ('"' + word + '"', limit)
    ).fetchall()


def _doc_pages(db, note_id):
    return [dict(r) for r in db.execute(
        """SELECT p.nota_id,p.numero_pagina,p.testo,p.metodo,
                  n.nome_file,n.percorso_zip,n.archivio_url,
                  n.farmaco_candidato,n.protocollo_candidato
           FROM pagine p JOIN note n ON n.id=p.nota_id
           WHERE p.nota_id=? ORDER BY p.numero_pagina""",(note_id,))]


def _evidence(page, annotation="", role="REGIONE"):
    source=(str(page["percorso_zip"])+"#p"+str(page["numero_pagina"])
            +" | archivio: "+str(page["archivio_url"]))
    page_text=str(page["testo"])
    partial=" [ESTRATTO PARZIALE: verificare il resto della pagina]" if len(page_text)>2150 else ""
    return {
        "tipo":role,
        "chiave":role+":"+str(page["nota_id"])+"#p"+str(page["numero_pagina"]),
        "testo":("Documento: "+str(page.get("nome_file") or "")+
                 "; farmaco (candidato): "+str(page.get("farmaco_candidato") or "")+
                 "; pagina "+str(page["numero_pagina"])+
                 ("; "+annotation if annotation else "")+
                 "; testo: "+page_text[:2150]+partial),
        "fonte":source,
    }


def _seleziona_pagine(pages, full=False):
    readable=[r for r in pages if r["metodo"] in ("TESTO","OCR") and r["testo"].strip()]
    if full and len(readable)<=MAX_PER_DOC:
        return readable
    if not readable:
        return []
    # Pagina introduttiva, pagine che riportano centri e rimandi e conclusioni.
    priority=lambda p:(0 if CENTRI.search(p["testo"]) or PROTOCOL.search(p["testo"])
                       else 1, p["numero_pagina"])
    chosen=sorted(readable, key=priority)[:MAX_PER_DOC]
    if full and readable[0] not in chosen:
        chosen[-1]=readable[0]
    return sorted(chosen,key=lambda p:p["numero_pagina"])


def _rimandi(db, src_id, limit=3):
    """Segue un riferimento solo con match UNIVOCO di protocollo estratto.

    Non equipara una mera menzione alla sostituzione/abrogazione della nota.
    """
    if not {"rimandi_candidati","note","pagine"}.issubset(_tables(db)):
        return [], []
    if "protocollo_candidato" not in _columns(db,"note"):
        return [], []
    target_notes=[dict(r) for r in db.execute(
        "SELECT id,protocollo_candidato FROM note "
        "WHERE protocollo_candidato IS NOT NULL AND id<>?",(src_id,))]
    by_key={}
    for r in target_notes:
        k=_key(r["protocollo_candidato"])
        if len(k)>=6:
            by_key.setdefault(k,[]).append(r["id"])
    matched=[]
    unresolved=[]
    checked=set()
    for item in db.execute(
        "SELECT numero_pagina,riferimento FROM rimandi_candidati "
        "WHERE nota_id=? ORDER BY numero_pagina",(src_id,)):
        ref=str(item["riferimento"])
        for m in PROTOCOL.finditer(ref):
            k=_key(m.group())
            if k in checked:
                continue
            checked.add(k)
            refs=by_key.get(k,[])
            if len(refs)==1:
                docs=_doc_pages(db,refs[0])
                for p in _seleziona_pagine(docs,full=True)[:limit]:
                    matched.append(_evidence(
                        p,"NOTA RICHIAMATA: protocollo "+m.group()+
                          "; corrispondenza identificativa automatica, "
                          "interpretare il rapporto giuridico nel testo"))
            else:
                unresolved.append("Rimando "+m.group()+" non risolto univocamente "
                                  "nello snapshot (documenti corrispondenti: "+str(len(refs))+")")
    return matched, unresolved


def regional_candidates(db,question,target="",limit=22):
    """Recupera evidenze regionali complete per farmaco oppure per categoria.

    Nessuna API e nessuna risposta inventata. Restituisce soltanto pagine
    leggibili dello snapshot (citazioni: PDF/ZIP + numero pagina).
    """
    needed={"note","pagine","pagine_fts"}
    if not needed.issubset(_tables(db)):
        return []
    columns=_columns(db,"note")
    if not {"farmaco_candidato","protocollo_candidato","nome_file"}.issubset(columns):
        return []  # i test con schema minimale usano il recupero legacy
    found=[]
    seen=set()

    def add(row):
        if row["chiave"] not in seen:
            seen.add(row["chiave"])
            found.append(row)

    exact=[]
    if target and len(target)>=3:
        escaped=target.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
        exact=[dict(r) for r in db.execute(
            "SELECT id FROM note WHERE farmaco_candidato = ? COLLATE NOCASE "
            "OR nome_file LIKE ? ESCAPE '\\' COLLATE NOCASE ORDER BY anno DESC LIMIT 4",
            (target,"%"+escaped+"%"))]
    if exact:
        for note in exact[:3]:
            pages=_doc_pages(db,note["id"])
            for p in _seleziona_pagine(pages,full=True):
                add(_evidence(p))
            linked, warnings=_rimandi(db,note["id"],limit=3)
            for p in linked:
                add(p)
            # I rimandi non risolti non vengono trasformati in fatti.
            for w in warnings:
                if pages:
                    warning=_evidence(pages[0],w)
                    warning["chiave"]+=":avviso:"+str(len(found))
                    add(warning)
        return found[:limit]

    # Nessun medicinale individuato: ricerca trasversale alle note.
    # Le espansioni della categoria producono solo candidati: non assegnano
    # automaticamente la categoria o un'autorizzazione a una struttura.
    stem, expanded=categoria(question)
    queries=list(expanded) if stem else _tokens(question)
    score={}
    notes={}
    for ix,term in enumerate(queries[:7]):
        for row in _sql_fts(db,term,limit=35):
            note=row["nota_id"]
            score[note]=score.get(note,0)+(4 if stem else 1)
            notes[note]=True
    # La presenza di una struttura nella domanda è una condizione da
    # verificare sul testo della nota, non un'abilitazione automaticamente data.
    q=question.casefold()
    institution=("federico" if "federico" in q else
                 "cardarelli" if "cardarelli" in q else
                 "vanvitelli" if "vanvitelli" in q else
                 "salerno" if "salerno" in q else None)
    if institution:
        for row in _sql_fts(db,institution,limit=80):
            note=row["nota_id"]
            if note in notes:
                score[note]=score.get(note,0)+7
    for note_id,_ in sorted(score.items(),key=lambda kv:(-kv[1],str(kv[0])))[:8]:
        pages=_doc_pages(db,note_id)
        readable=[p for p in pages if p["metodo"] in ("TESTO","OCR")
                  and p["testo"].strip()]
        if not readable:
            continue
        # Aggregazione documentale: LOTUS valuta insieme il testo della
        # patologia e la pagina dei centri, anche se sono pagine diverse.
        # Evita un falso match basato sulla sola menzione di Federico II.
        ranked=sorted(readable,key=lambda p:(
            0 if institution and institution in p["testo"].casefold() else 1,
            0 if any(w in p["testo"].casefold() for w in expanded) else 1,
            p["numero_pagina"]))
        selected=ranked[:4]
        combined="; ".join(
            "[pagina "+str(p["numero_pagina"])+"] "+p["testo"][:530]
            for p in selected)
        first=selected[0]
        docs=[str(p["percorso_zip"])+"#p"+str(p["numero_pagina"])
              for p in selected]
        annotation=("CANDIDATO PER CATEGORIA: verificare nel testo sia la "
                    "patologia sia il centro; relazione non verificata; "
                    "estratti parziali, risultati NON esaustivi. ")
        add({
            "tipo":"REGIONE",
            "chiave":"REGIONE:DOC:"+str(note_id),
            "testo":annotation+" Documento "+str(first.get("nome_file") or "")+
                     "; "+combined,
            "fonte":" | ".join(docs)+" | archivio: "+str(first["archivio_url"]),
        })
    return found[:limit]
