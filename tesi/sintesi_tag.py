"""Contesto breve e tracciabile per la sintesi TAG su categorie implicite.

Riduce il testo passato alla *seconda* chiamata LLM, dopo il filtro LOTUS.
Non effettua ricerche ulteriori e non inventa risposte. Conserva esplicitamente
le fonti e i numeri di pagina dei documenti realmente selezionati.
"""
from __future__ import annotations

import re
from tesi.revisione_categoria import verified_additions

PAGE_RE = re.compile(r"\[pagina\s+(\d+)\]", re.I)

# Solo per la chiamata finale di sintesi delle categorie implicite.
# Non controlla i timeout imposti dal provider Gemini.
CATEGORY_RESPONSE_TIMEOUT_SECONDS = 90

CATEGORY_SYSTEM = (
    "Sei un assistente di consultazione regolatoria. Rispondi in italiano "
    "SOLO con informazioni esplicite nei passaggi forniti dello snapshot. "
    "Per ogni medicinale verifica TRE condizioni: la nota identifica il "
    "medicinale; la patologia riportata appartiene effettivamente alla "
    "categoria richiesta; il centro richiesto è esplicitamente indicato "
    "per QUELLA indicazione. La semplice intestazione di un PDF o la "
    "presenza di un nome di ospedale non provano un'autorizzazione. "
    "Non includere la sclerosi multipla automaticamente nelle malattie "
    "neuromuscolari. Le miopatie infiammatorie, fra cui la "
    "dermatomiosite, possono rientrare nel perimetro neuromuscolare "
    "anche quando la nota le classifica amministrativamente nel sistema "
    "osteomuscolare e nel tessuto connettivo. La miastenia gravis "
    "è una patologia della giunzione "
    "neuromuscolare e NON va esclusa dalla categoria neuromuscolare "
    "soltanto perché è autoimmune. Per ciascuna nota distinguere "
    "la miastenia dalle indicazioni diverse, come NMOSD, e verificare "
    "la struttura sulla tabella associata alla SPECIFICA indicazione. "
    "Riporta medicinale, patologia, struttura, PDF e pagina "
    "per ciascun caso documentato. Non inventare centri, non usare fonti "
    "esterne, non confondere un richiamo con un'abrogazione. "
    "Se qualche relazione manca, esplicita il limite invece di inventarla. "
    "Non dichiarare che un medicinale È ESCLUSO da Federico II sulla sola "
    "assenza nelle pagine selezionate: le evidenze possono essere parziali. "
    "Non limitarti ai primi due documenti: valuta ciascun candidato. "
    "Quando una nota comprende PIÙ indicazioni (per esempio una "
    "neurologica centrale e una neuromuscolare), interpreta separatamente "
    "la tabella dei centri associata a ciascuna indicazione. "
    "Una nota può aggiornare esplicitamente i centri prescrittori anche "
    "per un SECONDO medicinale nominato nel testo: consideralo come "
    "candidato distinto soltanto se l'atto collega esplicitamente "
    "quella indicazione ai medesimi centri; cita la pagina precisa. "
    "Non includere automaticamente altri medicinali menzionati "
    "nell'intestazione, nelle premesse o perché condividono un principio "
    "attivo. Raggruppa più note riferite allo stesso medicinale senza "
    "contare due volte il medesimo nome commerciale. "
    "I passaggi INDICAZIONE NELLA PAGINA e RIGA DEL CENTRO sono "
    "finestre estratte, non prove automatiche: verifica il collegamento "
    "nel contenuto originale. Non escludere un medicinale solo perché "
    "una sua altra indicazione non soddisfa la domanda. "
    "Prima di scrivere la risposta, controlla ogni documento candidato " 
    "uno per uno, anche il primo, e verifica separatamente la pagina " 
    "con la specifica indicazione e la riga del centro. " 
    "Ogni caso positivo deve avere una propria voce che inizi con " 
    "'Medicinale: NOME', seguita da indicazione e fonte/pagina. " 
    "Una semplice menzione del farmaco in una nota finale non equivale " 
    "a includerlo tra i risultati verificati. " 
    "Un elenco fondato su documenti candidati non è necessariamente "
    "esaustivo; segnala la copertura parziale. "
    "Se nessun caso è dimostrabile, scrivi che la relazione "
    "non è verificabile nello snapshot, non che i medicinali non esistono."
)


