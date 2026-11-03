"""Controlli metodologici senza dati reali o chiamate API."""
import unittest

from tesi.pilota_8_audit import IDS, consolidate

SNAP = "a" * 64

def record(id="Q05", method="TAG", status="OK", model="gemini/test-model"):
    return {"id": id, "metodo": method, "stato": status, "modello": model,
            "snapshot_sha256": SNAP, "valutazione_risposta": "",
            "valutazione_citazioni": "", "risposta": "test", "fonti": "",
            "secondi": "1.0"}


class AuditOttoGoldTests(unittest.TestCase):
    def test_coppie_e_assenza_di_accuracy_fittizia(self):
        clean, report = consolidate([record(), record(method="Text-to-SQL")], SNAP)
        self.assertEqual(report["coppie_complete"], 1)
        self.assertEqual(report["risposte_valide_non_valutate"], 2)
        self.assertEqual(len(report["mancanti"]), 14)
        self.assertIsNone(report["accuratezza"])
        self.assertIsNone(report["correttezza_citazioni"])
        self.assertEqual(len(clean), 2)

    def test_quota_non_diventa_risposta(self):
        clean, report = consolidate([record(status="QUOTA"), record()], SNAP)
        self.assertEqual(len(clean), 1)
        self.assertEqual(report["stati_tentativi"]["QUOTA"], 1)
        self.assertEqual(report["tentativi_ripetuti"]["Q05/TAG"], 2)

    def test_blocca_seconda_risposta_valida(self):
        with self.assertRaisesRegex(ValueError, "Due risposte"):
            consolidate([record(), record()], SNAP)

    def test_blocca_scatto_su_altro_snapshot(self):
        wrong = record()
        wrong["snapshot_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "Snapshot"):
            consolidate([wrong], SNAP)

    def test_blocca_modelli_diversi(self):
        with self.assertRaisesRegex(ValueError, "modelli"):
            consolidate([record(), record(method="Text-to-SQL",model="gemini/other")], SNAP)

    def test_blocca_voti_automatici(self):
        rated=record()
        rated["valutazione_risposta"]="1"
        with self.assertRaisesRegex(ValueError,"giudizi"):
            consolidate([rated], SNAP)

    def test_ids_fissi(self):
        self.assertEqual(IDS, ("Q05", "Q06", "Q07", "Q08",
                               "Q09", "Q21", "Q28", "Q29"))


if __name__ == "__main__":
    unittest.main()
