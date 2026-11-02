import csv
import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

import fitz

import regione_campania_etl as etl


def document(testo):
    doc=fitz.open()
    page=doc.new_page()
    page.insert_text((35,65),testo,fontname="helv")
    data=doc.tobytes()
    doc.close()
    return data


def archive(items):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in items:
            z.writestr(name,raw)
    return bio.getvalue()


def structures(n=10_010):
    head=";".join(etl.EXPECTED_COLUMNS)+"\r\n"
    body="".join(
        "FARMACO TEST;MALATTIA;Indicazione test;AORN Cardarelli;CAMPANIA\r\n"
        for _ in range(n))
    return (head+body).encode("cp1252")


class NoteRegionaliTests(unittest.TestCase):
    def test_discovery_only_official_archives(self):
        html='<a href="/sites/default/files/2026-09/note-regionali-2026.zip">2026</a>'
        html+='<a href="https://evil.example/note-regionali-2025.zip">2025</a>'
        found=etl.discover_archives(html)
        self.assertIn(2026,found)
        self.assertNotIn(2025,found)
        self.assertEqual(etl.discover_aifa_csv(
            '<a href="/documents/20142/1826055/Strutture_registri_regioni_2026-09-14.csv">file</a>'
        ),"https://www.aifa.gov.it/documents/20142/1826055/Strutture_registri_regioni_2026-09-14.csv")

    def test_pdf_pagine_e_metadati(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=sqlite3.connect(":memory:")
            db.executescript(etl.SCHEMA)
            raw=document("Prot. 1234567 del 14/09/2026 - AORN Cardarelli")
            out=etl.extract_pdf(db,"SKYCLARYS.pdf",raw,2026,etl.FALLBACK[2026],False)
            self.assertEqual(out["nuovo"],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pagine").fetchone()[0],1)
            row=db.execute("SELECT nome_farmaco,anno,pagine FROM documenti").fetchone()
            self.assertEqual(row,("SKYCLARYS",2026,1))
            self.assertEqual(etl.extract_pdf(db,"COPY.pdf",raw,2026,etl.FALLBACK[2026],False),{"duplicato":1})

    def test_zip_rejects_unrelated_content(self):
        with self.assertRaises(ValueError):
            etl.safe_zip_files(b"<html>Not Found</html>")

    def test_strutture_solo_campania(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript(etl.SCHEMA)
            result=etl.import_structures(
                db,structures(),etl.AIFA_FALLBACK,"2026-09-14")
            self.assertEqual(result["righe_totali"],10010)
            self.assertEqual(result["righe_campania"],10010)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM strutture_registri").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT struttura_norm FROM strutture_registri").fetchone()[0],
                             etl.normalize("AORN Cardarelli"))

    def test_snapshot_compatto_e_rimandi(self):
        raw=document("Prot. 1234567 del 14/09/2026")
        blob=archive([("cartella/TEST.pdf",raw)])
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/"regional.sqlite.gz"
            report=Path(d)/"stato.json"
            result=etl.build_db([(2026,etl.FALLBACK[2026],blob)],None,False,output,report)
            self.assertEqual(result["statistiche"]["note"],1)
            self.assertTrue(output.is_file())
            self.assertTrue(report.is_file())


if __name__=="__main__":
    unittest.main()
