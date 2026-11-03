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
    "neuromuscolari. Riporta medicinale, patologia, struttura, PDF e pagina "
    "per ciascun caso documentato. Non inventare centri, non usare fonti "
    "esterne, non confondere un richiamo con un'abrogazione. "
    "Se qualche relazione manca, esplicita il limite invece di inventarla. "
    "Non dichiarare che un medicinale È ESCLUSO da Federico II sulla sola "
    "assenza nelle pagine selezionate: le evidenze possono essere parziali. "
    "Non limitarti ai primi due documenti: valuta ciascun candidato. "
    "Quando una nota comprende PIÙ indicazioni (per esempio una "
    "neurologica centrale e una neuromuscolare), interpreta separatamente "
    "la tabella dei centri associata a ciascuna indicazione. "
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


def revise_category_if_needed(model,question,answer,compact,ask_fn):
    """Riesamina i documenti omessi senza promuovere candidati a risultati.

    Esegue al massimo UNA chiamata supplementare; nessun nome, patologia o
    autorizzazione è precodificato come fatto. Una seconda risposta non deve
    perdere i medicinali già elencati nella prima.
    """
    missing=missing_category_candidates(answer,compact)
    if not missing:
        return answer,None,False,[]
    originally_listed={_candidate_short_name(doc).casefold()
                       for doc in compact
                       if _candidate_short_name(doc) and
                       _candidate_listed(answer,_candidate_short_name(doc))}
    context={
        "domanda":question,
        "documenti_candidati_non_elencati":missing,
        "avviso":"Documenti candidati NON equivalgono a prescrizioni provate. "
                 "Si devono verificare indicazione, centro e pagina insieme.",
    }
    revised,usage=ask_fn(
        model,
        "Esamina in autonomia SOLO i documenti candidati non elencati. "
        "Valuta ciascun medicinale separatamente. Controlla se il centro "
        "richiesto appartiene alla sezione della stessa indicazione, "
        "senza confondere tabelle di malattie diverse. "
        "Non dedurre un'autorizzazione dalla mera menzione del centro. "
        "Rispondi SOLO con JSON: un oggetto con 'nuove_voci' (array). "
        "Includi un candidato soltanto quando la relazione è dimostrata. "
        "Per ogni caso positivo usa le chiavi: 'confermato' (true), "
        "'medicinale', 'patologia', 'indicazione', "
        "'pagina_indicazione' e 'pagina_centro' (numeri), "
        "'citazione_indicazione' e 'citazione_centro'. "
        "Le citazioni devono essere stringhe letterali contigue dei "
        "passaggi forniti, di almeno 16 caratteri: la seconda deve "
        "contenere il nome del centro richiesto. Non riscrivere "
        "i medicinali della risposta precedente. Quando non emerge "
        "una prova sufficiente, restituisci un array vuoto. "
        "Non usare fonti esterne o risposte gold.",
        context,timeout=CATEGORY_RESPONSE_TIMEOUT_SECONDS,max_tokens=1750
    )
    additions=verified_additions(revised,missing,question,_candidate_short_name)
    if additions:
        answer=answer.rstrip()+"\n\n"+"\n\n".join(additions)
    return answer,usage,True,[_candidate_short_name(d) for d in missing ]
