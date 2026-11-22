import tempfile
from contextlib import closing
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from riskapp.fx_cache import FXRateCache, get_rates_cached
from riskapp.fx_service import FXError, RateSnapshot


def snapshot(day=date(2026, 11, 20), typ="ForexSelling"):
    return RateSnapshot(day, {"TRY": Decimal("1"), "USD": Decimal("44"),
                              "EUR": Decimal("51")}, typ,
                        "https://www.tcmb.gov.tr/kurlar/202611/20112026.xml")


class FXCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "riskapp_test.db"
        self.cache = FXRateCache(self.path)

    def test_write_and_read_persists(self):
        self.cache.save(snapshot())
        new_instance = FXRateCache(self.path)
        loaded = new_instance.get(date(2026, 11, 22))
        self.assertEqual(loaded.convert("10", "USD", "TRY"), Decimal("440"))
        self.assertEqual(loaded.published_date, date(2026, 11, 20))

    def test_updates_same_day_no_duplicate(self):
        self.cache.save(snapshot())
        self.cache.save(snapshot())
        import sqlite3
        with closing(sqlite3.connect(self.path)) as con, con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM fx_rate_snapshots").fetchone()[0], 1)

    def test_cache_does_not_accept_ancient_rate(self):
        self.cache.save(snapshot())
        self.assertIsNone(self.cache.get(date(2026, 12, 10)))

    def test_buy_and_sell_separate(self):
        self.cache.save(snapshot())
        self.cache.save(snapshot(typ="ForexBuying"))
        self.assertEqual(self.cache.get(date(2026, 11, 22), rate_type="ForexBuying").rate_type, "ForexBuying")

    def test_online_saves_then_offline_fallback(self):
        online = lambda **kwargs: snapshot()
        result, source = get_rates_cached(self.cache, day=date(2026, 11, 22), fetcher=online)
        self.assertEqual(source, "tcmb")
        def offline(**kwargs):
            raise FXError("network down")
        result, source = get_rates_cached(self.cache, day=date(2026, 11, 22), fetcher=offline)
        self.assertEqual(source, "cache")
        self.assertEqual(result.published_date, date(2026, 11, 20))

    def test_fails_closed_without_cached_rate(self):
        with self.assertRaises(FXError):
            get_rates_cached(self.cache, day=date(2026, 11, 22),
                             fetcher=lambda **kwargs: (_ for _ in ()).throw(FXError("offline")))

    def test_never_modifies_other_tables(self):
        import sqlite3
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute("CREATE TABLE risks (id INTEGER PRIMARY KEY, name TEXT)")
            con.execute("INSERT INTO risks VALUES (31, 'sample')")
        self.cache.save(snapshot())
        with closing(sqlite3.connect(self.path)) as con, con:
            self.assertEqual(con.execute("SELECT id, name FROM risks").fetchone(), (31, "sample"))

    def test_rejects_fake_source(self):
        bad = RateSnapshot(date(2026, 11, 20), snapshot().try_per_unit,
                           "ForexSelling", "https://example.com")
        with self.assertRaises(FXError):
            self.cache.save(bad)

if __name__ == "__main__":
    unittest.main()
