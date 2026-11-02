"""Assistente FarmaQuery: bolla flottante + finestra di chat autonoma.

Il vecchio st.popover era annidato dentro un contenitore fixed di soli
90 pixel. Questo file fissa SOLO il pulsante; il contenuto è un dialog
Streamlit separato e il campo rimane sempre modificabile.
"""
from __future__ import annotations

import sqlite3
import time
import re
from urllib.parse import urlsplit

import streamlit as st
from errori_chatbot import label_error
from chatbot_farmaquery import (
    answer_question, enable_server_key, history_key,
    model_from_settings, prepare_snapshot, snapshot_version,
    verify_provider,
)

MAX_QUESTIONS_PER_SESSION=12


def start_new_conversation():
    """Pulisce entrambe le cronologie, senza azzerare la quota API."""
    for method in ("Text-to-SQL", "TAG"):
        st.session_state[history_key(method)]=[]
    st.session_state["farmaquery_chat_just_cleared"]=True


@st.cache_resource(show_spinner=False,max_entries=2)
def _cached_snapshot(version):
    return prepare_snapshot()


def _server_config():
    try:
        secrets=dict(st.secrets)
    except (FileNotFoundError,RuntimeError):
        secrets={}
    model=model_from_settings(secrets)
    return model,enable_server_key(model,secrets)


def _reply(question,method,model,has_key,remaining):
    """Produce un risultato senza mai disabilitare l'editor dei messaggi."""
    if not has_key:
        return {"risposta":"La domanda è stata ricevuta. Il modello non è "
                "ancora collegato: controlla GEMINI_API_KEY nei Secrets "
                "di Streamlit Cloud.","fonti":[]}
    if remaining<=0:
        return {"risposta":"Hai raggiunto il limite di chiamate al modello "
                "per questa sessione. Puoi continuare a scrivere, ma "
                "non effettuare altre richieste in questa sessione.",
                "fonti":[]}
    st.session_state["farmaquery_chat_count"]+=1
    with st.spinner("Consulto le fonti..."):
        try:
            db,_manifest=_cached_snapshot(snapshot_version())
            return answer_question(db,question,method,model)
        except (ImportError,ModuleNotFoundError):
            return {"risposta":"Il motore selezionato non risulta installato "
                    "nell'ambiente del server.","fonti":[]}
        except (OSError,ValueError,sqlite3.DatabaseError):
            return {"risposta":"Il database non è temporaneamente disponibile.",
                    "fonti":[]}
        except Exception as exc:
            # NON visualizzare il messaggio grezzo: può contenere chiavi API
            # o dettagli privati della richiesta. Mostra fase e classe sicure.
            return label_error(exc)


def _show_citation(ref):
    """Mostra pagina e archivio originali senza fingere link PDF nei file ZIP."""
    source=str(ref)
    match=re.match(r"^(.+?)#p([0-9]+) \| archivio: (https?://\S+)$",source)
    if match:
        name,page,url=match.groups()
        st.caption(name+" — pagina "+page+" del PDF contenuto nell'archivio")
    else:
        parts=source.split(" | ",1)
        url=parts[1].split("#segmento-",1)[0] if len(parts)==2 else ""
        st.caption(parts[0])
    if url and urlsplit(url).hostname and (
        urlsplit(url).hostname.endswith(".aifa.gov.it")
        or urlsplit(url).hostname=="www.aifa.gov.it"
        or urlsplit(url).hostname=="www.regione.campania.it"
        or urlsplit(url).hostname=="www.ema.europa.eu"
        or urlsplit(url).hostname=="www.gazzettaufficiale.it"
    ):
        st.markdown("[Apri la fonte ufficiale]("+url+")")


