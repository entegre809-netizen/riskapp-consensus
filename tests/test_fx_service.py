import unittest
from datetime import date
from decimal import Decimal
from riskapp.fx_service import FXError, RateSnapshot, fetch_rates, historical_url, parse_tcmb_xml

XML = b'''<?xml version="1.0" encoding="utf-8"?>
<Tarih_Date Tarih="20.11.2026" Date="11/20/2026">
<Currency Kod="USD"><Unit>1</Unit><ForexBuying>43.90</ForexBuying><ForexSelling>44.00</ForexSelling></Currency>
<Currency Kod="EUR"><Unit>1</Unit><ForexBuying>50.90</ForexBuying><ForexSelling>51.00</ForexSelling></Currency>
</Tarih_Date>'''

class FXTests(unittest.TestCase):
    def test_conversion_cross(self):
        s = parse_tcmb_xml(XML, 'mock')
        self.assertEqual(s.convert('100', 'USD', 'TRY'), Decimal('4400'))
        self.assertEqual(s.convert('5100', 'TRY', 'EUR'), Decimal('100'))
        self.assertEqual(s.convert('51', 'EUR', 'USD'), Decimal('2601') / Decimal('44'))
        self.assertEqual(s.convert('123', 'USD', 'USD'), Decimal('123'))
    def test_buy_vs_sell(self):
        s = parse_tcmb_xml(XML, 'mock', 'ForexBuying')
        self.assertEqual(s.convert('100','USD','TRY'), Decimal('4390'))
    def test_no_silent_default(self):
        s = RateSnapshot(date(2026,11,20), {'TRY': Decimal('1')}, 'ForexSelling','mock')
        with self.assertRaises(FXError):
            s.convert('10', 'USD', 'TRY')
        with self.assertRaises(FXError):
            s.convert('NaN', 'TRY', 'USD')
    def test_historical_fallback(self):
        def downloader(url):
            if url.endswith('20112026.xml'):
                return XML
            raise OSError('not published')
        result = fetch_rates(date(2026,11,22), downloader=downloader)
        self.assertEqual(result.published_date, date(2026,11,20))
    def test_historical_url(self):
        self.assertEqual(historical_url(date(2026,11,20)), 'https://www.tcmb.gov.tr/kurlar/202611/20112026.xml')

if __name__ == '__main__':
    unittest.main()
