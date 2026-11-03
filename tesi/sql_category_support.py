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
    "differenti. Per quesiti SOLO sulle note regionali, usa prima "
    "note JOIN pagine, senza JOIN ad aifa_confezioni o ema_medicinali: "
    "le confezioni AIFA moltiplicano le righe e non attestano i centri. "
    "Non imporre che patologia e ospedale compaiano nella STESSA pagina: "
    "filtra le NOTE con due EXISTS distinti, uno per la malattia e "
    "uno per l'ospedale, e recupera le pagine utili a entrambe. "
    "Per evitare di saturare LIMIT con una singola nota, usa "
    "DISTINCT su nota_id e numero_pagina oppure una CTE che scelga "
    "pagine significative per documento. Non usare p.testo AS patologia: "
    "p.testo è il testo OCR dell'intera pagina, non una diagnosi. "
    "Non filtrare nome_file o archivio_url sulla parola Campania: "
    "la tabella note contiene già le note regionali dello snapshot. "
    "Valuta con EXISTS su pagine della stessa nota sia termini "
    "di patologia sia il centro richiesto; recupera le pagine testuali "
    "rilevanti per entrambe le condizioni e includi nota_id, numero_pagina, "
    "nome_file, farmaco_candidato e testo per permettere verifica e citazioni. "
    "strutture_registri, se consultata, è solo un registro candidato e non "
    "certifica la relazione fra indicazione e centro. La compresenza nello "
    "stesso PDF NON prova da sola l'autorizzazione: la sintesi deve "
    "interpretare la sezione corretta. Usa una sola SELECT di sola lettura "
    "e preferisci una query che recuperi prove piuttosto che conclusioni."
)

CATEGORY_DIVERSITY_RETRY_RULES = (
    "La prima SELECT regionale ha prodotto righe ripetute, un risultato "
    "dominato da pochissime note o un taglio dei risultati. "
    "Genera una SECONDA SELECT SQLite di sola lettura, autonoma e valida "
    "che migliori la COPERTURA DOCUMENTALE; non riutilizzare una JOIN "
    "con aifa_confezioni o altre relazioni uno-a-molti non necessarie. "
    "Usa note n JOIN pagine p ON p.nota_id=n.id. "
    "Per verificare una categoria implicita, usa due EXISTS sulla "
    "stessa n.id, uno per indizi di patologia e uno per la struttura. "
    "NON aggiungere entrambi questi filtri al WHERE della stessa "
    "pagina p: la diagnosi e il centro possono essere su pagine diverse. "
    "Restituisci nota_id, numero_pagina, nome_file, farmaco_candidato "
    "e testo originale delle pagine citabili; evita duplicati e porta "
    "evidenze da più note invece di ripetere confezioni di una sola. "
    "Non dichiarare alcuna autorizzazione nel SQL. "
    "Una SELECT sola, senza Markdown, LIMIT massimo 80. "
    "Non copiare l'elenco dei medicinali atteso e non usare fonti esterne."
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


# Secondo tentativo quando una SELECT regolarmente eseguita restituisce
# zero righe per un documento che potrebbe essere presente nello snapshot.
# Non include elenchi di risposte, protocolli o farmaci di benchmark.
DOCUMENT_SQL_RETRY_RULES = (
    "La SELECT precedente ha restituito ZERO RIGHE: non significa "
    "che la fonte o il fatto siano assenti. Genera una NUOVA singola "
    "SELECT SQLite di sola lettura, non una risposta in linguaggio naturale. "
    "Esamina i metadati reali delle note candidate forniti nel contesto. "
    "Per una domanda su una nota regionale identificata dal medicinale, "
    "filtra prima note per farmaco_candidato o nome_file, poi JOIN pagine "
    "per leggere il testo originale e associare la pagina corretta. "
    "NON imporre INNER JOIN con centri_candidati o rimandi_candidati: "
    "sono estrazioni candidate e possono non contenere tutte le righe. "
    "Non cercare parole come Campania nel percorso_zip: la tabella note "
    "è già il corpus regionale. Il protocollo nel nome_file può usare "
    "un TRATTINO dove il testo usa una BARRA: preferisci il nome del "
    "medicinale o la porzione numerica del protocollo. "
    "Un anno della nota RICHIAMATA non è necessariamente l'anno della "
    "nota citante: privilegia il documento oggetto della domanda. "
    "Per indicazioni multiple recupera tutte le pagine della nota, "
    "senza filtri sulle singole patologie che potrebbero comparire "
    "soltanto nelle intestazioni di altre pagine. "
    "Se non trovi una nota, NON inventarla. Includi "
    "nota_id, numero_pagina, nome_file e testo per citare le prove. "
    "Solo una SELECT, senza markdown, LIMIT massimo 80."
)

SQL_EXECUTION_REPAIR_RULES = (
    "La precedente SELECT è stata validata come sola lettura, ma SQLite "
    "ha restituito un errore operativo. Genera UNA NUOVA SELECT SQLite "
    "semplice e autonoma che usi soltanto colonne e tabelle dello schema. "
    "Usa i metadati reali delle fonti candidate se disponibili. "
    "Per note regionali preferisci note JOIN pagine senza join "
    "a estrazioni candidate e includi nota_id, numero_pagina, testo. "
    "Non riutilizzare riferimenti a colonne o alias inesistenti, "
    "non utilizzare PRAGMA, DML o più istruzioni e non inventare fatti. "
    "Restituisci soltanto la SELECT, LIMIT massimo 80."
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
        "Per domande basate su NOTE regionali usa note JOIN pagine "
        "per recuperare il TESTO ORIGINALE; centri_candidati e "
        "rimandi_candidati sono solo estrazioni candidate, quindi "
        "non usarle come INNER JOIN obbligatorie. "
        "Non filtrare percorso_zip o nome_file sulla parola Campania. "
        "Per ricercare un protocollo nel nome_file considera che la "
        "notazione usa spesso trattini al posto delle barre: cerca "
        "il numero o il nome commerciale, non il protocollo completo "
        "con punteggiatura non verificata. "
        "Distinguere ANNO della nota consultata da anno della nota "
        "precedente solo richiamata nel testo. "
        "Per più indicazioni della stessa nota NON imporre che "
        "ogni indicazione compaia nei campi menzione/stato dei centri "
        "o su ogni pagina: recupera le pagine della nota. "
        "Per le classi usa: CASE WHEN classe_a_h_snapshot IN ('A','H') "
        "THEN classe_a_h_snapshot ELSE 'C (dedotta per esclusione)' END "
        "AS classe. Includi anche classe_a_h_snapshot e classe_a_h_data "
        "per distinguere fonte e deduzione."
    )
    if category_sql_context(question):
        return base+" "+CATEGORY_SQL_RULES
    return base