@st.dialog("Assistente FarmaQuery",width="large")
def assistant_dialog():
    """Una finestra nativa: il campo è esterno al CSS del pulsante flottante."""
    st.caption("Informazioni EMA, AIFA, Gazzetta Ufficiale e Regione Campania.")
    method=st.selectbox("Metodo di risposta",
                        ("Text-to-SQL","TAG"),
                        key="farmaquery_float_method")
    model,has_key=_server_config()
    history_id=history_key(method)
    if history_id not in st.session_state:
        st.session_state[history_id]=[]
    history=st.session_state[history_id]
    if "farmaquery_chat_count" not in st.session_state:
        st.session_state["farmaquery_chat_count"]=0
    remaining=MAX_QUESTIONS_PER_SESSION-st.session_state["farmaquery_chat_count"]
    if not has_key:
        st.warning("Gemini non è configurato. Il campo di scrittura è comunque disponibile.")
    elif remaining<=0:
        st.info("Limite di richieste raggiunto. Puoi ancora scrivere, ma non ottenere nuove risposte.")
    else:
        st.caption(f"Richieste disponibili: {remaining}")

    st.button("Nuova conversazione",
              key="farmaquery_start_new_conversation",
              on_click=start_new_conversation,
              help="Cancella le conversazioni TAG e Text-to-SQL; preserva il limite API.")
    if st.session_state.pop("farmaquery_chat_just_cleared",False):
        st.success("Conversazioni cancellate.")

    # Diagnostica separata dalla chat: una chiamata minima permette di
    # capire se il provider risponde senza coinvolgere TAG o Text-to-SQL.
    with st.expander("Diagnostica del modello"):
        st.caption(f"Modello selezionato: {model}. Il test usa una richiesta "
                   "minima e può consumare una piccola quota API.")
        if st.button("Verifica connessione Gemini",key="farmaquery_probe",
                     disabled=not has_key or remaining<=0):
            st.session_state["farmaquery_chat_count"]+=1
            try:
                ok=verify_provider(model)
                if ok:
                    st.success("Connessione al modello riuscita. "
                               "Se la chat non risponde, il problema è nel "
                               "motore TAG oppure nella query SQL.")
                else:
                    st.warning("Gemini non ha restituito testo.")
            except Exception as exc:
                result=label_error(exc)
                st.error(result["risposta"])
                st.caption("Questo errore riguarda la connessione al modello, "
                           "non il database.")


    with st.container(height=290,border=True):
        if not history:
            st.caption("Scrivi una domanda per iniziare.")
        for item in history:
            with st.chat_message(item["role"]):
                st.markdown(item["text"])
                if item["role"]=="assistant":
                    if item.get("fonti"):
                        with st.expander("Fonti consultate"):
                            for ref in item["fonti"]:
                                _show_citation(ref)
                    if item.get("evidenze_fonti"):
                        with st.expander("Estratti dei dati consultati"):
                            st.caption("Estratti del contesto recuperato, non "
                                       "verifiche normative indipendenti.")
                            for source in item["evidenze_fonti"]:
                                st.caption(source.get("tipo","Fonte")+" · "+
                                           source.get("fonte","")[:150])
                                st.text(source.get("estratto",""))
                    if method=="Text-to-SQL" and item.get("sql"):
                        with st.expander("Query SQL"):
                            if item.get("sql_iniziale"):
                                st.caption("Prima SELECT: zero righe. "
                                           "Il modello ha generato una seconda "
                                           "query (mostrata più sotto).")
                                st.code(item["sql_iniziale"],language="sql")
                                st.caption("Seconda SELECT eseguita:")
                            st.code(item["sql"],language="sql")
                        if item.get("sql_tentativi"):
                            st.caption(
                                "Text-to-SQL · query generate: "+
                                str(item["sql_tentativi"])+
                                " · modello e snapshot invariati"
                            )
                    if item.get("secondi") is not None:
                        st.caption(f'{item["secondi"]:.1f} s · {method}')
                    if method=="TAG" and item.get("versione_tag"):
                        st.caption(
                            "Motore TAG: "+str(item["versione_tag"])+
                            " · contesto fonte: "+
                            str(item.get("verifica_contesto","?"))+
                            " · AIC rilevati nel testo: "+
                            str(item.get("aic_nel_testo_integrale",0))+
                            " · revisione richiesta: "+
                            ("sì" if item.get("revisione_completezza_llm") else "no"))
                    if method=="TAG" and item.get("modalita_selezione"):
                        st.caption(
                            "Selezione TAG: "+str(item["modalita_selezione"])+
                            " · evidenze: "+str(item.get("righe_recuperate","?"))+
                            " · elementi LOTUS: "+str(item.get("righe_sem_filter","?"))+
                            " · chiamate LLM stimate (non misurate): "+
                            str(item.get("chiamate_llm_stimate","?"))
                        )

    # Non usare st.popover o st.chat_input: un normale text_area in st.dialog
    # è interattivo e non dipende dalle dimensioni/coordinate della bolla.
    with st.form("farmaquery_message_form_"+method,clear_on_submit=True):
        question=st.text_area("Scrivi la tua domanda",
                              placeholder="Digita qui la domanda...",
                              height=85,max_chars=700,disabled=False)
        sent=st.form_submit_button("Invia",type="primary",use_container_width=True)

    if sent and question.strip():
        text_question=question.strip()
        history.append({"role":"user","text":text_question})
        start=time.monotonic()
        result=_reply(text_question,method,model,has_key,remaining)
        history.append({"role":"assistant",
                        "text":result.get("risposta","Nessuna risposta disponibile."),
                        "fonti":result.get("fonti",[]),
                        "evidenze_fonti":result.get("evidenze_fonti",[]),
                        "sql":result.get("sql",""),
                        "sql_iniziale":result.get("sql_iniziale"),
                        "sql_tentativi":result.get("sql_tentativi"),
                        "secondi":round(time.monotonic()-start,2),
                        "modalita_selezione":result.get("modalita_selezione"),
                        "righe_recuperate":result.get("righe_recuperate"),
                        "righe_sem_filter":result.get("righe_sem_filter"),
                        "chiamate_llm_stimate":result.get("chiamate_llm_stimate"),
                        "versione_tag":result.get("versione_tag"),
                        "verifica_contesto":result.get("verifica_contesto"),
                        "aic_nel_testo_integrale":result.get("aic_nel_testo_integrale"),
                        "revisione_completezza_llm":result.get("revisione_completezza_llm")})
        # Solo la finestra viene aggiornata: rimane aperta e scrivibile.
        st.rerun(scope="fragment")

    st.caption("Prototipo accademico: controlla le fonti prima di prendere "
               "decisioni cliniche.")


