#!/usr/bin/env python3
"""Audit del benchmark 30: stessa fotografia, fonti disponibili, gold documentati.

Non invoca LLM e non trasforma l'assenza di risultati in una classificazione
ufficiale oppure in una risposta negativa già verificata.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import csv
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from tesi.valida_gold import inspect

CATEGORIES = {
    "CONTROLLO": 4,
    "INTERPRETAZIONE": 7,
    "MULTIFONTE": 7,
    "TEMPORALE": 5,
    "NEGATIVA": 4,
    "RIMANDI": 3,
}
SOURCES = {"EMA", "AIFA", "REGIONE"}
EXPECTED_COLUMNS = {
    "id", "categoria", "domanda", "medicinale", "fonti_previste",
    "criterio_verifica", "risposta_gold", "fonti_gold",
    "stato_validazione", "note_revisore", "snapshot_sha256",
    "origine_validazione",
}


def load_benchmark(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        if not reader.fieldnames or not EXPECTED_COLUMNS <= set(reader.fieldnames):
            raise ValueError("Benchmark 30: colonne mancanti")
        rows = list(reader)
    if len(rows) != 30 or [r["id"] for r in rows] != [
        f"Q{i:02d}" for i in range(1, 31)
    ]:
        raise ValueError("Benchmark 30: servono esattamente gli ID Q01-Q30")
    if Counter(r["categoria"] for r in rows) != CATEGORIES:
        raise ValueError("Distribuzione delle categorie non conforme al protocollo")
    for row in rows:
        if not row["domanda"].strip() or not row["criterio_verifica"].strip():
            raise ValueError(row["id"] + ": domanda o criterio mancante")
        sources = set(row["fonti_previste"].split("+"))
        if not sources or not sources <= SOURCES:
            raise ValueError(row["id"] + ": fonti non consentite")
        if row["stato_validazione"] != "VALIDATO" and (
            row["risposta_gold"].strip() or row["fonti_gold"].strip()
        ):
            raise ValueError(row["id"] + ": gold compilato senza validazione")
        if row["categoria"] == "NEGATIVA" and row["stato_validazione"] == "VALIDATO":
            raise ValueError("Quesito negativo: richiede prima audit umano esaustivo")
    return rows


def sha_file(path):
    digest = sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def audit(benchmark, db_path, manifest_path):
    rows = load_benchmark(benchmark)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    expected = manifest["sha256_sqlite"]
    if sha_file(db_path) != expected:
        raise ValueError("Lo SQLite non coincide con l'hash del manifesto")
    if any(r["snapshot_sha256"] != expected for r in rows):
        raise ValueError("Il benchmark si riferisce a un altro snapshot: non mescolare le fotografie")

    report = {
        "snapshot_sha256": expected,
        "data_congelamento": "2026-11-02",
        "categorie": dict(Counter(x["categoria"] for x in rows)),
        "stati": dict(Counter(x["stato_validazione"] for x in rows)),
        "scheda": [],
        "avvertenze": [
            "L'aggiornamento dell'elenco A/H al 30/06/2026 e la data "
            "di congelamento 02/11/2026 sono date distinte.",
            "L'assenza da A/H non prova classe C ufficiale: C in UI e' "
            "una convenzione per esclusione.",
            "Le note regionali citate non provano che i centri siano "
            "operativamente attivi alla data dello snapshot.",
            "Il controllo automatico verifica la presenza delle fonti "
            "e delle pagine, NON la completezza delle risposte o "
            "l'assenza di qualsiasi altro documento.",
        ],
    }
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        reference = [dict(x) for x in db.execute(
            "SELECT fonte, data_riferimento, url FROM fonti_snapshot ORDER BY fonte"
        )]
        report["date_fonti"] = reference
        validation = inspect(rows, db)
        report["validazione_strutturale"] = validation
        if validation["esito"] != "OK":
            raise ValueError("Gold non coerenti con lo snapshot: " +
                             "; ".join(validation["errori"]))
        for row in rows:
            med = row["medicinale"].strip()
            sources = set(row["fonti_previste"].split("+"))
            found = {}
            if "EMA" in sources:
                found["EMA"] = db.execute(
                    "SELECT COUNT(*) FROM ema_medicinali WHERE nome = ? COLLATE NOCASE",
                    (med,)
                ).fetchone()[0]
            if "AIFA" in sources:
                found["AIFA"] = db.execute(
                    "SELECT COUNT(*) FROM aifa_confezioni WHERE nome = ? COLLATE NOCASE",
                    (med,)
                ).fetchone()[0]
            if "REGIONE" in sources:
                found["REGIONE"] = db.execute(
                    "SELECT COUNT(*) FROM note WHERE "
                    "UPPER(percorso_zip) LIKE '%' || UPPER(?) || '%'",
                    (med,)
                ).fetchone()[0]
            report["scheda"].append({
                "id": row["id"],
                "medicinale": med,
                "stato": row["stato_validazione"],
                "fonti_richieste": sorted(sources),
                "occorrenze_fonti": found,
                "fonti_non_identificate_per_nome": sorted(
                    k for k, n in found.items() if not n
                ),
                "nota": ("Le fonti identificate per nome sono un precontrollo; "
                         "la prova semantica resta manuale."),
            })
    report["fonte_mancante_per_nome"] = [
        x["id"] for x in report["scheda"]
        if x["fonti_non_identificate_per_nome"]
    ]
    report["esito"] = "PREVALIDAZIONE" if report["stati"].get(
        "DA_VERIFICARE", 0
    ) else "STRUTTURA_VERIFICATA"
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", default="tesi/benchmark_regolatorio_30.csv")
    parser.add_argument("--db", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out")
    opts = parser.parse_args()
    info = audit(opts.benchmark, opts.db, opts.manifest)
    content = json.dumps(info, ensure_ascii=False, indent=2) + "\n"
    if opts.out:
        Path(opts.out).write_text(content, encoding="utf-8")
    print(content)
    print("ATTENZIONE: le domande DA_VERIFICARE non hanno gold e "
          "non contribuiscono all'accuratezza.")


if __name__ == "__main__":
    main()
