#!/usr/bin/env python3
"""FarmaQuery: acquisizione verificabile delle note regionali della Campania.

Sorgenti: archivi ZIP annuali del portale Regione Campania, e elenco CSV AIFA
delle strutture abilitate ai registri. L'archivio sperimentale del relatore
non viene modificato. Nessun candidato e' automaticamente un'autorizzazione.
"""
from __future__ import annotations
import argparse
import csv
import gzip
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "risultati"
DB_GZ = DATA / "regione_campania.sqlite.gz"
REPORT = DATA / "stato_fonti" / "regione_campania.json"
REGIONE = "https://www.regione.campania.it/aree-tematiche/sanita/farmaci-farmacie-dispositivi-medici/ptr-prontuario-terapeutico-regionale"
AIFA = "https://www.aifa.gov.it/strutture-sanitarie-abilitate-dagli-approvatori-regionali2"
FALLBACK = {
  2022: "https://www.regione.campania.it/assets/documents/ptr-note-regionali-2022.zip",
  2023: "https://www.regione.campania.it/assets/documents/ptr-noteregionali2023-020124-x01day5s6s08qz9q.zip",
  2024: "https://www.regione.campania.it/assets/documents/ptr-note-regionali-11-12-24-ore-16-40.zip",
  2025: "https://www.regione.campania.it/sites/default/files/2025-12/note%202025%20-%2018.12.2025.zip",
  2026: "https://www.regione.campania.it/sites/default/files/2026-06/note-regionali-2026-03-06-26.zip",
}
AIFA_FALLBACK = "https://www.aifa.gov.it/documents/20142/1826055/Strutture_registri_regioni_2026-06-26.csv"
MAX_ZIP = 95_000_000
MAX_CSV = 95_000_000
MAX_PDF = 20_000_000
MAX_UNPACKED = 210_000_000
EXPECTED_COLUMNS = ("Medicinale", "Descrizione sintetica patologia",
                    "Indicazione terapeutica rimborsata",
                    "Struttura sanitaria abilitata", "Regione")
