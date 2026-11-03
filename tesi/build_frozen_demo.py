"""Crea uno SQLite statico per la demo dalla fotografia ufficiale del 02/11/2026.

Non scarica fonti e non contiene risposte per i chatbot: cura soltanto
metadati e relazioni nota-centro con evidenze. I candidati non sono autorizzazioni.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

SOURCE_SHA="bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53"

# (nome PDF, pagina, indicazione, [(centro, testo letterale, struttura AIFA candidata)])
CURATED=[
 ("PLUVICTO.pdf",2,"mCRPC PSMA-positivo dopo AR e chemioterapia a base di taxani",[
 ("AOU Federico II","-AOU FEDERICO II","A.O.U. 'FEDERICO II' DI NAPOLI"),
 ("AORN dei Colli","-AORN COLLI","Monaldi"),
 ("AORN Cardarelli","-AORN CARDARELLI","AZIENDA OSPEDALIERA 'A. CARDARELLI'"),
 ("ASL Napoli 1 Centro – Ospedale del Mare","-ASL NA 1 CENTRO - PO OSPEDALE DEL MARE","PRESIDIO OSPEDALIERO OSPEDALE DEL MARE"),
 ("IRCCS Pascale","-IRCCS-PASCALE","ISTITUTO NAZIONALE TUMORI DI NAPOLI")]),
 ("DUVYZAT  Prot.N.0368583-2026.pdf",2,"Distrofia muscolare di Duchenne (DMD)",[
 ("AORN Santobono-Pausilipon","A.O.R.N. Santobono-Pausilipon, Napoli","OSPEDALE SANTOBONO"),
 ("AOU Ruggi d'Aragona","AOU \"San Giovanni di Dio Ruggi d'Aragona\", Salerno",None),
 ("AOU Luigi Vanvitelli","della Campania \"Luigi Vanvitelli\"","AZIENDA OSPEDALIERA UNIVERSITARIA UNICAM"),
 ("AOU Federico II","Azienda Ospedaliera Universitaria Federico II, Napoli",None)]),
 ("CAMZYOS  Prot.N.0641382-2025.pdf",2,"CMIO sintomatica NYHA II-III",[
 ("AORN dei Colli – Monaldi","AORN COLLI- P.O. MONALDI","Monaldi"),
 ("AORN Sant'Anna e San Sebastiano","AORN S. ANNA E S. SEBASTIANO","A.O. SANT'ANNA E SAN SEBASTIANO  CASERTA"),
 ("AOU Federico II","AOU FEDERICO II","A.O.U. 'FEDERICO II' DI NAPOLI"),
 ("AOU Ruggi d'Aragona","AOU RUGGI D’ARAGONA","A.O. OO.RR. SANGIOVANNI DI DIO E RUGGI"),
 ("AORN Cardarelli","AORN CARDARELLI","AZIENDA OSPEDALIERA 'A. CARDARELLI'"),
 ("AO San Pio","AO SAN PIO",None),
 ("AORN Moscati","AORN MOSCATI","AZIENDA OSPEDALIERA S. G. MOSCATI"),
 ("ASL Napoli 2 Nord – Santa Maria delle Grazie","ASL NAPOLI 2 NORD- PO S. MARIA DELLE GRAZIE","OSPEDALE S.M.DELLE GRAZIE"),
 ("ASL Salerno – Umberto I","ASL SALERNO- PO UMBERTO I Nocera","P.O. UMBERTO I NOCERA INFERIORE"),
 ("ASL Benevento – Fatebenefratelli","ASL BENEVENTO - Ospedale Fatebenefratelli",None)]),
 ("AMVUTTRA Prot.N.0634617-2026.pdf",2,"ATTR-CM: cardiomiopatia da transtiretina",[
 ("AO Ospedali dei Colli","AO Ospedali dei Colli, Napoli","Monaldi"),
 ("AOU Ruggi d'Aragona","AOU S. Giovanni di Dio e Ruggi D'Aragona","A.O. OO.RR. SANGIOVANNI DI DIO E RUGGI"),
 ("AORN San Giuseppe Moscati","AORN S. Giuseppe Moscati, Avellino","AZIENDA OSPEDALIERA S. G. MOSCATI"),
 ("AO Sant'Anna e San Sebastiano","AO Sant'Anna e San Sebastiano, Caserta","A.O. SANT'ANNA E SAN SEBASTIANO  CASERTA"),
 ("AOU Federico II","AOU Federico II, Napoli","A.O.U. 'FEDERICO II' DI NAPOLI"),
 ("AORN Cardarelli","AORN. A. Cardarelli, Napoli","AZIENDA OSPEDALIERA 'A. CARDARELLI'")]),
 ("EVRYSDI 2025.pdf",2,"Atrofia muscolare spinale (SMA) 5q",[
 ("AOU Federico II","A.O.U. Federico II- Napoli",None)]),
 ("AGAMREE  Prot.N.0663946-2026.pdf",2,"Distrofia muscolare di Duchenne (DMD)",[
 ("AOU Federico II","AOU Federico II, Napoli",None)]),
 ("ZILBRYSQ.pdf",2,"Miastenia gravis generalizzata (gMG) AChR+",[
 ("AOU Federico II","NAPOLI FEDERICO II, NAPOLI","A.O.U. 'FEDERICO II' DI NAPOLI")])
]
META={
 "PLUVICTO.pdf":("PG/2025/0201843","2025-04-18","Determina AIFA n. 241 del 20 febbraio 2025","lutezio (177Lu) vipivotide tetraxetan"),
 "DUVYZAT  Prot.N.0368583-2026.pdf":("0368583/2026","2026-04-17","Determina AIFA Pres. n. 357 del 19 marzo 2026","givinostat"),
 "CAMZYOS  Prot.N.0641382-2025.pdf":("0641382/2025","2025-11-20","Determina AIFA Pres. n. 1387 del 21 ottobre 2025","mavacamten"),
 "AMVUTTRA Prot.N.0634617-2026.pdf":("0634617/2026","2026-07-17","Determina AIFA Pres. n. 655 del 21 maggio 2026","vutrisiran"),
}
SQL="""
PRAGMA foreign_keys=ON;
CREATE TABLE nota_metadati_revisionati(
 nota_id TEXT PRIMARY KEY REFERENCES note(id),protocollo TEXT,data_nota TEXT,
 determina_aifa TEXT,principio_attivo TEXT,indicazione TEXT,pagina_evidenza INTEGER,
 stato TEXT NOT NULL,metodo TEXT NOT NULL);
