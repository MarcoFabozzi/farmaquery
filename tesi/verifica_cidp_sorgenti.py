#!/usr/bin/env python3
"""Audit riproducibile KIOVIG/HYQVIA sulle note regionali originali.

Solo lettura: scarica gli ZIP ufficiali identificati nello snapshot,
confronta SHA-256 archivio e PDF e stampa evidenze per pagina.
NON genera risposte gold e NON modifica il database sperimentale.
"""
from __future__ import annotations

from base64 import b64encode
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.request
import zipfile

import fitz

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"risultati"
TERMS=("KIOVIG","HYQVIA")
MAX_ZIP=95_000_000


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def println(tag,data):
    print(tag+" "+json.dumps(data,ensure_ascii=False,default=str),flush=True)


def get_url(url):
    request=urllib.request.Request(
        url,headers={"User-Agent":"FarmaQuery-Thesis-EvidenceAudit/1.0",
                     "Accept":"application/zip,*/*"})
    with urllib.request.urlopen(request,timeout=70) as response:
        if response.geturl().split("/")[2] != "www.regione.campania.it":
            raise RuntimeError("Redirect fuori dal dominio regionale ufficiale")
        body=response.read(MAX_ZIP+1)
    if len(body)>MAX_ZIP or not zipfile.is_zipfile(io.BytesIO(body)):
        raise RuntimeError("Archivio troppo grande o non ZIP")
    return body


def zip_find(archive,document):
    exact=[info for info in archive.infolist()
           if info.filename.replace("\\","/").casefold()==
           document["path_zip"].replace("\\","/").casefold()]
    if not exact:
        exact=[info for info in archive.infolist()
               if Path(info.filename).name.casefold()==
               Path(document["path_zip"]).name.casefold()]
    if len(exact)!=1:
        raise RuntimeError("PDF non univoco nell'archivio: "+
                           document["path_zip"]+" "+str(len(exact)))
    return exact[0]


def log_page(name,page_num,page,show_image=False):
    text=page.get_text("text",sort=True)
    println("PAGINA_ORIGINALE",{
        "medicinale":name,"pagina":page_num,
        "testo":text[:18000],"caratteri_totali":len(text),
    })
    if not show_image:
        return
    # Riduci la pagina a immagine di consultazione; restituisce soltanto
    # un'immagine temporanea nei log del workflow, non pubblicata dal sito.
    pix=page.get_pixmap(matrix=fitz.Matrix(1.0,1.0),alpha=False)
    picture=pix.tobytes("jpg",jpg_quality=58)
    encoded=b64encode(picture).decode("ascii")
    chunks=[encoded[i:i+6500] for i in range(0,len(encoded),6500)]
    println("IMMAGINE_META",{"medicinale":name,"pagina":page_num,
                            "segmenti":len(chunks),"bytes":len(picture)})
    for idx,chunk in enumerate(chunks):
        print("IMMAGINE_SEGMENTO|"+name+"|"+str(page_num)+"|"+
              str(idx)+"|"+chunk,flush=True)


