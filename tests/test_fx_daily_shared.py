import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from riskapp.fx_cache import FXRateCache, get_rates_cached
from riskapp.fx_service import RateSnapshot, FXError

TR=timezone(timedelta(hours=3))
def clock(d,h=18):return datetime.combine(d,datetime.min.time(),TR).replace(hour=h)
def snap(d):return RateSnapshot(d,{"TRY":Decimal("1"),"USD":Decimal("44"),"EUR":Decimal("51")},"ForexSelling", "https://www.tcmb.gov.tr/kurlar/today.xml")

class DailySharedTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.path=Path(t.name)/'fx.db';self.cache=FXRateCache(self.path)

    def test_same_day_many_users_one_request(self):
        calls=[]
        d=date(2026,11,23)
        def load(**kw):calls.append(1);return snap(d)
        for _ in range(12):
            get_rates_cached(FXRateCache(self.path),now=clock(d),fetcher=load)
        self.assertEqual(len(calls),1)

    def test_next_day_before_24h_no_request(self):
        calls=[]
        def load(**kw): calls.append(1);return snap(date(2026,11,23))
        get_rates_cached(self.cache,now=clock(date(2026,11,23),18),fetcher=load)
        get_rates_cached(self.cache,now=clock(date(2026,11,24),17),fetcher=load)
        self.assertEqual(len(calls),1)

    def test_after_24h_refresh_only_on_next_visit(self):
        calls=[]
        def load(**kw):
            calls.append(1)
            return snap(date(2026,11,23) if len(calls)==1 else date(2026,11,24))
        get_rates_cached(self.cache,now=clock(date(2026,11,23),18),fetcher=load)
        # No background work: no call until next get_rates_cached()
        self.assertEqual(len(calls),1)
        s,_=get_rates_cached(self.cache,now=clock(date(2026,11,24),19),fetcher=load)
        self.assertEqual(len(calls),2)
        self.assertEqual(s.published_date,date(2026,11,24))

    def test_idle_for_weeks_fetch_once_on_return(self):
        calls=[]
        def load(**kw):calls.append(1);return snap(date(2026,12,15) if len(calls)>1 else date(2026,11,23))
        get_rates_cached(self.cache,now=clock(date(2026,11,23)),fetcher=load)
        get_rates_cached(self.cache,now=clock(date(2026,12,15)),fetcher=load)
        get_rates_cached(FXRateCache(self.path),now=clock(date(2026,12,15)),fetcher=load)
        self.assertEqual(len(calls),2)

    def test_shared_between_workers(self):
        from time import sleep
        d=date(2026,11,23);calls=[];lock=Lock()
        def loader(**kw):
            with lock:calls.append(1)
            sleep(.12)
            return snap(d)
        def worker(_):
            try:return get_rates_cached(FXRateCache(self.path),now=clock(d),fetcher=loader)
            except FXError:return None
        with ThreadPoolExecutor(max_workers=8) as p:list(p.map(worker,range(8)))
        self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