def render_assistant():
    # Il contenitore a posizione fissa contiene SOLO il pulsante. La chat
    # vera si apre nel dialog Streamlit (portal indipendente dal layout).
    st.markdown("""
    <style>
    .st-key-farmaquery_floating {
        position:fixed!important;
        right:22px!important;
        bottom:72px!important;
        z-index:99999!important;
        width:94px!important;
        max-width:94px!important;
        padding:0!important;
    }
    .st-key-farmaquery_floating button {
        width:88px!important;
        min-width:88px!important;
        max-width:88px!important;
        height:88px!important;
        min-height:88px!important;
        border-radius:50%!important;
        padding:0!important;
        font-size:2rem!important;
        color:white!important;
        background:#116b70!important;
        border:2px solid white!important;
        box-shadow:0 7px 26px rgba(0,0,0,.24)!important;
    }
    .st-key-farmaquery_floating button:hover {
        background:#098f85!important;
    }
    @media(max-width:650px) {
        .st-key-farmaquery_floating {
            right:13px!important;
            bottom:56px!important;
            width:84px!important;
            max-width:84px!important;
        }
        .st-key-farmaquery_floating button {
            width:78px!important;
            min-width:78px!important;
            max-width:78px!important;
            height:78px!important;
            min-height:78px!important;
        }
    }
    </style>
    """,unsafe_allow_html=True)
    with st.container(key="farmaquery_floating"):
        if st.button("💬",key="farmaquery_open_chat",
                     help="Apri assistente FarmaQuery"):
            assistant_dialog()
