"""Assistente FarmaQuery: bolla flottante + finestra di chat autonoma.

Il vecchio st.popover era annidato dentro un contenitore fixed di soli
90 pixel. Questo file fissa SOLO il pulsante; il contenuto è un dialog
Streamlit separato e il campo rimane sempre modificabile.
"""
from __future__ import annotations

import sqlite3
import time
import re
import json
import csv
from io import StringIO
from datetime import datetime,timezone
from urllib.parse import urlsplit

import streamlit as st
from errori_chatbot import label_error
from chatbot_farmaquery import (
    answer_question, enable_server_key, history_key,
    model_from_settings, prepare_snapshot, snapshot_version,
    verify_provider,
)

MAX_QUESTIONS_PER_SESSION=100


def start_new_conversation():
    """Pulisce le cronologie, senza azzerare la quota API."""
    for method in ("Text-to-SQL", "TAG", "TAG automatico",
                   "Text-to-SQL con auto-correzione"):
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


def _sql_validation_diagnostic(exc):
    """Espone solo categorie sicure, mai SQL grezzo rifiutato dal validatore."""
    if getattr(exc, "phase", "") != "validazione SQL TAG automatico":
        return None
    raw = str(getattr(exc, "original", "")).casefold()
    if "join senza condizione" in raw or "join senza collegamento" in raw:
        return "JOIN senza collegamento valido tra le tabelle."
    if "tabella o schema non consentito" in raw:
        return "Tabella o schema non presente fra quelli consentiti."
    if "sono consentite solo select" in raw:
        return "Il modello non ha prodotto una singola SELECT consentita."
    if "funzione sql non consentita" in raw or "sql non consentito" in raw:
        return "La SELECT contiene un'operazione o funzione non consentita."
    return "La SELECT non ha superato la validazione sintattica o strutturale."


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
            outcome=label_error(exc)
            if method=="TAG automatico":
                category=_sql_validation_diagnostic(exc)
                if category:
                    outcome["diagnostica_sql"]=category
            # Misure tecniche sicure anche se la chiamata ha fallito.
            diagnostics=getattr(exc,"metriche_llm",None)
            if isinstance(diagnostics,dict):
                outcome.update({
                    key:diagnostics.get(key)
                    for key in ("chiamate_llm_effettive","chiamate_llm_dirette",
                                "chiamate_llm_lotus","tempo_backend_s")
                })
            return outcome


def _citation_details(ref):
    """Prepara un link sicuro, distinguendo un archivio ZIP dal PDF.

    Un URL allo ZIP regionale NON apre il PDF interno alla pagina: non
    inventare URL diretti o aggiungere #page a file diversi dai PDF.
    """
    source=str(ref)
    match=re.match(
        r"^(.+?)#p([0-9]+) \| archivio: (https?://\S+)$",source)
    page=None
    is_regional=bool(match)
    if match:
        name,page_text,url=match.groups()
        page=int(page_text)
        title=name+" — pagina "+str(page)
    else:
        parts=source.split(" | ",1)
        title=parts[0]
        url=parts[1].split("#segmento-",1)[0] if len(parts)==2 else ""
    parsed=urlsplit(url)
    host=(parsed.hostname or "").lower()
    allowed=bool(parsed.scheme=="https" and parsed.username is None
                 and parsed.password is None and (
        host=="www.regione.campania.it"
        or host=="www.ema.europa.eu"
        or host=="www.gazzettaufficiale.it"
        or host=="www.aifa.gov.it"
        or host.endswith(".aifa.gov.it")))
    if not allowed:
        url=""
    is_pdf=bool(url and parsed.path.casefold().endswith(".pdf"))
    is_archive=bool(is_regional and url and not is_pdf)
    if is_pdf and page is not None:
        # Il browser PDF puo usare l'ancora pagina solo con un URL al PDF.
        url=parsed._replace(fragment="page="+str(page)).geturl()
    label=("Apri il PDF ufficiale alla pagina indicata" if is_pdf and page else
           "Apri il PDF ufficiale" if is_pdf else
           "Apri l'archivio ufficiale della Regione" if is_archive else
           "Apri la fonte ufficiale")
    return {"titolo":title,"url":url,"etichetta":label,
            "archivio":is_archive,"pagina":page,
            "documento":name if is_regional else ""}


@st.cache_data(ttl=3600,max_entries=2,show_spinner=False)
def _cached_pdf_from_archive(url,document):
    from demo_fonti_pdf import pdf_from_official_archive
    return pdf_from_official_archive(url,document)


