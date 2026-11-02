"""Diagnostica read-only dei dati locali: non pubblica classificazioni."""
from collections import Counter
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import tempfile

BASE=Path(__file__).resolve().parent
DATA=BASE/'risultati'
main=DATA/'farmaci_automatico.sqlite'
archive=DATA/'aifa_confezioni_complete.sqlite.gz'

with closing(sqlite3.connect(main.as_uri()+'?mode=ro',uri=True)) as db:
    print("CLASSI DB PRINCIPALE")
    print(db.execute("SELECT COALESCE(NULLIF(TRIM(classe_da_anagrafica),''),'[vuota]'), COUNT(*) FROM aifa_confezioni GROUP BY 1 ORDER BY 2 DESC LIMIT 20").fetchall())
    print("CLASSI DOCUMENTATE")
    print(db.execute("SELECT COALESCE(classe_nuova,'[vuota]'), COUNT(*) FROM eventi_verificati GROUP BY 1").fetchall())
    print("Cnn storico count",db.execute("SELECT COUNT(*) FROM cnn_elenco_storico").fetchone()[0])
    cnn=db.execute("SELECT nome,principio_attivo,numero_procedura,raw_json FROM cnn_elenco_storico LIMIT 1000").fetchall()
    keys=Counter()
    aic_samples=Counter()
    for nome,active,proc,raw in cnn:
        data=json.loads(raw)
        for k in data:keys[k]+=1
        v=str(data.get('aic_farmaco','') or '')
        aic_samples[('aic_len',len(v))]+=1
        if v:aic_samples[('example_chars',v[:24])]+=1
    print("Cnn keys",keys.most_common(15))
    print("Cnn AIC values",aic_samples.most_common(8))
if archive.exists():
    with tempfile.TemporaryDirectory() as d:
        target=Path(d)/'db.sqlite'
        with gzip.open(archive,'rb') as src,target.open('wb') as dst:
            while b:=src.read(2*1024*1024):dst.write(b)
        with closing(sqlite3.connect(target.as_uri()+'?mode=ro',uri=True)) as db:
            print("CLASSE NELL'ARCHIVIO AIFA")
            print(db.execute("SELECT COALESCE(NULLIF(TRIM(classe_da_anagrafica),''),'[vuota]'), COUNT(*) FROM confezioni GROUP BY 1 ORDER BY 2 DESC LIMIT 30").fetchall())
