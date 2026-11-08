"""Recupero documentale in due fasi per TAG automatico.

Fase 1: una SELECT ad alto richiamo + classificazione semantica per nota.
Fase 2: una seconda SELECT limitata agli ID selezionati + controllo LOTUS e
verifica strutturata delle prove centro/indicazione/pagina.

Le funzioni qui sono prive di dipendenze dal provider LLM: il motore inietta
gli esecutori e misura ogni chiamata. Nessun dizionario di patologie o farmaci.
"""
from __future__ import annotations

import json
import re

from sqlglot import exp, parse_one

from tesi.piano_documentale import document_center_anchors

MAX_SECOND_STAGE_NOTES = 55
TARGET_FINAL_VERIFY_BATCH_SIZE = 3
MAX_FINAL_VERIFY_BATCHES = 8


def final_verification_batches(documents):
    """Suddivide la verifica finale in lotti disgiunti e con budget massimo.

    Per pochi documenti usa lotti di tre; per insiemi maggiori amplia
    gradualmente i lotti, evitando un numero incontrollato di invii LLM.
    Indici locali del verificatore, zero duplicazioni o omissioni.
    """
    if not isinstance(documents, list) or not documents:
        raise ValueError("Nessun documento per la verifica finale")
    if len(documents)>MAX_SECOND_STAGE_NOTES:
        raise ValueError("Troppi documenti per la verifica finale")
    batch_size=max(
        TARGET_FINAL_VERIFY_BATCH_SIZE,
        (len(documents)+MAX_FINAL_VERIFY_BATCHES-1)//MAX_FINAL_VERIFY_BATCHES
    )
    batches=[
        (offset,documents[offset:offset+batch_size])
        for offset in range(0,len(documents),batch_size)
    ]
    if (len(batches)>MAX_FINAL_VERIFY_BATCHES or
            sum(len(batch) for _,batch in batches)!=len(documents)):
        raise ValueError("Copertura lotti verifica non completa")
    return batches


DISCOVER_PROMPT = (
    "Fase 1 di un recupero documentale. Sei un classificatore di NOTE, "
    "non l'autore della risposta. Restituisci SOLO JSON della forma "
    '{"indici":[0,1],"incerto":false}. '
    "Valuta ogni documento individualmente. Seleziona quelli che "
    "contengono un medicinale e una patologia/indicazione appartenente "
    "semanticamente alla CATEGORIA richiesta dall'utente. "
    "NON cercare soltanto la parola della categoria e non inventare "
    "elenchi fissi di malattie o sinonimi. NON richiedere ancora che il "
    "centro prescrittore sia attestato: quella verifica avverra' "
    "nella seconda fase. Se un documento e' plausibilmente pertinente "
    "ma l'estratto e' limitato, includilo e imposta incerto=true. "
    "Gli indici sono quelli LOCALI del lotto fornito, mai inventati. "
    "Non usare nomi di farmaci non presenti nei documenti."
)

STAGE2_LOTUS_PROMPT = (
    "Questo gruppo di note regionali {testo} potrebbe comprovare, "
    "per la domanda {domanda}, un medicinale per una determinata "
    "indicazione e un centro prescrittore specifico. Conserva il gruppo "
    "se contiene potenziali prove DOCUMENTALI dell'associazione "
    "medicinale-indicazione-centro, anche distribuite su pagine diverse. "
    "Una mera menzione del centro non e' un'autorizzazione. "
    "Non aggiungere sinonimi o diagnosi precostituite; la verifica "
    "puntuale finale decide sui documenti."
)

VERIFY_PROMPT = (
    "Fase 2 di verifica documentale per un elenco di farmaci. Usa SOLO "
    "le evidenze in input e la domanda. "
    "Esamina OGNI documento del lotto indipendentemente, senza "
    "sceglierne solo i piu' evidenti o limitarne arbitrariamente il numero. "
    "Per ogni medicinale registra una "
    "coppia indicazione-centro SOLTANTO se la NOTA individua realmente "
    "la struttura richiesta come centro di prescrizione per QUELLA "
    "indicazione; non basta menzionare la struttura o parlare del farmaco "
    "in un'altra indicazione. Identifica nome del medicinale dal testo "
    "anche se diverso dal titolo del PDF. Le pagine devono corrispondere "
    "ai marcatori [pagina N] nel documento. Non inventare dati, "
    "pagine, centri o medicinali. "
    "Rispondi SOLO con un oggetto JSON: "
    '{"verificati":[{"documento_indice":0,"medicinale":"...",'
    '"indicazione":"...","pagina_indicazione":1,"pagina_centro":2}],'
    '"incerto":false}. '
    "documento_indice e' l'indice della scheda nell'input e le pagine "
    "sono interi positivi. Se nessuna prova e' adeguata, restituisci "
    '"verificati":[]; imposta incerto=true per incertezza o prove troncate. '
    "Gli indici dei documenti sono LOCALI al lotto ricevuto. "
    "Se una nota contiene piu' medicinali, verifica separatamente ciascuno; "
    "se non emergono associazioni supportate, restituisci verificati vuoto. "
    "Non affermare completezza rispetto a tutti i PDF non consultati."
)


