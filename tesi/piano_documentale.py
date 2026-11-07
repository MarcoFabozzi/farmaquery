"""Piano tipizzato di recupero documentale: separa SQL da semantica.

Si usa come rete di sicurezza quando la SELECT documentale generata non
restituisce righe e i recuperi AST conservativi non riconoscono la forma SQL.
Non codifica malattie, nomi di centri o medicinali e non modifica il DB.
L'LLM restituisce SOLO una classificazione tipizzata; SQL di recupero viene
costruito con un template read-only e un'ancora ospedaliera verificata.
"""
from __future__ import annotations

import json
import re

from sqlglot import exp, parse_one

MAX_CENTER_CANDIDATES = 8
PLAN_PROMPT = (
    "Sei il pianificatore di RECUPERO di documenti da un database regolatorio "
    "regionale. Devi distinguere i criteri OGGETTIVI esplicitamente richiesti "
    "dalla domanda (farmaco preciso, data, protocollo, classe, stato, luogo) "
    "dai criteri SEMANTICI che vanno verificati leggendo i PDF, come "
    "categorie cliniche, patologie, indicazioni e relazioni tra farmaci. "
    "NON generare SQL e NON rispondere alla domanda. "
    "Valuta se la domanda richiede un ELENCO di note o medicinali appartenenti "
    "a una categoria semantica e collegati a una struttura nominata. "
    "Il nome della struttura deve essere scelto ESCLUSIVAMENTE fra "
    "i 'centri_candidati_sql' forniti e deve essere esplicitamente citato "
    "nella domanda. Non basta che il SQL generato abbia un filtro: "
    "devi giudicare SOLO i vincoli richiesti dal testo della domanda. "
    "Se la domanda richiede anche farmaco specifico, anno, intervallo di date, "
    "protocollo, stato amministrativo, attività confermata o altri vincoli "
    "oggettivi, non proporre questo piano: impostare applicabile=false. "
    "Non assumere che 'attivo' nei metadati dei centri equivalga ad "
    "autorizzato; i centri devono essere verificati nel testo dei documenti. "
    "Rispondi SOLTANTO con JSON nel formato "
    '{"applicabile":true,"centro":"...","criterio_semantico":"...",'
    '"vincoli_oggettivi_aggiuntivi":[]}. '
    "Se non applicabile, usa applicabile=false, centro=null, "
    "criterio_semantico=null e specifica eventuali vincoli nella lista. "
    "Nessuna diagnosi, tassonomia di malattie o nome di farmaco inventati."
)


def _simple_document_source(tree):
    if not isinstance(tree, exp.Select):
        return None
    if any(tree.args.get(k) is not None for k in (
            "with_", "group", "having", "qualify", "limit", "offset",
            "order", "windows", "intersect", "except", "connect")):
        return None
    if any(tree.find_all(exp.Subquery)):
        return None
    source = tree.args.get("from_") or tree.args.get("from")
    if not source or not isinstance(source.this, exp.Table):
        return None
    if str(source.this.name).casefold() != "note":
        return None
    names = {str(source.this.alias_or_name).casefold(): "note"}
    joins = tree.args.get("joins") or []
    if not joins:
        return None
    for join in joins:
        if (not isinstance(join.this, exp.Table) or
                join.args.get("side") or join.args.get("kind")):
            return None
        kind = str(join.this.name).casefold()
        if kind not in ("pagine","centri_candidati","nota_centro_documentato"):
            return None
        alias = str(join.this.alias_or_name).casefold()
        if alias in names:
            return None
        names[alias]=kind
    if "pagine" not in names.values():
        return None
    return names


