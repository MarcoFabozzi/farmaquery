# Archivio dei rami storici GitHub

**Data:** 25 novembre 2026.

L'applicazione FarmaQuery è gestita tramite il ramo `main`. I rami storici sono legati alle varie fasi di sviluppo e di sperimentazione della tesi e non devono essere confusi con il codice finale.

## Politica di pulizia

Il workflow `.github/workflows/archivia-rami-storici.yml` esegue **una sola volta** l'archiviazione quando viene introdotto in `main`.

1. Mantiene **`main`**, i rami protetti e quelli associati a pull request **ancora aperte**.
2. Per ciascun altro ramo crea un **tag Git permanente** `archivio/rami-20261125/<nome-originale>` che punta esattamente al commit originale.
3. Verifica che il tag sia stato creato e che il ramo non sia cambiato; **soltanto allora** elimina il ramo.
4. Produce un manifesto `archivio_rami_esito.json` scaricabile dai risultati di GitHub Actions (retention 90 giorni).

**Non vengono cancellati commit o snapshot**, e il codice pubblicato in `main` non viene alterato dalla rimozione dei rami. Un ramo può essere ricreato in seguito dal corrispondente tag.

Esempio di recupero:

```bash
git fetch origin --tags
git switch -c recupero/vecchio-lavoro archivio/rami-20261125/nome-del-ramo
```

I tag servono esclusivamente a preservare le versioni storiche; non sono nuove versioni applicative.

**Limiti:** i rami associati a pull request aperte o protetti vengono conservati. Eventuali errori di autorizzazione o rami aggiornati durante la procedura vengono segnalati e non eliminati. La procedura non elimina né modifica i file dentro `risultati/`, `tesi/` o `tests/`.