def _show_citation(ref,instance_key=""):
    """Fonte e pagina con anteprima opzionale del vero PDF nello ZIP."""
    details=_citation_details(ref)
    st.caption(details["titolo"])
    if details["url"]:
        st.markdown("["+details["etichetta"]+"]("+details["url"]+")")
    if details["archivio"]:
        st.caption("Il PDF è contenuto nello ZIP: il link apre "
                   "l'archivio, non direttamente il documento interno.")
        if st.button("Visualizza la pagina del PDF originale",
                     key="pdf_demo_"+instance_key):
            try:
                with st.spinner("Apro la pagina dal PDF ufficiale..."):
                    data=_cached_pdf_from_archive(
                        details["url"],details["documento"])
                    from streamlit_pdf_viewer import pdf_viewer
                    pdf_viewer(input=data,
                               pages_to_render=[details["pagina"]],
                               height=540,key="viewer_"+instance_key)
            except Exception:
                st.warning("Anteprima PDF non disponibile: consulta "
                           "il nome, il numero di pagina e l'estratto "
                           "testuale della fonte riportati nella demo.")


def _show_excerpt(source):
    """Passo documentale mostrato come citazione; non altera il PDF."""
    raw=str(source.get("estratto") or "").strip()
    if not raw:
        return
    st.caption("Passaggio recuperato dal database · "+
               str(source.get("tipo") or "Fonte"))
    # Il testo del documento resta testuale, senza eseguire HTML o Markdown.
    st.text(raw)


def _visible_message(item, mostra_dettagli):
    """Per gli screenshot nasconde il codice tecnico, non l'errore reale."""
    text=str(item.get("text") or "")
    if (not mostra_dettagli and item.get("role")=="assistant"
            and item.get("stato") in ("ERRORE","ERRORE_SQL")):
        # Il messaggio originale resta intatto nell'esportazione JSON.
        text=re.sub(r"\s*\(fase:\s*[^)]*\)\.?$", "", text).strip()
    return text



APP_UI_VERSION="2026-11-09-sqlretry-csv-v1"
CSV_FIELDS=("metodo","numero_domanda","domanda","risposta_integrale",
            "fonti","evidenze_fonti","stato","sql","sql_originale_llm",
            "sql_proposte","sql_tentativi","correzioni_sql","errori_sql_tentativi",
            "codice_errore","fase_errore","tipo_errore","secondi",
            "tempo_backend_s","chiamate_llm_effettive","chiamate_llm_dirette",
            "chiamate_llm_lotus","token_input","token_output","costo_usd",
            "modello","snapshot_sha256","esportazione_utc")


def _full_results_csv(report):
    """Conserva ogni domanda/risposta integrale e le metriche in CSV.

    Punto e virgola, virgolette per tutte le celle, BOM UTF-8 per Excel.
    JSON resta l'originale autorevole per i campi strutturati.
    """
    file=StringIO(newline="")
    writer=csv.DictWriter(file,fieldnames=CSV_FIELDS,delimiter=";",
                          quoting=csv.QUOTE_ALL,lineterminator="\\n")
    writer.writeheader()
    for method in report.get("metodi",[]):
        if not isinstance(method,dict):
            continue
        pending=[]
        count=0
        for item in method.get("messaggi") or []:
            if not isinstance(item,dict):
                continue
            if item.get("role")=="user":
                pending.append(str(item.get("text") or ""))
                continue
            if item.get("role")!="assistant":
                continue
            count+=1
            row={
                "metodo":str(method.get("etichetta") or method.get("metodo") or ""),
                "numero_domanda":count,
                "domanda":pending.pop(0) if pending else "",
                "risposta_integrale":str(item.get("text") or ""),
                "modello":str(item.get("modello") or report.get("modello") or ""),
                "snapshot_sha256":report.get("snapshot_sha256") or "",
                "esportazione_utc":report.get("esportazione_utc") or "",
            }
            for key in CSV_FIELDS:
                if key in row:
                    continue
                value=item.get(key)
                row[key]=(json.dumps(value,ensure_ascii=False,default=str)
                          if isinstance(value,(dict,list)) else
                          "" if value is None else value)
            writer.writerow(row)
    return "\\ufeff"+file.getvalue()


