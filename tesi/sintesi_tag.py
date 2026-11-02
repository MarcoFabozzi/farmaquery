"""Contesto breve e tracciabile per la sintesi TAG su categorie implicite.

Riduce il testo passato alla *seconda* chiamata LLM, dopo il filtro LOTUS.
Non effettua ricerche ulteriori e non inventa risposte. Conserva esplicitamente
le fonti e i numeri di pagina dei documenti realmente selezionati.
"""
from __future__ import annotations

import re

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
    "neuromuscolari. Riporta medicinale, patologia, struttura, PDF e pagina "
    "per ciascun caso documentato. Non inventare centri, non usare fonti "
    "esterne, non confondere un richiamo con un'abrogazione. "
    "Se qualche relazione manca, esplicita il limite invece di inventarla. "
    "Non dichiarare che un medicinale È ESCLUSO da Federico II sulla sola "
    "assenza nelle pagine selezionate: le evidenze possono essere parziali. "
    "Non limitarti ai primi due documenti: valuta ciascun candidato. "
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
