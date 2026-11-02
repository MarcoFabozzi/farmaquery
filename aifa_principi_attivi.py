#!/usr/bin/env python3
"""Join ufficiale AIFA tra confezioni_fornitura.csv e PA_confezioni.csv, per codice AIC.

Il primo CSV non contiene necessariamente il principio attivo. Non ricavarlo
dal nome commerciale: la seconda tabella elenca le sostanze per confezione.
"""
from __future__ import annotations
from collections import defaultdict
import re
import pipeline


def principi_per_aic(csv_path, audit=None):
    """Aggrega sostanze per AIC senza pubblicare associazioni anomale.

    Se un codice AIC presenta più di 20 sostanze distinte, lo si mette
    interamente in quarantena: NON si trattengono le prime 20 sostanze
    e NON si interrompe l'importazione di tutte le altre confezioni.
    La soglia è un controllo prudenziale, non un limite farmacologico.
    """
    results=defaultdict(dict)
    quarantena={}
    rows=pipeline.lista_csv(csv_path)
    # Non considerare un CSV scaricato con intestazioni diverse come una lista vuota.
    if not rows:
        raise ValueError('Elenco PA_confezioni AIFA vuoto')
    heads={pipeline.key(k) for k in rows[0] if k}
    if not {'codice_aic','principio_attivo'}.issubset(heads):
        raise ValueError('PA_confezioni AIFA: colonne CODICE_AIC/PRINCIPIO_ATTIVO assenti')
    valid=0
    for row in rows:
        aic=pipeline.campo(row,'CODICE_AIC','CODICE AIC')
        active=pipeline.campo(row,'PRINCIPIO_ATTIVO','PRINCIPIO ATTIVO')
        if not re.fullmatch(r'\d{9}',aic or '') or not active:
            continue
        valid+=1
        norm=pipeline.normalizza(active)
        if not norm:
            continue
        if aic in quarantena:
            quarantena[aic].add(norm)
            continue
        results[aic].setdefault(norm,active.strip())
        if len(results[aic])>20:
            quarantena[aic]=set(results.pop(aic))
    if audit is not None:
        audit.update({
            'aic_anomale_escluse': len(quarantena),
            'aic_anomale_con_numero_sostanze': {
                aic: len(sostanze) for aic, sostanze in sorted(quarantena.items())
            },
            'nota_quarantena': (
                'AIC con oltre 20 sostanze distinte: esclusa solo questa associazione '
                'dalla sorgente PA_confezioni; richiede controllo manuale.'
            ),
        })
    if not results:
        raise ValueError('PA_confezioni AIFA non contiene coppie AIC/principio valide')
    combined={aic:'; '.join(sorted(components.values(),key=str.casefold))
              for aic,components in results.items()}
    return combined,valid


def arricchisci_confezioni(confezioni,principi,min_copertura=0.7):
    """Modifica solo le confezioni con AIC presente nell'elenco dei principi AIFA."""
    total=len(confezioni)
    hits=sum(aic in principi for aic in confezioni)
    if total and hits/total<min_copertura:
        raise ValueError(f'Copertura PA_confezioni insufficiente: {hits}/{total}')
    for aic,row in confezioni.items():
        if aic in principi:
            row['principio_attivo']=principi[aic]
    return {'aic_con_principio':hits,'aic_totali':total,
            'percentuale_copertura':round(100*hits/max(total,1),2)}