@st.dialog("Assistente FarmaQuery",width="large")
def assistant_dialog():
    """Una finestra nativa: il campo è esterno al CSS del pulsante flottante."""
    st.caption("Informazioni EMA, AIFA, Gazzetta Ufficiale e Regione Campania.")
    # Due soli motori visibili: il Text-to-SQL standard rimane in codice
    # esclusivamente per confronti riproducibili con la vecchia baseline.
    method=st.selectbox("Metodo di risposta",
                        ("Text-to-SQL con auto-correzione","TAG automatico"),
                        format_func=lambda value: (
                            "Text-to-SQL" if value=="Text-to-SQL con auto-correzione"
                            else "TAG"),
                        key="farmaquery_float_method")
    mostra_dettagli=st.toggle(
        "Mostra dettagli tecnici",value=False,
        key="farmaquery_show_technical_details",
        help="Le metriche e gli errori restano salvati nell'esportazione JSON anche quando sono nascosti.")

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

    # Comando indipendente e allineato a sinistra, lontano da 'Invia'.
    new_chat_col, _ = st.columns([1.6, 2.4])
    with new_chat_col:
        st.button("↺ Nuova conversazione",
                  key="farmaquery_start_new_conversation",
                  on_click=start_new_conversation,
                  help="Cancella le conversazioni; preserva il limite API.")
    if st.session_state.pop("farmaquery_chat_just_cleared",False):
        st.success("Conversazioni cancellate.")

    if mostra_dettagli:
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
        for msg_index,item in enumerate(history):
            with st.chat_message(item["role"]):
                st.markdown(_visible_message(item, mostra_dettagli))
                if item["role"]=="assistant":
                    if item.get("fonti"):
                        with st.expander("Fonti consultate"):
                            for ref_index,ref in enumerate(item["fonti"]):
                                _show_citation(
                                    ref,instance_key=method+"_"+str(msg_index)+
                                    "_"+str(ref_index))
                    if mostra_dettagli:
                        if item.get("evidenze_fonti"):
                            tabular_auto=(method=="TAG automatico" and all(
                                src.get("tipo")=="SQL" for src in item["evidenze_fonti"]))
                            with st.expander(
                                "Righe strutturate consultate" if tabular_auto
                                else "Passaggi del testo consultato"):
                                if tabular_auto:
                                    st.caption("Record dello snapshot SQLite: "
                                               "per queste fonti non sono previsti "
                                               "numeri di pagina PDF.")
                                else:
                                    st.caption("Testo originale estratto dalle fonti, "
                                               "non evidenziazione nel PDF e non "
                                               "verifica normativa indipendente.")
                                for source in item["evidenze_fonti"]:
                                    st.caption(str(source.get("fonte") or "")[:200])
                                    _show_excerpt(source)
                        if method=="TAG automatico" and item.get("diagnostica_sql"):
                            st.caption("Diagnostica SQL: "+str(item["diagnostica_sql"]))
                        if method in ("Text-to-SQL","TAG automatico",
                                      "Text-to-SQL con auto-correzione") and item.get("sql"):
                            with st.expander("SQL di recupero e tracciabilità" if method=="TAG automatico"
                                             else "Query SQL generata dall'LLM"):
                                original = item.get("sql_originale_llm")
                                if method=="TAG automatico" and original:
                                    st.caption("SQL generato dall'LLM (prima dei controlli)")
                                    st.code(original,language="sql")
                                    if (item.get("sql_normalizzato_nome") or
                                            item.get("sql_normalizzato_ambito_regione") or
                                            item.get("sql_normalizzato_join_documentali") or
                                            item.get("sql") != original):
                                        if item.get("sql_normalizzato_nome"):
                                            st.caption("Confronti dei nomi normalizzati: case-insensitive.")
                                        if item.get("sql_normalizzato_ambito_regione"):
                                            st.caption(
                                                "Filtro regionale spurio sul percorso ZIP rimosso: "
                                                "la tabella note contiene già le note della Campania.")
                                        if item.get("sql_normalizzato_join_documentali"):
                                            st.caption(
                                                "JOIN con tabella revisionata parziale "
                                                "convertita in LEFT JOIN per non perdere "
                                                "note prive di una relazione già verificata. "
                                                "I centri andranno confermati nel PDF.")
                                        st.caption("SQL effettivamente eseguito (incluso eventuale fallback)")
                                        st.code(item["sql"],language="sql")
                                    else:
                                        st.caption("SQL eseguito senza normalizzazioni")
                                else:
                                    st.code(item["sql"],language="sql")

                                if method=="Text-to-SQL con auto-correzione":
                                    st.caption("Text-to-SQL · massimo due correzioni su errore SQL")
                                elif method=="Text-to-SQL":
                                    st.caption("Text-to-SQL standard · una sola SELECT")
                                else:
                                    st.caption("TAG · SQL validato, candidati SQLite, filtro LOTUS")
                        if method=="TAG automatico" and item.get("tag_auto_revision"):
                            st.caption("Revisione del motore in uso: "+
                                       str(item["tag_auto_revision"]))
                        if item.get("secondi") is not None:
                            st.caption(f'{item["secondi"]:.1f} s · {method}')
                        if method=="TAG" and item.get("versione_tag"):
                            st.caption("TAG "+str(item["versione_tag"])+" · fonte "+str(item.get("verifica_contesto","?"))+" · AIC "+str(item.get("aic_nel_testo_integrale",0)))
                        if method=="TAG" and item.get("versione_tag"):
                            st.caption("TAG: "+str(item["versione_tag"])+
                                       " · testo originale: "+
                                       str(item.get("verifica_contesto","n.d."))+
                                       " · AIC nell'atto: "+
                                       str(item.get("aic_nel_testo_integrale","n.d."))+
                                       " · revisione LLM: "+
                                       ("sì" if item.get("revisione_completezza_llm")
                                        else "no"))
                        if method=="TAG" and item.get("fallback_pagina_integrale"):
                            st.caption("LOTUS non ha selezionato gruppi: risposta "
                                       "elaborata dal testo integrale della "
                                       "pagina identificata, recuperata dallo SQLite.")
                        if method=="Text-to-SQL con auto-correzione" and item.get("correzioni_sql") is not None:
                            st.caption("Text-to-SQL con auto-correzione · correzioni SQL: "+
                                       str(item["correzioni_sql"])+"/2 · SELECT tentate: "+
                                       str(item.get("sql_tentativi","?"))+".")
                        if item.get("chiamate_llm_effettive") is not None:
                            st.caption(
                                "Invii LLM misurati: "+
                                str(item["chiamate_llm_effettive"])+
                                " · diretti: "+str(item.get("chiamate_llm_dirette","?"))+
                                " · LOTUS: "+str(item.get("chiamate_llm_lotus") or 0))
                        elif item.get("chiamate_llm_stimate") is not None:
                            st.caption(
                                "Chiamate LLM stimate (conteggio completo non disponibile): "+
                                str(item["chiamate_llm_stimate"]))
                        if method in ("TAG","TAG automatico") and item.get("modalita_selezione"):
                            st.caption(
                                "Selezione TAG: "+str(item["modalita_selezione"])+
                                " · evidenze: "+str(item.get("righe_recuperate","?"))+
                                " · elementi LOTUS: "+str(item.get("righe_sem_filter","?")))
                        if method=="TAG automatico" and item.get("errore_sql_iniziale"):
                            st.caption(
                                "La SQL iniziale e' stata rifiutata prima "
                                "dell'esecuzione (tabella non consentita). "+
                                "Le SELECT alternative, se presenti, sono "
                                "state generate da codice e validate separatamente."
                            )
                        if method=="TAG automatico" and item.get("controllo_copertura_eseguito"):
                            st.caption(
                                "Controllo copertura documentale · note candidate: "+
                                str(item.get("documenti_controllo_copertura","?"))+
                                " · note escluse dalla prima SELECT: "+
                                str(item.get("documenti_esclusi_primo_recupero","?"))+
                                ". I documenti aggiuntivi non sono automaticamente "
                                "pertinenti alla domanda.")
                            with st.expander("SQL del controllo di copertura"):
                                st.code(
                                    item.get("sql_controllo_copertura")
                                    or "Non disponibile",language="sql"
                                )
                        if method=="TAG automatico" and item.get("strategia_tag")=="due_fasi":
                            st.caption(
                                "Metodo alternativo in due fasi · motivo: "+
                                str(item.get("motivo_due_fasi","?"))+
                                " · note prima fase: "+
                                str(item.get("documenti_fase1","?"))+
                                " · note seconda fase: "+
                                str(item.get("documenti_fase2","?"))+
                                " · coppie documentate: "+
                                str(item.get("coppie_documentate","?"))+
                                " · lotti prima fase: "+
                                str(item.get("lotti_fase1_validi","?"))+"/"+
                                str(item.get("lotti_fase1","?"))+".")
                            with st.expander("SQL delle due fasi"):
                                st.caption("Prima SELECT controllata (recupero documenti)")
                                st.code(item.get("sql_fase1") or "Non eseguita",language="sql")
                                st.caption("Seconda SELECT controllata (note selezionate)")
                                st.code(item.get("sql_fase2") or "Non eseguita",language="sql")
                        if method=="TAG automatico" and item.get("codice_errore_due_fasi"):
                            st.caption(
                                "Diagnostica interruzione TAG · causa: "+
                                str(item.get("codice_errore_due_fasi"))+
                                " · fase: "+
                                str(item.get("fase_errore_due_fasi") or "sconosciuta")+
                                " · tipo: "+
                                str(item.get("tipo_errore_due_fasi") or "non disponibile")+
                                " · lotto interrotto: "+
                                str(item.get("lotto_verifica_interrotto") or "non applicabile")+
                                ". Le informazioni già verificate non vengono inventate "
                                "né presentate come elenco completo."
                            )
                        if method=="TAG automatico" and item.get("lotti_verifica_finale"):
                            st.caption(
                                "Verifica finale distribuita · lotti completati: "+
                                str(item.get("lotti_verifica_conclusi",0))+"/"+
                                str(item["lotti_verifica_finale"])+
                                " · lotti non validi: "+
                                str(item.get("lotti_verifica_non_validi",0))+
                                " · schede inviate al verificatore: "+
                                str(item.get("documenti_inviati_verifica",0))+"."
                            )
                        if method=="TAG automatico" and item.get("asserzioni_verifica_proposte") is not None:
                            st.caption(
                                "Verifica delle associazioni · proposte: "+
                                str(item["asserzioni_verifica_proposte"])+
                                " · accettate: "+
                                str(item.get("asserzioni_verifica_accettate",0))+
                                " · respinte: "+
                                str(item.get("asserzioni_verifica_respinte",0))+
                                ". Ogni associazione è controllata separatamente."
                            )
                        if method=="TAG automatico" and (
                                item.get("motivi_rifiuto_verifica")
                                or item.get("documenti_candidati_verifica")):
                            with st.expander("Diagnostica puntuale della seconda fase"):
                                st.caption(
                                    "Documenti sottoposti alla verifica finale "
                                    "(l'elenco non dimostra la loro pertinenza clinica)."
                                )
                                for doc in item.get("documenti_candidati_verifica") or []:
                                    st.write(str(doc.get("documento") or "Documento privo di titolo"))
                                uncovered=item.get("documenti_senza_associazione_verificata") or []
                                if uncovered:
                                    st.caption(
                                        "Documenti senza associazione accettata "
                                        "(non significa che il medicinale non sia pertinente):"
                                    )
                                    for name in uncovered:
                                        st.write(str(name))
                                reasons=item.get("motivi_rifiuto_verifica") or {}
                                if reasons:
                                    st.caption("Cause dei riferimenti non accettati")
                                    for label,number in reasons.items():
                                        st.write(str(label)+": "+str(number))
                        if method=="TAG automatico" and item.get("motivo_astensione"):
                            st.caption("Astensione documentale: "+str(item["motivo_astensione"]))
                        if method=="TAG automatico" and item.get("raffinamento_documentale_usato"):
                            st.caption(
                                "Raffinamento documentale · candidati valutati: "+
                                str(item.get("documenti_candidati_raffinamento","?"))+
                                " · documenti scelti: "+
                                str(item.get("documenti_selezionati_raffinamento","?"))+
                                " · lotti completati: "+
                                str(item.get("lotti_raffinamento_completati","?"))+
                                "/"+str(item.get("lotti_raffinamento","?"))+
                                " · lotti non validi: "+
                                str(item.get("lotti_raffinamento_non_validi",0))+
                                " · chiamate dirette del raffinamento: "+
                                str(item.get("chiamate_dirette_raffinamento","?"))+
                                ". Pertinenza e completezza non certificate.")
                        if method=="TAG automatico" and item.get("chiamate_piano_documentale"):
                            st.caption(
                                "Piano documentale strutturato · esito: "+
                                str(item.get("piano_documentale_esito","?"))+
                                " · struttura: "+
                                str(item.get("piano_documentale_centro") or "non confermata")+
                                " · chiamate LLM piano: "+
                                str(item.get("chiamate_piano_documentale",0))+
                                ". Piano e pertinenza soggetti a verifica.")
                        if method=="TAG automatico" and item.get("recupero_progressivo_usato"):
                            st.caption(
                                "Recupero SQL progressivo attivato · SELECT eseguite: "+
                                str(item.get("sql_tentativi","?"))+
                                ". SQL originale e finale disponibili sopra.")
                        if method=="TAG automatico" and item.get("note_nell_indice") is not None:
                            st.caption(
                                "Note documentali nel contesto di sintesi: "+
                                str(item.get("note_nel_contesto","?"))+
                                " · schede nell'indice: "+
                                str(item["note_nell_indice"])+
                                ". La presenza nel contesto non certifica che "
                                "la risposta abbia elencato tutte le note.")
                        if method=="TAG automatico" and item.get("identificativi_sql_riconciliati"):
                            st.caption(
                                "Provenienza identificativi riallineata dopo la SELECT: "+
                                str(item["identificativi_sql_riconciliati"])+
                                " riga/e, con verifica nello snapshot. "
                                "La query originale rimane visibile per l'audit.")
                        if method=="TAG" and item.get("sql_first_note_con_centro"):
                            st.caption(
                                "SQL-first · note che menzionano la struttura: "+
                                str(item["sql_first_note_con_centro"])+
                                " · note candidate per la sintesi: "+
                                str(item.get("sql_first_note_preselezionate",0)))

                        if method=="TAG" and item.get("statistiche_revisione_categoria"):
                            stats=item["statistiche_revisione_categoria"]
                            if stats.get("chiamate",0)>0:
                                st.caption(
                                    "Revisione categoria · candidati: "+
                                    str(stats.get("candidati",0))+
                                    " · verifiche individuali: "+
                                    str(stats.get("chiamate",0))+
                                    " · voci integrate: "+
                                    str(stats.get("accettati",0)))
                                with st.expander("Diagnostica della revisione TAG"):
                                    st.caption(
                                        "Esiti del controllo sulle citazioni "
                                        "dello snapshot; non costituiscono "
                                        "una valutazione clinica indipendente.")
                                    for check in item.get("diagnostica_revisione_categoria",[]):
                                        label=(str(check.get("medicinale","?"))+
                                               ": "+str(check.get("esito","n.d.")))
                                        if check.get("proposte_esaminate",0)>1:
                                            label+=(" ("+str(check["proposte_esaminate"])+
                                                    " proposte valutate)")
                                        st.write(label)
                                        if check.get("citazione_proposta"):
                                            st.caption("Citazione da verificare: "+
                                                       str(check["citazione_proposta"])[:180])

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
                        "modello":model,
                        "token_input":result.get("token_input"),
                        "token_output":result.get("token_output"),
                        "costo_usd":result.get("costo_usd"),
                        "costo_completo":result.get("costo_completo"),
                        "fonti":result.get("fonti",[]),
                        "evidenze_fonti":result.get("evidenze_fonti",[]),
                        "sql":result.get("sql",""),
                        "diagnostica_sql":result.get("diagnostica_sql"),
                        "sql_originale_llm":result.get("sql_originale_llm"),
                        "sql_normalizzato_nome":result.get("sql_normalizzato_nome"),
                        "sql_normalizzato_ambito_regione":result.get(
                            "sql_normalizzato_ambito_regione"),
                        "sql_normalizzato_join_documentali":result.get(
                            "sql_normalizzato_join_documentali"),
                        "tag_auto_revision":result.get("tag_auto_revision"),
                        "errore_sql_iniziale":result.get("errore_sql_iniziale"),
                        "sql_iniziale_validata":result.get("sql_iniziale_validata"),
                        "strategia_tag":result.get("strategia_tag"),
                        "motivo_due_fasi":result.get("motivo_due_fasi"),
                        "sql_fase1":result.get("sql_fase1"),
                        "sql_fase2":result.get("sql_fase2"),
                        "documenti_fase1":result.get("documenti_fase1"),
                        "documenti_fase2":result.get("documenti_fase2"),
                        "coppie_documentate":result.get("coppie_documentate"),
                        "lotti_fase1":result.get("lotti_fase1"),
                        "lotti_fase1_validi":result.get("lotti_fase1_validi"),
                        "motivo_astensione":result.get("motivo_astensione"),
                        "asserzioni_verifica_proposte":result.get(
                            "asserzioni_verifica_proposte"),
                        "asserzioni_verifica_accettate":result.get(
                            "asserzioni_verifica_accettate"),
                        "asserzioni_verifica_respinte":result.get(
                            "asserzioni_verifica_respinte"),
                        "motivi_rifiuto_verifica":result.get(
                            "motivi_rifiuto_verifica"),
                        "dettagli_rifiuto_verifica":result.get(
                            "dettagli_rifiuto_verifica"),
                        "documenti_candidati_verifica":result.get(
                            "documenti_candidati_verifica"),
                        "codice_errore_due_fasi":result.get(
                            "codice_errore_due_fasi"),
                        "fase_errore_due_fasi":result.get(
                            "fase_errore_due_fasi"),
                        "tipo_errore_due_fasi":result.get(
                            "tipo_errore_due_fasi"),
                        "lotto_verifica_interrotto":result.get(
                            "lotto_verifica_interrotto"),
                        "lotti_verifica_finale":result.get(
                            "lotti_verifica_finale"),
                        "lotti_verifica_conclusi":result.get(
                            "lotti_verifica_conclusi"),
                        "lotti_verifica_non_validi":result.get(
                            "lotti_verifica_non_validi"),
                        "documenti_inviati_verifica":result.get(
                            "documenti_inviati_verifica"),
                        "documenti_senza_associazione_verificata":result.get(
                            "documenti_senza_associazione_verificata"),
                        "sql_controllo_copertura":result.get(
                            "sql_controllo_copertura"),
                        "documenti_controllo_copertura":result.get(
                            "documenti_controllo_copertura"),
                        "documenti_esclusi_primo_recupero":result.get(
                            "documenti_esclusi_primo_recupero"),
                        "controllo_copertura_eseguito":result.get(
                            "controllo_copertura_eseguito"),
                        "raffinamento_documentale_usato":result.get(
                            "raffinamento_documentale_usato"),
                        "raffinamento_documentale_incerto":result.get(
                            "raffinamento_documentale_incerto"),
                        "documenti_candidati_raffinamento":result.get(
                            "documenti_candidati_raffinamento"),
                        "documenti_selezionati_raffinamento":result.get(
                            "documenti_selezionati_raffinamento"),
                        "lotti_raffinamento":result.get("lotti_raffinamento"),
                        "lotti_raffinamento_completati":result.get(
                            "lotti_raffinamento_completati"),
                        "lotti_raffinamento_non_validi":result.get(
                            "lotti_raffinamento_non_validi"),
                        "chiamate_dirette_raffinamento":result.get(
                            "chiamate_dirette_raffinamento"),
                        "recupero_progressivo_usato":result.get("recupero_progressivo_usato"),
                        "piano_documentale_usato":result.get("piano_documentale_usato"),
                        "piano_documentale_centro":result.get("piano_documentale_centro"),
                        "piano_documentale_esito":result.get("piano_documentale_esito"),
                        "chiamate_piano_documentale":result.get("chiamate_piano_documentale"),
                        "sql_tentativi":result.get("sql_tentativi"),
                        "stato":result.get("stato"),
                        "codice_errore":result.get("codice_errore"),
                        "fase_errore":result.get("fase_errore"),
                        "tipo_errore":result.get("tipo_errore"),
                        "secondi":round(time.monotonic()-start,2),
                        "versione_tag":result.get("versione_tag"),
                        "verifica_contesto":result.get("verifica_contesto"),
                        "aic_nel_testo_integrale":result.get("aic_nel_testo_integrale"),
                        "revisione_completezza_llm":result.get("revisione_completezza_llm"),
                        "fallback_pagina_integrale":result.get("fallback_pagina_integrale"),
                        "modalita_selezione":result.get("modalita_selezione"),
                        "righe_recuperate":result.get("righe_recuperate"),
                        "righe_sem_filter":result.get("righe_sem_filter"),
                        "note_nell_indice":result.get("note_nell_indice"),
                        "note_nel_contesto":result.get("note_nel_contesto"),
                        "identificativi_sql_riconciliati":result.get(
                            "identificativi_sql_riconciliati"),
                        "chiamate_llm_stimate":result.get("chiamate_llm_stimate"),
                        "correzioni_sql":result.get("correzioni_sql"),
                        "sql_proposte":result.get("sql_proposte",[]),
                        "errori_sql_tentativi":result.get("errori_sql_tentativi",[]),
                        "chiamate_llm_effettive":result.get("chiamate_llm_effettive"),
                        "chiamate_llm_dirette":result.get("chiamate_llm_dirette"),
                        "chiamate_llm_lotus":result.get("chiamate_llm_lotus"),
                        "tempo_backend_s":result.get("tempo_backend_s"),
                        "sql_first_note_con_centro":result.get("sql_first_note_con_centro"),
                        "sql_first_note_preselezionate":result.get(
                            "sql_first_note_preselezionate"),
                        "diagnostica_revisione_categoria":result.get(
                            "diagnostica_revisione_categoria",[]),
                        "statistiche_revisione_categoria":result.get(
                            "statistiche_revisione_categoria",{}),
                        "versione_tag":result.get("versione_tag"),
                        "verifica_contesto":result.get("verifica_contesto"),
                        "aic_nel_testo_integrale":result.get("aic_nel_testo_integrale")})
        # Solo la finestra viene aggiornata: rimane aperta e scrivibile.
        st.rerun(scope="fragment")

    # Conserva integralmente risposte e dati tecnici nel JSON, ma tieni
    # il pulsante di download fuori dalla vista degli screenshot standard.
    try:
        _,snapshot_meta=_cached_snapshot(snapshot_version())
        snapshot_sha=snapshot_meta.get("sha256_sqlite")
    except (OSError,ValueError,TypeError,KeyError,sqlite3.DatabaseError):
        snapshot_sha=None
    complete={
        "esportazione_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modello":model,
        "snapshot_sha256":snapshot_sha,
        "base_dati":"copia statica FarmaQuery per i test",
        "metodi":[{
            "metodo":m,
            "etichetta":"Text-to-SQL" if m=="Text-to-SQL con auto-correzione" else "TAG",
            "messaggi":st.session_state.get(history_key(m),[])
        } for m in ("Text-to-SQL con auto-correzione","TAG automatico")]
    }
    with st.expander("Esporta risultati della tesi"):
        st.caption("Salva CSV e JSON prima di cliccare Nuova conversazione. "
                   "Contengono risposte integrali, fonti, SQL, tempi ed errori. "
                   "Il JSON è il riferimento per l'audit.")
        st.caption("Interfaccia: "+APP_UI_VERSION+" · Motori: Text-to-SQL con auto-correzione / TAG")
        col_csv,col_json=st.columns(2)
        with col_csv:
            st.download_button(
                "Scarica CSV",
                data=_full_results_csv(complete),
                file_name="farmaquery_risposte_complete.csv",
                mime="text/csv",
                key="farmaquery_export_full_csv",
                use_container_width=True
            )
        with col_json:
            st.download_button(
                "Scarica JSON",
                data=json.dumps(complete,ensure_ascii=False,indent=2,default=str),
                file_name="farmaquery_risposte_complete.json",
                mime="application/json",
                key="farmaquery_export_full_experiment",
                use_container_width=True
            )

    st.caption("Prototipo accademico: controlla le fonti prima di prendere "
               "decisioni cliniche.")