CREATE TABLE nota_aifa_corrispondenze(
 nota_id TEXT REFERENCES note(id),aic TEXT REFERENCES aifa_confezioni(aic),
 principio_attivo_aifa TEXT,tipo TEXT NOT NULL,stato TEXT NOT NULL,
 PRIMARY KEY(nota_id,aic));
CREATE TABLE nota_centro_documentato(
 id INTEGER PRIMARY KEY,nota_id TEXT REFERENCES note(id),centro TEXT,
 indicazione TEXT,numero_pagina INTEGER,ancora_testuale TEXT,
 fonte_percorso_zip TEXT,stato TEXT,
 FOREIGN KEY(nota_id,numero_pagina) REFERENCES pagine(nota_id,numero_pagina));
CREATE TABLE nota_struttura_aifa_corrispondenze(
 nota_centro_id INTEGER PRIMARY KEY REFERENCES nota_centro_documentato(id),
 struttura_registro_id TEXT REFERENCES strutture_registri(id),
 stato TEXT,spiegazione TEXT);
CREATE TABLE nota_rimando_revisionato(
 nota_id TEXT REFERENCES note(id),numero_pagina INTEGER,protocollo_richiamato TEXT,
 rapporto TEXT,frase TEXT,stato TEXT,
 PRIMARY KEY(nota_id,protocollo_richiamato));
