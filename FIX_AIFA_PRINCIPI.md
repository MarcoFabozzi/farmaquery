# Correzione importazione principi attivi AIFA — 02/11/2026

## Errore osservato

La pipeline `aifa_anagrafica` scarica già `confezioni_fornitura.csv` e
`PA_confezioni.csv`, ma le esecuzioni GitHub Actions del 02/11/2026
fallivano con:

```
AGGIORNAMENTO AIFA_ANAGRAFICA FALLITO:
Numero anomalo di principi attivi per AIC: 040716019
```

Il blocco è un vincolo locale del parser (>20 sostanze distinte per AIC),
**non** una prova di indisponibilità della sorgente AIFA.

## Strategia prudente

- Non è stata aumentata arbitrariamente la soglia né tagliata la lista
  alle prime 20 sostanze.
- Le AIC che superano 20 sostanze **vengono escluse interamente dal join
  del file PA**, mantenendo invariati i valori della fonte anagrafica
  originale e permettendo di completare le altre confezioni.
- La statistica `audit_principi_attivi` segnala AIC e numero di sostanze
  distinte per revisione manuale.
- Restano attivi la verifica della copertura minima (70%), il blocco se
  il CSV non è interpretabile e le verifiche dello snapshot prima di
  pubblicare.
- I dati AIFA descrivono le sostanze per confezione, non dimostrano
  disponibilità, classe vigente o prescrivibilità regionale.

## Test locale (PowerShell)

```powershell
python -m unittest -v tests.test_aifa_principi_attivi
```

### Collaudo con dati reali

Dopo il merge su `main`, verificare nel GitHub Actions
`FarmaQuery - aifa anagrafica indipendente` l'esecuzione riuscita
del task `Update AIFA and validate snapshot`.

Nel rapporto `risultati/stato_fonti/aifa_anagrafica.json`, cercare:

- `esito: OK`;
- `statistiche.copertura_principi_attivi`;
- `statistiche.audit_principi_attivi.aic_anomale_con_numero_sostanze`;
- `fonti.aifa_principi_attivi`, che include URL e SHA-256 del file ufficiale.

**Non considerare il problema risolto finché non c'è un'esecuzione
completa riuscita**: potrebbero emergere altre anomalie dopo la prima.

## Separazione dai test TAG della tesi

L'app pubblica continuerà a ricevere aggiornamenti automatici. Il
benchmark TAG vs Text-to-SQL deve invece usare lo snapshot AIFA
specificato dal relatore (liste A/H al 31/05/2026 e ulteriori dati
datati), bloccato con relativo hash. Non sostituire quelle liste con
quelle più recenti scaricate dalla pipeline dell'app.
