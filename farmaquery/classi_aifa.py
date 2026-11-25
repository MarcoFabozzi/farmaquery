"""Indice A/H nazionale datato per l'archivio AIFA completo.

Il file A/H descrive uno snapshot, non certifica la rimborsabilita' corrente.
Non assegnare mai C alle AIC assenti nelle liste A/H.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re

INDICE_FILE = 'aifa_classi_ah.json'
AIC_PATTERN = re.compile(r'\d{9}\Z')


def costruisci_indice(classi, data_riferimento, fonti, destinazione):
    """Genera un indice A/H per *tutte* le AIC delle liste ufficiali."""
    date.fromisoformat(data_riferimento)
    if set(classi) != {'A', 'H'}:
        raise ValueError('Sono richieste entrambe le liste A e H')
    a, h = set(classi['A']), set(classi['H'])
    if a & h:
        raise ValueError('La stessa AIC compare sia in A sia in H')
    if len(a) < 1000 or len(h) < 100:
        raise ValueError('Liste A/H insufficienti')
    if any(not isinstance(x, str) or not AIC_PATTERN.fullmatch(x) for x in a | h):
        raise ValueError('Codice AIC non valido nelle liste A/H')
    if set(fonti) != {'aifa_a', 'aifa_h'}:
        raise ValueError('Provenienza liste A/H incompleta')
    for item in fonti.values():
        if not isinstance(item, dict) or not re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', '')):
            raise ValueError('Hash della fonte AIFA non valido')
        if not str(item.get('url', '')).startswith('https://www.aifa.gov.it/'):
            raise ValueError('Origine della lista AIFA non valida')
    obj = {
        'schema': 1, 'data_riferimento': data_riferimento,
        'nota': 'Classe presente nell’elenco A/H alla data indicata; non prova la classe vigente.',
        'totali': {'A': len(a), 'H': len(h)},
        'fonti': fonti,
        'classi': {code: ('A' if code in a else 'H') for code in sorted(a | h)},
    }
    path = Path(destinazione)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return {'file_indice': path.name, 'aic_indicizzate': len(obj['classi']),
            'data_riferimento': data_riferimento}


def leggi_indice(percorso):
    """Rifiuta file incompleti/non validi, invece di mostrare classi inesatte."""
    path = Path(percorso)
    if path.stat().st_size > 2_500_000:
        raise ValueError('Indice delle classi troppo grande')
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict) or obj.get('schema') != 1:
        raise ValueError('Formato indice A/H non valido')
    date.fromisoformat(obj['data_riferimento'])
    classes = obj.get('classi')
    counts = obj.get('totali')
    if not isinstance(classes, dict) or not isinstance(counts, dict):
        raise ValueError('Indice A/H incompleto')
    if any(not AIC_PATTERN.fullmatch(x) or cls not in ('A', 'H') for x, cls in classes.items()):
        raise ValueError('Valori non validi nell’indice A/H')
    if sum(1 for cls in classes.values() if cls == 'A') != counts.get('A') or \
       sum(1 for cls in classes.values() if cls == 'H') != counts.get('H'):
        raise ValueError('Conteggi A/H non coerenti')
    return obj


def etichetta_classe(indice, aic):
    """Ritorna una classe e la sua data, oppure N/D; mai dedurre classe C."""
    if not indice:
        return 'N/D'
    classe = indice['classi'].get(str(aic))
    if not classe:
        return 'N/D'
    data = date.fromisoformat(indice['data_riferimento']).strftime('%d/%m/%Y')
    return f'{classe} (lista {data})'