def compact_category_evidence(rows, per_page_chars=790, per_doc_chars=2370):
    """Conserva riferimenti e finestre indicazione/centro di ciascun PDF.

    Ritorna evidenze per la chiamata finale, NON per la selezione LOTUS.
    Una finestra tagliata è dichiarata come estratto, mai come pagina integrale.
    """
    out=[]
    for row in rows:
        text=str(row.get("testo") or "")
        sources=list(dict.fromkeys(row.get("fonti") or
                                   [row.get("fonte") or ""]))
        prepared=row.get("passaggi_sintesi")
        if prepared:
            pages=[
                {"pagina":int(p["pagina"]),
                 "estratto":str(p["estratto"])[:min(per_page_chars,1100)]}
                for p in prepared if p.get("estratto")
            ]
        else:
            matches=list(PAGE_RE.finditer(text))
            pages=[]
            if matches:
                for i,m in enumerate(matches):
                    end=matches[i+1].start() if i+1<len(matches) else len(text)
                    part=text[m.end():end].strip()
                    if not part:
                        continue
                    pages.append({"pagina":int(m.group(1)),
                                  "estratto":part[:per_page_chars]})
            if not pages:
                pages=[{"pagina":None,"estratto":text[:per_doc_chars]}]
        selected=[]
        used=0
        for page in pages[:3]:
            remaining=per_doc_chars-used
            if remaining<=0:
                break
            snippet=page["estratto"][:remaining]
            selected.append({"pagina":page["pagina"],"estratto":snippet})
            used+=len(snippet)
        header=text.split("[pagina ",1)[0]
        header=" ".join(header.split())
        out.append({
            "chiave":str(row.get("chiave") or ""),
            "documento_e_medicinale_candidato":header[:290],
            "passaggi":selected,
            "fonti":sources[:len(selected)],
            "copertura":"estratti di pagine candidate, non elenco esaustivo",
            "documenti_troncati":bool(row.get("documenti_troncati",False))
        })
    return out


# Il controllo di copertura considera i nomi indicati dai DOCUMENTI dello
# snapshot, non una lista gold. I nomi sono CANDIDATI: il LLM deve ancora
# stabilire se l'indicazione e il centro siano davvero collegati.
def _candidate_short_name(doc):
    header=str(doc.get("documento_e_medicinale_candidato") or "")
    match=re.search(r"farmaco candidato:\s*([^;]+)",header,re.I)
    if not match:
        return ""
    pieces=re.findall(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9_-]*",match.group(1))
    if not pieces:
        return ""
    name=pieces[0]
    if len(name)<4 or name.casefold() in ("farmaco","medicinale","nessuno"):
        return ""
    return name


def _candidate_listed(answer,name):
    """Il nome nelle note a margine NON è una voce positiva dell'elenco."""
    pattern=(r"(?im)^\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?"
             r"(?:\*\*)?(?:medicinale\s*:\s*)?(?:\*\*)?"
             +re.escape(name)+r"\b")
    return bool(re.search(pattern,str(answer)))


def missing_category_candidates(answer,compact):
    """Candidati non elencati: indizi per revisione, non errori certi."""
    misses=[]
    seen=set()
    for doc in compact:
        name=_candidate_short_name(doc)
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        if not _candidate_listed(answer,name):
            misses.append(doc)
    return misses


def expand_review_pages(db,question,answer,compact,max_docs=6,max_pages=2,max_chars=10500):
    """Arricchisce SOLO i candidati omessi con le pagine originali SQLite.

    La prima sintesi continua a usare estratti compatti. Per verificare
    omissioni si usano le pagine selezionate per lo stesso documento,
    senza introdurre fonti o risultati predefiniti.
    """
    missing=missing_category_candidates(answer,compact)
    if not missing:
        return compact
    by_key={str(doc.get("chiave")):doc for doc in missing[:max_docs]}
    enriched=[]
    for doc in compact:
        if str(doc.get("chiave")) not in by_key:
            enriched.append(doc)
            continue
        key=str(doc.get("chiave") or "")
        if not key.startswith("REGIONE:DOC:"):
            enriched.append(doc)
            continue
        note_id=key[len("REGIONE:DOC:"):]
        try:
            pages=[dict(p) for p in db.execute(
                "SELECT numero_pagina,testo FROM pagine "
                "WHERE nota_id=? AND metodo IN ('TESTO','OCR') "
                "AND length(trim(testo))>0 ORDER BY numero_pagina",
                (note_id,))]
        except Exception:
            enriched.append(doc)
            continue
        if not pages:
            enriched.append(doc)
            continue
        # Recupera dapprima le pagine già citate nella selezione.
        # Conserva le fonti puntuali; non riordina indicazioni e
        # strutture di pagine diverse nella stessa citazione.
        cited={int(p["pagina"]) for p in doc.get("passaggi",[])
               if p.get("pagina") is not None}
        center=(re.search(r"\b(?:federico|cardarelli|vanvitelli)\b",question,re.I))
        term=center.group().casefold() if center else ""
        from tesi.recupero_regionale import categoria
        category_terms=categoria(question)[1]
        def rank(page):
            body=str(page["testo"] or "").casefold()
            hit_center=bool(term and term in body)
            hit_disease=any(word in body for word in category_terms)
            return (0 if hit_center and hit_disease else
                    1 if hit_center else 2 if hit_disease else 3,
                    0 if page["numero_pagina"] in cited else 1,
                    page["numero_pagina"])
        pages.sort(key=rank)
        selected=[]
        budget=max_chars
        for p in pages:
            if len(selected)>=max_pages or budget<=0:
                break
            page_no=int(p["numero_pagina"])
            text=str(p["testo"])
            if not text or (page_no not in cited and selected):
                continue
            portion=text[:min(len(text),budget)]
            selected.append({"pagina":page_no,"estratto":portion})
            budget-=len(portion)
        if not selected:
            enriched.append(doc)
            continue
        new_doc=dict(doc)
        new_doc["passaggi"]=selected
        source_by_page={}
        for source in doc.get("fonti",[]):
            match=re.search(r"#p(\d+)\b",str(source))
            if match:
                source_by_page[int(match.group(1))]=source
        if any(p["pagina"] not in source_by_page for p in selected):
            enriched.append(doc)
            continue
        new_doc["fonti"]=[source_by_page[p["pagina"]] for p in selected]
        new_doc["origine_verifica"]="testo delle pagine originali nello SQLite"
        enriched.append(new_doc)
    return enriched


