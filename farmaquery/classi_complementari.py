"""Riferimenti C(nn) storici AIFA; mai classificazione corrente automatica.

Il CSV 2026 contiene un identificativo AIC del *medicinale* (5/6 cifre),
non il codice univoco della confezione (9 cifre). Sono quindi permesse
solo corrispondenze di prefisso AIC + nome medicinale normalizzato,
presentate SEMPRE come evidenza storica.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
import unicodedata

CNN_FILE = "aifa_riferimenti_cnn.json"


def normalizza_nome(value):
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def prefisso_aic(value):
    text = str(value or "").strip()
    return text.zfill(6) if re.fullmatch(r"\d{5,6}", text) else None


def costruisci_indice_cnn(records, data_riferimento, fonte, output):
    date.fromisoformat(data_riferimento)
    if not str(fonte.get("url", "")).startswith("https://www.aifa.gov.it/"):
        raise ValueError("Fonte C(nn) non ufficiale")
    if not re.fullmatch(r"[0-9a-f]{64}", str(fonte.get("sha256", ""))):
        raise ValueError("SHA-256 del CSV C(nn) mancante")
    by_prefix = {}
    n = 0
    for record in records:
        raw = record.get("raw_json")
        if not isinstance(raw, str):
            continue
        dettagli = json.loads(raw)
        if not isinstance(dettagli, dict):
            continue
        base = prefisso_aic(dettagli.get("aic_farmaco"))
        nome = str(record.get("nome", "")).strip()
        proc = str(record.get("numero_procedura", "")).strip()
        if not base or not normalizza_nome(nome) or not proc:
            continue
        item = {
            "nome": nome, "numero_procedura": proc,
            "principio_attivo": str(record.get("principio_attivo") or ""),
            "riferimento_atto": str(record.get("riferimento_atto") or ""),
            "data_provvedimento": str(dettagli.get("data_provvedimento") or ""),
        }
        group = by_prefix.setdefault(base, [])
        if item not in group:
            group.append(item)
            n += 1
    if n < 100:
        raise ValueError("Indice C(nn) insufficiente: controllare il formato AIFA")
    obj = {
        "schema": 1,
        "data_riferimento_file": data_riferimento,
        "fonte": {"url": fonte["url"], "sha256": fonte["sha256"]},
        "nota": "Presenza storica in elenco AIFA C(nn) al livello del medicinale; "
                "non certifica la classe vigente o una specifica confezione.",
        "record_indicizzati": n, "per_codice_medicinale": by_prefix,
    }
    dest = Path(output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    return {"file_indice": dest.name, "record_indicizzati": n,
            "codici_medicinale": len(by_prefix),
            "data_riferimento_file": data_riferimento}


def leggi_indice_cnn(path):
    file = Path(path)
    if file.stat().st_size > 4_000_000:
        raise ValueError("Indice C(nn) troppo grande")
    data = json.loads(file.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("per_codice_medicinale"), dict):
        raise ValueError("Indice C(nn) non valido")
    date.fromisoformat(data["data_riferimento_file"])
    if not str(data.get("fonte", {}).get("url", "")).startswith("https://www.aifa.gov.it/"):
        raise ValueError("Fonte C(nn) non ufficiale")
    for codice, gruppi in data["per_codice_medicinale"].items():
        if not re.fullmatch(r"\d{6}", codice) or not isinstance(gruppi, list):
            raise ValueError("Codice medicinale C(nn) non valido")
        if any(not isinstance(item, dict) or not normalizza_nome(item.get("nome"))
               for item in gruppi):
            raise ValueError("Voce C(nn) non valida")
    return data


def riferimenti_cnn(indice, aic, nome):
    """Riscontri *storici*, soltanto con prefisso E nome esatti."""
    if not indice or not re.fullmatch(r"\d{9}", str(aic or "")):
        return []
    matches = indice["per_codice_medicinale"].get(str(aic)[:6], [])
    norm = normalizza_nome(nome)
    if not norm:
        return []
    return [dict(item, data_riferimento_file=indice["data_riferimento_file"],
                 fonte_url=indice["fonte"]["url"])
            for item in matches if normalizza_nome(item["nome"]) == norm]


def etichetta_cnn_storica(riferimenti):
    if not riferimenti:
        return "N/D"
    date_ref = date.fromisoformat(riferimenti[0]["data_riferimento_file"])
    return "C(nn) (storica " + date_ref.strftime("%d/%m/%Y") + ")"


def classe_con_fonti(registry_class, ah, evento, cnn_matches):
    """Ordine prudenziale: classi esplicite AIFA > A/H > atto verificato > Cnn storica."""
    explicit = str(registry_class or "").strip().upper().replace(" ", "")
    if explicit in ("A", "H", "C"):
        return explicit + " (anagrafica AIFA)"
    if explicit in ("C(NN)", "CNN"):
        return "C(nn) (anagrafica AIFA)"
    if ah:
        from datetime import date as _date
        cls,ref = ah
        return cls + " (lista " + _date.fromisoformat(ref).strftime("%d/%m/%Y") + ")"
    if evento:
        cls = evento["classe_nuova"]
        if cls in ("C", "C(nn)"):
            ref = _date_from_iso(evento["data_pubblicazione"])
            return cls + " (atto storico sul medicinale " + ref + ")"
    if cnn_matches:
        return etichetta_cnn_storica(cnn_matches)
    return "N/D"


def classe_sintetica_demo(etichetta_evidenza):
    """Tre sole categorie per la UI; C residuale, NON dato AIFA ufficiale.

    La classificazione dettagliata resta intatta per audit e benchmark.
    Nessuna classe C derivata qui va scritta nel database regolatorio.
    """
    testo = str(etichetta_evidenza or "")
    if testo.startswith("A ("):
        return "A"
    if testo.startswith("H ("):
        return "H"
    return "C"


def _date_from_iso(val):
    try:
        return date.fromisoformat(str(val)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return "data n.d."
