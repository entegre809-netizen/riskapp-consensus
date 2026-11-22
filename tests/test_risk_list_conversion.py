"""Riskler page conversion regressions: read-only, per-risk, fail closed."""
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from jinja2 import Environment

from riskapp.fx_service import FXError, RateSnapshot
from riskapp.risk_list_fx import converted_risk_costs

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "riskapp" / "app.py").read_text(encoding="utf-8")
HTML = (ROOT / "riskapp" / "templates" / "risk_select.html").read_text(encoding="utf-8")

class RiskListConversionTests(unittest.TestCase):
    def setUp(self):
        self.rate = RateSnapshot(date(2026, 11, 20),
            {"TRY": Decimal("1"), "USD": Decimal("40"), "EUR": Decimal("50")},
            "ForexSelling", "https://www.tcmb.gov.tr/kurlar/today.xml")

    def test_mixed_costs_to_try_aggregated_by_risk(self):
        inputs = {1: [("USD", 10), ("EUR", 2), ("TRY", 100)], 2: [("USD", 5)]}
        output, total = converted_risk_costs(inputs, "TRY", self.rate)
        self.assertEqual(output[1], Decimal("600"))
        self.assertEqual(output[2], Decimal("200"))
        self.assertEqual(total, Decimal("800"))
        self.assertEqual(inputs[1][0], ("USD", 10))

    def test_try_to_usd_and_eur(self):
        inputs = {1: [("TRY", 200), ("EUR", 2), ("USD", 1)]}
        a, _ = converted_risk_costs(inputs, "USD", self.rate)
        b, _ = converted_risk_costs(inputs, "EUR", self.rate)
        self.assertEqual(a[1], Decimal("8.5"))
        self.assertEqual(b[1], Decimal("6.8"))

    def test_invalid_currency_fails_whole_conversion(self):
        with self.assertRaises(FXError):
            converted_risk_costs({1: [("TRY", 100)], 2: [("GBP", 30)]}, "USD", self.rate)

    def test_nan_fails_whole_conversion(self):
        with self.assertRaises(FXError):
            converted_risk_costs({1: [("TRY", 100)], 2: [("USD", float('nan'))]}, "TRY", self.rate)

    def test_original_default_and_cache_shared(self):
        route = APP.split('    def risk_select():', 1)[1].split('    def risk_delete(', 1)[0]
        self.assertIn('or "original"', route)
        self.assertIn('get_rates_cached(', route)
        self.assertIn('FXRateCache(db.engine.url.database)', route)
        self.assertIn('if needs_conversion:', route)
        self.assertIn('converted_cost_map = {}', route)

    def test_all_three_pareto_modes_preserved(self):
        self.assertIn('currency_scope == "combined"', APP)
        self.assertIn('currency_scope == "original"', APP)
        self.assertIn('currency_scope == "automatic"', APP)

    def test_jinja_template_parses_and_selector_exists(self):
        Environment().parse(HTML)
        self.assertIn('name="display_currency"', HTML)
        self.assertIn('Orijinal para birimi', HTML)
        self.assertIn('TRY (₺) karşılığı', HTML)
        self.assertIn('Döviz dönüşümü şu an yapılamadı', HTML)

    def test_row_shows_original_below_converted(self):
        # Isolate the cost cell: verify both converted and source amounts.
        section = HTML.split('                {% set amounts = ', 1)[1].split('              </td>', 1)[0]
        tpl = Environment().from_string('{% set amounts = ' + section)
        class Risk: id = 42
        out = tpl.render(cost_map={42: [('TRY', 100), ('USD', 20)]}, r=Risk(),
            display_currency='TRY', converted_cost_map={42: Decimal('900')},
            converted_cost_total=Decimal('900'))
        self.assertIn('900,00', out)
        self.assertIn('100,00 TRY', out)
        self.assertIn('20,00 USD', out)
        old = tpl.render(cost_map={42: [('USD', 20)]}, r=Risk(),
            display_currency='ORIGINAL', converted_cost_total=None)
        self.assertIn('20,00', old)
        self.assertIn('$', old)

if __name__ == '__main__': unittest.main()