def secondary_medicine_candidates(db,question,compact,max_candidates=6):
    """Trova secondi medicinali richiamati per l'aggiornamento dei centri.

    L'aggiornamento documentato e' soltanto un candidato: la sintesi TAG
    deve ancora verificare la patologia, la tabella e l'ospedale citato.
    Il nome e le prove provengono dalle pagine SQLite, mai dal benchmark.
    """
    from tesi.recupero_regionale import categoria
    if not categoria(question)[0]:
        return []
    pattern=re.compile(
        r"(?i:(?:aggiornat[ioe]|abilitat[ioe]|autorizzat[ioe])\s+"
        r"(?:(?:i|gli|le)\s+)?(?:centri|presidi)\s+"
        r"(?:prescrittori|abilitati)\s+(?:del|per\s+il)\s+"
        r"(?:farmaco|medicinale)\s+)"
        r"([A-Z][A-Z0-9_-]{3,})"
    )
    found=[]
    seen=set()
    center=re.search(r"\b(?:federico|cardarelli|vanvitelli)\b",
                     question,re.I)
    for doc in compact:
        key=str(doc.get("chiave") or "")
        if not key.startswith("REGIONE:DOC:"):
            continue
        note_id=key.split("REGIONE:DOC:",1)[1]
        try:
            pages=[dict(x) for x in db.execute(
                "SELECT numero_pagina,testo FROM pagine WHERE nota_id=? "
                "AND metodo IN ('TESTO','OCR') ORDER BY numero_pagina",
                (note_id,))]
        except Exception:
            continue
        if not pages:
            continue
        first_name=_candidate_short_name(doc).casefold()
        if center and not any(center.group().casefold() in
                              str(page["testo"] or "").casefold()
                              for page in pages):
            continue
        for page in pages:
            body=" ".join(str(page["testo"] or "").split())
            for match in pattern.finditer(body):
                name=match.group(1)
                if name.casefold() in seen or name.casefold()==first_name:
                    continue
                source_by_page={}
                for source in doc.get("fonti",[]):
                    m=re.search(r"#p(\d+)\b",str(source))
                    if m:
                        source_by_page[int(m.group(1))]=str(source)
                others=[p for p in pages
                        if p["numero_pagina"]!=page["numero_pagina"]]
                ordered=[page]+others
                passages=[]
                sources=[]
                for p in ordered:
                    no=int(p["numero_pagina"])
                    if no not in source_by_page:
                        continue
                    passages.append({"pagina":no,
                                     "estratto":str(p["testo"] or "")[:10000]})
                    sources.append(source_by_page[no])
                    if len(passages)>=2:
                        break
                if not passages or passages[0]["pagina"]!=page["numero_pagina"]:
                    continue
                seen.add(name.casefold())
                found.append({
                    "chiave":key+":SECONDARIO:"+name,
                    "documento_e_medicinale_candidato":(
                        "farmaco candidato: "+name+
                        "; citato in aggiornamento dei centri di una nota "
                        "intestata a un altro medicinale"),
                    "passaggi":passages,"fonti":sources,
                    "origine_verifica":"secondo medicinale citato nell'atto",
                })
                if len(found)>=max_candidates:
                    return found
    return found


