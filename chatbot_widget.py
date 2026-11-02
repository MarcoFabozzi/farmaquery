"""Chatbot flottante di FarmaQuery, disponibile in fondo alla dashboard.

Nessuna password e nessuna domanda precompilata: l'utente scrive
liberamente e sceglie il motore dal menu a tendina.
"""
from __future__ import annotations

from contextlib import closing
import sqlite3
import time

import streamlit as st
from chatbot_farmaquery import (
    answer_question, enable_server_key, history_key,
    model_from_settings, prepare_snapshot, snapshot_version,
)

MAX_QUESTIONS_PER_SESSION=12


def start_new_conversation():
    """Azzera entrambe le chat prima del rerun gestito da Streamlit.

    Il contatore delle richieste resta invariato, per non eludere il
    limite della quota pubblica del provider.
    """
    for method in ("Text-to-SQL", "TAG"):
        st.session_state[history_key(method)]=[]
    st.session_state["farmaquery_chat_just_cleared"]=True


@st.cache_resource(show_spinner=False,max_entries=2)
def _cached_snapshot(version):
    return prepare_snapshot()


def render_assistant():
    st.markdown("""
    <style>
    /* L'icona resta sempre in basso a destra, anche durante lo scroll. */
    .st-key-farmaquery_floating {
       position:fixed!important;
       right:22px!important;
       bottom:64px!important;
       width:66px!important;
       z-index:99999!important;
       padding:0!important;
    }
    .st-key-farmaquery_floating div[data-testid="stPopover"] > button {
       width:62px!important;
       height:62px!important;
       min-height:62px!important;
       border-radius:50%!important;
       background:#116b70!important;
       border:2px solid #ffffff!important;
       box-shadow:0 7px 26px rgba(0,0,0,.22)!important;
       color:white!important;
       font-size:1.6rem!important;
       padding:0!important;
    }
    .st-key-farmaquery_floating div[data-testid="stPopover"] > button:hover {
       background:#098f85!important;
       transform:translateY(-2px);
    }
    @media(max-width:650px) {
       .st-key-farmaquery_floating {right:13px!important;bottom:48px!important;}
    }
    </style>""",unsafe_allow_html=True)

    try:
        secrets=dict(st.secrets)
    except (FileNotFoundError,RuntimeError):
        secrets={}
    model=model_from_settings(secrets)
    has_key=enable_server_key(model,secrets)

    with st.container(key="farmaquery_floating"):
        with st.popover("💬",help="Apri assistente FarmaQuery",use_container_width=False):
            st.markdown("#### 💊 Assistente FarmaQuery")
            st.caption("Fai una domanda su farmaci, classi, indicazioni "
                       "e centri di prescrizione.")
            method=st.selectbox("Metodo di risposta",
                                ("Text-to-SQL","TAG"),
                                key="farmaquery_float_method")
            key=history_key(method)
            if key not in st.session_state:
                st.session_state[key]=[]
            history=st.session_state[key]
            if "farmaquery_chat_count" not in st.session_state:
                st.session_state["farmaquery_chat_count"]=0
            remaining=MAX_QUESTIONS_PER_SESSION-st.session_state["farmaquery_chat_count"]

            if not has_key:
                st.info("L'assistente non è ancora disponibile: "
                        "manca la configurazione del modello sul server.")
            elif remaining<=0:
                st.info("Hai raggiunto il limite di domande per questa sessione.")
            else:
                st.caption(f"Domande disponibili nella sessione: {remaining}")

            st.button("Nuova conversazione",
                      key="farmaquery_start_new_conversation",
                      on_click=start_new_conversation,
                      help="Cancella entrambe le cronologie; il limite di richieste rimane.",
                      use_container_width=True)
            if st.session_state.pop("farmaquery_chat_just_cleared",False):
                st.success("Nuova conversazione avviata: messaggi eliminati.")

            # Le cronologie per TAG e Text-to-SQL sono separate.
            with st.container(height=260,border=False):
                if not history:
                    st.caption("Scrivi liberamente una domanda per iniziare.")
                for item in history:
                    with st.chat_message(item["role"]):
                        st.markdown(item["text"])
                        if item["role"]=="assistant":
                            if item.get("fonti"):
                                with st.expander("Fonti"):
                                    for ref in item["fonti"]:
                                        st.write(str(ref))
                            if method=="Text-to-SQL" and item.get("sql"):
                                with st.expander("SQL generato"):
                                    st.code(item["sql"],language="sql")
                            if item.get("secondi") is not None:
                                st.caption(f"{item['secondi']:.1f} s · {method}")

            # Nessuna lista di esempi e nessuna domanda inserita nel codice.
            with st.form("farmaquery_float_form_"+method,clear_on_submit=True):
                question=st.text_input("La tua domanda",max_chars=700,
                                       placeholder="Scrivi qui...",
                                       disabled=(not has_key or remaining<=0))
                sent=st.form_submit_button("Invia",type="primary",
                                            disabled=(not has_key or remaining<=0),
                                            use_container_width=True)

            if sent and question.strip():
                st.session_state["farmaquery_chat_count"]+=1
                history.append({"role":"user","text":question.strip()})
                start=time.monotonic()
                with st.spinner("Sto consultando le fonti..."):
                    try:
                        db,manifest=_cached_snapshot(snapshot_version())
                        result=answer_question(db,question,method,model)
                    except (ImportError,ModuleNotFoundError):
                        result={"risposta":"Il modulo di risposta non è disponibile "
                                "nell'ambiente del server.","fonti":[]}
                    except (OSError,ValueError,sqlite3.DatabaseError) as err:
                        result={"risposta":"Non riesco ad accedere al database "
                                f"({type(err).__name__}).","fonti":[]}
                    except Exception as err:
                        msg=str(err).lower()
                        if "429" in msg or "resource_exhausted" in msg or "rate limit" in msg:
                            info="La quota del modello è esaurita. Riprova più tardi."
                        elif "api key" in msg or "401" in msg or "authentication" in msg:
                            info="La chiave API del modello deve essere controllata."
                        else:
                            info="Non è stato possibile ottenere una risposta dal modello."
                        result={"risposta":info,"fonti":[]}
                history.append({"role":"assistant",
                                "text":result.get("risposta","Nessuna risposta disponibile."),
                                "fonti":result.get("fonti",[]),
                                "sql":result.get("sql",""),
                                "secondi":round(time.monotonic()-start,2)})
                st.rerun()

            st.caption("Prototipo accademico: verifica sempre le fonti "
                       "prima di prendere decisioni cliniche.")
