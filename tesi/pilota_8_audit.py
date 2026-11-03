#!/usr/bin/env python3
"""Preflight e raccolta non valutativa delle otto domande gold.

Nessuna chiamata al provider. Le risposte restano NON VALUTATE finché
un revisore non assegna esplicitamente i giudizi 0/1 dopo i PDF originali.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from tesi.esegui_benchmark import FIELDS, METHODS, verify_snapshot
from tesi.valida_gold import inspect, read

IDS = ("Q05", "Q06", "Q07", "Q08", "Q09", "Q21", "Q28", "Q29")
VALID_OUTCOMES = {"OK", "NESSUNA_EVIDENZA", "NESSUNA_EVIDENZA_SEMANTICA",
                  "NESSUNA_RIGA_SQL", "RISULTATI_PARZIALI"}


def consolidate(rows, snapshot, ids=IDS):
    """Conserva una sola risposta utile per coppia, senza nascondere gli errori.

    I tentativi non riusciti restano nel CSV grezzo. Ripetere una risposta
    gia' valida e' un errore metodologico, non una scelta del risultato migliore.
    """
    allowed = set(ids)
    grouped = defaultdict(list)
    models = set()
    for row in rows:
        if row.get("id") not in allowed:
            raise ValueError("ID non compreso nel lotto dei gold: " + str(row.get("id")))
        if row.get("metodo") not in METHODS:
            raise ValueError("Metodo non riconosciuto")
        if row.get("snapshot_sha256") != snapshot:
            raise ValueError("Snapshot diverso da quello congelato")
        if not row.get("modello", "").strip():
            raise ValueError("Modello mancante in un tentativo")
        models.add(row["modello"].strip())
        if row.get("stato") not in VALID_OUTCOMES | {"QUOTA", "ERRORE"}:
            raise ValueError("Stato di esecuzione non riconosciuto")
        grouped[(row["id"], row["metodo"])].append(row)
    if len(models) > 1:
        raise ValueError("Confronto non omogeneo: modelli LLM diversi")
    cleaned = []
    status_counts = Counter()
    retried = {}
    for key, attempts in grouped.items():
        for attempt in attempts:
            status_counts[attempt["stato"]] += 1
        successes = [a for a in attempts if a["stato"] in VALID_OUTCOMES]
        if len(successes) > 1:
            raise ValueError("Due risposte valide sulla stessa coppia: " + str(key))
        if successes:
            final = dict(successes[0])
            # Nessuna valutazione automatica, neanche dopo un errore precedente.
            if final.get("valutazione_risposta") or final.get("valutazione_citazioni"):
                raise ValueError("I giudizi devono essere compilati solo in revisione manuale")
            cleaned.append(final)
        if len(attempts) > 1:
            retried[key[0] + "/" + key[1]] = len(attempts)
    cleaned.sort(key=lambda x: (IDS.index(x["id"]), METHODS.index(x["metodo"])))
    present = {(r["id"], r["metodo"]) for r in cleaned}
    missing = [{"id": q, "metodo": m} for q in ids for m in METHODS if (q, m) not in present]
    paired = sum(all((q, m) in present for m in METHODS) for q in ids)
    return cleaned, {
        "modello": next(iter(models), None),
        "tentativi_totali": len(rows),
        "stati_tentativi": dict(status_counts),
        "risposte_valide_non_valutate": len(cleaned),
        "coppie_complete": paired,
        "mancanti": missing,
        "tentativi_ripetuti": retried,
        "accuratezza": None,
        "correttezza_citazioni": None,
    }


def audit(db_file, manifest_file, gold_file, responses_file=None, clean_csv=None):
    manifest = verify_snapshot(db_file, manifest_file)
    digest = manifest["sha256_sqlite"]
    questions = read(gold_file)
    if tuple(row["id"] for row in questions) != IDS:
        raise ValueError("Il lotto deve avere esattamente gli otto gold Q05-Q29")
    if any(row["stato_validazione"] != "VALIDATO" or
           row.get("snapshot_sha256") != digest for row in questions):
        raise ValueError("Gold non validati o riferiti ad altro snapshot")
    with closing(sqlite3.connect(Path(db_file).resolve().as_uri() + "?mode=ro",
                                 uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        validation = inspect(questions, db)
    if validation["esito"] != "OK" or validation["validati"] != len(IDS):
        raise ValueError("Le citazioni gold non sono coerenti: " + str(validation["errori"]))
    report = {
        "stato": "PREFLIGHT_OK",
        "generato_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_sha256": digest,
        "snapshot_git_commit": manifest.get("git_commit"),
        "gold_validati": len(IDS),
        "ids": list(IDS),
        "citazioni_gold_verificate_strutturalmente": validation["validati"],
        "nota_validazione": validation["nota"],
        "chiamate_llm_da_questo_script": 0,
    }
    if responses_file is not None:
        with Path(responses_file).open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter=";")
            if reader.fieldnames != FIELDS:
                raise ValueError("Intestazione delle risposte non conforme al runner")
            data = list(reader)
        cleaned, measures = consolidate(data, digest)
        report.update(measures)
        report["stato"] = "RISPOSTE_RACCOLTE_NON_VALUTATE"
        if clean_csv:
            out = Path(clean_csv)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=FIELDS, delimiter=";")
                writer.writeheader()
                writer.writerows(cleaned)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--gold", default="tesi/benchmark_regolatorio_8_validati.csv")
    p.add_argument("--risposte")
    p.add_argument("--csv-consolidato")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = audit(a.db, a.manifest, a.gold, a.risposte, a.csv_consolidato)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