def main():
    status=json.loads((DATA/"stato_fonti/regione_campania.json").read_text())
    sources={int(r["anno"]):r for r in status["fonti"]}
    gz=(DATA/"regione_campania.sqlite.gz").read_bytes()
    db=sqlite3.connect(":memory:")
    db.deserialize(gzip.decompress(gz))
    db.row_factory=sqlite3.Row
    selected=[]
    for term in TERMS:
        matches=db.execute(
            "SELECT id,nome,anno,path_zip,zip_url,sha256_pdf,nome_farmaco "
            "FROM documenti WHERE upper(nome) LIKE ? OR "
            "upper(nome_farmaco) LIKE ? ORDER BY anno,nome",
            ("%"+term+"%","%"+term+"%")).fetchall()
        for row in matches:
            doc=dict(row)
            doc["medicinale_cercato"]=term
            selected.append(doc)
            println("DOCUMENTO_SNAPSHOT",doc)
            pages=db.execute(
                "SELECT pagina,testo,metodo FROM pagine "
                "WHERE documento_id=? ORDER BY pagina",(doc["id"],)
            ).fetchall()
            for p in pages:
                println("PAGINA_SNAPSHOT",{
                    "nome":doc["nome"],"pagina":p["pagina"],
                    "metodo":p["metodo"],"testo":p["testo"][:14000]
                })
    # Verifica di copertura: conta le note del corpus che possono
    # soddisfare i criteri della domanda. È un pool di CANDIDATI,
    # non una risposta gold né una prova di autorizzazione.
    from recupero_regionale import ESPANSIONI
    terms=ESPANSIONI["neuromuscolar"]+("cidp","nervoso")
    source_rows=db.execute(
        "SELECT d.nome,d.anno,d.path_zip,d.sha256_pdf,"
        "p.pagina,p.testo FROM documenti AS d "
        "JOIN pagine AS p ON p.documento_id=d.id ORDER BY d.nome,p.pagina"
    ).fetchall()
    by_doc={}
    for src in source_rows:
        item=by_doc.setdefault(src["path_zip"],{
            "nome":src["nome"],"anno":src["anno"],
            "pdf":src["path_zip"],"sha256":src["sha256_pdf"],
            "pagine_centro":[],"pagine_categoria":[]})
        page=int(src["pagina"])
        text=src["testo"].casefold()
        if re.search(r"federico\s*(?:ii|2)",text):
            item["pagine_centro"].append(page)
        if any(t in text for t in terms):
            item["pagine_categoria"].append(page)
    doc_candidates=[x for x in by_doc.values()
                    if x["pagine_centro"] and x["pagine_categoria"]]
    for item in doc_candidates:
        println("CANDIDATO_NEUROMUSCOLARE",item)
    println("COPERTURA_CANDIDATI",{
        "note_con_indizi_di_categoria_e_centro":len(doc_candidates),
        "note_totali":len(by_doc),"distinzione":"solo candidati, non gold"})

    if not selected:
        raise RuntimeError("Nessuna nota originale KIOVIG/HYQVIA nello snapshot")
    println("DOCUMENTI_TROVATI",{"numero":len(selected)})
    failures=[]
    for year in sorted({int(d["anno"]) for d in selected}):
        source=sources.get(year)
        if source is None:
            failures.append("Non esiste SHA ufficiale dell'anno "+str(year))
            continue
        println("ARCHIVIO_RICHIESTO",{"anno":year,"url":source["url"],
                                   "sha256_atteso":source["sha256"]})
        try:
            blob=get_url(source["url"])
            actual=sha256(blob)
            if actual!=source["sha256"]:
                raise RuntimeError("SHA-256 archivio diverso: "+actual)
            println("ARCHIVIO_VERIFICATO",{"anno":year,"sha256":actual,
                                          "bytes":len(blob)})
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for doc in [d for d in selected if int(d["anno"])==year]:
                    info=zip_find(archive,doc)
                    pdf=archive.read(info)
                    pdf_hash=sha256(pdf)
                    if pdf_hash!=doc["sha256_pdf"]:
                        raise RuntimeError(
                            "HASH PDF DISCORDANTE "+doc["nome"]+" "+pdf_hash)
                    println("PDF_ORIGINALE_VERIFICATO",{
                        "nome":doc["nome"],"percorso":info.filename,
                        "sha256_pdf":pdf_hash,"anno":year,
                        "url_archivio":source["url"]})
                    with fitz.open(stream=pdf,filetype="pdf") as original:
                        for no,page in enumerate(original,1):
                            log_page(doc["nome"],no,page,
                                     show_image=(no<=4 and
                                                 os.getenv("AUDIT_IMAGES")=="1"))
        except Exception as exc:
            failures.append("Anno "+str(year)+": "+str(exc))
            println("ARCHIVIO_NON_VERIFICATO",{"anno":year,"errore":str(exc)})
    println("ESITO_AUDIT",{
        "documenti_snapshot":len(selected),
        "archivi_non_verificati":failures,
        "verifica_PDF_originale":not bool(failures)})
    if failures:
        sys.exit(2)


if __name__=="__main__":
    main()
