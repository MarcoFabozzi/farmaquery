import tempfile
import unittest
from pathlib import Path
from aifa_principi_attivi import principi_per_aic,arricchisci_confezioni

class PrincipiAifaTest(unittest.TestCase):
    def test_join_by_aic_and_multiple_actives(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'PA_confezioni.csv'
            path.write_text('CODICE_AIC;PRINCIPIO_ATTIVO\n051960019;Lecanemab\n001234567;Sostanza B\n001234567;Sostanza A\n001234567;Sostanza A\n',encoding='utf-8')
            active,rows=principi_per_aic(path)
            self.assertEqual(rows,4)
            self.assertEqual(active['001234567'],'Sostanza A; Sostanza B')
            packs={'051960019':{'principio_attivo':''},
                   '001234567':{'principio_attivo':''}}
            stats=arricchisci_confezioni(packs,active)
            self.assertEqual(stats['aic_con_principio'],2)
            self.assertEqual(packs['051960019']['principio_attivo'],'Lecanemab')
    def test_aic_con_oltre_20_sostanze_in_quarantena(self):
        # Caso reale segnalato dai log GitHub Actions, ma con sostanze
        # inventate per non dipendere dalla composizione del medicinale.
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'PA_confezioni.csv'
            righe=['CODICE_AIC;PRINCIPIO_ATTIVO']
            righe.extend(f'040716019;Componente di test {i}' for i in range(25))
            righe.extend(['051960019;Lecanemab',
                          '001234567;Sostanza B',
                          '001234567;Sostanza A'])
            path.write_text('\\n'.join(righe)+'\\n',encoding='utf-8')
            audit={}
            principi,righe_valide=principi_per_aic(path,audit=audit)
            self.assertEqual(righe_valide,28)
            self.assertNotIn('040716019',principi)
            self.assertEqual(principi['001234567'],'Sostanza A; Sostanza B')
            self.assertEqual(audit['aic_anomale_escluse'],1)
            self.assertEqual(audit['aic_anomale_con_numero_sostanze']['040716019'],25)
            confezioni={'040716019':{'principio_attivo':''},
                        '001234567':{'principio_attivo':''},
                        '051960019':{'principio_attivo':''}}
            esito=arricchisci_confezioni(confezioni,principi,min_copertura=0.6)
            self.assertEqual(esito['aic_con_principio'],2)
            self.assertEqual(confezioni['040716019']['principio_attivo'],'')

    def test_numerose_righe_duplicate_non_sono_un_anomalia(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'PA_confezioni.csv'
            path.write_text('CODICE_AIC;PRINCIPIO_ATTIVO\\n'+
                            '051960019;Lecanemab\\n'*35,encoding='utf-8')
            audit={}
            principi,righe_valide=principi_per_aic(path,audit=audit)
            self.assertEqual(righe_valide,35)
            self.assertEqual(principi['051960019'],'Lecanemab')
            self.assertEqual(audit['aic_anomale_escluse'],0)

    def test_reject_unexpected_columns(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'unexpected.csv'
            path.write_text('AIC;NOME\n051960019;Test\n',encoding='utf-8')
            with self.assertRaises(ValueError):
                principi_per_aic(path)
    def test_reject_low_coverage(self):
        with self.assertRaises(ValueError):
            arricchisci_confezioni({'001234567':{},'001234568':{}},{'001234567':'A'})
if __name__=='__main__':unittest.main()
