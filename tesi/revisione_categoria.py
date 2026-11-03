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


def verified_additions(review_text,missing,question,name_fn):
    """Formatta solo casi esplicitamente sostenuti da due citazioni.

    I controlli verificano l'esistenza dei passi; il loro significato resta
    responsabilità dell'interpretazione semantica del modello.
    """
    raw=str(review_text or "").strip()
    fence=chr(96)*3
    if raw.startswith(fence) and raw.endswith(fence):
        raw=re.sub(r"^"+fence+r"(?:json)?\s*|\s*"+fence+r"$","",raw,flags=re.I)
    try:
        parsed=json.loads(raw)
    except (TypeError,ValueError):
        return []
    if not isinstance(parsed,dict) or not isinstance(parsed.get("nuove_voci"),list):
        return []
    docs={name_fn(doc).casefold():doc for doc in missing if name_fn(doc)}
    requested=re.search(r"\b(?:aou|aorn|irccs)\s+([a-zà-ÿ]{4,})",
                        str(question).casefold())
    facility=requested.group(1) if requested else ""
    inserted=set()
    additions=[]
    for item in parsed["nuove_voci"]:
        if not isinstance(item,dict) or item.get("confermato") is not True:
            continue
        name=str(item.get("medicinale") or "").strip()
        doc=docs.get(name.casefold())
        if not doc or name.casefold() in inserted:
            continue
        illness=str(item.get("patologia") or "").strip()
        indication=str(item.get("indicazione") or "").strip()
        evidence1=str(item.get("citazione_indicazione") or "").strip()
        evidence2=str(item.get("citazione_centro") or "").strip()
        if not illness or not indication or (facility and facility not in _norm(evidence2)):
            continue
        try:
            p1=int(item["pagina_indicazione"])
            p2=int(item["pagina_centro"])
        except (KeyError,ValueError,TypeError):
            continue
        excerpts={}
        for page in doc.get("passaggi",[]):
            if page.get("pagina") is not None:
                excerpts.setdefault(int(page["pagina"]),[]).append(
                    str(page.get("estratto") or ""))
        if not (_quoted(evidence1," ".join(excerpts.get(p1,[])))
                and _quoted(evidence2," ".join(excerpts.get(p2,[])))):
            continue
        sources=[str(src).split(" | ",1)[0] for src in doc.get("fonti",[])]
        sources=[src for src in sources if src.endswith("#p"+str(p2))]
        if not sources:
            continue
        filename=sources[0].split("#p",1)[0].rsplit("/",1)[-1]
        additions.append(
            "Medicinale: "+name+"\n"
            "- Patologia: "+illness+"\n"
            "- Indicazione: "+indication+"\n"
            "- Fonte/Pagina: "+filename+", pagina "+str(p2))
        inserted.add(name.casefold())
    return additions
