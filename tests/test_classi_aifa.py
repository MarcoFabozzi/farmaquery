import json
import tempfile
import unittest
from pathlib import Path

from classi_aifa import costruisci_indice, leggi_indice, etichetta_classe


class ClassiAifaTests(unittest.TestCase):
    def setUp(self):
        self.a = {f'{n:09d}' for n in range(1000, 2300)}
        self.h = {f'{n:09d}' for n in range(3000, 3150)}
        self.fonti = {
            'aifa_a': {'url': 'https://www.aifa.gov.it/test_a.csv', 'sha256': 'a' * 64},
            'aifa_h': {'url': 'https://www.aifa.gov.it/test_h.csv', 'sha256': 'b' * 64},
        }

    def test_tutte_le_aic_e_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'indice.json'
            info = costruisci_indice({'A': self.a, 'H': self.h},
                                     '2026-06-30', self.fonti, target)
            self.assertEqual(info['aic_indicizzate'], 1450)
            indice = leggi_indice(target)
            self.assertEqual(etichetta_classe(indice, '000001001'),
                             'A (lista 30/06/2026)')
            self.assertEqual(etichetta_classe(indice, '000003001'),
                             'H (lista 30/06/2026)')
            self.assertEqual(etichetta_classe(indice, '000008000'), 'N/D')

    def test_rifiuta_aic_doppia(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                costruisci_indice({'A': self.a, 'H': self.h | {'000001001'}},
                                 '2026-06-30', self.fonti, Path(tmp) / 'x.json')

    def test_rifiuta_manomissione(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'x.json'
            costruisci_indice({'A': self.a, 'H': self.h},
                             '2026-06-30', self.fonti, target)
            obj = json.loads(target.read_text(encoding='utf-8'))
            obj['classi']['000001001'] = 'C'
            target.write_text(json.dumps(obj), encoding='utf-8')
            with self.assertRaises(ValueError):
                leggi_indice(target)


if __name__ == '__main__':
    unittest.main()
