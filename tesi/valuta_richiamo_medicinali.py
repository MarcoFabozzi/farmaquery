#!/usr/bin/env python3
"""Misura la copertura dei NOMI in un pilot; non attribuisce accuracy semantica."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _names(values, label):
    if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
        raise ValueError(label + ": elenco nomi non valido")
    cleaned = [v.strip().upper() for v in values]
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(label + ": nomi duplicati")
    return set(cleaned)


def evaluate(reference: dict, observations: dict) -> dict:
    if reference.get("schema") != 1 or observations.get("schema") != 1:
        raise ValueError("Schema non riconosciuto")
    digest = reference.get("snapshot_sha256")
    if not digest or observations.get("snapshot_sha256_riferimento") != digest:
        raise ValueError("Hash del riferimento non coincidente")
    if observations.get("stato") != "PILOTA_ESPLORATIVO_NON_USARE_PER_ACCURATEZZA_BENCHMARK":
        raise ValueError("Solo pilot esplorativi, non benchmark ufficiali")
    positives = reference["casi_positivi"]
    if not isinstance(positives, list) or not positives:
        raise ValueError("Riferimento vuoto")
    all_items = _names([x["medicinale"] for x in positives], "gold")
    core = _names([x["medicinale"] for x in positives if x["perimetro"] == "core"], "core")
    extended = _names([x["medicinale"] for x in positives if x["perimetro"] in ("core", "esteso")], "esteso")
    strict = _names([x["medicinale"] for x in positives
                     if x["perimetro"] == "core" and
                     x["relazione_prova"] != "RINVIO_ESPLICITO_AGGIORNAMENTO_STESSI_CENTRI"], "core_stretto")
    if len(core) != reference.get("conta_core") or len(extended) != reference.get("conta_esteso") or extended != all_items:
        raise ValueError("Conteggi gold incoerenti")
    scopes = {"core": core, "core_senza_rinvii": strict, "esteso": extended}
    runs = observations.get("risultati", [])
    if len(runs) != 2 or {r.get("metodo") for r in runs} != {"TAG", "Text-to-SQL"}:
        raise ValueError("Servono una osservazione TAG e una Text-to-SQL")
    methods = {}
    raw = {}
    for run in runs:
        name = run["metodo"]
        predicted = _names(run.get("nomi_medicinali"), name)
        raw[name] = predicted
        per_scope = {}
        for scope, expected in scopes.items():
            hits = predicted & expected
            per_scope[scope] = {
                "totale_gold": len(expected),
                "nomi_riportati": len(predicted),
                "corrispondenze_nomi": len(hits),
                "copertura_nomi": round(len(hits) / len(expected), 4),
                "nomi_riscontrati": sorted(hits),
                "nomi_mancanti": sorted(expected - predicted),
                "nomi_fuori_perimetro": sorted(predicted - expected),
            }
        methods[name] = {
            "tempo_secondi_riportato_non_verificato": run.get("tempo_secondi_riportato"),
            "casi": per_scope,
            "errori_documentali_verificati_nel_resoconto": run.get("errori_documentali_verificati", []),
        }
    union = raw["TAG"] | raw["Text-to-SQL"]
    intersection = raw["TAG"] & raw["Text-to-SQL"]
    return {
        "stato": observations["stato"],
        "snapshot_sha256_riferimento": digest,
        "validazione_esecuzioni_stesso_commit_e_snapshot": False,
        "metrica": "Copertura dei nomi, NON accuratezza completa della risposta",
        "metodi": methods,
        "confronto_core": {
            "presenti_in_entrambi": sorted(intersection & core),
            "solo_tag": sorted((raw["TAG"] - raw["Text-to-SQL"]) & core),
            "solo_text_to_sql": sorted((raw["Text-to-SQL"] - raw["TAG"]) & core),
            "non_riportati_da_nessuno": sorted(core - union),
            "copertura_unione": round(len(core & union) / len(core), 4),
            "vantaggio_tag_punti_percentuali": round(
                100 * (len(raw["TAG"] & core) - len(raw["Text-to-SQL"] & core)) / len(core), 2
            ),
        },
        "avvertenze": observations.get("verifiche_non_disponibili", []),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="tesi/riferimento_neuromuscolari_federico_ii_2026-11-03.json")
    parser.add_argument("--osservazioni", default="tesi/pilota_neuromuscolari_2026-11-03.json")
    parser.add_argument("--out")
    args = parser.parse_args()
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    observations = json.loads(Path(args.osservazioni).read_text(encoding="utf-8"))
    report = json.dumps(evaluate(gold, observations), ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
