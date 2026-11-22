"""Orijinal para birimi modunda izolasyon ve AI kapsam regresyon testi."""
import ast
import unittest
from pathlib import Path
from test_pareto_fx_step3 import ParetoFXTests, Cost, Query

class CurrencyScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ParetoFXTests.setUpClass()
        cls.code = ParetoFXTests.code

    def setUp(self):
        ParetoFXTests.setUp(self)
        self.ns['request'].args['currency_scope'] = 'original'

    def test_try_only_no_fx_request(self):
        data = self.fn()
        self.assertEqual(data['currency_scope'], 'original')
        self.assertEqual(data['cost_item_count'], 1)
        self.assertEqual(data['fx']['status'], 'original_only')
        self.assertEqual(data['fx']['converted_cost_count'], 0)
        self.assertEqual(len(self.rate_calls), 0)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['cost_value'], 50)
        self.assertEqual(data['items'][0]['value'], 175)

    def test_usd_only_no_fx_request(self):
        self.ns['request'].args['currency'] = 'USD'
        data = self.fn()
        self.assertEqual(len(self.rate_calls), 0)
        self.assertEqual(data['cost_item_count'], 1)
        self.assertEqual(data['items'][0]['cost_value'], 100)
        self.assertEqual(data['items'][0]['value'], 350)

    def test_eur_only_no_fx_request(self):
        self.ns['request'].args['currency'] = 'EUR'
        data = self.fn()
        self.assertEqual(len(self.rate_calls), 0)
        self.assertEqual(data['items'][0]['risk_id'], 2)
        self.assertEqual(data['items'][0]['cost_value'], 10)

    def test_combined_default_still_converts(self):
        self.ns['request'].args.pop('currency_scope')
        data = self.fn()
        self.assertEqual(len(self.rate_calls), 1)
        self.assertEqual(data['currency_scope'], 'combined')
        self.assertEqual(data['fx']['converted_cost_count'], 2)

    def test_invalid_scope_fails(self):
        self.ns['request'].args['currency_scope'] = 'unknown'
        data, status = self.fn()
        self.assertEqual(status, 400)
        self.assertIn('currency_scope', data['error'])

    def test_non_selected_bad_amount_ignored(self):
        self.cost_model.query = Query([Cost(1, 1, 'invalid', 'EUR'), Cost(2, 1, 50, 'TRY')])
        data = self.fn()
        self.assertEqual(data['items'][0]['cost_value'], 50)
        self.assertEqual(len(self.rate_calls), 0)

    def test_rpn_has_no_fx(self):
        self.ns['request'].args['mode'] = 'rpn'
        data = self.fn()
        self.assertEqual(data['fx']['status'], 'not_applicable')
        self.assertEqual(len(self.rate_calls), 0)

    def test_ai_passes_scope_and_filters_costs(self):
        source = (Path(__file__).parents[1] / 'riskapp' / 'app.py').read_text('utf-8')
        self.assertIn('currency_scope = (request.args.get("currency_scope")', source)
        self.assertIn('if currency_scope == "original" and source_ccy != currency:', source)
        self.assertIn('cache_key = (_get_active_project_id(), currency, mode, currency_scope,', source)

if __name__ == '__main__':
    unittest.main()
