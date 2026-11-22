"""Adım 3 regresyon kontrolleri: uç nokta çekirdeğini izole koşullarda çalıştırır."""
import ast
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from riskapp.fx_service import FXError, RateSnapshot

class Query:
    def __init__(self, items): self.items = items
    def filter(self, *args): return self
    def all(self): return self.items

class Risk:
    project_id = 1
    def __init__(self, ident, p=3.5, s=4):
        self.id=ident;self.title=f"Risk {ident}";self.category="DENEME";self.responsible="Test";self.p=p;self.s=s
    def avg_prob(self): return self.p
    def avg_sev(self): return self.s
    def score(self): return self.p*self.s

class Cost:
    project_id=1
    def __init__(self, ident, rid, amount, currency):
        self.id=ident;self.risk_id=rid;self.total=amount;self.currency=currency

class MockApp:
    def get(self,*args,**kwargs): return lambda fn:fn

class ParetoFXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(Path(__file__).parents[1]/"riskapp"/"app.py").read_text(encoding="utf-8")
        tree=ast.parse(source)
        create=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="create_app")
        endpoint=next(n for n in create.body if isinstance(n,ast.FunctionDef) and n.name=="pareto_cost")
        endpoint.decorator_list=[]
        cls.code=compile(ast.Module(body=[endpoint],type_ignores=[]),"pareto_isolated.py","exec")

    def setUp(self):
        self.risks=[Risk(1),Risk(2,p=4)]
        self.costs=[Cost(1,1,"100", "USD"), Cost(2,1,"50","TRY"), Cost(3,2,"10","EUR")]
        self.risk_model=SimpleNamespace(query=Query(self.risks),project_id=1)
        self.cost_model=SimpleNamespace(query=Query(self.costs),project_id=1)
        self.rate_calls=[]
        self.network_error=False
        self.snapshot=RateSnapshot(date(2026,11,20), {"TRY":Decimal(1),"USD":Decimal(44),"EUR":Decimal(51)},"ForexSelling","https://www.tcmb.gov.tr/kurlar/today.xml")
        def rates(*args,**kwargs):
            self.rate_calls.append(kwargs)
            if self.network_error: raise FXError("Ağ yok")
            return self.snapshot,"tcmb"
        ns={"_get_active_project_id":lambda: 1,"request":SimpleNamespace(args={"currency":"TRY"}),
            "Risk":self.risk_model,"CostItem":self.cost_model,"defaultdict":defaultdict,
            "Decimal":Decimal,"InvalidOperation":InvalidOperation,"date":date,"sqlite3":sqlite3,
            "FXError":FXError,"FXRateCache":lambda path:path,"get_rates_cached":rates,
            "db":SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"),url=SimpleNamespace(database="/tmp/example.db"))),
            "jsonify":lambda data:data}
        exec(self.code,ns)
        self.fn=ns["pareto_cost"]
        self.ns=ns

    def test_mixed_currencies_all_included(self):
        obj=self.fn()
        self.assertEqual(obj["cost_item_count"],3)
        self.assertEqual(obj["fx"]["converted_cost_count"],2)
        costs={x["risk_id"]:x["cost_value"] for x in obj["items"]}
        self.assertEqual(costs,{1:4450,2:510})
        scores={x["risk_id"]:x["value"] for x in obj["items"]}
        self.assertEqual(scores,{1:15575,2:2040})
        self.assertEqual(obj["fx"]["published_date"],"2026-11-20")

    def test_usd_output_cross_conversion(self):
        self.ns["request"].args["currency"]="USD"
        obj=self.fn()
        costs={x["risk_id"]:x["cost_value"] for x in obj["items"]}
        self.assertAlmostEqual(costs[1],101.14,2)
        self.assertAlmostEqual(costs[2],11.59,2)

    def test_failure_does_not_return_partial_pareto(self):
        self.network_error=True
        obj,status=self.fn()
        self.assertEqual(status,503)
        self.assertIn("Döviz kuru alınamadı",obj["error"])

    def test_rpn_does_not_download_rates(self):
        self.ns["request"].args["mode"]="rpn"
        obj=self.fn()
        self.assertEqual(obj["fx"]["status"],"not_applicable")
        self.assertEqual(len(self.rate_calls),0)

    def test_same_currency_does_not_download_rates(self):
        self.cost_model.query=Query([Cost(1,1,50,"TRY")])
        obj=self.fn()
        self.assertEqual(obj["fx"]["status"],"not_required")
        self.assertEqual(len(self.rate_calls),0)

    def test_unsupported_currency_fails_closed(self):
        self.cost_model.query=Query([Cost(1,1,10,"GBP")])
        obj,status=self.fn()
        self.assertEqual(status,422)

if __name__=="__main__": unittest.main()
