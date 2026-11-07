"""Raffinamento documentale per TAG automatico: selezione su prove, non liste.

Quando un sem_filter LOTUS per gruppi conserva molti documenti eterogenei,
una sola chiamata LLM aggiuntiva individua gli indici dei singoli documenti
candidati. I PDF restano le uniche fonti: nessuna patologia, farmaco o
struttura specifica è codificata nella selezione.
"""
from __future__ import annotations

import json
import re

MIN_DOCS_FOR_REFINEMENT = 19
MAX_REFINEMENT_DOCS = 220
MAX_REFINEMENT_TEXT_CHARS = 155000
PER_NOTE_EXCERPT_CHARS = 600

REFINEMENT_PROMPT = (
    "Sei un classificatore di PERTINENZA di NOTE REGIONALI, non il generatore "
    "della risposta finale. Ricevi una domanda e un indice di documenti "
    "con passaggi estratti dal testo. Restituisci solo JSON della forma "
    '{"indici":[0,1],"incerto":false}. '
    "Gli indici devono riferirsi ai documenti in input. Seleziona i "
    "documenti che, dal loro contenuto, riguardano le indicazioni o "
    "condizioni cliniche richieste e la struttura oggetto della domanda. "
    "La menzione di una struttura non prova autorizzazione: il controllo "
    "dei centri e delle pagine spetta alla sintesi finale. "
    "Riconosci semanticamente le patologie anche quando sono chiamate "
    "con nomi specifici diversi dal termine generale della domanda. "
    "Non usare elenchi precostituiti di patologie o inferire medicine nuove. "
    "Privilegia il richiamo: in caso di dubbio pertinente, includi "
    "il documento e imposta incerto=true. Non inserire indici estranei; "
    "non superare il massimo esplicitato. Non inventare citazioni o pagine."
)


def _evidence_excerpt(raw, max_chars=PER_NOTE_EXCERPT_CHARS):
    """Campione neutro ma distribuito su pagine/sezioni generiche del PDF."""
    text = str(raw or "")
    pieces = re.split(r"(?=\[pagina\s+\d+\])", text)
    if len(text) <= max_chars:
        return text
    if len(pieces) < 2:
        return (text[:max_chars // 2] + " [...] " +
                text[-(max_chars - max_chars // 2 - 7):])
    prefix = pieces[0][:120]
    pages = pieces[1:]
    per_page = max(35, (max_chars - len(prefix) - 15) // len(pages))
    snippets = [prefix]
    for p in pages:
        if len(p) <= per_page:
            snippets.append(p)
            continue
        head = p[:min(95, per_page // 4)]
        # "Indicazione", "centro" e "prescrizione" sono intestazioni generali
        # delle note, non nomi di farmaci/patologie. Preleva i dintorni dei
        # punti testuali, senza decidere in Python la loro rilevanza clinica.
        matches = list(re.finditer(
            r"indicazion\w*|prescri\w*|centri\b|centro\b|abilitat\w*|"
            r"trattament\w*|presidi\b", p, re.I
        ))
        room = max(0, per_page - len(head) - 12)
        candidates = []
        for m in matches[:2]:
            snippet = p[max(0, m.start()-45):m.start()+max(55, room//2)]
            if snippet not in candidates:
                candidates.append(snippet)
        excerpt = " […] ".join(candidates)
        if not excerpt:
            excerpt = p[-room:]
        snippets.append((head + " […] " + excerpt)[:per_page])
    return ("\n".join(snippets))[:max_chars]


def refinement_payload(documents, question, cap):
    """Prepara l'indice stabile delle note per un unico confronto semantico."""
    if not 1 <= cap <= 220:
        raise ValueError("Cap raffinamento non valido")
    if len(documents) > MAX_REFINEMENT_DOCS:
        return None, "troppi_documenti_per_raffinamento"
    rows = []
    for i, document in enumerate(documents):
        if not str(document.get("chiave","")).startswith("NOTA:"):
            return None, "fonti_non_documentali"
        rows.append({
            "indice":i,
            "documento":document.get("nome_file") or document.get("chiave"),
            "anno":document.get("anno"),
            "passaggi":_evidence_excerpt(
                document.get("testo") or document.get("testo_selezione")
            ),
        })
    payload={"domanda":question,"massimo_documenti":cap,"documenti":rows}
    if len(json.dumps(payload,ensure_ascii=False)) > MAX_REFINEMENT_TEXT_CHARS:
        return None, "indice_documenti_troppo_grande"
    return payload, "ok"


def parse_refinement_result(answer, document_count, cap):
    """Valida gli indici ricevuti dall'LLM, non ammette indici inventati."""
    raw = str(answer or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^\s*```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Risposta di raffinamento non in JSON valido") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Risposta di raffinamento non oggetto JSON")
    chosen = parsed.get("indici")
    uncertain = parsed.get("incerto")
    if (not isinstance(chosen, list) or not isinstance(uncertain, bool)):
        raise ValueError("Campi del raffinamento mancanti o non validi")
    if (len(chosen) > cap or
            any(type(i) is not int or i < 0 or i >= document_count
                for i in chosen)):
        raise ValueError("Il raffinamento ha restituito indici non validi")
    if len(chosen) != len(set(chosen)):
        raise ValueError("Il raffinamento ha duplicato alcuni indici")
    return chosen, uncertain
