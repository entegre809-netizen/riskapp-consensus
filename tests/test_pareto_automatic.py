"""Automatic multi-currency analysis regression tests."""
import unittest
from test_pareto_fx_step3 import ParetoFXTests, Cost, Query

class AutomaticCurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ParetoFXTests.setUpClass()
        cls.code = ParetoFXTests.code
    def setUp(self):
        ParetoFXTests.setUp(self)
        self.ns['request'].args['currency_scope'] = 'automatic'

    def test_three_independent_totals_and_zero_rate_requests(self):
        result=self.fn()
        self.assertEqual(result['currency_scope'],'automatic')
        self.assertEqual(len(self.rate_calls),0)
        self.assertEqual(result['groups']['TRY']['total'],175)
        self.assertEqual(result['groups']['USD']['total'],350)
        self.assertEqual(result['groups']['EUR']['total'],40)
        self.assertEqual(result['total'],175)
        self.assertEqual(result['groups']['USD']['cost_item_count'],1)

    def test_currency_switch_keeps_three_groups(self):
        self.ns['request'].args['currency']='USD'
        result=self.fn()
        self.assertEqual(result['currency'],'USD')
        self.assertEqual(result['total'],350)
        self.assertEqual(result['groups']['TRY']['total'],175)
        self.assertEqual(len(self.rate_calls),0)

    def test_same_risk_separates_per_currency(self):
        result=self.fn()
        self.assertEqual([it['risk_id'] for it in result['items']], [1])
        self.ns['request'].args['currency']='USD'
        usd=self.fn()
        self.assertEqual(usd['items'][0]['risk_id'],1)
        self.assertEqual(usd['items'][0]['cost_value'],100)

    def test_invalid_other_currency_fails_closed(self):
        self.cost_model.query=Query([Cost(1,1,50,'TRY'),Cost(2,1,5,'GBP')])
        result,status=self.fn()
        self.assertEqual(status,422)
        self.assertIn('desteklenmeyen para birimi',result['error'])

    def test_rpn_ignores_currency_and_rates(self):
        self.ns['request'].args['mode']='rpn'
        result=self.fn()
        self.assertEqual(result['mode'],'rpn')
        self.assertEqual(result['fx']['status'],'not_applicable')
        self.assertEqual(len(self.rate_calls),0)

    def test_default_combined_unchanged(self):
        self.ns['request'].args.pop('currency_scope')
        result=self.fn()
        self.assertEqual(result['currency_scope'],'combined')
        self.assertEqual(result['total'],17615)
        self.assertEqual(len(self.rate_calls),1)