def render_assistant():
    # Il contenitore a posizione fissa contiene SOLO il pulsante. La chat
    # vera si apre nel dialog Streamlit (portal indipendente dal layout).
    st.markdown("""
    <style>
    /* Solo estetica: il dialog Streamlit rimane nativo e sempre editabile. */
    .st-key-farmaquery_floating {
        position:fixed!important;
        right:23px!important;
        bottom:70px!important;
        z-index:99999!important;
        width:92px!important;
        max-width:92px!important;
        padding:0!important;
    }
    .st-key-farmaquery_floating button {
        width:86px!important;
        min-width:86px!important;
        max-width:86px!important;
        height:86px!important;
        min-height:86px!important;
        border-radius:50%!important;
        padding:0!important;
        font-size:2rem!important;
        color:white!important;
        background:linear-gradient(145deg,#096f80,#13a28c)!important;
        border:3px solid #fff!important;
        box-shadow:0 10px 32px rgba(12,77,95,.28)!important;
    }
    .st-key-farmaquery_floating button:hover {
        background:linear-gradient(145deg,#075969,#0e8577)!important;
        box-shadow:0 12px 34px rgba(12,77,95,.35)!important;
        transform:translateY(-2px);
    }
    @media(max-width:650px) {
        .st-key-farmaquery_floating {
            right:12px!important;
            bottom:52px!important;
            width:79px!important;
            max-width:79px!important;
        }
        .st-key-farmaquery_floating button {
            width:75px!important;
            min-width:75px!important;
            max-width:75px!important;
            height:75px!important;
            min-height:75px!important;
        }
    }
    @media (prefers-reduced-motion:reduce) {
        .st-key-farmaquery_floating button:hover {transform:none;}
    }
    </style>
    """,unsafe_allow_html=True)
    with st.container(key="farmaquery_floating"):
        if st.button("💬",key="farmaquery_open_chat",
                     help="Apri assistente FarmaQuery"):
            assistant_dialog()
