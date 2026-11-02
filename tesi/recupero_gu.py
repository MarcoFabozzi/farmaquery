"""Ricerca deterministica di passaggi GU per la fase semantica TAG.

La selezione iniziale recupera righe reali del medesimo SQLite. Il successivo
sem_filter di LOTUS valuta la pertinenza e compone la risposta con le fonti.
"""
import re


def domanda_gu(question):
    return bool(re.search(r"\b(?:gu|gazzetta|determina|atto)\b", question, re.I)
                or re.search(r"\b\d{2}[a-z]\d{5}\b", question, re.I))


def candidati_gu(db, question, limit=6):
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='gu_segmenti_fts'"
    ).fetchone():
        return []
    codici = list(dict.fromkeys(x.upper() for x in
        re.findall(r"\b\d{2}[A-Za-z]\d{5}\b", question)))
    # I nomi espressamente attribuiti agli atti sono nel DB, non in liste esterne.
    words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9-]{3,}", question)
    names = []
    for word in words:
        match = db.execute(
            "SELECT 1 FROM gu_atti WHERE nominativi_campione "
            "LIKE ? COLLATE NOCASE LIMIT 1", ('%"' + word + '"%',)
        ).fetchone()
        if match and word.casefold() not in {n.casefold() for n in names}:
            names.append(word)
    names = names[:4]
    # I codici senza nome restano validi: il testo viene comunque recuperato.
    statement = """SELECT a.codice,a.data_pubblicazione,a.completezza,
                       d.documento_id,d.tipo_documento,d.url_fonte,
                       s.numero_segmento,s.testo
                   FROM gu_segmenti_fts
                   JOIN gu_segmenti s
                     ON s.documento_id=gu_segmenti_fts.documento_id
                    AND s.numero_segmento=gu_segmenti_fts.numero_segmento
                   JOIN gu_documenti d ON d.documento_id=s.documento_id
                   JOIN gu_atti a ON a.codice=d.codice
                   WHERE gu_segmenti_fts MATCH ?"""
    out, seen = [], set()

    def append(rows):
        for r in rows:
            rec = dict(r)
            ident = (rec["documento_id"], rec["numero_segmento"])
            if ident not in seen:
                out.append(rec)
                seen.add(ident)

    if codici:
        for code in codici:
            for name in names[:2]:
                append(db.execute(statement + " AND a.codice=? "
                                  "ORDER BY bm25(gu_segmenti_fts) LIMIT 2",
                                  ('"' + name.replace('"', '') + '"', code)))
            if not any(row["codice"] == code for row in out):
                append(db.execute(
                    """SELECT a.codice,a.data_pubblicazione,a.completezza,
                       d.documento_id,d.tipo_documento,d.url_fonte,
                       s.numero_segmento,s.testo
                       FROM gu_segmenti s
                       JOIN gu_documenti d ON d.documento_id=s.documento_id
                       JOIN gu_atti a ON a.codice=d.codice
                       WHERE a.codice=? ORDER BY s.numero_segmento LIMIT 2""",
                    (code,)))
    else:
        for name in names:
            append(db.execute(
                statement + " ORDER BY bm25(gu_segmenti_fts) LIMIT 2",
                ('"' + name.replace('"', '') + '"',)))
    return out[:limit]