CREATE TABLE revisione_relazioni_manuale_v2(
 relazione_id INTEGER PRIMARY KEY REFERENCES nota_centro_documentato(id),
 nota_id TEXT,pagina INTEGER,estratto_evidenza TEXT,richiamo_autorizzativo TEXT,
 esito TEXT,metodo TEXT,osservazioni TEXT);
CREATE TABLE revisione_collegamenti_aifa_v2(
 relazione_id INTEGER PRIMARY KEY REFERENCES nota_centro_documentato(id),
 stato TEXT,nota TEXT);
"""
def digest(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def build(origin,manifest,packed,out_manifest):
    origin,manifest,packed,out_manifest=map(Path,(origin,manifest,packed,out_manifest))
    if digest(origin)!=SOURCE_SHA or json.loads(manifest.read_text())["sha256_sqlite"]!=SOURCE_SHA:
        raise ValueError("Fotografia originale non corrispondente, bloccato")
    packed.parent.mkdir(parents=True,exist_ok=True)
    work=packed.with_suffix(".building.sqlite")
    shutil.copyfile(origin,work)
    try:
        with sqlite3.connect(work) as db:
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(SQL)
            notes=list(db.execute("SELECT * FROM note"))
            names={}
            for aic,name,principio in db.execute(
                "SELECT aic,nome,principio_attivo FROM aifa_confezioni"):
                names.setdefault((name or "").strip().casefold(),[]).append((aic,principio))
            for n in notes:
                pkgs=names.get((n["farmaco_candidato"] or "").strip().casefold(),[])
                actives={p for _,p in pkgs if p}
                active=next(iter(actives)) if len(actives)==1 else None
                db.execute("INSERT INTO nota_metadati_revisionati VALUES (?,?,?,?,?,?,?,?,?)",
                    (n["id"],n["protocollo_candidato"],n["data_candidata"],
                    n["determina_candidata"],active,n["indicazione_candidata"],
                    None,"CANDIDATO_ESTRATTO","Regex e corrispondenza nome commerciale"))
                for aic,p in pkgs:
                    db.execute("INSERT INTO nota_aifa_corrispondenze VALUES (?,?,?,?,?)",
                        (n["id"],aic,p,"STESSO_NOME_COMMERCIALE","CANDIDATO_NOME_COMMERCIALE"))
            for filename,page,indication,centers in CURATED:
                matches=[n for n in notes if n["nome_file"]==filename]
                if len(matches)!=1:raise ValueError("Nota ambigua "+filename)
                n=matches[0]
                body=db.execute("SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina=?",
                                (n["id"],page)).fetchone()
                if not body:raise ValueError("Pagina non presente "+filename)
                body=body[0]
                first="\n".join(r[0] for r in db.execute(
                    "SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina<=?",
                    (n["id"],page)))
                approvals=list(re.finditer(r"sono\s+autorizzat[ie]",first,re.I))
                if not approvals:raise ValueError("Autorizzazione non trovata "+filename)
                at=approvals[-1].start()
                approval=" ".join(first[max(0,at-65):at+270].split())[:270]
                if filename in META:
                    proto,date,determ,active=META[filename]
                    db.execute("""UPDATE nota_metadati_revisionati
                     SET protocollo=?,data_nota=?,determina_aifa=?,principio_attivo=?,
                         indicazione=?,pagina_evidenza=1,stato='RIVISTO_SU_TESTO',
                         metodo='Controllo pagina testuale originale'
                     WHERE nota_id=?""",(proto,date,determ,active,indication,n["id"]))
                for center,anchor,registry_name in centers:
                    index=body.find(anchor)
                    if index<0:raise ValueError("Ancora non attestata: "+filename+" "+anchor)
                    status=("GOLD_PDF_VERIFICATO" if filename=="PLUVICTO.pdf"
                            else "CONTROLLATO_SU_TESTO_PDF_DA_REVISIONARE")
                    cur=db.execute("""INSERT INTO nota_centro_documentato
                        (nota_id,centro,indicazione,numero_pagina,ancora_testuale,
                         fonte_percorso_zip,stato) VALUES (?,?,?,?,?,?,?)""",
                        (n["id"],center,indication,page,anchor,n["percorso_zip"],status))
                    rid=cur.lastrowid
                    regs=list(db.execute("SELECT id FROM strutture_registri WHERE medicinale=? AND struttura=?",
                                         (n["farmaco_candidato"],registry_name))) if registry_name else []
                    reg=regs[0][0] if len(regs)==1 else None
                    db.execute("INSERT INTO nota_struttura_aifa_corrispondenze VALUES (?,?,?,?)",
                        (rid,reg,"CANDIDATO_EQUIVALENZA_DENOMINAZIONE" if reg else
                        "NESSUNA_CORRISPONDENZA_UNIVOCA",
                        "Confronto nominale: non prova operativita' attuale"))
                    snippet=" ".join(body[max(0,index-170):index+len(anchor)+170].split())
                    db.execute("INSERT INTO revisione_relazioni_manuale_v2 VALUES (?,?,?,?,?,?,?,?)",
                        (rid,n["id"],page,snippet,approval,
                         "VERIFICATO_SU_TESTO_ESTRATTO","Rilettura manuale OCR originale",
                         "Non equivale a verifica visiva di tutti i PDF"))
                    db.execute("INSERT INTO revisione_collegamenti_aifa_v2 VALUES (?,?,?)",
                        (rid,"CANDIDATO_NOMINALE_CON_MEDICINALE_COINCIDENTE" if reg else
                         "NESSUN_COLLEGAMENTO_UNIVOCO_AIFA","Abbinamento non certificato"))
            cam=[n for n in notes if n["nome_file"].startswith("CAMZYOS  Prot.N.0641382")]
            if len(cam)!=1:raise ValueError("Nota CAMZYOS ambigua")
            for page,proto,rel,quote in [
              (1,"0624981/2025","ANNULLA_E_SOSTITUISCE",
               "La presente annulla e  sostituisce la nota Prot. N.0624981/2025"),
              (2,"PG/2024/0503681","SEMPLICE_RICHIAMO",
               "Come da Nota PG/2024/0503681 del 24/10/2024")]:
                pg=db.execute("SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina=?",
                              (cam[0]["id"],page)).fetchone()
                if not pg or quote not in pg[0]:raise ValueError("Rimando non attestato "+proto)
                db.execute("INSERT INTO nota_rimando_revisionato VALUES (?,?,?,?,?,?)",
                           (cam[0]["id"],page,proto,rel,quote,"CONFERMATO_TESTO_DA_RIVEDERE"))
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("Corruzione SQLite")
            if db.execute("PRAGMA foreign_key_check").fetchall():raise ValueError("FK non valide")
            count={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
                   for t in ("note","pagine","aifa_confezioni","ema_medicinali",
                             "nota_centro_documentato","nota_aifa_corrispondenze",
                             "nota_rimando_revisionato","revisione_relazioni_manuale_v2")}
            if count["note"]!=380 or count["pagine"]!=942 or count["nota_centro_documentato"]!=28:
                raise ValueError("Conteggi inesperati "+str(count))
        h=digest(work)
        with work.open("rb") as input,packed.open("wb") as output:
            with gzip.GzipFile(fileobj=output,mode="wb",filename="",mtime=0) as z:
                for chunk in iter(lambda:input.read(1<<20),b""):z.write(chunk)
        result={"tipo":"SNAPSHOT_STATICO_DEMO_TESI","data_fonte":"2026-11-02",
                "snapshot_origine_sha256":SOURCE_SHA,"sha256_sqlite":h,
                "conteggi":count,
                "limiti":["28 relazioni revisionate, non tutte le 380 note",
                         "23 relazioni non verificate visivamente sul PDF",
                         "corrispondenze AIFA nominali, non autorizzazioni vigenti"]}
        out_manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return result
    finally:
        work.unlink(missing_ok=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--output-manifest",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(build(a.db,a.manifest,a.output,a.output_manifest),ensure_ascii=False))
