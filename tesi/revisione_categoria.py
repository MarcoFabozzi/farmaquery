"""Controllo delle integrazioni TAG per categorie implicite.

Nessuna lista gold: le prove testuali vengono controllate contro i passaggi
dello stesso snapshot che ha alimentato la sintesi.
"""
import json
import re
import unicodedata


def _norm(value):
    value=unicodedata.normalize("NFKC",str(value)).casefold()
    return " ".join(re.findall(r"[^\W_]+",value))


def _quoted(quote,text):
    q=_norm(quote)
    return len(q)>=16 and q in _norm(text)


def verified_additions(review_text,missing,question,name_fn,diagnostics=None):
    """Formatta solo casi esplicitamente sostenuti da due citazioni.

    I controlli verificano l'esistenza dei passi; il loro significato resta
    responsabilità dell'interpretazione semantica del modello.
    """
    def report(name,reason):
        if diagnostics is not None:
            diagnostics.append({"medicinale":str(name),"esito":reason})

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
        if not _quoted(evidence1," ".join(excerpts.get(p1,[]))):
            report(name,"citazione_indicazione_non_trovata")
            continue
        if not _quoted(evidence2," ".join(excerpts.get(p2,[]))):
            report(name,"citazione_centro_non_trovata")
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
        report(name,"accettato")
    for name in docs:
        if name not in seen_names:
            report(name,"non_proposto_dal_modello")
    return additions
