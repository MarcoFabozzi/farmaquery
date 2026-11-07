"""Raffinamento documentale per TAG automatico: selezione su prove, non liste.

Quando un sem_filter LOTUS per gruppi conserva documenti eterogenei,
il raffinamento opera in piccoli lotti indipendenti, ciascuno con un limite
esplicito di contesto, per selezionare gli indici di ogni singolo documento. I PDF restano le uniche fonti: nessuna patologia, farmaco o
struttura specifica è codificata nella selezione.
"""
from __future__ import annotations

import json
import re

MIN_DOCS_FOR_REFINEMENT = 19
MAX_REFINEMENT_DOCS = 240
REFINEMENT_BATCH_SIZE = 20
MAX_REFINEMENT_BATCHES = 12
MAX_REFINEMENT_TEXT_CHARS = 48000
PER_NOTE_EXCERPT_CHARS = 1450

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
    "Questa e' una classificazione ad alto richiamo: non scartare una nota "
    "solo perche' una pagina descrive la patologia e un'altra descrive "
    "il centro. Quando i passaggi sono abbreviati, segnala incerto=true "
    "e includi il documento se la pertinenza e' plausibile. "
    "Non usare elenchi precostituiti di patologie o inferire medicine nuove. "
    "Privilegia il richiamo: in caso di dubbio pertinente, includi "
    "il documento e imposta incerto=true. Valuta ogni documento del lotto "
    "indipendentemente dagli altri. Non inserire indici estranei; "
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
        # Campione della pagina: testa, coda e due punti vicino a
        # intestazioni generiche (la prima e l'ultima). Non contiene
        # elenchi di patologie o nomi di strutture preimpostati.
        head_chars = max(8, min(75, per_page//5))
        tail_chars = max(8, min(95, per_page//4))
        head, tail = p[:head_chars], p[-tail_chars:]
        budget = max(0, per_page - len(head)-len(tail)-10)
        matches = list(re.finditer(
            r"indicazion\w*|prescri\w*|centri\b|centro\b|abilitat\w*|"
            r"trattament\w*|presidi\b", p, re.I
        ))
        locations = []
        if matches:
            locations = [matches[0]]
            if matches[-1].start() != matches[0].start():
                locations.append(matches[-1])
        parts = []
        for m in locations:
            length = max(0, budget//len(locations)-3)
            if not length:
                break
            begin = max(0, m.start()-25)
            parts.append(p[begin:begin+length])
        middle = " […] ".join(parts)
        piece = (head + " […] " + middle + " […] " + tail
                 if middle else head + " […] " + tail)
        snippets.append(piece[:per_page])
    return ("\n".join(snippets))[:max_chars]


def refinement_payload(documents, question, cap, offset=0):
    """Indice dei documenti di UN lotto: indici locali da 0 a N-1."""
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
    payload={
        "domanda":question, "indice_globale_inizio":offset,
        "massimo_documenti":cap, "documenti":rows
    }
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



def refinement_batches(documents, batch_size=REFINEMENT_BATCH_SIZE):
    """Lotti stabili, senza perdere note né attraversare i limiti SQL.

    L'ordine di input viene preservato: gli indici nel JSON sono locali
    e vanno ricondotti al pool originale tramite offset.
    """
    if not 1 <= batch_size <= REFINEMENT_BATCH_SIZE:
        raise ValueError("Dimensione lotto non consentita")
    if len(documents) > MAX_REFINEMENT_DOCS:
        raise ValueError("Numero di documenti oltre il limite di sicurezza")
    chunks = [(i, documents[i:i+batch_size])
              for i in range(0,len(documents),batch_size)]
    if len(chunks)>MAX_REFINEMENT_BATCHES:
        raise ValueError("Numero di lotti oltre il limite di sicurezza")
    return chunks
