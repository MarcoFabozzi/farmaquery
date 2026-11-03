"""Controllo delle integrazioni TAG per categorie implicite.

Nessuna lista gold: le prove testuali vengono controllate contro i passaggi
dello stesso snapshot che ha alimentato la sintesi.
"""
import json
import re
import unicodedata


def _norm(value):
    # I PDF OCR spesso perdono accenti, apostrofi, trattini e capoversi.
    value=unicodedata.normalize("NFKD",str(value)).casefold()
    value="".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+",value))


def _quoted(quote,text):
    q=_norm(quote)
    return len(q)>=16 and q in _norm(text)


# Solo termini descrittivi generici: nessun nome di medicinale o gold.
_GENERIC_WORDS={
    "trattamento","pazienti","paziente","adulti","adulto","indicazione",
    "regione","campania","farmaco","medicinale","centri","centro",
    "riferimento","terapia","prescrizione","presidi","presidio",
    "struttura","strutture","autorizzati","autorizzato","ospedaliera",
    "universitaria","universita","napoli","della","delle","degli",
    "sono","nelle","questa","questo","dello","delle","dello",
}


def _anchor_indication(quote,text):
    """Controllo limitato per citazioni non letterali da PDF/OCR.

    Occorrono almeno due parole significative condivise e consecutive
    nel testo dell'atto. Parole generiche come trattamento/pazienti
    NON costituiscono un'ancora clinica.
    """
    q=_norm(quote)
    source=_norm(text)
    tokens=[w for w in q.split() if len(w)>=4 and w not in _GENERIC_WORDS]
    if len(tokens)<2:
        return False
    unique=list(dict.fromkeys(tokens))
    present=[w for w in unique if re.search(r"\b"+re.escape(w)+r"\b",source)]
    if len(present)<2 or len(present)/len(unique)<0.7:
        return False
    # Richiede una coppia coerente, non due parole isolate e lontane.
    return any(" ".join((a,b)) in source
               for a,b in zip(tokens,tokens[1:])
               if a in present and b in present)


def _anchor_center(quote,text,facility):
    """Accetta un centro riconoscibile anche con il nome esteso in tabella.

    Non basta una menzione isolata: la fonte deve contenere l'ente e
    la sua intestazione ospedaliera in un intervallo ristretto.
    """
    if not facility:
        return False
    q=_norm(quote)
    source=_norm(text)
    if not re.search(r"\b"+re.escape(facility)+r"\b",q):
        return False
    if facility=="federico":
        if "federico ii" not in q:
            return False
        match=re.search(
            r"\b(?:aou|a o u|azienda ospedaliera universitaria)\b"
            r".{0,155}\bfederico ii\b",source)
        return bool(match)
    # Per altri centri la verifica resta volutamente conservativa:
    # il modello deve aver fornito la citazione letterale.
    return False


def _match_quote(quote,text,kind,facility=""):
    if _quoted(quote,text):
        return "letterale"
    if kind=="indicazione" and _anchor_indication(quote,text):
        return "ancora_indicazione"
    if kind=="centro" and _anchor_center(quote,text,facility):
        return "ancora_centro"
    return None


def verified_additions(review_text,missing,question,name_fn,diagnostics=None):
    """Formatta solo casi esplicitamente sostenuti da due citazioni.

    I controlli verificano l'esistenza dei passi; il loro significato resta
    responsabilità dell'interpretazione semantica del modello.
    """
    def report(name,reason,quote=""):
        if diagnostics is not None:
            entry={"medicinale":str(name),"esito":reason}
            if quote:
                entry["citazione_proposta"]=str(quote)[:180]
            diagnostics.append(entry)

    raw=str(review_text or "").strip()
    fence=chr(96)*3
    if raw.startswith(fence) and raw.endswith(fence):
        raw=re.sub(r"^"+fence+r"(?:json)?\s*|\s*"+fence+r"$","",raw,flags=re.I)
    try:
        parsed=json.loads(raw)
    except (TypeError,ValueError):
        for doc in missing:
            report(name_fn(doc),"json_non_valido")
        return []
    if not isinstance(parsed,dict) or not isinstance(parsed.get("nuove_voci"),list):
        for doc in missing:
            report(name_fn(doc),"formato_non_valido")
        return []
    docs={name_fn(doc).casefold():doc for doc in missing if name_fn(doc)}
    requested=re.search(r"\b(?:aou|aorn|irccs)\s+([a-zà-ÿ]{4,})",
                        str(question).casefold())
    facility=requested.group(1) if requested else ""
    inserted=set()
    additions=[]
    seen_names=set()
    for item in parsed["nuove_voci"]:
        if not isinstance(item,dict):
            continue
        name=str(item.get("medicinale") or "").strip()
        seen_names.add(name.casefold())
        if item.get("confermato") is not True:
            report(name,"non_confermato_dal_modello")
            continue
        doc=docs.get(name.casefold())
        if not doc or name.casefold() in inserted:
            report(name,"candidato_non_corrispondente_o_duplicato")
            continue
        illness=str(item.get("patologia") or "").strip()
        indication=str(item.get("indicazione") or "").strip()
        evidence1=str(item.get("citazione_indicazione") or "").strip()
        evidence2=str(item.get("citazione_centro") or "").strip()
        if not illness or not indication:
            report(name,"indicazione_non_specificata")
            continue
        if facility and facility not in _norm(evidence2):
            report(name,"citazione_centro_non_pertinente")
            continue
        try:
            p1=int(item["pagina_indicazione"])
            p2=int(item["pagina_centro"])
        except (KeyError,ValueError,TypeError):
            report(name,"pagine_non_valide")
            continue
        excerpts={}
        for page in doc.get("passaggi",[]):
            if page.get("pagina") is not None:
                excerpts.setdefault(int(page["pagina"]),[]).append(
                    str(page.get("estratto") or ""))
        mode_ind=_match_quote(
            evidence1," ".join(excerpts.get(p1,[])),"indicazione")
        if not mode_ind:
            report(name,"citazione_indicazione_non_trovata",evidence1)
            continue
        mode_center=_match_quote(
            evidence2," ".join(excerpts.get(p2,[])),"centro",facility)
        if not mode_center:
            report(name,"citazione_centro_non_trovata",evidence2)
            continue
        sources=[str(src).split(" | ",1)[0] for src in doc.get("fonti",[])]
        sources=[src for src in sources if src.endswith("#p"+str(p2))]
        if not sources:
            report(name,"pagina_non_citabile")
            continue
        filename=sources[0].split("#p",1)[0].rsplit("/",1)[-1]
        additions.append(
            "Medicinale: "+name+"\n"
            "- Patologia: "+illness+"\n"
            "- Indicazione: "+indication+"\n"
            "- Fonte/Pagina: "+filename+", pagina "+str(p2))
        inserted.add(name.casefold())
        report(name,"accettato" if
               mode_ind=="letterale" and mode_center=="letterale"
               else "accettato_con_ancore")
    for name in docs:
        if name not in seen_names:
            report(name,"non_proposto_dal_modello")
    return additions
