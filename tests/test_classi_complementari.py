import json
import tempfile
import unittest
from pathlib import Path

from classi_complementari import (
    costruisci_indice_cnn, leggi_indice_cnn, riferimenti_cnn,
    etichetta_cnn_storica, classe_con_fonti,
)


class ClassiComplementariTests(unittest.TestCase):
    def test_confronto_per_codice_base_e_nome(self):
        records = [{
            "nome": "FARMACO PROVA", "numero_procedura": f"EMEA/H/C/{i:06d}",
            "principio_attivo": "Molecola dimostrativa",
            "riferimento_atto": "https://www.aifa.gov.it/atto",
            "raw_json": json.dumps({"aic_farmaco": f"{i:06d}",
                                    "data_provvedimento": "2026-03-10"}),
        } for i in range(1000, 1110)]
        fonti = {"url": "https://www.aifa.gov.it/elenco-cnn.csv", "sha256": "a" * 64}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cnn.json"
            r = costruisci_indice_cnn(records, "2026-10-14", fonti, path)
            self.assertEqual(r["record_indicizzati"], 110)
            indice = leggi_indice_cnn(path)
            evid = riferimenti_cnn(indice, "001000019", "Farmaco Prova")
            self.assertEqual(len(evid), 1)
            self.assertEqual(etichetta_cnn_storica(evid),
                             "C(nn) (storica 14/10/2026)")
            self.assertEqual(riferimenti_cnn(indice, "001000019", "Farmaco Diverso"), [])
            self.assertEqual(riferimenti_cnn(indice, "001000"), [])
            self.assertEqual(riferimenti_cnn(indice, "001000999", "Farmaco Prova"), evid)

    def test_codici_cinque_cifre_e_priorita_a_h(self):
        records = [{
            "nome": "Medicinale X", "numero_procedura": f"EMEA/H/C/{i:06d}",
            "principio_attivo": "Sostanza X", "riferimento_atto": "",
            "raw_json": json.dumps({"aic_farmaco": str(i)}),
        } for i in range(20000, 20110)]
        fonti = {"url": "https://www.aifa.gov.it/cnn.csv", "sha256": "b" * 64}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cnn.json"
            costruisci_indice_cnn(records, "2026-10-14", fonti, path)
            matched = riferimenti_cnn(leggi_indice_cnn(path),
                                     "020000011", "Medicinale X")
            self.assertTrue(matched)
            self.assertEqual(classe_con_fonti("", ("H", "2026-06-30"), None, matched),
                             "H (lista 30/06/2026)")
            self.assertEqual(classe_con_fonti("", None, None, matched),
                             "C(nn) (storica 14/10/2026)")

    def test_c_da_provvedimento_verificato(self):
        event = {"classe_nuova": "C", "data_pubblicazione": "2023-05-16",
                 "fonte": "https://www.gazzettaufficiale.it/"}
        self.assertEqual(classe_con_fonti("", None, event, []),
                         "C (atto storico 16/05/2023)")
        self.assertEqual(classe_con_fonti("", ("A", "2026-06-30"), event, []),
                         "A (lista 30/06/2026)")
        self.assertEqual(classe_con_fonti("", None, None, []), "N/D")
        self.assertEqual(classe_con_fonti("C", None, None, []),
                         "C (anagrafica AIFA)")

    def test_rifiuta_json_alterato(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cnn.json"
            path.write_text(json.dumps({
                "schema": 1, "data_riferimento_file": "2026-10-14",
                "fonte": {"url": "https://example.com/false"},
                "per_codice_medicinale": {}
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                leggi_indice_cnn(path)


if __name__ == "__main__":
    unittest.main()
