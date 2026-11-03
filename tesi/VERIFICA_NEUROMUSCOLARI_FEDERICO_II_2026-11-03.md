# Verifica documentale: medicinali neuromuscolari e AOU Federico II

**Data del controllo:** 3 novembre 2026  
**Snapshot:** `bb43ae4b00b6d581f4209ad83cbf9945054628868e6a52c59470ad32cada9a53`  
**Stato:** riferimento documentale **provvisorio**, non attestazione di esaustività assoluta né di abilitazione operativa attuale.

## Metodo

È stato esaminato lo snapshot delle **380 note regionali**. Una ricerca lessicale ampia su patologie e Federico II ha selezionato **25 PDF candidati**; un esame più mirato ne aveva individuati 14. Sono stati recuperati e verificati per SHA-256 **27 PDF originali** dagli archivi ZIP ufficiali della Regione Campania (annate 2022–2026); la verifica puntuale delle pagine distingue l'indicazione clinica dalla tabella dei centri.

La definizione *core* comprende malattie di nervi periferici, motoneuroni, muscolo scheletrico e giunzione neuromuscolare, in linea con i gruppi della rete [EURO-NMD](https://ern-euro-nmd.eu/groups/disease/). Il perimetro *esteso* aggiunge l'atassia di Friedreich, classificata anche tra le malattie neuromuscolari dalla [Muscular Dystrophy Association](https://www.mda.org/disease/friedreichs-ataxia). Questa scelta va dichiarata nel protocollo sperimentale.

## Medicinali con evidenze documentali positive

| Medicinale | Patologia e indicazione sintetica | Documento e pagine | Perimetro |
|---|---|---|---|
| **EVRYSDI** | Atrofia muscolare spinale 5q | `EVRYSDI 2025.pdf`, p. 1 indicazione; p. 2 centro | core |
| **AGAMREE** | Distrofia muscolare di Duchenne | `AGAMREE  Prot.N.0663946-2026.pdf`, p. 1 indicazione; p. 2 centro | core |
| **DUVYZAT** | Distrofia muscolare di Duchenne | `DUVYZAT  Prot.N.0368583-2026.pdf`, p. 1 indicazione; p. 2 centro | core |
| **ULTOMIRIS** | Miastenia gravis generalizzata | `ULTOMIRIS neurolielite e miastenia.pdf`, p. 1 indicazione; p. 3 centro | core |
| **SOLIRIS** | Miastenia gravis generalizzata refrattaria | `SOLIRIS.pdf`, p. 1 indicazione; p. 4 centro | core |
| **ZILBRYSQ** | Miastenia gravis generalizzata | `ZILBRYSQ.pdf`, p. 1 indicazione; p. 2 centro | core |
| **VYVGART** | Miastenia gravis generalizzata | `VYVGART.pdf`, p. 1 indicazione; p. 3 centro | core |
| **KIOVIG** | Poliradicoloneuropatia demielinizzante infiammatoria cronica (CIDP) | `KIOVIG.pdf`, p. 1 indicazione; p. 2 centro | core |
| **HYQVIA** | Polineuropatia demielinizzante infiammatoria cronica (CIDP) | `HYQVIA CIDP.pdf`, p. 1 indicazione; p. 2 centro | core |
| **HIZENTRA** | Polineuropatia demielinizzante infiammatoria cronica (CIDP) | `HYQVIA CIDP.pdf`, p. 2 | core |
| **GAMTEN** | Dermatomiosite in fase attiva | `GAMTEN.pdf`, p. 1 indicazione; p. 2 centro | core |
| **AMVUTTRA** | Polineuropatia ereditaria da transtiretina (hATTR) | `AMVUTTRA Prot.N.0634617-2026.pdf`, p. 1 indicazione; p. 3 centro | core |
| **WAINZUA** | Neuropatia ereditaria da transtiretina (ATTRv) | `WAINZUA  Prot.N.0664045-2026.pdf`, p. 1 indicazione; p. 2 centro | core |
| **SKYCLARYS** | Atassia di Friedreich | `SKYCLARYS  Prot.N.0143659-2026.pdf`, p. 1 indicazione; p. 2 centro | esteso |

**Attenzione a quattro associazioni fra indicazione e centri:**

- **ULTOMIRIS:** la tabella di pagina **2** riguarda la neuromielite ottica NMOSD; per miastenia gravis generalizzata la tabella corretta è quella di pagina **3**. Non trasferire una struttura da una tabella all'altra.
- **AMVUTTRA:** la pagina **2** riguarda la cardiomiopatia ATTR-CM, mentre il gruppo neuropatie ereditarie con Federico II è alla pagina **3**.
- **VYVGART:** distinguere l'indicazione generale di terapia aggiuntiva per gMG AChR-positiva dai criteri/registri descritti nella nota regionale, che qualificano la relativa tabella come gMG refrattaria.
- **HIZENTRA:** non è una nuova nota autonoma nell'elenco: la pagina **2** della nota HYQVIA dichiara l'aggiornamento dei centri HIZENTRA per CIDP sulla stessa ricognizione codice RF0180.

## Riscontri specifici KIOVIG e HYQVIA

**KIOVIG** — Nota del **16/09/2022**, PDF `PTR_Note regionali 2022/KIOVIG.pdf`, SHA-256 `1d8148dd7a76efe28e367418df0578e67dc5d5ce44309d006ae9d78cfeadd771`. L'immunomodulazione per CIDP è descritta a pagina **1**; pagina **2** autorizza i presidi RF0180 e riporta **AOU Federico II, Napoli**, DAI Materno Infantile e DAI Testa Collo – Neurologia/Centro per epilessia.

**HYQVIA** — Nota **PG/2025/0151508 del 25/03/2025**, PDF `note 2025 - 18.12.2025/HYQVIA CIDP.pdf`, SHA-256 `dfb6231803b1b1a669785f27fb0470180c466f73103e44c2d6558fc1bb8f4f01`. La pagina **1** riguarda la terapia di mantenimento della CIDP dopo stabilizzazione con IVIg; la pagina **2** riporta Federico II fra i presidi codice RF0180 e aggiorna espressamente i centri HIZENTRA.

Entrambi i casi sono pertanto **documentati sul PDF originale**: non sono inferenze ricavate dalla sola co-occorrenza del nome di un ospedale e di una malattia.

## Casi non pertinenti e duplicati

Il semplice ritrovamento di Federico II nel documento non basta. Fra le esclusioni esaminate: **ALHEMO** (emofilia), **BEYONTTRA** e **CAMZYOS** (indicazioni cardiache), **MYALEPTA** (lipodistrofia), **FINTEPLA** (sindrome di Dravet), **FILSUVEZ** (epidermolisi bollosa), **IMFINZI/OPDIVO** (indicazioni oncologiche), **PROCYSBI** (cistinosi) e **VOXZOGO** (acondroplasia). Le note aggiuntive su SOLIRIS pediatrico, VYVGART sottocutaneo e AMVUTTRA 2023 non sono conteggiate come medicinali distinti.

## Implicazioni per il confronto sperimentale

Con questo criterio sono supportate **13 voci core** e **14 con Friedreich**. Le ultime prove conversazionali avevano restituito **7 medicinali con TAG** e **4 con Text-to-SQL**: tali misure sono **esplorative**, non punteggi definitivi, perché i motori sono stati modificati fra una prova e l'altra.

Prima del benchmark definitivo occorre fissare: 1) tassonomia e politica HIZENTRA; 2) versione del codice e snapshot; 3) risposte gold e riferimenti di pagina; 4) criteri distinti per recupero, correttezza della specifica indicazione, associazione al centro, completezza, citazioni e latenza.

