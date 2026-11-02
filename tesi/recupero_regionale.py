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
    # La sclerosi multipla non va automaticamente considerata una
    # patologia neuromuscolare: evitare espansioni troppo generiche.
    # Sinonimi, abbreviazioni e codice di esenzione presenti nelle note.
    # Servono al RECUPERO, non attestano un'autorizzazione.
    "neuromuscolar": ("miastenia", "mgg", "rfg101", "muscolare", "spinale",
                      "duchenne", "atrofia", "distrofia", "motoneurone",
                      "neuropatia", "polineuropatia"),
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
    complete=bool(re.search(
        r"\\b(?:tutt[ieo]|elenco completo|quante confezioni|quanti aic)\\b",
        question,re.I))
    explicit_page=re.search(r"\\bpagina\\s+(\\d+)\\b",question,re.I)
    if exact:
        for note in exact[:3]:
            pages=_doc_pages(db,note["id"])
            usable=sum(p["metodo"] in ("TESTO","OCR") and bool(p["testo"].strip())
                       for p in pages)
            selected=_seleziona_pagine(pages,full=True)
            partial=usable>len(selected)
            if complete and explicit_page:
                # Una tabella individuata da pagina esplicita ha priorità
                # sulle copertine e sulle pagine di contesto.
                selected=sorted(selected,key=lambda p:(
                    p["numero_pagina"]!=int(explicit_page.group(1)),
                    p["numero_pagina"]))
            for p in selected:
                if complete and (not explicit_page or
                                 p["numero_pagina"]==int(explicit_page.group(1))):
                    # Per gli elenchi completi la pagina non può essere
                    # troncata a 2150 caratteri: suddivisione controllata
                    # in finestre con sovrapposizione e fonte identica.
                    whole=str(p["testo"])
                    stride=1500
                    for offset in range(0,len(whole),stride):
                        chunk=whole[offset:offset+1650]
                        ev=_evidence(p,"Sezione della pagina "+
                                     str(offset//stride+1)+
                                     "; non è una pagina integrale")
                        ev["chiave"]+=":parte:"+str(offset//stride+1)
                        ev["testo"]=(
                            "Documento: "+str(p.get("nome_file") or "")+
                            "; farmaco candidato: "+
                            str(p.get("farmaco_candidato") or "")+
                            "; pagina "+str(p["numero_pagina"])+
                            "; parte "+str(offset//stride+1)+
                            "; testo: "+chunk)
                        add(ev)
                        if len(found)>=limit:
                            break
                else:
                    add(_evidence(p,"ESTRATTO PARZIALE: altre pagine della nota "
                                      "non incluse nel contesto" if partial else ""))
                if len(found)>=limit:
                    break
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

    # Domande per categoria: prima MASSIMIZZIAMO IL RICHIAMO dei documenti.
    # La precedente top-8, fondata sul numero di occorrenze FTS, escludeva
    # note corrette: un PDF breve con una tabella centri poteva essere superato
    # da un PDF con molti richiami alla patologia.
    stem, expanded=categoria(question)
    queries=list(expanded) if stem else _tokens(question)
    terms_by_note={}
    for term in queries[:10]:
        # Non troncare ai primi 35 risultati PER TERMINE: l'unità di
        # recupero è la nota, non la singola occorrenza sulla pagina.
        for hit in _sql_fts(db,term,limit=1000):
            terms_by_note.setdefault(hit["nota_id"],set()).add(term)
    q=question.casefold()
    institution=("federico" if "federico" in q else
                 "cardarelli" if "cardarelli" in q else
                 "vanvitelli" if "vanvitelli" in q else
                 "salerno" if "salerno" in q else None)

    def extract_window(text, terms, radius=450, cap=1650):
        """Finestre su condizioni/centri; NON taglia la tabella all'intestazione."""
        body=" ".join(str(text).split())
        lower=body.casefold()
        centers=[m.start() for m in re.finditer(
            re.escape(institution),lower)] if institution else []
        diseases=[]
        for t in terms:
            diseases += [m.start() for m in re.finditer(re.escape(t),lower)][:3]
        # Le occorrenze centrali sono più importanti delle intestazioni:
        # conserva gli ultimi centri nelle tabelle, oltre alla prima.
        positions=(centers[:2]+centers[-2:]+diseases[:3])
        if not positions:
            return body[:cap]
        result=[]
        intervals=[]
        for pos in sorted(set(positions)):
            left=max(0,pos-radius)
            right=min(len(body),pos+radius)
            if intervals and left<=intervals[-1][1]:
                intervals[-1]=(intervals[-1][0],max(intervals[-1][1],right))
            else:
                intervals.append((left,right))
        for left,right in intervals:
            result.append(body[left:right])
        return " […] ".join(result)[:cap]

    eligible=[]
    for note_id,terms in terms_by_note.items():
        pages=_doc_pages(db,note_id)
        readable=[p for p in pages if p["metodo"] in ("TESTO","OCR")
                  and str(p["testo"]).strip()]
        if not readable:
            continue
        center_pages=[p for p in readable if institution and
                      institution in p["testo"].casefold()]
        if institution and not center_pages:
            continue
        both=sum(1 for p in center_pages
                 if any(t in p["testo"].casefold() for t in terms))
        # Numero di DIVERSI indizi patologici, non frequenza di parole.
        rank=(1 if both else 0,len(terms),len(center_pages))
        eligible.append((rank,str(note_id),readable,terms))

    # Il tetto è controllato da limit e dalla dimensione del contesto,
    # ma non è più il primo top-8 arbitrario.
    eligible.sort(key=lambda item:(-item[0][0],-item[0][1],
                                  -item[0][2],item[1]))
    def focused_passage(page, terms):
        """Collega INTESTAZIONE dell'indicazione e riga del centro.

        Molte note hanno due sezioni diverse (es. NMOSD e miastenia):
        riportare soltanto la riga "Federico II" non dice a quale delle
        due appartenga. La finestra principale include prima il contesto
        terapeutico della sezione e poi la riga del centro, dalla stessa
        pagina, con riconoscimento OCR case-insensitive.
        """
        body=" ".join(str(page["testo"]).split())
        lower=body.casefold()
        disease_hits=[]
        for term in sorted(terms):
            disease_hits.extend((match.start(),term)
                                for match in list(re.finditer(re.escape(term),lower))[:2])
        disease_hits.sort()
        center_hits=(list(re.finditer(re.escape(institution),lower))
                     if institution else [])
        parts=[]
        # Si favorisce l'indicazione più vicina al centro richiesto.
        if disease_hits:
            if center_hits:
                nearest=min(disease_hits,key=lambda item: min(
                    abs(item[0]-hit.start()) for hit in center_hits))
            else:
                nearest=disease_hits[0]
            at,term=nearest
            parts.append("INDICAZIONE NELLA PAGINA (DA VERIFICARE): "+
                         body[max(0,at-140):min(len(body),at+155)])
        if center_hits:
            hit=center_hits[-1]
            parts.append("RIGA DEL CENTRO (DA VERIFICARE): "+
                         body[max(0,hit.start()-200):
                              min(len(body),hit.end()+170)])
        if not parts:
            return ""
        return " […] ".join(parts)[:1200]

    for _,note_id,readable,terms in eligible[:limit]:
        indexed={p["numero_pagina"]:p for p in readable}
        priority=lambda p:(
            0 if institution and institution in p["testo"].casefold()
                  and any(t in p["testo"].casefold() for t in terms) else
            1 if institution and institution in p["testo"].casefold() else
            2 if any(t in p["testo"].casefold() for t in terms) else 3,
            p["numero_pagina"])
        picked=sorted(readable,key=priority)[:5]
        # Una patologia nella pagina precedente deve restare visibile
        # anche quando il centro è presente solo nella tabella seguente.
        for p in list(picked):
            before=indexed.get(p["numero_pagina"]-1)
            if before and before not in picked and len(picked)<6:
                picked.append(before)
        # LLM riceve prima le pagine più probanti, non la copertina.
        picked.sort(key=priority)
        first=picked[0]
        passages=[
            "[pagina "+str(p["numero_pagina"])+"] "+
            extract_window(p["testo"],terms,radius=530,cap=2350)
            for p in picked
        ]
        selection_passages=[
            "[pagina "+str(p["numero_pagina"])+"] "+
            extract_window(p["testo"],terms,radius=210,cap=830)
            for p in picked
        ]
        sources=[
            str(p["percorso_zip"])+"#p"+str(p["numero_pagina"])+
            " | archivio: "+str(p["archivio_url"])
            for p in picked
        ]
        add({
            "tipo":"REGIONE",
            "chiave":"REGIONE:DOC:"+str(note_id),
            "testo":(
                "DOCUMENTO CANDIDATO, NON AUTORIZZAZIONE VERIFICATA. "
                "Controllare la corrispondenza tra indicazione e centro. "
                "Documento: "+str(first.get("nome_file") or "")+
                "; farmaco candidato: "+str(first.get("farmaco_candidato") or "")+
                "; "+" ".join(passages)
            ),
            "fonte":sources[0],
            "fonti":sources,
            "passaggi_sintesi":[
                {"pagina":p["numero_pagina"],
                 "estratto":focused_passage(p,terms)}
                for p in picked if focused_passage(p,terms)
            ],
            "testo_selezione":(
                "Documento: "+str(first.get("nome_file") or "")+
                "; farmaco candidato: "+str(first.get("farmaco_candidato") or "")+
                "; "+" ".join(selection_passages)
            ),
            "copertura_documenti":len(eligible),
            "documenti_troncati":len(eligible)>limit,
        })
    return found[:limit]
