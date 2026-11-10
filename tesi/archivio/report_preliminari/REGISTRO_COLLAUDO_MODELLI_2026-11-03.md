# Registro delle revisioni del confronto — 3 novembre 2026

## Prima interrogazione reale (prova di sviluppo, NON benchmark finale)

Workflow GitHub Actions: **41636801742**, modello `gemini/gemini-3.5-flash-lite`, SHA-256 SQLite `f0e5e1935cc00b844996234e78756f61338aa95a70bebcfc8b256382b327a742`.

- **S1, PLUVICTO:** Text-to-SQL ha generato una sola SELECT e ottenuto **zero righe**. La SELECT filtrava `data_candidata='2025-04-18'` e non ha trovato corrispondenze. TAG ha recuperato le cinque strutture, il requisito Lutezio-177 e la scheda AIFA, con pagine del PDF.
- **S2, categorie neuromuscolari:** Text-to-SQL ha avuto un **errore tecnico in esecuzione SQL** (no retry, conforme alla baseline standard). TAG ha recuperato documenti utili, ma nella sintesi ha scritto erroneamente che la miastenia gravis non rientrerebbe strettamente nelle malattie neuromuscolari, pur riportando poi medicinali per MG nelle note a margine.

L'errore TAG è una **contraddizione clinica**: la miastenia gravis è una malattia della giunzione neuromuscolare. Riferimento scientifico: <https://medlineplus.gov/ency/article/000712.htm>; <https://www.ninds.nih.gov/sites/default/files/2025-05/myasthenia-gravis.pdf>.

## Correzione e controllo

La correzione riguarda **solo il prompt di sintesi delle categorie di TAG**, che deve distinguere la miastenia dalle patologie del sistema nervoso centrale, e non trasformare le categorie cliniche in relazioni autorizzative. Non sono state modificate le fonti, le tabelle o la baseline Text-to-SQL.

Queste prove fanno parte del **set di sviluppo** e non possono essere riutilizzate come stima indipendente della qualità del sistema dopo l'ottimizzazione. Il workflow finale verifica le **quattro tipologie** del relatore sul medesimo SQLite e conserva risposte grezze e citazioni, senza attribuire punteggi gold automaticamente.

Per la sperimentazione conclusiva occorrono domande di test non usate durante questa revisione, risposte gold verificate sui documenti e analisi di risposte, errori e costi.
