# Valutazione manuale Q08 (3 novembre 2026)

TAG: 5,3 s; 3/3 indicazioni, 2/3 combinazioni; omessa la chemioradioterapia per cervice. Completezza rigorosa: 0/1. Stato tecnico: fonte non_recuperato, evidenze 12, LOTUS 3.

Text-to-SQL: 1,1 s; risposta "Informazione non documentata nello snapshot consultato"; 0/3 combinazioni; 0/1. La condizione SQL sul nome file cerca il protocollo con barra 0116205/2026, mentre il documento nel gold usa 0116205-2026: il file pertinente viene escluso dal filtro.

SQL originale:
```sql
SELECT p.nota_id, p.numero_pagina, p.testo, n.id AS nota_id, n.archivio_url FROM pagine AS p JOIN note AS n ON p.nota_id = n.id WHERE n.nome_file LIKE '%0116205/2026%' AND (n.farmaco_candidato LIKE '%KEYTRUDA%' OR p.testo LIKE '%KEYTRUDA%') LIMIT 80
```

Fonte gold: tesi/benchmark_regolatorio_8_validati.csv, Q08. Riferimenti pagina 1-4.
Prova manuale esplorativa: non mescolare al benchmark sullo snapshot congelato.
