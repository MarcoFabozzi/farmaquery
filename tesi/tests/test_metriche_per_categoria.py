"""Regressioni report sperimentale: medie reali e punteggi manuali."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from tesi.valuta_confronto import evaluate


class MetricsReportTests(unittest.TestCase):
    def test_tabella_categorie_con_valori_e_assenze(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            gold=root/"gold.csv"
            pred=root/"pred.csv"
            manifest=root/"manifest.json"
            snapshot="a"*64
            manifest.write_text(json.dumps({"sha256_sqlite":snapshot}))
            gfields=["id","categoria","domanda","risposta_gold","fonti_gold",
                     "stato_validazione","note_revisore","elementi_gold",
                     "snapshot_sha256"]
            records=[
                {"id":"r1","categoria":"RELAZIONALI","elementi_gold":"A|B"},
                {"id":"a1","categoria":"ASSENZA_DOCUMENTALE","elementi_gold":""},
            ]
            with gold.open("w",encoding="utf-8",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=gfields,delimiter=";")
                writer.writeheader()
                for x in records:
                    writer.writerow({**{"domanda":"Domanda di esempio",
                                       "risposta_gold":"Risposta di riferimento",
                                       "fonti_gold":"file.pdf#p1",
                                       "stato_validazione":"VALIDATO",
                                       "note_revisore":"Conferma umana","snapshot_sha256":snapshot},
                                     **x})
            pfields=["id","metodo","modello","snapshot_sha256","risposta",
                     "fonti","secondi","token_input","token_output","costo_usd",
                     "valutazione_risposta","valutazione_citazioni","note_revisore",
                     "chiamate_llm_effettive","elementi_predetti",
                     "valutazione_astensione","errore_tecnico",
                     "citazioni_corrette_n","citazioni_verificate_n"]
            with pred.open("w",encoding="utf-8",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=pfields,delimiter=";")
                writer.writeheader()
                for method in ("TAG","Text-to-SQL"):
                    for q in ("r1","a1"):
                        writer.writerow({
                            "id":q,"metodo":method,"modello":"mock",
                            "snapshot_sha256":snapshot,
                            "risposta":"una risposta","fonti":"file.pdf#p1",
                            "secondi":"2" if method=="TAG" else "1",
                            "token_input":"4","token_output":"5","costo_usd":"0.001",
                            "valutazione_risposta":"1" if method=="TAG" else "0",
                            "valutazione_citazioni":"1",
                            "note_revisore":"Controllata manualmente",
                            "chiamate_llm_effettive":"3" if method=="TAG" else "2",
                            "elementi_predetti":("A|B" if method=="TAG" else "A")
                                if q=="r1" else "",
                            "valutazione_astensione":"1" if q=="a1" and method=="TAG"
                                else ("0" if q=="a1" else ""),
                            "errore_tecnico":"0","citazioni_corrette_n":"1",
                            "citazioni_verificate_n":"1"})
            report=evaluate(gold,pred,manifest)
        self.assertEqual(report["domande_con_entrambe_le_risposte"],2)
        self.assertEqual(report["metodi"]["TAG"]["chiamate_llm_medie"],3)
        self.assertEqual(report["metodi"]["Text-to-SQL"]["chiamate_llm_medie"],2)
        self.assertEqual(report["metodi"]["TAG"]["precision_micro"],1)
        self.assertEqual(report["metodi"]["TAG"]["recall_micro"],1)
        self.assertEqual(report["metodi"]["Text-to-SQL"]["recall_micro"],0.5)
        self.assertEqual(report["metodi"]["TAG"]["accuratezza_astensione"],1)
        self.assertEqual(len(report["tabella_categorie"]),2)
        row=next(x for x in report["tabella_categorie"]
                 if x["categoria"]=="RELAZIONALI")
        self.assertEqual(row["TAG_accuratezza"],1)
        self.assertEqual(row["Text_to_SQL_accuratezza"],0)

    def test_senza_annotazioni_non_inventa_f1_o_chiamate(self):
        from tesi.valuta_confronto import _micro_list_metrics
        self.assertIsNone(_micro_list_metrics([{"id":"x"}],
            {"x":{"elementi_gold":"A"}})["f1_micro"])


if __name__=="__main__":
    unittest.main()
