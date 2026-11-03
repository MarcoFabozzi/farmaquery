#!/usr/bin/env python3
"""Fotografia offline FarmaQuery: deriva SQLite statico da artifact 02/11/2026.
Nessun download di nuove fonti, LLM, preclassificazione clinica o gold inseriti.
I 28 legami centro/nota provengono dalla revisione manuale del progetto.
"""
import argparse,gzip,hashlib,json,re,shutil,sqlite3
from pathlib import Path
ORIGIN="bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53"
def digest(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1048576),b""):h.update(b)
 return h.hexdigest()
# nome PDF, medicinale, indicazione, pagina e coppie (centro,ancora), non una
# dichiarazione di abilitazione vigente; i nomi vengono verificati nei testi.
CURATED=[
("PLUVICTO.pdf","PLUVICTO","mCRPC progressivo, PSMA-positivo, pazienti adulti dopo inibizione AR e chemioterapia a base di taxani",2,[
("AOU Federico II","-AOU FEDERICO II"),("AORN dei Colli","-AORN COLLI"),
("AORN Cardarelli","-AORN CARDARELLI"),
("ASL Napoli 1 Centro – P.O. Ospedale del Mare","-ASL NA 1 CENTRO - PO OSPEDALE DEL MARE"),
("IRCCS Pascale","-IRCCS-PASCALE")]),
("DUVYZAT  Prot.N.0368583-2026.pdf","DUVYZAT","Distrofia muscolare di Duchenne (DMD), pazienti deambulanti >=6 anni con corticosteroidi",2,[
("AORN Santobono-Pausilipon","A.O.R.N. Santobono-Pausilipon, Napoli"),
("AOU San Giovanni di Dio e Ruggi d'Aragona","AOU \"San Giovanni di Dio Ruggi d'Aragona\", Salerno"),
("AOU Luigi Vanvitelli","della Campania \"Luigi Vanvitelli\""),
("AOU Federico II","Azienda Ospedaliera Universitaria Federico II, Napoli")]),
("CAMZYOS  Prot.N.0641382-2025.pdf","CAMZYOS","CMIO sintomatica NYHA II-III in adulti; indicazione negoziata con terapia standard insufficiente",2,[
("AORN dei Colli – P.O. Monaldi","AORN COLLI- P.O. MONALDI"),
("AORN Sant’Anna e San Sebastiano","AORN S. ANNA E S. SEBASTIANO"),
("AOU Federico II","AOU FEDERICO II"),("AOU Ruggi d'Aragona","AOU RUGGI D’ARAGONA"),
("AORN Cardarelli","AORN CARDARELLI"),("AO San Pio","AO SAN PIO"),
("AORN Moscati","AORN MOSCATI"),
("ASL Napoli 2 Nord – P.O. Santa Maria delle Grazie","ASL NAPOLI 2 NORD- PO S. MARIA DELLE GRAZIE"),
("ASL Salerno – P.O. Umberto I, Nocera","ASL SALERNO- PO UMBERTO I Nocera"),
("ASL Benevento – Ospedale Fatebenefratelli","ASL BENEVENTO - Ospedale Fatebenefratelli")]),
("AMVUTTRA Prot.N.0634617-2026.pdf","AMVUTTRA","ATTR-CM: cardiomiopatia da transtiretina wild-type o ereditaria in adulti (Tabella 1)",2,[
("AO Ospedali dei Colli","AO Ospedali dei Colli, Napoli"),
("AOU San Giovanni di Dio e Ruggi d'Aragona","AOU S. Giovanni di Dio e Ruggi D'Aragona"),
("AORN San Giuseppe Moscati","AORN S. Giuseppe Moscati, Avellino"),
("AO Sant'Anna e San Sebastiano","AO Sant'Anna e San Sebastiano, Caserta"),
("AOU Federico II","AOU Federico II, Napoli"),
("AORN Cardarelli","AORN. A. Cardarelli, Napoli")])]
ADDITIONS=[
("EVRYSDI 2025.pdf","AOU Federico II","A.O.U. Federico II- Napoli","Atrofia muscolare spinale (SMA) 5q; indicazione della nota"),
("AGAMREE  Prot.N.0663946-2026.pdf","AOU Federico II","AOU Federico II, Napoli","Distrofia muscolare di Duchenne (DMD); indicazione della nota"),
("ZILBRYSQ.pdf","AOU Federico II","NAPOLI FEDERICO II, NAPOLI","Miastenia gravis generalizzata (gMG) AChR positiva; indicazione della nota")]
MANUAL_META={
"PLUVICTO":("PG/2025/0201843","2025-04-18","Determina AIFA n. 241 del 20 febbraio 2025","lutezio (177Lu) vipivotide tetraxetan"),
"DUVYZAT":("0368583/2026","2026-04-17","Determina AIFA Pres. n. 357 del 19 marzo 2026","givinostat"),
"CAMZYOS":("0641382/2025","2025-11-20","Determina AIFA Pres. n. 1387 del 21 ottobre 2025","mavacamten"),
"AMVUTTRA":("0634617/2026","2026-07-17","Determina AIFA Pres. n. 655 del 21 maggio 2026","vutrisiran")}
SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE nota_metadati_revisionati(nota_id TEXT PRIMARY KEY REFERENCES note(id),protocollo TEXT,data_nota TEXT,determina_aifa TEXT,principio_attivo TEXT,indicazione TEXT,pagina_evidenza INTEGER,stato TEXT,metodo TEXT);
CREATE TABLE nota_aifa_corrispondenze(nota_id TEXT REFERENCES note(id),aic TEXT REFERENCES aifa_confezioni(aic),principio_attivo_aifa TEXT,tipo TEXT,stato TEXT,PRIMARY KEY(nota_id,aic));
CREATE TABLE nota_centro_documentato(id INTEGER PRIMARY KEY,nota_id TEXT REFERENCES note(id),centro TEXT,indicazione TEXT,numero_pagina INTEGER,ancora_testuale TEXT,fonte_percorso_zip TEXT,stato TEXT,FOREIGN KEY(nota_id,numero_pagina) REFERENCES pagine(nota_id,numero_pagina));
CREATE TABLE nota_struttura_aifa_corrispondenze(nota_centro_id INTEGER PRIMARY KEY REFERENCES nota_centro_documentato(id),struttura_registro_id TEXT REFERENCES strutture_registri(id),stato TEXT,spiegazione TEXT);
CREATE TABLE nota_rimando_revisionato(nota_id TEXT REFERENCES note(id),numero_pagina INTEGER,protocollo_richiamato TEXT,rapporto TEXT,frase TEXT,stato TEXT,PRIMARY KEY(nota_id,protocollo_richiamato));
CREATE TABLE revisione_relazioni_manuale_v2(relazione_id INTEGER PRIMARY KEY REFERENCES nota_centro_documentato(id),nota_id TEXT REFERENCES note(id),pagina INTEGER,estratto_evidenza TEXT,richiamo_autorizzativo TEXT,esito TEXT,metodo TEXT,osservazioni TEXT);
CREATE TABLE revisione_collegamenti_aifa_v2(relazione_id INTEGER PRIMARY KEY REFERENCES nota_centro_documentato(id),stato TEXT,nota TEXT);
CREATE INDEX idx_nota_centro ON nota_centro_documentato(centro);
CREATE INDEX idx_nota_aifa ON nota_aifa_corrispondenze(principio_attivo_aifa);
"""
def build(source,source_manifest,dest,manifest,gzip_dest):
 if digest(source)!=ORIGIN or json.loads(Path(source_manifest).read_text())["sha256_sqlite"]!=ORIGIN:
  raise ValueError("Fotografia originale differente dal 02/11/2026; esecuzione interrotta")
 dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(source,dest)
 with sqlite3.connect(dest) as db:
  db.row_factory=sqlite3.Row
  db.executescript(SCHEMA)
  notes=list(db.execute("SELECT * FROM note"))
  aifa={}
  for r in db.execute("SELECT aic,nome,principio_attivo FROM aifa_confezioni"):
   aifa.setdefault((r["nome"] or "").strip().upper(),[]).append(r)
  for n in notes:
   pkgs=aifa.get((n["farmaco_candidato"] or "").strip().upper(),[])
   active={x["principio_attivo"] for x in pkgs if x["principio_attivo"]}
   db.execute("INSERT INTO nota_metadati_revisionati VALUES(?,?,?,?,?,?,?,?,?)",
      (n["id"],n["protocollo_candidato"],n["data_candidata"],n["determina_candidata"],
       next(iter(active)) if len(active)==1 else None,n["indicazione_candidata"],
       None,"CANDIDATO_ESTRATTO","Regex/nome commerciale da verificare"))
   for p in pkgs:
    db.execute("INSERT INTO nota_aifa_corrispondenze VALUES(?,?,?,?,?)",
       (n["id"],p["aic"],p["principio_attivo"],"STESSO_NOME_COMMERCIALE","CANDIDATO_NOME_COMMERCIALE"))
  for title,med,ind,page,centers in CURATED:
   found=[n for n in notes if n["nome_file"]==title and (n["farmaco_candidato"] or "").upper()==med]
   if len(found)!=1:raise ValueError("Documento ambiguo: "+title)
   n=found[0];p=db.execute("SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina=?",(n["id"],page)).fetchone()
   if not p or not re.search(r"sono\s+autorizzat[ie]",p["testo"],re.I):
    raise ValueError("Manca autorizzazione nella pagina: "+title)
   proto,date,det,active=MANUAL_META[med]
   db.execute("""UPDATE nota_metadati_revisionati SET protocollo=?,data_nota=?,
      determina_aifa=?,principio_attivo=?,indicazione=?,pagina_evidenza=1,
      stato='RIVISTO_SU_TESTO',metodo='Revisione manuale del testo dello snapshot'
      WHERE nota_id=?""",(proto,date,det,active,ind,n["id"]))
   fulltext=" ".join(row["testo"] for row in db.execute("SELECT testo FROM pagine WHERE nota_id=?",(n["id"],)))
   codes=set(re.findall(r"\b\d{9}\b",fulltext))
   for aic, in db.execute("SELECT aic FROM nota_aifa_corrispondenze WHERE nota_id=?",(n["id"],)).fetchall():
    if aic in codes:
     db.execute("""UPDATE nota_aifa_corrispondenze SET tipo='AIC_PRESENTE_NELLA_NOTA',
                  stato='AIC_DOCUMENTATO_NEL_TESTO' WHERE nota_id=? AND aic=?""",(n["id"],aic))
   for center,anchor in centers:
    append_center(db,n,page,center,anchor,ind,med=="PLUVICTO")
  for title,center,anchor,ind in ADDITIONS:
   found=[n for n in notes if n["nome_file"]==title]
   if len(found)!=1:raise ValueError("Documento ambiguo: "+title)
   n=found[0]
   text=" ".join(x["testo"] for x in db.execute("SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina<=2",(n["id"],)))
   if not re.search(r"sono\s+autorizzat[ie]",text,re.I):
    raise ValueError("Nessun paragrafo autorizzativo: "+title)
   append_center(db,n,2,center,anchor,ind,False)
  cam=[n for n in notes if n["nome_file"]=="CAMZYOS  Prot.N.0641382-2025.pdf"][0]
  for page,ref,code,reln in [(1,"La presente annulla e  sostituisce la nota Prot. N.0624981/2025","0624981/2025","ANNULLA_E_SOSTITUISCE"),
                              (2,"Come da Nota PG/2024/0503681 del 24/10/2024","PG/2024/0503681","SEMPLICE_RICHIAMO")]:
   body=db.execute("SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina=?",(cam["id"],page)).fetchone()["testo"]
   if ref not in body:raise ValueError("Rimando non trovato")
   db.execute("INSERT INTO nota_rimando_revisionato VALUES(?,?,?,?,?,?)",(cam["id"],page,code,reln,ref,"CONFERMATO_TESTO_PDF_DA_RIVEDERE"))
  db.commit()
  if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or db.execute("PRAGMA foreign_key_check").fetchall():
   raise ValueError("Integrità SQLite non valida")
  counts={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("note","pagine","ema_medicinali","aifa_confezioni","strutture_registri","nota_metadati_revisionati","nota_centro_documentato","nota_aifa_corrispondenze","nota_rimando_revisionato")}
  if counts["note"]!=380 or counts["pagine"]!=942 or counts["nota_centro_documentato"]!=28:
   raise ValueError("Conteggio sorgente non corrispondente")
 gzip_dest=Path(gzip_dest);gzip_dest.parent.mkdir(parents=True,exist_ok=True)
 with open(dest,"rb") as src,open(gzip_dest,"wb") as raw:
  with gzip.GzipFile(fileobj=raw,mode="wb",filename="",mtime=0,compresslevel=7) as comp:
   shutil.copyfileobj(src,comp)
 result={"tipo":"TESI_STATICO_V2_CI","data_fonte":"2026-11-02","snapshot_origine_sha256":ORIGIN,
         "sha256_sqlite":digest(dest),"sha256_gzip":digest(gzip_dest),
         "file":dest.name,"file_gzip":gzip_dest.name,"conteggi":counts,
         "revisione":"5 PDF già verificati; 23 solo testo; AIFA solo corrispondenze candidate"}
 Path(manifest).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(result,ensure_ascii=False))
 return result
def append_center(db,n,page,center,anchor,ind,verified_pdf):
 body=db.execute("SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina=?",(n["id"],page)).fetchone()["testo"]
 if anchor not in body:raise ValueError("Ancora non trovata: "+n["nome_file"]+" "+center)
 status="GOLD_PDF_VERIFICATO" if verified_pdf else "CONTROLLATO_SU_TESTO_PDF_DA_REVISIONARE"
 cur=db.execute("""INSERT INTO nota_centro_documentato
  (nota_id,centro,indicazione,numero_pagina,ancora_testuale,fonte_percorso_zip,stato)
  VALUES (?,?,?,?,?,?,?)""",(n["id"],center,ind,page,anchor,n["percorso_zip"],status))
 rid=cur.lastrowid
 # Solo associazione candidata: cercare nel registro la stessa medicina e
 # il nome del centro non prova un'autorizzazione per la specifica indicazione.
 match=list(db.execute("SELECT id,struttura FROM strutture_registri WHERE medicinale=? AND struttura LIKE ?",
                       (n["farmaco_candidato"],"%"+center.split(" ")[-1]+"%")))
 if len(match)==1:
  sid=match[0]["id"];st="CANDIDATO_EQUIVALENZA_DENOMINAZIONE"
 else:sid=None;st="NESSUNA_CORRISPONDENZA_UNIVOCA"
 db.execute("INSERT INTO nota_struttura_aifa_corrispondenze VALUES(?,?,?,?)",
            (rid,sid,st,"Match nominale candidato, non prova di abilitazione"))
 before=list(db.execute("SELECT numero_pagina,testo FROM pagine WHERE nota_id=? AND numero_pagina<=? ORDER BY numero_pagina",(n["id"],page)))
 prior=[]
 for p in before:
  m=re.search(r"sono\s+autorizzat[ie]",p["testo"],re.I)
  if m:prior.append((p["numero_pagina"],p["testo"][max(0,m.start()-60):m.end()+180]))
 if not prior:raise ValueError("Paragrafo centro non attestato "+n["nome_file"])
 pnum,phrase=prior[-1]
 flat=" ".join(body.split());at=flat.find(" ".join(anchor.split()))
 snippet=flat[max(0,at-170):at+len(anchor)+170]
 db.execute("INSERT INTO revisione_relazioni_manuale_v2 VALUES(?,?,?,?,?,?,?,?)",(
  rid,n["id"],page,snippet,"pagina "+str(pnum)+": "+" ".join(phrase.split())[:250],
  "VERIFICATO_SU_TESTO_ESTRATTO","Lettura testo estratto; PDF da verificare visivamente",
  "La nota storica non certifica attivazione corrente"))
 db.execute("INSERT INTO revisione_collegamenti_aifa_v2 VALUES(?,?,?)",
            (rid,"CANDIDATO_NOMINALE" if sid else "NESSUN_COLLEGAMENTO_UNIVOCO_AIFA",
             "Abbinamento nominale; non prova abilitazione operativa"))
def main():
 p=argparse.ArgumentParser()
 for name in ("original","manifest-originale","db","manifest","gzip"):
  p.add_argument("--"+name,required=True)
 a=p.parse_args()
 build(a.original,a.manifest_originale,a.db,a.manifest,a.gzip)
if __name__=="__main__":
 main()