## Archivi ufficiali e integrità

- **2022:** [ZIP ufficiale Regione Campania](https://www.regione.campania.it/assets/documents/ptr-note-regionali-2022.zip) — SHA-256 `7a4d07d0e102102c6acfdc8e4120dffec5098a4980330176b1bd62b5477e77aa`
- **2023:** [ZIP ufficiale Regione Campania](https://www.regione.campania.it/assets/documents/ptr-noteregionali2023-020124-x01day5s6s08qz9q.zip) — SHA-256 `a26441de5468e2f1159345b572caf5cfcd9fbc12f29be0294a1e69cf770b1716`
- **2024:** [ZIP ufficiale Regione Campania](https://www.regione.campania.it/assets/documents/ptr-note-regionali-11-12-24-ore-16-40.zip) — SHA-256 `c17b3d9dd54f70438c443c4b960be10abbce33b8ef42d929f64c4333884f2f9a`
- **2025:** [ZIP ufficiale Regione Campania](https://www.regione.campania.it/sites/default/files/2025-12/note%202025%20-%2018.12.2025.zip) — SHA-256 `d11f06be1acd94b4b20c0d2059553cb7b47837f4a8c6368fca01d8721fdd8806`
- **2026:** [ZIP ufficiale Regione Campania](https://www.regione.campania.it/sites/default/files/2026-09/note-regionali-2026%2022.09.2026.zip) — SHA-256 `92e64fd5c897cf794f8c4e7f125542151dfef7bc9c1a9058f969dea855268097`

Le impronte dei singoli PDF, i percorsi interni allo ZIP, le pagine e i 14 casi sono raccolti nel file associato [riferimento_neuromuscolari_federico_ii_2026-11-03.json](riferimento_neuromuscolari_federico_ii_2026-11-03.json).

**Limite dichiarato:** lo screening è sensibile alle espressioni presenti nei testi OCR. L'insieme non va descritto come definitivamente esaustivo senza revisione delle possibili omissioni e approvazione del criterio clinico da parte del relatore.
