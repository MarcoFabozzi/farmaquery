"""Indicazioni di recupero per la generazione Text-to-SQL, senza SQL predefinito.

La query rimane interamente prodotta dal medesimo modello LLM usato in TAG.
Il vocabolario condiviso è quello di recupero, non una tabella di farmaci
autorizzati o di risposte gold. Ogni inferenza richiede il testo originale.
"""
from __future__ import annotations

from tesi.recupero_regionale import categoria


CATEGORY_SQL_RULES = (
    "DOMANDE SU CATEGORIE CLINICHE IMPLICITE: la categoria citata nella "
    "domanda può NON comparire letteralmente nelle fonti. Non filtrare "
    "soltanto con LIKE sulla categoria ombrello (per es. cercando "
    "'neuromuscolari' come stringa letterale). Usa gli indizi clinici "
    "forniti come termini candidati OR, mai come diagnosi o autorizzazioni "
    "già verificate. Considera note e pagine della Regione Campania: "
    "nello stesso PDF la diagnosi può trovarsi in una pagina diversa dalla "
    "tabella del centro, e un PDF può avere PIÙ indicazioni con tabelle "
    "differenti. Valuta con EXISTS su pagine della stessa nota sia termini "
    "di patologia sia il centro richiesto; recupera le pagine testuali "
    "rilevanti per entrambe le condizioni e includi nota_id, numero_pagina, "
    "nome_file, farmaco_candidato e testo per permettere verifica e citazioni. "
    "strutture_registri, se consultata, è solo un registro candidato e non "
    "certifica la relazione fra indicazione e centro. La compresenza nello "
    "stesso PDF NON prova da sola l'autorizzazione: la sintesi deve "
    "interpretare la sezione corretta. Usa una sola SELECT di sola lettura "
    "e preferisci una query che recuperi prove piuttosto che conclusioni."
)

SQL_SYNTAX_REPAIR_RULES = (
    "La query SELECT generata in precedenza NON è stata eseguita: "
    "il parser SQLite/sqlglot non ne riconosce la sintassi. "
    "Genera una NUOVA singola SELECT SQLite valida e più semplice, "
    "senza Markdown, spiegazioni, commenti, query multiple o "
    "dialetti non SQLite. Non ripetere l'errore sintattico precedente. "
    "Consulta solo le tabelle e colonne dello schema fornito, "
    "usa esclusivamente operazioni di lettura e LIMIT massimo 80. "
    "Per domande sulle categorie cliniche considera la patologia "
    "e il centro anche su pagine distinte della stessa nota, "
    "ma non dedurre autorizzazioni dalla loro semplice presenza. "
    "Conserva nota_id, numero_pagina, testo e nome_file "
    "per verificare e citare le evidenze. "
    "Non inventare dati, medicinali o nomi di colonne."
)


CATEGORY_RETRY_RULES = (
    "LA PRIMA QUERY È STATA ESEGUITA CORRETTAMENTE MA HA RESTITUITO ZERO "
    "RIGHE. Non concludere che il fatto manchi dal database: potrebbe "
    "essere un errore di traduzione semantica della categoria. "
    "Genera UNA NUOVA SELECT, non una risposta, che usi le indicazioni "
    "sulle categorie implicite e interroghi le note regionali. "
    "Non ripetere il filtro letterale astratto che ha fallito; non "
    "trasformare menzioni di centri in autorizzazioni."
)


def category_sql_context(question):
    """Indizi condivisi a priori con TAG, senza medicine/centri gold."""
    name, terms=categoria(question)
    if not name:
        return None
    return {
        "categoria_riconosciuta":name,
        "indizi_di_ricerca_non_probatori":list(terms),
        "regole_sql":CATEGORY_SQL_RULES,
    }


def select_generation_guidance(question):
    base=(
        "Genera SOLO UNA query SELECT SQLite eseguibile, senza Markdown. "
        "Usa esclusivamente le tabelle documentate; non generare DDL, DML, "
        "PRAGMA né più istruzioni. LIMIT massimo 80. Se la domanda chiede "
        "un elenco completo non usare limiti più bassi. Per citazioni includi "
        "aic, ema_id oppure nota_id e numero_pagina nel risultato, "
        "e per GU codice AS gu_codice o documento_id, "
        "e archivio_url o fonte_url quando pertinenti. "
        "Per le classi usa: CASE WHEN classe_a_h_snapshot IN ('A','H') "
        "THEN classe_a_h_snapshot ELSE 'C (dedotta per esclusione)' END "
        "AS classe. Includi anche classe_a_h_snapshot e classe_a_h_data "
        "per distinguere fonte e deduzione."
    )
    if category_sql_context(question):
        return base+" "+CATEGORY_SQL_RULES
    return base
