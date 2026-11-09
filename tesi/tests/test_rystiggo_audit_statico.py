"""Audit riproducibile del testo RYSTIGGO nel database statico.
Il test non modifica lo SQLite e non promuove il Gold Q11.
"""
import gzip
import hashlib
from pathlib import Path
import sqlite3
import unittest
import urllib.request
import urllib.error
import zipfile
import io
import shutil
import subprocess
import tempfile

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

    def test_remote_original_rystiggo_page_three_when_available(self):
        """Controllo documentale online facoltativo, indipendente dal database."""
        urls=[
            "https://www.regione.campania.it/sites/default/files/2025-12/note%202025%20-%2018.12.2025.zip",
            "https://archivioportale.regione.campania.it/assets/documents/note-2025-18-12-2025.zip",
        ]
        payload=None
        for url in urls:
            try:
                request=urllib.request.Request(
                    url,headers={"User-Agent":"Mozilla/5.0 FarmaQuery audit"})
                with urllib.request.urlopen(request,timeout=15) as stream:
                    raw=stream.read(75000001)
                    print("URL_ORIGINALE",url,"bytes",len(raw),flush=True)
                if len(raw)<75000000 and zipfile.is_zipfile(io.BytesIO(raw)):
                    payload=raw
                    break
                print("URL_ORIGINALE_NON_ZIP",url,flush=True)
            except (OSError,urllib.error.HTTPError,TimeoutError) as exc:
                print("URL_ORIGINALE_NON_DISPONIBILE",url,type(exc).__name__,
                      str(exc)[:160],flush=True)
        if payload is None:
            self.skipTest("ZIP ufficiale non scaricabile dal runner: verifica visiva resta aperta")
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            paths=[n for n in z.namelist()
                   if n.lower().endswith("rystiggo.pdf")
                   and "__macosx" not in n.lower()]
            print("RYSTIGGO_ZIP_MATCHES",paths,flush=True)
            self.assertTrue(paths,"Archivio disponibile, nota RYSTIGGO non trovata")
            doc=z.read(paths[0])
        actual=hashlib.sha256(doc).hexdigest()
        print("RYSTIGGO_PDF_SHA256",actual,"bytes",len(doc),flush=True)
        with tempfile.TemporaryDirectory() as temp:
            pdf=Path(temp)/"RYSTIGGO.pdf"
            pdf.write_bytes(doc)
            if shutil.which("pdftotext"):
                extracted=subprocess.run(
                    ["pdftotext","-f","3","-l","3","-layout",
                     str(pdf),"-"],capture_output=True,text=True,timeout=25)
                t=extracted.stdout
                print("RYSTIGGO_P3_LAYOUT_CHARS",len(t),flush=True)
                print("RYSTIGGO_P3_LAYOUT",t[:14000],flush=True)
                print("FEDERICO_P3_LAYOUT", "federico" in t.casefold(),flush=True)
            if shutil.which("pdftoppm") and shutil.which("tesseract"):
                png=Path(temp)/"rystiggo-3"
                subprocess.run(
                    ["pdftoppm","-f","3","-l","3","-r","150","-png",
                     "-singlefile",str(pdf),str(png)],
                    capture_output=True,timeout=35,check=True)
                langs=subprocess.run(["tesseract","--list-langs"],
                                     capture_output=True,text=True,timeout=5).stdout
                lang="ita+eng" if "ita" in langs else "eng"
                ocr=subprocess.run(
                    ["tesseract",str(png)+".png","stdout","-l",lang,"--psm","6"],
                    capture_output=True,text=True,timeout=35)
                t=ocr.stdout
                print("RYSTIGGO_P3_OCR_CHARS",len(t),flush=True)
                print("RYSTIGGO_P3_OCR",t[:14000],flush=True)
                print("FEDERICO_P3_OCR","federico" in t.casefold(),flush=True)