def _unbox(node):
    while isinstance(node,(exp.Paren,exp.Collate)):
        node=node.this
    return node


def semantic_filter_warning(sql, question):
    """Segnale oggettivo: SELECT per note/centro usa LIKE clinici restrittivi.

    Non prova incompletezza. Serve a NON equiparare SQL non vuota a una
    ricerca esaustiva quando l'LLM applica filtri lessicali su patologie
    o nomi dei medicinali.
    """
    anchors = document_center_anchors(sql,question)
    if not anchors:
        return None
    try:
        tree=parse_one(sql,read="sqlite")
    except Exception:
        return None
    if not isinstance(tree,exp.Select):
        return None
    # Gli ancoraggi centro sono valori literal del WHERE: i rimanenti
    # LIKE sul documento sono restrizioni lessicali, non criteri
    # semanticamente verificati da LOTUS.
    anchor_set={a.casefold() for a in anchors}
    where=tree.args.get("where")
    if where is None:
        return None
    for match in where.find_all(exp.Like):
        target=_unbox(match.this)
        pattern=_unbox(match.expression)
        if not isinstance(pattern,exp.Literal) or not pattern.is_string:
            continue
        value=str(pattern.this).strip("%").casefold()
        if value in anchor_set or not value:
            continue
        if isinstance(target,exp.Column) and target.name.casefold() in {
                "testo","farmaco_candidato","indicazione_candidata"}:
            return "filtro_lessicale_non_esaustivo_su_documenti"
    return None


def sql_second_stage(ids):
    """Seconda SELECT: recupero per gli ID emersi solo da fase 1."""
    ids=list(dict.fromkeys(str(value) for value in ids))
    if not ids or len(ids)>MAX_SECOND_STAGE_NOTES:
        raise ValueError("Numero di note da verificare non valido")
    if any(not value.strip() or len(value)>180 for value in ids):
        raise ValueError("Identificativo nota non valido")
    values=",".join(exp.Literal.string(x).sql(dialect="sqlite") for x in ids)
    return (
        "SELECT DISTINCT n.id AS nota_id FROM note AS n "
        "JOIN pagine AS p ON p.nota_id=n.id "
        "WHERE n.id IN ("+values+")"
    )


def _parse_json(raw):
    text=str(raw or "").strip()
    if text.startswith("```"):
        text=re.sub(r"^\s*```(?:json)?\s*","",text,flags=re.I)
        text=re.sub(r"\s*```\s*$","",text)
    try:
        obj=json.loads(text)
    except (TypeError,ValueError) as exc:
        raise ValueError("JSON di verifica non valido") from exc
    if not isinstance(obj,dict):
        raise ValueError("La verifica non e' un oggetto JSON")
    return obj


def verified_document_pairs(raw, documents, db, center):
    """Controllo deterministico di identita', pagine e centro sulle fonti.

    La correttezza semantica dell'abilitazione non si puo' dimostrare con una
    regexp, ma non si accettano documenti, medicinali o pagine inventati.
    Una risposta malformata non viene trasformata in una falsa assenza.
    """
    obj=_parse_json(raw)
    records=obj.get("verificati")
    uncertain=obj.get("incerto")
    if not isinstance(records,list) or type(uncertain) is not bool:
        raise ValueError("Campi verifica mancanti")
    if len(records)>80:
        raise ValueError("Troppe asserzioni per un singolo contesto")
    terms=re.findall(r"[^\W\d_]{5,}",center,flags=re.UNICODE)
    if not terms:
        raise ValueError("Centro richiesto privo di termini ricercabili")
    anchor=max(terms,key=len).casefold()
    valid=[]
    keys=set()
    for item in records:
        if not isinstance(item,dict):
            raise ValueError("Elemento non strutturato")
        idx=item.get("documento_indice")
        drug=item.get("medicinale")
        indication=item.get("indicazione")
        p_center=item.get("pagina_centro")
        p_indication=item.get("pagina_indicazione")
        if (type(idx) is not int or idx<0 or idx>=len(documents) or
                not isinstance(drug,str) or len(drug.strip())<3 or
                not isinstance(indication,str) or len(indication.strip())<4 or
                type(p_center) is not int or p_center<1 or
                type(p_indication) is not int or p_indication<1):
            raise ValueError("Riferimento a nota, pagina o medicinale invalido")
        doc=documents[idx]
        note_id=doc.get("nota_id")
        rows=db.execute(
            "SELECT numero_pagina,testo FROM pagine "
            "WHERE nota_id=? AND numero_pagina IN (?,?) "
            "AND metodo IN ('TESTO','OCR')",
            (note_id,p_center,p_indication)
        ).fetchall()
        pages={int(x["numero_pagina"]):str(x["testo"] or "") for x in rows}
        if p_center not in pages or p_indication not in pages:
            raise ValueError("La pagina non esiste nello snapshot")
        if anchor not in pages[p_center].casefold():
            raise ValueError("La pagina indicata non menziona la struttura")
        # Controllo lessicale MINIMO della patologia sulla pagina citata.
        # Non usa alcuna tassonomia clinica: impedisce semplicemente
        # che la verifica inventi un'indicazione del tutto estranea.
        generic={
            "trattamento","terapia","medicinale","farmaco","pazienti",
            "paziente","adulti","adulto","malattia","malattie",
            "indicazione","terapeutica","terapeutico","sindrome",
            "della","delle","degli","nella","nelle","del","con","per"
        }
        words=[
            w.casefold() for w in re.findall(
                r"[^\W\d_]{4,}",indication,flags=re.UNICODE
            ) if w.casefold() not in generic
        ]
        if not words or not any(
            w in pages[p_indication].casefold() for w in words
        ):
            raise ValueError("Indicazione non supportata dalla pagina citata")
        medicine=drug.strip()
        drug_lower=medicine.casefold()
        # Il nome deve figurare nel testo PDF o nel nome della nota.
        if (drug_lower not in str(doc.get("testo") or "").casefold()
                and drug_lower not in str(doc.get("nome_file") or "").casefold()):
            # La lettura di pagina in tag_automatico tronca testi molto lunghi.
            # Qui consultiamo il testo originale di tutte le pagine.
            full_pages=db.execute(
                "SELECT testo FROM pagine WHERE nota_id=? "
                "AND metodo IN ('TESTO','OCR')",
                (note_id,)
            ).fetchall()
            if not any(drug_lower in str(p["testo"] or "").casefold()
                       for p in full_pages):
                raise ValueError("Medicinale assente dalla nota")
        key=(str(note_id),drug_lower,indication.casefold(),p_center)
        if key in keys:
            continue
        keys.add(key)
        source=next((x for x in doc.get("fonti",[])
                     if "#p"+str(p_center)+" " in x),None)
        if not source:
            raise ValueError("Fonte originale della pagina mancante")
        valid.append({
            "nota_id":note_id,
            "medicinale":medicine,
            "indicazione":indication.strip(),
            "documento":doc.get("nome_file"),
            "pagina_centro":p_center,
            "pagina_indicazione":p_indication,
            "fonte":source,
        })
    return valid,uncertain


