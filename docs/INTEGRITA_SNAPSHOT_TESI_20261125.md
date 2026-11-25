# Integrità dello snapshot congelato della tesi

**Verifica del 25 novembre 2026.**

Il file `risultati/tesi_statico_20261102.sqlite.gz` associato alle **35 domande** e alle Gold pubblicate è identificato dall'hash SHA-256 del file SQLite **decompresso**:

```
f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742
```

## Anomalia individuata

Il 25/11/2026 un workflow ha **rigenerato** e pubblicato una versione diversa dello SQLite, con hash `7f5a4bea7864931e1af1d4a50c1e487edf8f15e89a2e813ea66578d46a3c66f0`, pur indicando ancora la data di riferimento `02/11/2026`. Le Gold e i rapporti dei risultati continuavano a puntare a `f0e5e193…`, causando fallimenti ai test automatici della riproducibilità.

## Ripristino e prevenzione

Sono stati ripristinati **entrambi** i file statici dal commit GitHub [`d1a743dd5491a24ea4676027d573ec74ab7d4a04`](https://github.com/MarcoFabozzi/farmaquery/commit/d1a743dd5491a24ea4676027d573ec74ab7d4a04) del **3 novembre 2026**: l'archivio `.sqlite.gz` e il manifesto JSON. Non sono stati modificati valori, Gold, esecuzioni LLM o risposte della tesi.

Il workflow `tesi-deploy-statico.yml` continua a consentire **verifiche e ricostruzioni di prova**, salvando il prodotto come **artifact GitHub Actions** senza eseguire commit né `git push` verso `main`. La ricostruzione di prova non rappresenta una nuova versione dei dati della tesi.

L'allineamento dei tre riferimenti — hash del file SQLite decompresso, `sha256_sqlite` nel manifesto e `snapshot_statico` nei file Gold — viene verificato dai test nella cartella `tesi/tests/`.

**Nota:** il controllo di integrità dei byte non equivale a una nuova validazione clinico-regolatoria delle risposte Gold. Le revisioni documentali del 16/11/2026 relative a Q11 e Q14 restano separate dai dati originali.
