"""Regression guards for currency-aware risk list rendering (no Flask dependency)."""
from pathlib import Path
import re
import unittest
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'riskapp' / 'app.py').read_text(encoding='utf-8')
HTML = (ROOT / 'riskapp' / 'templates' / 'risk_select.html').read_text(encoding='utf-8')

class RiskListCurrencyTests(unittest.TestCase):
    def test_risk_list_no_try_only_filter(self):
        block = APP.split('    def risk_select():', 1)[1].split('    def risk_delete(', 1)[0]
        self.assertNotIn('CostItem.currency == "TRY"', block)
        self.assertIn('CostItem.currency,', block)
        self.assertIn('group_by(CostItem.risk_id, CostItem.currency)', block)
        self.assertIn('CostItem.project_id == pid', block)

    def test_preserves_all_pareto_modes(self):
        self.assertIn('currency_scope == "combined"', APP)
        self.assertIn('currency_scope == "original"', APP)
        self.assertIn('currency_scope == "automatic"', APP)

    def test_currency_separate_row_rendering(self):
        segment = HTML.split('                {% set amounts = ',1)[1].split('              </td>', 1)[0]
        tpl = Environment().from_string('{% set amounts = ' + segment)
        class Risk: id = 42
        result=tpl.render(cost_map={42:[('TRY',500),('USD',120),('EUR',30)]},r=Risk())
        self.assertRegex(result, r'500,00\s+₺')
        self.assertRegex(result, r'120,00\s+\$')
        self.assertRegex(result, r'30,00\s+€')
        self.assertNotIn('—',result)
        missing=tpl.render(cost_map={},r=Risk())
        self.assertIn('—',missing)

    def test_kpi_shows_separate_currency_totals(self):
        segment = HTML.split('          {% if cost_totals %}',1)[1].split('        </div>',1)[0]
        tpl=Environment().from_string('{% if cost_totals %}'+segment)
        result=tpl.render(cost_totals={'TRY':100,'USD':20,'EUR':40})
        self.assertIn('100,00',result)
        self.assertRegex(result, r'20,00\s+\$')
        self.assertRegex(result, r'40,00\s+€')

if __name__=='__main__':unittest.main()