def audit_verified_document_pairs(raw, documents, db, center):
    """Valida ogni asserzione indipendentemente e rende visibile il motivo.

    Il modello puo' produrre sia coppie supportate sia riferimenti
    sbagliati. Un singolo errore non deve cancellare prove indipendenti,
    ma nessuna coppia respinta deve arrivare alla risposta.

    Un JSON non valido o un contratto globale incompleto rimangono errori:
    non vengono interpretati come una lista vuota di associazioni.
    Non invia richieste LLM e non modifica le regole di verifica.
    """
    obj=_parse_json(raw)
    items=obj.get("verificati")
    uncertain=obj.get("incerto")
    if (not isinstance(items,list) or type(uncertain) is not bool
            or len(items)>80):
        raise ValueError("Campi verifica mancanti o numero eccessivo")
    valid=[]
    discarded=[]
    reasons={}
    seen=set()
    for position,item in enumerate(items):
        singleton=json.dumps(
            {"verificati":[item],"incerto":uncertain},
            ensure_ascii=False
        )
        try:
            passed,_=verified_document_pairs(
                singleton,documents,db,center
            )
        except ValueError as exc:
            # Solo ragioni strutturate prodotte dal validatore locale;
            # mai il testo integrale della risposta dell'LLM.
            reason=str(exc)
            reasons[reason]=reasons.get(reason,0)+1
            record={"posizione":position,"motivo":reason}
            if isinstance(item,dict):
                idx=item.get("documento_indice")
                if type(idx) is int and 0<=idx<len(documents):
                    record["documento"]=documents[idx].get("nome_file")
            discarded.append(record)
            continue
        for entry in passed:
            key=(
                str(entry["nota_id"]),
                str(entry["medicinale"]).casefold(),
                str(entry["indicazione"]).casefold(),
                int(entry["pagina_centro"]),
            )
            if key not in seen:
                seen.add(key)
                valid.append(entry)
    audit={
        "asserzioni_verifica_proposte":len(items),
        "asserzioni_verifica_accettate":len(valid),
        "asserzioni_verifica_respinte":len(discarded),
        "motivi_rifiuto_verifica":dict(sorted(reasons.items())),
        "dettagli_rifiuto_verifica":discarded[:30],
    }
    return valid, bool(uncertain or discarded), audit


def format_verified_pairs(rows):
    """Sintesi deterministica, senza ulteriore generazione di fatti."""
    if not rows:
        return "Non sono state individuate associazioni medicinale-indicazione-centro verificabili nelle evidenze selezionate."
    lines=["Le note regionali consultate documentano le seguenti "
           "associazioni con il centro richiesto:"]
    for i,row in enumerate(rows,1):
        lines.append(
            "\n"+str(i)+". **"+row["medicinale"]+"** — "+
            row["indicazione"]+". Documento: **"+
            str(row["documento"])+"**, pagina del centro prescrittore **"+
            str(row["pagina_centro"])+"** (indicazione: pagina "+
            str(row["pagina_indicazione"])+")."
        )
    return "\n".join(lines)