PROTOCOLLO = re.compile(r"(?:PG[\s/.-]*20\d{2}[\s/.-]*\d{4,9}|(?:prot(?:ocollo)?\.?\s*(?:n\.?)?\s*)\d{4,10})", re.I)
DATE = re.compile(r"\b([0-3]?\d)[/.-]([01]?\d)[/.-](20\d{2})\b")
DETERMINA = re.compile(r"(?:determina|determinazione)\s+(?:AIFA\s+)?[^\n]{0,95}", re.I)
REF = re.compile(r"(?:nota|prot(?:ocollo)?\.?)\s+(?:regionale\s+)?(?:n\.?\s*)?(?:PG/)?(?:20\d{2}[\s/.-]*)?\d{5,10}", re.I)
CENTER = re.compile(r"\b(?:A\.?\s?O\.?\s?R\.?\s?N\.?|A\.?\s?O\.?\s?U\.?|IRCCS|POLICLINICO|OSPEDALE|CENTR[OI]|UU\.?\s?OO\.?)\b", re.I)

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS documenti(
  id TEXT PRIMARY KEY, anno INTEGER NOT NULL, nome TEXT NOT NULL, nome_farmaco TEXT,
  zip_url TEXT NOT NULL, path_zip TEXT NOT NULL, sha256_pdf TEXT NOT NULL,
  pagine INTEGER NOT NULL, pagine_ocr INTEGER NOT NULL DEFAULT 0,
  protocollo_estratto TEXT, data_estratta TEXT, determina_aifa_estratta TEXT,
  indicazione_estratta TEXT, stato_estrazione TEXT NOT NULL,
  flag_ambiguita TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_documenti_nome ON documenti(nome_farmaco);
CREATE TABLE IF NOT EXISTS pagine(
  documento_id TEXT NOT NULL REFERENCES documenti(id),
  pagina INTEGER NOT NULL, testo TEXT NOT NULL,
  metodo TEXT NOT NULL CHECK(metodo IN ('TESTO','OCR','OCR_MANCANTE','VUOTA')),
  PRIMARY KEY(documento_id,pagina)
);
CREATE TABLE IF NOT EXISTS centri_candidati(
  documento_id TEXT NOT NULL REFERENCES documenti(id),
  pagina INTEGER NOT NULL, testo_candidato TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'DA_VERIFICARE',
  PRIMARY KEY(documento_id,pagina,testo_candidato)
);
CREATE TABLE IF NOT EXISTS rimandi_candidati(
  documento_id TEXT NOT NULL REFERENCES documenti(id),
  pagina INTEGER NOT NULL, testo_rimando TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'DA_VERIFICARE',
  PRIMARY KEY(documento_id,pagina,testo_rimando)
);
CREATE TABLE IF NOT EXISTS strutture_registri(
  id TEXT PRIMARY KEY, data_riferimento TEXT NOT NULL,
  medicinale TEXT NOT NULL, patologia TEXT NOT NULL, indicazione TEXT NOT NULL,
  struttura TEXT NOT NULL, struttura_norm TEXT NOT NULL, regione TEXT NOT NULL,
  fonte_url TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_strutture_nome ON strutture_registri(medicinale);
CREATE INDEX IF NOT EXISTS idx_strutture_norm ON strutture_registri(struttura_norm);
CREATE TABLE IF NOT EXISTS acquisizioni(
  fonte TEXT PRIMARY KEY, url TEXT NOT NULL, sha256 TEXT NOT NULL,
  data_riferimento TEXT, nota TEXT
);
"""

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.words = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.words = []
    def handle_data(self, data):
        if self.href is not None:
            self.words.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href:
            self.links.append((self.href, " ".join(self.words)))
            self.href = None
            self.words = []

def verify_url(url, allowed):
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in allowed or p.username or p.password:
        raise ValueError("URL non istituzionale: " + str(url))
    return url

def download(url, max_bytes):
    verify_url(url, {"www.regione.campania.it", "www.aifa.gov.it"})
    req = Request(url, headers={"User-Agent":"FarmaQuery-academic-research/1.0",
                               "Accept":"text/html,application/zip,text/csv,application/octet-stream,*/*"})
    with urlopen(req,timeout=120) as response:
        verify_url(response.geturl(), {"www.regione.campania.it", "www.aifa.gov.it"})
        chunks = []
        size = 0
        while True:
            buf = response.read(1024*1024)
            if not buf: break
            size += len(buf)
            if size > max_bytes:
                raise ValueError("Fonte troppo grande (limite download)")
            chunks.append(buf)
    return b"".join(chunks)

def discover_archives(html):
    reader = Links()
    reader.feed(html)
    found = {}
    for href, label in reader.links:
        url = urljoin(REGIONE, href)
        path = unquote(urlparse(url).path).lower()
        if not path.endswith(".zip") or "note" not in path:
            continue
        if urlparse(url).hostname != "www.regione.campania.it":
            continue
        for year in FALLBACK:
            if re.search(r"(?<!\d)" + str(year) + r"(?!\d)", path + " " + label):
                found[year] = url
                break
    return found

def discover_aifa_csv(html):
    reader = Links()
    reader.feed(html)
    candidates=[]
    for href,label in reader.links:
        url=urljoin(AIFA,href)
        name=unquote(urlparse(url).path).lower()
        if re.search(r"strutture_registri_regioni_\d{4}[-_]\d{2}[-_]\d{2}\.csv$",name):
            if urlparse(url).hostname == "www.aifa.gov.it":
                candidates.append(url)
    return sorted(candidates)[-1] if candidates else AIFA_FALLBACK

def normalize(v):
    return re.sub(r"[^A-Z0-9]+","",str(v or "").upper())

def safe_zip_files(blob):
    if blob[:2] != b"PK":
        raise ValueError("Risposta non ZIP")
    out=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as arc:
        total=0
        for entry in arc.infolist():
            if entry.is_dir() or not entry.filename.lower().endswith(".pdf"):
                continue
            parts=Path(entry.filename).parts
            if ".." in parts or entry.file_size>MAX_PDF:
                raise ValueError("Percorso o PDF non sicuro nell'archivio")
            total+=entry.file_size
            if total>MAX_UNPACKED:
                raise ValueError("Archivio espanso troppo grande")
            pdf=arc.read(entry)
            if not pdf.startswith(b"%PDF-"):
                raise ValueError("Documento non PDF: "+entry.filename)
            out.append((entry.filename,pdf))
    if not out: raise ValueError("Nessun PDF nell'archivio ufficiale")
    return out

def get_ocr(page):
    zoom=1.65
    pix=page.get_pixmap(matrix=__import__("fitz").Matrix(zoom,zoom),
                         colorspace=__import__("fitz").csRGB,alpha=False)
    raw=pix.tobytes("png")
    proc=subprocess.run(["tesseract","stdin","stdout","-l","ita+eng","--psm","3"],
                        input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        timeout=95)
    if proc.returncode:
        raise RuntimeError("OCR Tesseract: "+proc.stderr.decode("utf-8","replace")[:160])
    return proc.stdout.decode("utf-8","replace").strip()

def extract_pdf(db, name, pdf, year, source, use_ocr=True):
    import fitz
    digest=sha256(pdf).hexdigest()
    doc_id=digest
    if db.execute("SELECT 1 FROM documenti WHERE id=?",(doc_id,)).fetchone():
        return {"duplicato":1}
    with fitz.open(stream=pdf,filetype="pdf") as d:
        if d.page_count>80: raise ValueError("PDF oltre il limite di pagine "+name)
        page_data=[]
        failures=0
        for i,page in enumerate(d):
            text=page.get_text("text",sort=True).strip()
            method="TESTO" if len(text)>=80 else "VUOTA"
            if len(text)<80 and use_ocr:
                try:
                    ocr=get_ocr(page)
                    if len(ocr)>len(text):
                        text,method=ocr,"OCR"
                except (OSError,subprocess.TimeoutExpired,RuntimeError):
                    failures+=1
                    method="OCR_MANCANTE"
            elif len(text)<80:
                method="OCR_MANCANTE"
            page_data.append((i+1,text,method))
    alltext="\n".join(x[1] for x in page_data)
    head=alltext[:7000]
    proto=PROTOCOLLO.search(head)
    dt=DATE.search(head)
    det=DETERMINA.search(alltext[:16000])
    ind=re.search(r"(?:indicazione terapeutica|indicazioni terapeutiche)[^\n]{0,240}",alltext,re.I)
    nome=Path(name).stem
    med=re.split(r"\s+(?:prot\.?|20\d\d|nota|aggiornamento)\b",nome,1,flags=re.I)[0].strip()
    ambig=[]
    if not proto:ambig.append("PROTOCOLLO_DA_VERIFICARE")
    if failures or any(x[2]=="OCR_MANCANTE" for x in page_data):ambig.append("OCR_INCOMPLETO")
    if any("rimando" in x[1].lower() or "precedent" in x[1].lower() for x in page_data):
        ambig.append("POSSIBILE_RIMANDO")
    db.execute("""INSERT INTO documenti VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (doc_id,year,Path(name).name,med,source,name,digest,len(page_data),
         sum(x[2]=="OCR" for x in page_data),
         proto.group()[:100] if proto else None,
         ".".join(dt.groups()) if dt else None,
         det.group()[:200] if det else None,
         ind.group()[:250] if ind else None,
         "COMPLETO" if "OCR_INCOMPLETO" not in ambig else "DA_COMPLETARE",
         ",".join(ambig)))
    for page_number,text,method in page_data:
        db.execute("INSERT INTO pagine VALUES(?,?,?,?)",(doc_id,page_number,text,method))
        for line in text.splitlines():
            line=" ".join(line.split())[:300]
            if 12<len(line)<240 and CENTER.search(line):
                db.execute("INSERT OR IGNORE INTO centri_candidati VALUES(?,?,?,?)",
                           (doc_id,page_number,line,"DA_VERIFICARE"))
        for m in REF.finditer(text):
            db.execute("INSERT OR IGNORE INTO rimandi_candidati VALUES(?,?,?,?)",
                       (doc_id,page_number,m.group()[:130],"DA_VERIFICARE"))
    return {"nuovo":1,"pagine":len(page_data),
            "ocr":sum(x[2]=="OCR" for x in page_data),
            "ocr_mancante":sum(x[2]=="OCR_MANCANTE" for x in page_data)}

def import_structures(db, blob, source_url, snapshot_date):
    if len(blob)>MAX_CSV: raise ValueError("CSV strutture troppo grande")
    try: raw=blob.decode("utf-8-sig")
    except UnicodeDecodeError: raw=blob.decode("cp1252")
    rows=csv.DictReader(io.StringIO(raw),delimiter=";")
    if tuple(rows.fieldnames or ()) != EXPECTED_COLUMNS:
        raise ValueError("Intestazioni CSV AIFA strutture non riconosciute")
    total=0
    selected=0
    for row in rows:
        total+=1
        if str(row["Regione"]).strip().upper()!="CAMPANIA":continue
        vals=[(row[k] or "").strip() for k in EXPECTED_COLUMNS]
        if not vals[0] or not vals[3]:continue
        key=sha256("\x1f".join(vals).encode("utf-8")).hexdigest()[:32]
        db.execute("INSERT OR IGNORE INTO strutture_registri VALUES(?,?,?,?,?,?,?,?,?)",
                   (key,snapshot_date,vals[0],vals[1],vals[2],vals[3],
                    normalize(vals[3]),vals[4],source_url))
        selected+=1
    if total<10000 or selected<1000:
        raise ValueError("CSV AIFA incompleto / assenza dati Campania")
    return {"righe_totali":total,"righe_campania":selected}

def build_db(zip_inputs, structure_input=None, ocr=True, output=DB_GZ, report=REPORT):
    """zip_inputs: sequence of (anno, url, bytes). Snapshot atomico e ripetibile."""
    output=Path(output)
    report=Path(report)
    output.parent.mkdir(parents=True,exist_ok=True)
    report.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="farmaquery_region_",dir=output.parent) as temp:
        stage=Path(temp)/"regione.sqlite"
        counts={"note":0,"duplicati":0,"pagine":0,"pagine_ocr":0,"pagine_da_ocr":0}
        sources=[]
        with sqlite3.connect(stage) as db:
            db.executescript(SCHEMA)
            for year,url,blob in zip_inputs:
                sha=sha256(blob).hexdigest()
                records=safe_zip_files(blob)
                sources.append({"anno":year,"url":url,"sha256":sha,"pdf":len(records)})
                for name,pdf in records:
                    info=extract_pdf(db,name,pdf,year,url,use_ocr=ocr)
                    for field,source_field in (("note","nuovo"),("duplicati","duplicato"),
                                               ("pagine","pagine"),("pagine_ocr","ocr"),
                                               ("pagine_da_ocr","ocr_mancante")):
                        counts[field]+=info.get(source_field,0)
            if structure_input:
                url,csv_blob,ref=structure_input
                counts.update(import_structures(db,csv_blob,url,ref))
                db.execute("INSERT INTO acquisizioni VALUES(?,?,?,?,?)",
                           ("aifa_strutture",url,sha256(csv_blob).hexdigest(),ref,
                            "Elenco strutture abilitate ai registri AIFA, non note regionali"))
            for src in sources:
                db.execute("INSERT INTO acquisizioni VALUES(?,?,?,?,?)",
                    ("note_"+str(src["anno"]),src["url"],src["sha256"],str(src["anno"]),
                     "Archivio ZIP regionale: PDF consultabile tramite archivio ufficiale"))
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise ValueError("SQLite regionale non integro")
            counts["centri_candidati"]=db.execute("SELECT COUNT(*) FROM centri_candidati").fetchone()[0]
            counts["rimandi_candidati"]=db.execute("SELECT COUNT(*) FROM rimandi_candidati").fetchone()[0]
            counts["strutture_registri"]=db.execute("SELECT COUNT(*) FROM strutture_registri").fetchone()[0]
        if counts["note"]<1:
            raise ValueError("Nessuna nota regionale acquisita")
        packed=Path(temp)/"regione.sqlite.gz"
        with stage.open("rb") as source,packed.open("wb") as dest:
            with gzip.GzipFile(fileobj=dest,mode="wb",filename="",mtime=0,compresslevel=7) as z:
                while chunk:=source.read(1024*1024):z.write(chunk)
        if packed.stat().st_size>90_000_000:
            raise ValueError("Snapshot regionale troppo grande per GitHub")
        meta={"esito":"OK" if counts["pagine_da_ocr"]==0 else "PARZIALE_OCR",
              "statistiche":counts,"fonti":sources,
              "archivio_compresso_sha256":sha256(packed.read_bytes()).hexdigest(),
              "nota":"Centri individuati in PDF come candidati DA_VERIFICARE. "
                     "La presenza nella lista registri non prova di per se' ogni indicazione regionale."}
        tmp=Path(temp)/"stato.json"
        tmp.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(packed,output)
        os.replace(tmp,report)
        return meta

