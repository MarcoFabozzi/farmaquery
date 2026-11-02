"""Tests for reading complete source sections."""
import unittest
from tesi.recupero_integrale import PAGE_REQUEST, GU_CODE

class SectionTests(unittest.TestCase):
    def test_page(self):
        self.assertEqual(PAGE_REQUEST.search('pagina 2').group(1), '2')
    def test_act(self):
        self.assertEqual(GU_CODE.search('23A02767').group(), '23A02767')
