"""Importa nello snapshot sperimentale i testi GU già acquisiti da FarmaQuery.

Non scarica documenti né promuove evidenze automatiche a provvedimenti validati.
Ogni testo e allegato è verificato con SHA-256 e copiato nello STESSO SQLite
usato da TAG e Text-to-SQL. L'archivio sorgente resta intatto.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3


SCHEMA_GU = """
CREATE TABLE gu_atti (
    codice TEXT PRIMARY KEY, data_pubblicazione TEXT NOT NULL,
    titolo TEXT, tipo TEXT, url_ufficiale TEXT NOT NULL,
    nominativi_campione TEXT NOT NULL, completezza TEXT NOT NULL
);
CREATE TABLE gu_documenti (
    documento_id TEXT PRIMARY KEY, codice TEXT NOT NULL REFERENCES gu_atti(codice),
    tipo_documento TEXT NOT NULL, url_fonte TEXT NOT NULL,
    sha256_testo TEXT NOT NULL, testo TEXT NOT NULL
);
CREATE TABLE gu_segmenti (
    documento_id TEXT NOT NULL REFERENCES gu_documenti(documento_id),
    numero_segmento INTEGER NOT NULL, testo TEXT NOT NULL,
    PRIMARY KEY (documento_id, numero_segmento)
);
CREATE VIRTUAL TABLE gu_segmenti_fts USING fts5(
    documento_id UNINDEXED, numero_segmento UNINDEXED, testo
);
CREATE INDEX idx_gu_documenti_codice ON gu_documenti(codice);
"""


def segmenta(testo, limite=1800, sovrapposizione=180):
    """Segmenti riproducibili con sovrapposizione per non perdere un passaggio."""
    if not 0 < sovrapposizione < limite:
        raise ValueError("Dimensioni segmenti non valide")
    testo = testo.strip()
    out = []
    pos = 0
    while pos < len(testo):
        fine = min(pos + limite, len(testo))
        if fine < len(testo):
            stacco = testo.rfind("\n", pos + limite // 2, fine)
            if stacco > pos:
                fine = stacco + 1
        piece = testo[pos:fine].strip()
        if piece:
            out.append(piece)
        if fine == len(testo):
            break
        pos = max(pos + 1, fine - sovrapposizione)
    return out


def importa_gu(db: sqlite3.Connection, fonte: sqlite3.Connection, root: Path):
    """Copia atti, testi e allegati verificati; fallisce su fonti incoerenti."""
    origine = Path(root) / "risultati"
    directory = (origine / "gazzetta_testi").resolve()
    presenti = {row[0] for row in fonte.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    richieste = {"gazzetta_atti", "gu_allegati"}
    if not richieste.issubset(presenti):
        raise ValueError("Sorgente Gazzetta incompleta: " + str(richieste - presenti))
    db.executescript(SCHEMA_GU)
    n_atti = n_documenti = n_segmenti = 0

    def salva(codice, kind, url, relativo, expected):
        nonlocal n_documenti, n_segmenti
        if not relativo or not expected:
            raise ValueError("Riferimento o hash GU mancante per " + codice)
        percorso = (origine / relativo).resolve()
        if not percorso.is_relative_to(directory) or not percorso.is_file():
            raise ValueError("Testo GU mancante o percorso fuori archivio: " + str(relativo))
        if percorso.stat().st_size > 2_500_000:
            raise ValueError("Testo GU troppo grande: " + str(relativo))
        raw = percorso.read_bytes()
        observed = sha256(raw).hexdigest()
        if observed != expected:
            raise ValueError("SHA-256 non corrispondente per testo GU: " + str(relativo))
        text = raw.decode("utf-8-sig")
        if not text.strip():
            raise ValueError("Testo GU vuoto: " + str(relativo))
        ident = codice + (":atto" if kind == "ATTO" else ":allegato:" + expected[:16])
        db.execute("INSERT INTO gu_documenti VALUES (?,?,?,?,?,?)",
                   (ident, codice, kind, url, expected, text))
        for ix, snippet in enumerate(segmenta(text), start=1):
            db.execute("INSERT INTO gu_segmenti VALUES (?,?,?)",
                       (ident, ix, snippet))
            db.execute("INSERT INTO gu_segmenti_fts VALUES (?,?,?)",
                       (ident, ix, snippet))
            n_segmenti += 1
        n_documenti += 1

    for row in fonte.execute(
        "SELECT codice,data_pubblicazione,titolo,tipo,url_ufficiale,"
        "nominativi_campione,completezza,url_testo,testo_file,sha256_testo "
        "FROM gazzetta_atti ORDER BY codice"
    ):
        code, when, title, typ, url, names, completezza, text_url, file, digest = row
        db.execute("INSERT INTO gu_atti VALUES (?,?,?,?,?,?,?)",
                   (code, when, title, typ, url, names, completezza))
        salva(code, "ATTO", text_url, file, digest)
        n_atti += 1
    for code, url, file, digest in fonte.execute(
        "SELECT codice,url,testo_file,sha256 FROM gu_allegati ORDER BY codice,url"
    ):
        if not db.execute("SELECT 1 FROM gu_atti WHERE codice=?", (code,)).fetchone():
            raise ValueError("Allegato GU privo di atto: " + code)
        salva(code, "ALLEGATO", url, file, digest)

    if n_atti < 1 or n_segmenti < n_atti:
        raise ValueError("Nessun corpus GU utilizzabile nello snapshot")
    return {"gu_atti": n_atti, "gu_documenti": n_documenti,
            "gu_segmenti": n_segmenti}