def online_sources():
    html=download(REGIONE,2_000_000).decode("utf-8","replace")
    detected=discover_archives(html)
    if len(detected)<5:
        raise ValueError("Pagina regionale incompleta: sono attesi gli archivi 2022-2026")
    archives=[(year,detected[year],download(detected[year],MAX_ZIP))
              for year in sorted(detected)]
    aifa_html=download(AIFA,3_000_000).decode("utf-8","replace")
    source=discover_aifa_csv(aifa_html)
    match=re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})\.csv",source,re.I)
    if not match:raise ValueError("Data della fonte AIFA assente")
    reference="-".join(match.groups())
    return archives,(source,download(source,MAX_CSV),reference)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--notes-zip",type=Path,help="ZIP aggregato del relatore per collaudo riproducibile")
    parser.add_argument("--structures-csv",type=Path,help="CSV strutture del relatore")
    parser.add_argument("--structures-date",default="2026-09-14")
    parser.add_argument("--skip-ocr",action="store_true")
    parser.add_argument("--db-out",type=Path,default=DB_GZ)
    parser.add_argument("--report-out",type=Path,default=REPORT)
    args=parser.parse_args()
    if args.notes_zip:
        archive=[(0,"https://www.regione.campania.it/archivio-fornito-dal-relatore",
                  args.notes_zip.read_bytes())]
        structures=(AIFA,args.structures_csv.read_bytes(),args.structures_date) if args.structures_csv else None
    else:
        archive,structures=online_sources()
    print(json.dumps(build_db(archive,structures,not args.skip_ocr,args.db_out,
                              args.report_out),ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