def document_center_anchors(sql, question):
    """Ricava SOLO valori testuali verificabili di centro dall'SQL esistente.

    Non considera valori su n.farmaco_candidato, n.indicazione_candidata o
    c.stato. Convalida i nomi rispetto alla domanda e non interpreta il
    significato clinico dei LIKE.
    """
    try:
        tree = parse_one(sql,read="sqlite")
    except Exception:
        return []
    names = _simple_document_source(tree)
    if not names:
        return []
    where = tree.args.get("where")
    if not where:
        return []
    structured=[]
    page_text=[]
    for node in where.find_all(exp.Like):
        column = node.this
        literal = node.expression
        while isinstance(column,(exp.Paren,exp.Collate)):
            column=column.this
        while isinstance(literal,(exp.Paren,exp.Collate)):
            literal=literal.this
        if (not isinstance(column,exp.Column) or
                not isinstance(literal,exp.Literal) or
                not literal.is_string):
            continue
        source = names.get(str(column.table).casefold())
        field = str(column.name).casefold()
        if (source,field) not in {
            ("pagine","testo"),
            ("centri_candidati","menzione"),
            ("nota_centro_documentato","centro")
        }:
            continue
        pattern=str(literal.this)
        if not (pattern.startswith("%") and pattern.endswith("%")):
            continue
        value=pattern[1:-1]
        if (len(value.strip())<5 or "%" in value or "_" in value or
                value.casefold() not in question.casefold()):
            continue
        target = page_text if source == "pagine" else structured
        if value.casefold() not in {x.casefold() for x in target}:
            target.append(value)
    # Le colonne di CENTRO sono la fonte piu' affidabile. Il testo libero
    # puo' contenere anche il termine della CATEGORIA clinica: lo usiamo
    # soltanto quando nessun campo di centro offre un'ancora verificabile.
    found = structured if structured else page_text
    return found[:MAX_CENTER_CANDIDATES]


def _strip_json_fence(value):
    text=str(value or "").strip()
    if text.startswith("```"):
        text=re.sub(r"^\s*```(?:json)?\s*","",text,flags=re.I)
        text=re.sub(r"\s*```\s*$","",text)
    return text


def validated_document_plan(answer, anchors, question):
    """Accetta solo classificazioni tipizzate prive di ulteriori vincoli."""
    try:
        obj=json.loads(_strip_json_fence(answer))
    except (ValueError,TypeError):
        return None,"json_non_valido"
    if not isinstance(obj,dict):
        return None,"oggetto_mancante"
    if type(obj.get("applicabile")) is not bool:
        return None,"tipo_applicabilita_non_valido"
    if not obj["applicabile"]:
        return None,"piano_non_applicabile"
    center=obj.get("centro")
    category=obj.get("criterio_semantico")
    additional=obj.get("vincoli_oggettivi_aggiuntivi")
    if not (isinstance(center,str) and
            isinstance(category,str) and category.strip() and
            isinstance(additional,list) and
            all(isinstance(x,str) for x in additional)):
        return None,"campi_piano_non_validi"
    if additional:
        return None,"vincoli_oggettivi_aggiuntivi_richiesti"
    if center.casefold() not in {x.casefold() for x in anchors}:
        return None,"centro_non_tracciato_nel_sql"
    if center.casefold() not in question.casefold():
        return None,"centro_non_richiesto_nella_domanda"
    if len(category.strip())<4:
        return None,"criterio_semantico_non_valido"
    return {"centro":center,"criterio_semantico":category}, "ok"


def sql_from_document_plan(plan):
    """SELECT sicura sui soli ID di nota, costruita senza SQL dall'LLM.

    Viene usato un token discriminante dalla struttura scelta; non si
    dichiarano mai centri 'autorizzati' sulla base di una menzione.
    """
    center=plan["centro"]
    words=re.findall(r"[^\W\d_]{5,}",center,flags=re.UNICODE)
    if not words:
        raise ValueError("Centro privo di token discriminante")
    token=sorted(words,key=lambda t:(-len(t),t.casefold()))[0]
    literal=exp.Literal.string("%"+token+"%").sql(dialect="sqlite")
    return (
        "SELECT DISTINCT n.id AS nota_id FROM note AS n "
        "JOIN pagine AS p ON n.id=p.nota_id "
        "WHERE p.testo LIKE "+literal+" COLLATE NOCASE"
    )
