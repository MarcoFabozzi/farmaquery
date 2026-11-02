#!/usr/bin/env python3
"""Crea uno snapshot sperimentale dalle FONTI ONLINE aggiornate da FarmaQuery.

Non utilizza i file A/H del 31 maggio ricevuti come ripiego dal relatore.
Le GitHub Actions che aggiornano EMA, AIFA, Campania e strutture restano
indipendenti. Eseguire questo script su un preciso commit del repository:
il manifesto JSON blocca hash, date e versione delle fonti per entrambi
i metodi TAG e Text-to-SQL.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TABLES = """
PRAGMA foreign_keys=ON;
CREATE TABLE note (
 id TEXT PRIMARY KEY, nome_file TEXT NOT NULL, percorso_zip TEXT NOT NULL,
 anno INTEGER NOT NULL, farmaco_candidato TEXT, protocollo_candidato TEXT,
 data_candidata TEXT, determina_candidata TEXT, indicazione_candidata TEXT,
 archivio_url TEXT NOT NULL, hash_pdf TEXT NOT NULL, stato_estrazione TEXT,
 flag_ambiguita TEXT
);
CREATE TABLE pagine (
 nota_id TEXT NOT NULL REFERENCES note(id),
 numero_pagina INTEGER NOT NULL, testo TEXT NOT NULL, metodo TEXT NOT NULL,
 PRIMARY KEY (nota_id,numero_pagina)
);
CREATE VIRTUAL TABLE pagine_fts USING fts5(
 nota_id UNINDEXED,numero_pagina UNINDEXED,testo
);
CREATE TABLE strutture_registri (
 id TEXT PRIMARY KEY, medicinale TEXT NOT NULL, patologia TEXT,
 indicazione TEXT, struttura TEXT NOT NULL, regione TEXT NOT NULL,
 data_riferimento TEXT NOT NULL, fonte_url TEXT NOT NULL
);
CREATE TABLE centri_candidati (
 nota_id TEXT NOT NULL REFERENCES note(id), numero_pagina INTEGER NOT NULL,
 menzione TEXT NOT NULL, stato TEXT NOT NULL
);
CREATE TABLE rimandi_candidati (
 nota_id TEXT NOT NULL REFERENCES note(id), numero_pagina INTEGER NOT NULL,
 riferimento TEXT NOT NULL, stato TEXT NOT NULL
);
CREATE TABLE aifa_confezioni (
 aic TEXT PRIMARY KEY, nome TEXT, principio_attivo TEXT,
 descrizione TEXT, classe_a_h_snapshot TEXT, classe_a_h_data TEXT
);
CREATE TABLE ema_medicinali (
 ema_id TEXT PRIMARY KEY,nome TEXT,principio_attivo TEXT,
 stato_ema TEXT,data_decisione_ue TEXT,indicazione_ema TEXT,url_ema TEXT
);
CREATE TABLE fonti_snapshot (
 fonte TEXT PRIMARY KEY, url TEXT, sha256 TEXT, data_riferimento TEXT
);
CREATE INDEX idx_note_farmaco ON note(farmaco_candidato);
CREATE INDEX idx_strutture_medicinale ON strutture_registri(medicinale);
CREATE INDEX idx_confezioni_nome ON aifa_confezioni(nome);
"""

FILES = {
    "regionale": "risultati/regione_campania.sqlite.gz",
    "aifa_completo": "risultati/aifa_confezioni_complete.sqlite.gz",
    "principale": "risultati/farmaci_automatico.sqlite",
    "classi_ah": "risultati/aifa_classi_ah.json",
}
REPORTS = {
    "regione": "risultati/stato_fonti/regione_campania.json",
    "aifa_anagrafica": "risultati/stato_fonti/aifa_anagrafica.json",
    "aifa_ah": "risultati/stato_fonti/aifa_ah.json",
    "ema": "risultati/stato_fonti/ema.json",
}


def sha_file(path):
    hash_obj = sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1024 * 1024):
            hash_obj.update(block)
    return hash_obj.hexdigest()


def connect_ro(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def decompress(source, dest, max_unpacked=450_000_000):
    size = 0
    with gzip.open(source, "rb") as source_fd, Path(dest).open("wb") as target:
        while chunk := source_fd.read(1024 * 1024):
            size += len(chunk)
            if size > max_unpacked:
                raise ValueError("Archivio oltre limite: " + str(source))
            target.write(chunk)


def load_sources(root):
    root = Path(root)
    states = {}
    for name, rel in REPORTS.items():
        states[name] = json.loads((root / rel).read_text(encoding="utf-8"))
        if states[name].get("esito") != "OK":
            raise ValueError("Fonte non validata: " + name)
    for name, rel in FILES.items():
        if not (root / rel).is_file():
            raise FileNotFoundError("File fonte assente: " + rel)
    ah = json.loads((root / FILES["classi_ah"]).read_text(encoding="utf-8"))
    if ah.get("schema") != 1 or ah.get("data_riferimento") != (
        states["aifa_ah"]["statistiche"]["data_riferimento_ah"]
    ):
        raise ValueError("Data degli elenchi A/H incoerente con lo stato AIFA")
    classes = ah.get("classi")
    if not isinstance(classes, dict) or not classes:
        raise ValueError("Indice A/H assente o vuoto")
    if any(value not in ("A", "H") for value in classes.values()):
        raise ValueError("Classi A/H non valide")
    for name, report_field in (
        ("regionale", states["regione"]["archivio_compresso_sha256"]),
        ("aifa_completo", states["aifa_anagrafica"]["statistiche"]["archivio_completo"]["sha256_archivio"]),
    ):
        if sha_file(root / FILES[name]) != report_field:
            raise ValueError("Hash dell'archivio non corrisponde: " + name)
    return states, ah


def build_snapshot(root, output, manifest):
    root, output, manifest = Path(root), Path(output), Path(manifest)
    states, ah = load_sources(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="farmaquery_snapshot_", dir=output.parent) as temp:
        temp_dir = Path(temp)
        region = temp_dir / "regione.sqlite"
        aifa = temp_dir / "aifa.sqlite"
        stage = temp_dir / "esperimento.sqlite"
        decompress(root / FILES["regionale"], region)
        decompress(root / FILES["aifa_completo"], aifa)
        with (closing(connect_ro(region)) as regional,
              closing(connect_ro(aifa)) as national,
              closing(connect_ro(root / FILES["principale"])) as main,
              closing(sqlite3.connect(stage)) as db):
            for name, src in (("Regione", regional), ("AIFA", national), ("EMA", main)):
                if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("SQLite sorgente non integro: " + name)
            db.executescript(TABLES)
            db.executemany(
                "INSERT INTO note VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                regional.execute(
                    "SELECT id,nome,path_zip,anno,nome_farmaco,protocollo_estratto,"
                    "data_estratta,determina_aifa_estratta,indicazione_estratta,"
                    "zip_url,sha256_pdf,stato_estrazione,flag_ambiguita FROM documenti"
                ),
            )
            db.executemany(
                "INSERT INTO pagine VALUES (?,?,?,?)",
                regional.execute("SELECT documento_id,pagina,testo,metodo FROM pagine"),
            )
            db.execute(
                "INSERT INTO pagine_fts(nota_id,numero_pagina,testo) "
                "SELECT nota_id,numero_pagina,testo FROM pagine"
            )
            db.executemany(
                "INSERT INTO strutture_registri VALUES (?,?,?,?,?,?,?,?)",
                regional.execute(
                    "SELECT id,medicinale,patologia,indicazione,struttura,regione,"
                    "data_riferimento,fonte_url FROM strutture_registri"
                ),
            )
            db.executemany(
                "INSERT INTO centri_candidati VALUES (?,?,?,?)",
                regional.execute(
                    "SELECT documento_id,pagina,testo_candidato,stato FROM centri_candidati"
                ),
            )
            db.executemany(
                "INSERT INTO rimandi_candidati VALUES (?,?,?,?)",
                regional.execute(
                    "SELECT documento_id,pagina,testo_rimando,stato FROM rimandi_candidati"
                ),
            )
            # Tutti gli AIC nazionali: A/H esplicita se pubblicata, altrimenti NULL.
            # Non scrivere C per esclusione nel dataset regolatorio della tesi.
            classes = ah["classi"]
            date_ah = ah["data_riferimento"]
            batch = (
                (row[0],row[1],row[2],row[3],classes.get(row[0]),
                 date_ah if row[0] in classes else None)
                for row in national.execute(
                    "SELECT aic,nome,principio_attivo,descrizione FROM confezioni"
                )
            )
            db.executemany("INSERT INTO aifa_confezioni VALUES (?,?,?,?,?,?)", batch)
            db.executemany(
                "INSERT INTO ema_medicinali VALUES (?,?,?,?,?,?,?)",
                main.execute(
                    "SELECT ema_id,nome,principio_attivo,stato_ema,"
                    "data_decisione_ue,indicazione_ema,url_ema FROM ema_medicinali"
                ),
            )
            for source, meta in states["aifa_ah"]["fonti"].items():
                db.execute(
                    "INSERT INTO fonti_snapshot VALUES (?,?,?,?)",
                    (source,meta["url"],meta["sha256"],date_ah),
                )
            for source, meta in states["ema"]["fonti"].items():
                db.execute(
                    "INSERT INTO fonti_snapshot VALUES (?,?,?,?)",
                    (source,meta["url"],meta["sha256"],states["ema"]["ultimo_successo_utc"]),
                )
            for year in states["regione"]["fonti"]:
                db.execute(
                    "INSERT INTO fonti_snapshot VALUES (?,?,?,?)",
                    ("note_" + str(year["anno"]),year["url"],year["sha256"],str(year["anno"])),
                )
            structure = states["regione"]["strutture"]
            db.execute(
                "INSERT INTO fonti_snapshot VALUES (?,?,?,?)",
                ("strutture",structure["url"],structure["sha256"],structure["data_riferimento"]),
            )
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Snapshot sperimentale SQLite non integro")
            counts = {
                table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in ("note","pagine","strutture_registri","aifa_confezioni",
                              "ema_medicinali","centri_candidati","rimandi_candidati")
            }
            if counts["note"] < 1 or counts["pagine"] < counts["note"] or (
                counts["aifa_confezioni"] < 10000 or counts["ema_medicinali"] < 100
            ):
                raise ValueError("Snapshot incompleto; nessun risultato sperimentale valido")
        provenance = {name:sha_file(root / rel) for name,rel in FILES.items()}
        try:
            commit = subprocess.check_output(
                ["git","-C",str(root),"rev-parse","HEAD"],text=True,timeout=6
            ).strip()
        except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):
            commit = os.environ.get("GITHUB_SHA","NON_DISPONIBILE")
        info = {
            "schema": 1,
            "tipo": "SNAPSHOT_ONLINE_FISSO_PER_ESPERIMENTO",
            "creato_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_commit": commit,
            "file": output.name,
            "sha256_sqlite": sha_file(stage),
            "conteggi": counts,
            "file_sorgenti_sha256": provenance,
            "fonti_ufficiali": {
                "ema": states["ema"]["fonti"]["ema"],
                "classi_ah": {
                    "data_riferimento": ah["data_riferimento"],
                    "elenchi": states["aifa_ah"]["fonti"],
                },
                "aifa_anagrafica": states["aifa_anagrafica"]["fonti"],
                "note_regionali": states["regione"]["fonti"],
                "strutture_registri": states["regione"]["strutture"],
            },
            "acquisizioni": {
                name: doc.get("ultimo_successo_utc") for name,doc in states.items()
            },
            "avvertenza": "La classe A/H è documentata dagli elenchi datati; "
                         "l'assenza non dimostra ufficialmente C. Centri e rimandi "
                         "estratti sono candidati, da validare sui PDF. "
                         "Lo snapshot è immutabile per tutte le prove del benchmark.",
        }
        temp_manifest = temp_dir / "manifest.json"
        temp_manifest.write_text(
            json.dumps(info,ensure_ascii=False,indent=2) + "\n",encoding="utf-8"
        )
        os.replace(stage,output)
        os.replace(temp_manifest,manifest)
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.manifest.resolve():
        raise ValueError("Output e manifesto devono essere file diversi")
    result = build_snapshot(args.root,args.output,args.manifest)
    print(json.dumps({"esito":"OK","conteggi":result["conteggi"],
                      "classi_ah":result["fonti_ufficiali"]["classi_ah"]["data_riferimento"],
                      "sha256_sqlite":result["sha256_sqlite"]},
                     ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
