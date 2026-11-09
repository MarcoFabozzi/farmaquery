"""Audit riproducibile del testo RYSTIGGO nel database statico.
Il test non modifica lo SQLite e non promuove il Gold Q11.
"""
import gzip
import hashlib
from pathlib import Path
import sqlite3
import unittest

ROOT=Path(__file__).resolve().parents[2]


class RystiggoPageAudit(unittest.TestCase):
    def test_extract_page_three_from_frozen_snapshot(self):
        source=ROOT/"risultati/tesi_statico_20261102.sqlite.gz"
        sqlite_bytes=gzip.decompress(source.read_bytes())
        digest=hashlib.sha256(sqlite_bytes).hexdigest()
        self.assertEqual(digest,
          "f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742")
        db=sqlite3.connect(":memory:")
        db.row_factory=sqlite3.Row
        try:
            db.deserialize(sqlite_bytes)
            matches=db.execute(
                "SELECT id,nome_file,percorso_zip,archivio_url,anno,hash_pdf "
                "FROM note WHERE nome_file LIKE '%RYSTIGGO%' COLLATE NOCASE "
                "ORDER BY anno,nome_file"
            ).fetchall()
            print("\\n=== RYSTIGGO NOTE TROVATE: ",len(matches)," ===",flush=True)
            self.assertGreater(len(matches),0)
            for note in matches:
                print("\\nNOTA",dict(note),flush=True)
                pages=db.execute(
                  "SELECT numero_pagina,metodo,testo FROM pagine WHERE nota_id=? "
                  "ORDER BY numero_pagina",(note["id"],)
                ).fetchall()
                print("PAGINE",len(pages),flush=True)
                relations=db.execute(
                    "SELECT centro,indicazione,numero_pagina,stato "
                    "FROM nota_centro_documentato WHERE nota_id=?",
                    (note["id"],)).fetchall()
                print("CENTRI_REVISIONATI", [dict(r) for r in relations],flush=True)
                candidates=db.execute(
                    "SELECT numero_pagina,menzione,stato "
                    "FROM centri_candidati WHERE nota_id=?",
                    (note["id"],)).fetchall()
                print("CENTRI_CANDIDATI", [dict(r) for r in candidates][:25],flush=True)
                regs=db.execute(
                    "SELECT medicinale,struttura,indicazione FROM strutture_registri "
                    "WHERE medicinale LIKE '%RYSTIGGO%' COLLATE NOCASE"
                ).fetchall()
                print("REGISTRI_AIFA_RYSTIGGO", [dict(r) for r in regs][:25],flush=True)
                for page in pages:
                    t=page["testo"] or ""
                    print("PAGINA",page["numero_pagina"],"metodo",
                          page["metodo"],"n_caratteri",len(t),
                          "federico",("federico" in t.lower()),
                          "napoli",("napoli" in t.lower()),flush=True)
                    if page["numero_pagina"]==3:
                        print("=== TESTO PAGINA 3 INIZIO ===",flush=True)
                        print(t[:14000],flush=True)
                        print("=== TESTO PAGINA 3 FINE ===",flush=True)
        finally:
            db.close()
