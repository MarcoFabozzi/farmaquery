"""Pagina Streamlit del chatbot di FarmaQuery: tecnica selezionata da menu."""
from __future__ import annotations

from pathlib import Path
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
can_call=enable_server_key(model,keys)
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

if not can_call:
    st.info("Il chatbot è predisposto, ma per generare risposte serve "
            "configurare una chiave API nelle impostazioni riservate "
            "di Streamlit Cloud. Non inserire chiavi in chat o su GitHub.")
else:
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

new_question=st.chat_input(
    "Es. Quali centri possono prescrivere DUVYZAT in Campania?",
    disabled=not can_call,
    max_chars=700,
)

if new_question:
    st.session_state["farmaquery_chat_count"]+=1
    history.append({"role":"user","text":new_question})
    with st.chat_message("user"):
        st.markdown(new_question)

    with st.chat_message("assistant"):
        started=time.monotonic()
        with st.spinner("Ricerca nelle fonti ufficiali..."):
            try:
                version=snapshot_version(ROOT)
                db,manifest=cached_db(version)
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
        history.append({"role":"assistant","text":result.get("risposta",""),
                        "metodo":method,"secondi":seconds,
                        "fonti":sources,"sql":result.get("sql","")})

st.divider()
st.caption("Le classi A/H si riferiscono a elenchi AIFA datati. "
           "L'assenza da questi elenchi non dimostra ufficialmente classe C. "
           "Le strutture abilitate ai registri AIFA non equivalgono necessariamente "
           "ai centri autorizzati per tutte le indicazioni regionali.")
