"""Pagina Streamlit del chatbot di FarmaQuery: tecnica selezionata da menu."""
from __future__ import annotations

from pathlib import Path
import csv
from io import StringIO
import hmac
import sqlite3
import sys
import time

import streamlit as st

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from chatbot_farmaquery import (
    answer_question, enable_server_key, history_key, model_from_settings,
    prepare_snapshot, snapshot_version,
)

st.set_page_config(page_title="FarmaQuery · Chatbot",page_icon="💬",layout="centered")
st.title("💬 FarmaQuery")
st.subheader("Assistente per informazioni sui medicinali")
st.caption("Interroga EMA, AIFA e le note regionali della Campania. "
           "L'applicazione è un prototipo universitario e non sostituisce "
           "la verifica sulle fonti ufficiali.")

with st.sidebar:
    st.page_link("dashboard_regolatorio.py",label="Ricerca medicinali",icon="💊")
    st.caption("Per il confronto sperimentale, le domande vengono "
               "interpretate singolarmente, senza trasferire automaticamente "
               "le risposte precedenti da un metodo all'altro.")

method=st.selectbox(
    "Metodo con cui rispondere",
    ("Text-to-SQL","TAG"),
    help="Text-to-SQL genera una SELECT in sola lettura; TAG applica "
         "gli operatori semantici LOTUS alle informazioni recuperate.",
    key="farmaquery_selected_method"
)
st.caption(
    "Text-to-SQL: il modello interroga le tabelle SQLite."
    if method=="Text-to-SQL"
    else "TAG: LOTUS seleziona semanticamente le informazioni tabellari prima della risposta."
)

try:
    keys=dict(st.secrets)
except (FileNotFoundError,RuntimeError):
    keys={}
model=model_from_settings(keys)
has_key=enable_server_key(model,keys)
can_call=has_key
secret_password=str(keys.get("FARMAQUERY_CHAT_PASSWORD") or "").strip()
if can_call and not secret_password:
    st.warning("Per proteggere la quota API, configura anche "
               "FARMAQUERY_CHAT_PASSWORD nei segreti di Streamlit Cloud.")
    can_call=False
elif can_call:
    if not st.session_state.get("farmaquery_chat_authorized",False):
        candidate=st.text_input("Password di accesso al chatbot",
                                type="password",key="farmaquery_chat_password_input")
        if st.button("Accedi al chatbot"):
            if hmac.compare_digest(candidate,secret_password):
                st.session_state["farmaquery_chat_authorized"]=True
                st.rerun()
            else:
                st.error("Password non corretta.")
    can_call=bool(st.session_state.get("farmaquery_chat_authorized",False))

if "farmaquery_chat_count" not in st.session_state:
    st.session_state["farmaquery_chat_count"]=0
if st.session_state["farmaquery_chat_count"]>=12:
    st.info("Limite della sessione di prova raggiunto (12 domande). "
            "La quota protegge le chiamate al modello.")
    can_call=False

@st.cache_resource(show_spinner="Preparazione delle fonti aggiornate...",max_entries=2)
def cached_db(version):
    return prepare_snapshot(ROOT)

if not has_key:
    st.info("Il chatbot è predisposto, ma per generare risposte serve "
            "configurare una chiave API nei segreti di Streamlit Cloud. "
            "Non inserire chiavi in chat o su GitHub.")
elif can_call:
    st.caption("Modello configurato: "+model+" · Fonti acquisite da EMA, AIFA e Campania.")

key=history_key(method)
if key not in st.session_state:
    st.session_state[key]=[]
history=st.session_state[key]

left,right=st.columns([3,1])
with right:
    if st.button("Pulisci chat",key="clear_farmaquery_"+method):
        st.session_state[key]=[]
        st.rerun()

for item in history:
    with st.chat_message(item["role"]):
        st.markdown(item["text"])
        if item["role"]=="assistant" and item.get("fonti"):
            with st.expander("Fonti consultate"):
                for source in item["fonti"]:
                    st.write("• "+source)
        if item["role"]=="assistant" and item.get("sql"):
            with st.expander("Query SQL generata"):
                st.code(item["sql"],language="sql")
        if item["role"]=="assistant" and item.get("secondi") is not None:
            st.caption("Metodo: "+item["metodo"]+" · "+
                       str(round(item["secondi"],1))+" s")

@st.cache_data(show_spinner=False)
def domande_della_tesi():
    with (ROOT/"tesi"/"domande_utente_35.csv").open(
        encoding="utf-8-sig",newline=""
    ) as source:
        return list(csv.DictReader(source,delimiter=";"))


questions=domande_della_tesi()
lookup={row["id"]:row for row in questions}
by_text={row["domanda"]:row for row in questions}
with st.expander("🧪 Le 35 domande della tesi (facoltativo)"):
    st.caption("Seleziona una domanda già preparata, oppure scrivine "
               "liberamente una nel campo della chat.")
    selected_id=st.selectbox(
        "Domanda di prova",
        [row["id"] for row in questions],
        format_func=lambda ident: ident+" · "+lookup[ident]["domanda"],
        key="farmaquery_benchmark_selected",
    )
    selected_send=st.button(
        "Invia la domanda selezionata",
        disabled=not can_call,
        key="farmaquery_benchmark_send"
    )

