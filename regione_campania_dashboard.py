"""Vista sperimentale di note Campania e centri AIFA in FarmaQuery.

Non confonde le strutture nei registri AIFA con i centri autorizzati
per ogni indicazione dalle singole note regionali.
"""
from __future__ import annotations

from contextlib import closing
import gzip
from pathlib import Path
import re
import sqlite3
import tempfile
import streamlit as st


@st.cache_resource(show_spinner=False,max_entries=2)
def _db_regionale(gz_path,version):
    archive=Path(gz_path)
    dest=Path(tempfile.mkdtemp(prefix="farmaquery_regione_"))/"regione.sqlite"
    with gzip.open(archive,"rb") as source,dest.open("wb") as target:
        total=0
        while chunk:=source.read(1024*1024):
            total+=len(chunk)
            if total>120_000_000:
                raise ValueError("Database regionale oltre limite di sicurezza")
            target.write(chunk)
    with closing(sqlite3.connect(dest.as_uri()+"?mode=ro",uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("Integrità della raccolta regionale non verificata")
    return dest


def _query(database,sql,params=()):
    with closing(sqlite3.connect(Path(database).as_uri()+"?mode=ro",uri=True)) as con:
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        return [dict(x) for x in con.execute(sql,params)]


def mostra_sezione_regione(data_dir):
    path=Path(data_dir)/"regione_campania.sqlite.gz"
    st.markdown("### 🏥 Note regionali e centri prescrittori")
    st.caption("Regione Campania · Documenti regionali e strutture abilitate ai registri AIFA. "
               "La verifica della prescrivibilità per una specifica indicazione richiede "
               "la consultazione della nota e dei suoi eventuali aggiornamenti.")
    if not path.is_file():
        st.info("La raccolta regionale è in fase di acquisizione. "
                "Sono in preparazione l'estrazione delle pagine e il collegamento ai centri.")
        return
    try:
        db=_db_regionale(str(path),path.stat().st_mtime_ns)
        counts=_query(db,"SELECT (SELECT COUNT(*) FROM documenti) note, "
                         "(SELECT COUNT(*) FROM pagine) pagine, "
                         "(SELECT COUNT(*) FROM strutture_registri) strutture")[0]
        c1,c2,c3=st.columns(3)
        c1.metric("Note PDF",counts["note"])
        c2.metric("Pagine indicizzate",counts["pagine"])
        c3.metric("Abilitazioni registri",counts["strutture"])
        term=st.text_input("Cerca farmaco, nota, patologia o centro",
                           key="cerca_regione",placeholder="Es. SKYCLARYS, Cardarelli, miastenia")
        if not term.strip():
            st.caption("Digita un medicinale, una patologia oppure un centro per consultare le fonti.")
            return
        safe=term.strip()[:100].replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
        like="%"+safe+"%"
        notes=_query(db,
            "SELECT DISTINCT d.id,d.nome,d.nome_farmaco,d.anno,d.protocollo_estratto,"
            "d.zip_url,d.path_zip,d.pagine,d.flag_ambiguita FROM documenti d "
            "LEFT JOIN pagine p ON p.documento_id=d.id "
            "WHERE d.nome LIKE ? ESCAPE '\\' OR d.nome_farmaco LIKE ? ESCAPE '\\' "
            "OR p.testo LIKE ? ESCAPE '\\' "
            "ORDER BY d.anno DESC,d.nome LIMIT 35",(like,like,like))
        st.markdown("#### Note regionali")
        if not notes:
            st.write("Nessuna nota trovata nei testi indicizzati. "
                     "Non significa che il medicinale non sia prescrivibile.")
        for note in notes:
            title=note["nome"]+" · "+str(note["anno"])
            with st.expander(title):
                st.write("**Protocollo estratto (da verificare):**",
                         note["protocollo_estratto"] or "Non identificato")
                st.write("**File nell'archivio:**",note["path_zip"])
                st.link_button("Archivio ufficiale della Regione",note["zip_url"])
                pages=_query(db,"SELECT pagina,testo,metodo FROM pagine WHERE documento_id=? "
                                "AND (testo LIKE ? ESCAPE '\\' OR pagina=1) "
                                "ORDER BY pagina LIMIT 4",(note["id"],like))
                for page in pages:
                    st.markdown("**Pagina "+str(page["pagina"])+" · "+page["metodo"]+"**")
                    excerpt=page["testo"]
                    found=re.search(re.escape(term.strip()),excerpt,flags=re.I)
                    if found:
                        excerpt=excerpt[max(0,found.start()-320):found.end()+650]
                    else:
                        excerpt=excerpt[:700]
                    st.text(excerpt if excerpt.strip() else "Testo non estraibile: OCR da completare")
                centre=_query(db,"SELECT pagina,testo_candidato FROM centri_candidati "
                                 "WHERE documento_id=? ORDER BY pagina LIMIT 5",(note["id"],))
                if centre:
                    st.caption("Possibili menzioni di centri (non validate):")
                    for c in centre:
                        st.write("p. "+str(c["pagina"])+": "+c["testo_candidato"])
                if note["flag_ambiguita"]:
                    st.caption("Verifiche necessarie: "+note["flag_ambiguita"])
        clinics=_query(db,
            "SELECT medicinale,patologia,indicazione,struttura,data_riferimento,fonte_url "
            "FROM strutture_registri WHERE medicinale LIKE ? ESCAPE '\\' "
            "OR patologia LIKE ? ESCAPE '\\' OR struttura LIKE ? ESCAPE '\\' "
            "ORDER BY medicinale,struttura LIMIT 70",(like,like,like))
        st.markdown("#### Strutture abilitate ai registri AIFA")
        if clinics:
            st.dataframe([{"Medicinale":r["medicinale"],"Patologia":r["patologia"],
                           "Struttura":r["struttura"],"Fonte (data)":r["data_riferimento"]}
                          for r in clinics],hide_index=True,use_container_width=True)
            st.link_button("Elenco ufficiale AIFA",clinics[0]["fonte_url"])
            st.caption("Queste abilitazioni sono relative ai registri AIFA. "
                       "Non sostituiscono le note regionali per singola indicazione.")
        else:
            st.write("Nessuna struttura corrispondente nel file acquisito.")
        st.caption("Le citazioni alle note indicano l'archivio PDF, il nome del "
                   "documento e la pagina. I nomi di centri individuati "
                   "automaticamente sono candidati, non autorizzazioni confermate.")
    except (OSError,ValueError,sqlite3.DatabaseError) as exc:
        st.warning("Raccolta regionale non disponibile: "+str(exc))