def revise_category_if_needed(model,question,answer,compact,ask_fn,
                              audit=None,stats=None,max_checks=4):
    """Riesamina un candidato per chiamata, senza riscrivere il primo elenco.

    Una nota può contenere più indicazioni: separare i candidati evita che
    il modello privilegi il primo caso positivo e ignori gli altri.
    Conserva le evidenze originali, non promuove i candidati automaticamente.
    """
    missing=missing_category_candidates(answer,compact)
    # I secondi medicinali citati esplicitamente in un aggiornamento
    # vengono verificati con le medesime regole delle note principali.
    missing.sort(key=lambda doc: 0 if doc.get("origine_verifica") ==
                 "secondo medicinale citato nell'atto" else 1)
    if not missing:
        if stats is not None:
            stats.update({"chiamate":0,"candidati":0,"accettati":0})
        return answer,None,False,[]

    accepted=[]
    usage_total=None
    calls=0
    for doc in missing[:max_checks]:
        name=_candidate_short_name(doc)
        context={
            "domanda":question,
            "documenti_candidati_non_elencati":[{
                "medicinale_candidato":name,
                "passaggi":doc.get("passaggi",[]),
                "fonti":doc.get("fonti",[])}],
            "avviso":("Il documento è solo un candidato. Verifica "
                      "l'indicazione specifica e il centro della stessa "
                      "sezione, non trasferire centri da altre tabelle.")
        }
        reviewed,usage=ask_fn(
            model,
            "Esamina SOLTANTO il medicinale candidato fornito. "
            "Se e' nominato come secondo medicinale nella nota di un "
            "altro farmaco, accerta il collegamento ESPLICITO fra il "
            "richiamo, la specifica indicazione e i centri richiesti: "
            "non basta che due nomi compaiano nello stesso PDF. Verifica "
            "la categoria richiesta e la CORRISPONDENZA fra indicazione "
            "e centro nella stessa sezione del documento; la mera "
            "menzione della struttura non basta. Restituisci soltanto "
            "JSON con 'nuove_voci' (array). Se è effettivamente provato "
            "riporta una voce con: 'confermato':true, 'medicinale', "
            "'patologia', 'indicazione', 'pagina_indicazione', "
            "'pagina_centro', 'citazione_indicazione', 'citazione_centro'. "
            "Le citazioni DEVONO essere frasi LETTERALI CONTIGUE presenti "
            "nelle pagine fornite, non parafrasi o frasi concatenate. "
            "La citazione del centro deve contenere il nome del centro "
            "richiesto. Se il nome dell'ospedale è esteso nel PDF, "
            "COPIA LA RIGA ORIGINALE senza abbreviarla e conserva "
            "l'ordine delle parole. Scegli sempre l'indicazione "
            "nella SEZIONE della tabella contenente il centro. "
            "Se l'appartenenza all'indicazione non è "
            "dimostrabile, restituisci JSON con 'nuove_voci':[]. "
            "Non usare fonti esterne, risposte gold né altri medicinali.",
            context,timeout=CATEGORY_RESPONSE_TIMEOUT_SECONDS,
            max_tokens=1000
        )
        calls+=1
        if usage_total is None:
            usage_total=usage
        elif usage is not None:
            usage_total={
                key:(usage_total.get(key)+usage.get(key)
                     if (usage_total.get(key) is not None and
                         usage.get(key) is not None) else None)
                for key in ("token_input","token_output","costo_usd")}
        local_checks=[]
        new_items=verified_additions(
            reviewed,[doc],question,_candidate_short_name,
            diagnostics=local_checks)
        accepted.extend(new_items)
        if audit is not None:
            # Più proposte dello stesso medicinale contano come UNA
            # decisione diagnostica. Preferire l'esito positivo se
            # almeno una proposta supera i controlli sulle fonti.
            positive=[x for x in local_checks
                      if x.get("esito","").startswith("accettato")]
            chosen=(positive[-1] if positive else
                    local_checks[-1] if local_checks else
                    {"medicinale":name,"esito":"nessun_esito"})
            audit.append({**chosen,"proposte_esaminate":len(local_checks)})

    if audit is not None:
        for doc in missing[max_checks:]:
            audit.append({"medicinale":_candidate_short_name(doc),
                          "esito":"non_esaminato_limite_verifiche"})
    if stats is not None:
        stats.update({"chiamate":calls,"candidati":len(missing),
                      "accettati":len(accepted),
                      "non_esaminati":max(0,len(missing)-max_checks)})

    if accepted:
        # I farmaci integrati vengono prima di note finali, incluse
        # varianti Markdown come '*Nota:'.
        anchor=re.search(r"(?im)^\s*(?:\*{1,2}\s*)?"
                         r"(?:copertura\s*:|nota\s*:|per quanto riguarda\b)",
                         answer)
        if anchor:
            before=answer[:anchor.start()].rstrip()
            after=answer[anchor.start():].lstrip()
            answer=before+"\n\n"+"\n\n".join(accepted)+"\n\n"+after
        else:
            answer=answer.rstrip()+"\n\n"+"\n\n".join(accepted)
    return answer,usage_total,bool(calls),[
        _candidate_short_name(doc) for doc in missing]