new_question=st.chat_input(
    "Es. Quali centri possono prescrivere DUVYZAT in Campania?",
    disabled=not can_call,
    max_chars=700,
)
if selected_send:
    new_question=lookup[selected_id]["domanda"]

if new_question:
    st.session_state["farmaquery_chat_count"]+=1
    history.append({"role":"user","text":new_question})
    with st.chat_message("user"):
        st.markdown(new_question)

    with st.chat_message("assistant"):
        started=time.monotonic()
        snapshot_hash=""
        with st.spinner("Ricerca nelle fonti ufficiali..."):
            try:
                version=snapshot_version(ROOT)
                db,manifest=cached_db(version)
                snapshot_hash=manifest["sha256_sqlite"]
                result=answer_question(db,new_question,method,model)
            except (ImportError,ModuleNotFoundError):
                result={"risposta":"Il componente del metodo selezionato non "
                        "è disponibile nell'ambiente Python. "
                        "Verificare i requisiti dell'app.","fonti":[],"stato":"ERRORE"}
            except (OSError,ValueError,sqlite3.DatabaseError) as exc:
                # Evitare di mostrare credenziali, payload o percorsi locali.
                result={"risposta":"Non è stato possibile consultare le fonti: "
                        +type(exc).__name__+". Controllare che gli aggiornamenti "
                        "del database siano completati.","fonti":[],"stato":"ERRORE"}
            except Exception as exc:
                # Messaggio generico anche per errori del provider LLM.
                reason=str(exc).lower()
                if "429" in reason or "resource_exhausted" in reason or "rate limit" in reason:
                    msg="Il modello ha raggiunto il limite di richieste. Riprova più tardi."
                elif "api key" in reason or "authentication" in reason or "401" in reason:
                    msg="L'accesso al modello non è configurato correttamente sul server."
                else:
                    msg="Il modello non ha prodotto una risposta. Controllare "
                    msg+="l'accesso API o la disponibilità del servizio."
                result={"risposta":msg,"fonti":[],"stato":"ERRORE"}

        seconds=round(time.monotonic()-started,2)
        st.markdown(result.get("risposta","Nessuna risposta disponibile."))
        sources=result.get("fonti",[])
        if sources:
            with st.expander("Fonti consultate"):
                for source in sources:
                    st.write("• "+source)
        if method=="Text-to-SQL" and result.get("sql"):
            with st.expander("Query SQL generata"):
                st.code(result["sql"],language="sql")
        st.caption("Metodo: "+method+" · "+str(seconds)+" s")
        question_meta=by_text.get(new_question,{})
        history.append({"role":"assistant","text":result.get("risposta",""),
                        "domanda":new_question,"id":question_meta.get("id",""),
                        "categoria":question_meta.get("categoria",""),
                        "metodo":method,"modello":model,
                        "snapshot_sha256":snapshot_hash,
                        "token_input":result.get("token_input"),
                        "token_output":result.get("token_output"),
                        "costo_usd":result.get("costo_usd"),
                        "stato":result.get("stato",""),
                        "secondi":seconds,"fonti":sources,
                        "sql":result.get("sql","")})

# L'esportazione e' locale alla sessione Streamlit e non salva i dati
# personali sul repository. Le due tecniche sono incluse nello stesso CSV.
records=[]
for technique in ("Text-to-SQL","TAG"):
    for msg in st.session_state.get(history_key(technique),[]):
        if msg.get("role")!="assistant":
            continue
        records.append({
            "id":msg.get("id",""),
            "categoria":msg.get("categoria",""),
            "domanda":msg.get("domanda",""),
            "metodo":msg.get("metodo",""),
            "modello":msg.get("modello",""),
            "snapshot_sha256":msg.get("snapshot_sha256",""),
            "risposta":msg.get("text",""),
            "fonti":" | ".join(msg.get("fonti",[])),
            "secondi":msg.get("secondi",""),
            "token_input":msg.get("token_input",""),
            "token_output":msg.get("token_output",""),
            "costo_usd":msg.get("costo_usd",""),
            "valutazione_risposta":"",
            "valutazione_citazioni":"",
            "note_revisore":"",
        })
if records:
    fields=list(records[0].keys())
    buffer=StringIO()
    writer=csv.DictWriter(buffer,fieldnames=fields,delimiter=";")
    writer.writeheader()
    writer.writerows(records)
    st.download_button(
        "⬇️ Scarica le risposte delle prove (CSV)",
        data=buffer.getvalue().encode("utf-8-sig"),
        file_name="farmaquery_risposte_chat.csv",
        mime="text/csv",
        help="Include entrambi i metodi e lascia vuoti i giudizi di correttezza.",
    )

st.divider()
st.caption("Le classi A/H si riferiscono a elenchi AIFA datati. "
           "L'assenza da questi elenchi non dimostra ufficialmente classe C. "
           "Le strutture abilitate ai registri AIFA non equivalgono necessariamente "
           "ai centri autorizzati per tutte le indicazioni regionali.")
