# Verifica del gold Q01 — indicazione EMA di PLUVICTO

**Data della verifica:** 3 novembre 2026  
**Categoria:** CONTROLLO — dato strutturato EMA  
**Quesito:** «Quale indicazione terapeutica è registrata per PLUVICTO nella scheda EMA presente nello snapshot?»

## Fonte sperimentale effettivamente controllata

- Artifact GitHub Actions `tesi-snapshot-fonti-online`, workflow run `41436480339` del 2 novembre 2026.
- File `esperimento_online.sqlite`.
- Manifesto allegato `manifest_fonti_online.json`, commit sorgente `630613a1b3e5353fe33e207e843fb8dad5591b2a`.
- **SHA-256 effettivo del SQLite**, ricalcolato sui byte estratti: `bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`. Coincide con il manifesto e con il benchmark.
- Origine EMA registrata nella tabella `fonti_snapshot`: `https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json`; data di acquisizione indicata `2026-11-02T05:20:55+00:00`; SHA-256 della fonte `4d88cc745ccefbea37c04eace7a76420fef2c4d31f11222c41ec753240aa9f00`.

**SELECT di verifica, sola lettura:**
```sql
SELECT ema_id, nome, principio_attivo, stato_ema,
       data_decisione_ue, indicazione_ema, url_ema
FROM ema_medicinali
WHERE nome = 'Pluvicto' COLLATE NOCASE;
```

La query restituisce **una sola riga**, con:
- `ema_id`: `EMEA/H/C/005483`
- `nome`: `Pluvicto`
- `principio_attivo`: `lutetium (177Lu) vipivotide tetraxetan`
- `stato_ema`: `Authorised`
- `url_ema`: `https://www.ema.europa.eu/en/medicines/human/EPAR/pluvicto`

**Campo `indicazione_ema` originale, senza correzioni:**

> Pluvicto in combination with androgen deprivation therapy (ADT) with or without androgen receptor (AR) pathway inhibition is indicated for the treatment of adult patients with progressive prostate-specific membrane antigen (PSMA)-positive metastatic castration-resistant prostate cancer (mCRPC) who have been treated with AR pathway inhibition and taxane based chemotherapy.

## Risposta gold approvata per Q01

Nel record EMA EMEA/H/C/005483 dello snapshot, PLUVICTO è indicato **in associazione alla terapia di deprivazione androgenica (ADT), con o senza inibizione della via del recettore degli androgeni**, nel trattamento di **pazienti adulti con carcinoma prostatico metastatico resistente alla castrazione (mCRPC), progressivo e PSMA-positivo**, già trattati con **inibizione della via del recettore degli androgeni e chemioterapia a base di taxani**.

**Citazione gold:** `EMA:EMEA/H/C/005483`.

**Riscontro primario indipendente:** la sezione «Therapeutic indication» della [scheda EMA di PLUVICTO](https://www.ema.europa.eu/en/medicines/human/EPAR/pluvicto) riporta la stessa indicazione del record congelato.

## Criterio di valutazione predefinito

Per assegnare **1/1**, la risposta deve includere tutti gli elementi: carcinoma prostatico metastatico resistente alla castrazione; malattia progressiva e PSMA-positiva; pazienti adulti; precedente inibizione della via del recettore degli androgeni e chemioterapia a base di taxani; associazione con ADT, con o senza inibizione della via AR. La risposta può parafrasare fedelmente la fonte, senza introdurre indicazioni non documentate; un'omissione sostanziale assegna **0/1** secondo la rubrica rigorosa. La fonte deve essere ricondotta al record EMA `EMEA/H/C/005483`.

**Avvertenza temporale:** il campo etichettato `data_decisione_ue` dello snapshot contiene `2026-07-20`; non usarlo come data della **prima autorizzazione**, avvenuta il **9 dicembre 2022** secondo EMA. Q01 richiede soltanto l'indicazione terapeutica.

## Integrità del protocollo

Q01 era `DA_VERIFICARE` in `tesi/benchmark_regolatorio_30.csv`; a seguito del controllo della riga dello **stesso snapshot congelato** e della scheda EMA viene marcata `VALIDATO`, con risposta e fonte esplicite. Non sono stati cambiati la domanda, il criterio o gli altri 29 quesiti, e non sono state effettuate chiamate ai motori LLM.

Il file `tesi/benchmark_regolatorio_8_validati.csv` mantiene il proprio perimetro storico di **otto casi di sviluppo**, indipendente dal nuovo controllo Q01.
