# Esecuzione controllata delle otto domande gold

**Snapshot bloccato:** run [41436480339](https://github.com/MarcoFabozzi/farmaquery/actions/runs/41436480339), acquisito il 2 novembre 2026, SHA-256 `bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`.  
**Gold validati:** `tesi/benchmark_regolatorio_8_validati.csv` (Q05, Q06, Q07, Q08, Q09, Q21, Q28, Q29).  
**Workflow:** `.github/workflows/tesi-pilota-8.yml`.

Il workflow su push e PR avvia soltanto **test e preflight offline** (zero API). Verifica l'hash completo dello SQLite, le otto domande, la presenza delle pagine citate e produce un'anteprima. Non cambia i motori né i gold.

## Esecuzione reale su Gemini (quando la quota è disponibile)

1. Nel repository andare in **Settings → Secrets and variables → Actions** e configurare `GEMINI_API_KEY` come secret, **mai** nel codice.
2. Aprire **Actions → Tesi - pilot 8 gold TAG vs Text-to-SQL → Run workflow**.
3. Selezionare **esegui_api = true**, prima **max_domande = 2**, e un modello LiteLLM Gemini disponibile per il proprio account. Il valore proposto `gemini/gemini-2.5-flash` è un esempio, non prova della disponibilità.
4. Controllare l'artefatto `tesi-pilota-8-risultati`: `risposte_grezze_8.csv` conserva le due risposte, SQL, fonti, tempi, errori, token e costi quando disponibili; `pilota_8_risultati_non_valutati.json` segnala stato e coppie realmente completate. **Nessun voto viene assegnato automaticamente.**
5. Quando il test sulle prime due domande funziona e la quota basta, ripetere con **max_domande = 8** come nuova esecuzione. Non unire file ottenuti con modelli o commit diversi.

Il runner usa `temperature=0`, ma un provider LLM può comunque produrre variazioni; le ripetizioni devono essere registrate separatamente e non si deve scegliere la risposta migliore a posteriori. Se compare QUOTA, annotare il tentativo non riuscito e ripetere solo dopo il ripristino della quota, senza considerarlo una risposta.

## Revisione umana
Per ogni coppia domanda/metodo verificare: tutti gli elementi richiesti, associazione clinica-indicazione, attribuzione dei centri, pagina corretta, relazioni tra note, date, falsi negativi e allucinazioni. Compilare `valutazione_risposta` e `valutazione_citazioni` (0/1) solo dopo confronto con il gold. Il file `risposte_da_revisionare_8.csv` contiene le risposte utilizzabili ma giudizi intenzionalmente vuoti.

Per il report dopo revisione (e **solo** con valutazioni manuali compilate):
```bash
python -m tesi.valuta_confronto \
  --benchmark tesi/benchmark_regolatorio_8_validati.csv \
  --risultati dist_tesi/risposte_da_revisionare_8.csv \
  --manifest dist_tesi/manifest_fonti_online.json \
  --out dist_tesi/metriche_8_revisionate.json
```

Lo script di valutazione non calcola accuracy quando non esistono giudizi. Le otto domande coprono solo INTERPRETAZIONE, TEMPORALE e RIMANDI e **non** rappresentano l'intera distribuzione delle 30 domande. L'esito della pipeline è una misura end-to-end, non una prova che i singoli operatori TAG siano superiori in ogni contesto.

### Limitazione sull'artefatto
L'artefatto dello snapshot scade secondo i criteri GitHub Actions. Prima della scadenza conservare una copia durevole del database e del manifesto; non rigenerare lo snapshot sostituendo silenziosamente quello utilizzato dai gold.
