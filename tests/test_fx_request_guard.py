import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from riskapp.fx_cache import FXRateCache, get_rates_cached
from riskapp.fx_service import FXError, RateSnapshot

TR = timezone(timedelta(hours=3))
def clock(y, m, d, h=18):
    return datetime(y,m,d,h,tzinfo=TR)
def snap(d=date(2026,11,20)):
    return RateSnapshot(d,{"TRY":Decimal("1"),"USD":Decimal("44"),"EUR":Decimal("51")},"ForexSelling", "https://www.tcmb.gov.tr/kurlar/202611/20112026.xml")

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache=FXRateCache(Path(self.tmp.name)/"riskapp_test.db")

    def test_weekend_cached_zero_requests(self):
        self.cache.save(snap())
        calls=[]
        result,src=get_rates_cached(self.cache,now=clock(2026,11,22),fetcher=lambda **kw: calls.append(1))
        self.assertEqual((result.published_date,src),(date(2026,11,20),"cache"))
        self.assertEqual(calls,[])

    def test_workday_current_cached_zero_requests(self):
        self.cache.save(snap())
        result,src=get_rates_cached(self.cache,now=clock(2026,11,20),fetcher=lambda **kw: self.fail("Ağ çağrısı olmamalı"))
        self.assertEqual(src,"cache")

    def test_failed_request_throttled_persistently(self):
        calls=[]
        def fail(**kw):
            calls.append(1)
            raise FXError("offline")
        with self.assertRaises(FXError):
            get_rates_cached(self.cache,now=clock(2026,11,23),fetcher=fail)
        with self.assertRaises(FXError):
            get_rates_cached(FXRateCache(self.cache.database_path),now=clock(2026,11,23,18),fetcher=fail)
        self.assertEqual(len(calls),1)

    def test_one_fetch_for_concurrent_requests(self):
        import threading, time
        calls=[]
        def fetch(**kw):
            calls.append(1)
            time.sleep(0.2)
            return snap(date(2026,11,23))
        def run(_):
            try:
                return get_rates_cached(FXRateCache(self.cache.database_path),now=clock(2026,11,23),fetcher=fetch)
            except FXError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(run,range(8)))
        self.assertEqual(len(calls),1)

    def test_historical_exact_hit_zero_requests(self):
        self.cache.save(snap())
        got,src=get_rates_cached(self.cache,day=date(2026,11,20),now=clock(2026,11,22),fetcher=lambda **kw:self.fail("Ağ yok"))
        self.assertEqual(src,"cache")

    def test_old_cache_no_silent_use(self):
        self.cache.save(snap())
        with self.assertRaises(FXError):
            get_rates_cached(self.cache,now=clock(2026,12,10),fetcher=lambda **kw: (_ for _ in ()).throw(FXError("offline")))

if __name__=="__main__":unittest.main()
