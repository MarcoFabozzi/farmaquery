#!/usr/bin/env python3
"""Collaudo documentale offline delle quattro dimostrazioni della tesi.

Controlla le evidenze nel medesimo SQLite dei due motori. NON è un risultato
di accuratezza dei chatbot e NON contiene risposte LLM precompilate.
"""
from contextlib import closing
import argparse, hashlib, json
from pathlib import Path
import sqlite3

def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def check(dbfile,manifest):
    metadata=json.loads(Path(manifest).read_text(encoding="utf-8"))
    expected=metadata["sha256_sqlite"]
    if digest(dbfile)!=expected:raise ValueError("Hash SQLite non coincidente")
    with closing(sqlite3.connect(Path(dbfile).resolve().as_uri()+"?mode=ro",uri=True)) as con:
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        assert con.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        note=con.execute("SELECT id FROM note WHERE nome_file='PLUVICTO.pdf'").fetchall()
        assert len(note)==1
        source_id=note[0]["id"]
        centers=list(con.execute(
            "SELECT centro,numero_pagina,ancora_testuale FROM nota_centro_documentato WHERE nota_id=?",
            (source_id,)))
        assert len(centers)==5
        assert all(r["numero_pagina"]==2 for r in centers)
        page=con.execute("SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina=2",
                         (source_id,)).fetchone()["testo"]
        assert all(r["ancora_testuale"] in page for r in centers)
        assert "Lutezio 177" in page or "Lutezio 177 LU" in page
        semantic={}
        for med in ("EVRYSDI 2025.pdf","AGAMREE  Prot.N.0663946-2026.pdf",
                    "ZILBRYSQ.pdf"):
            row=con.execute("""
                SELECT n.id,r.centro,r.numero_pagina,r.ancora_testuale,p.testo
                FROM note n JOIN nota_centro_documentato r ON n.id=r.nota_id
                JOIN pagine p ON p.nota_id=r.nota_id AND p.numero_pagina=r.numero_pagina
                WHERE n.nome_file=? AND r.centro='AOU Federico II'
            """,(med,)).fetchone()
            assert row is not None and row["numero_pagina"]==2
            assert row["ancora_testuale"] in row["testo"]
            semantic[med]=row["numero_pagina"]
        cam=con.execute("SELECT id FROM note WHERE nome_file='CAMZYOS  Prot.N.0641382-2025.pdf'").fetchall()
        assert len(cam)==1
        references=list(con.execute("""
            SELECT numero_pagina,protocollo_richiamato,rapporto,frase FROM nota_rimando_revisionato
            WHERE nota_id=? ORDER BY numero_pagina
        """,(cam[0]["id"],)))
        assert [(r["numero_pagina"],r["rapporto"]) for r in references]==[
            (1,"ANNULLA_E_SOSTITUISCE"),(2,"SEMPLICE_RICHIAMO")]
        for r in references:
            original=con.execute("SELECT testo FROM pagine WHERE nota_id=? AND numero_pagina=?",
                                (cam[0]["id"],r["numero_pagina"])).fetchone()["testo"]
            assert r["frase"] in original
        # Una data di attivazione SINFONIA non è una colonna dello schema:
        # questa verifica strutturale NON dimostra che il fatto non sia nei PDF.
        negative_status=("DA_VERIFICARE_DOCUMENTALMENTE: il mancato recupero "
                         "non equivale a prova normativa di assenza")
        return {
            "esito":"PRECOLLAUDO_FONTI_SUPERATO",
            "snapshot_sha256":expected,
            "semplice":{"fonte":"PLUVICTO.pdf","pagina":2,"centri_rintracciati":len(centers)},
            "semantica":{"fonti_con_federico_ii":semantic,
                         "categoria_automatica_memorizzata":False},
            "rimandi":{"fonte":"CAMZYOS Prot. N.0641382/2025",
                       "relazioni":[dict(r) for r in references]},
            "negativa":{"esito":negative_status},
            "limitazione":"Nessuna chiamata LLM. Le relazioni rivedute sul testo non sono convalide visive dei PDF."
        }

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--db",required=True)
    a.add_argument("--manifest",required=True)
    a.add_argument("--out")
    args=a.parse_args()
    report=check(args.db,args.manifest)
    if args.out:
        path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
