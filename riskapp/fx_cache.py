"""RiskApp TCMB ortak kur önbelleği (istek üzerine, 24 saatlik yenileme).

Yalnızca fx_rate_snapshots tablosu yaratır/değiştirir. Risk ve maliyet
kayıtlarını değiştirmez. SQLite dosya yolu uygulamadan açıkça verilmelidir.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import time
from urllib.error import HTTPError, URLError

from .fx_service import FXError, RateSnapshot, fetch_rates

RATE_TYPES = frozenset({"ForexBuying", "ForexSelling"})


class FXRateCache:
    def __init__(self, database_path: str | Path):
        if str(database_path).strip() in ("", ":memory:"):
            raise FXError("Kalıcı önbellek için gerçek bir SQLite dosyası gerekli")
        self.database_path = str(database_path)

    def _connect(self):
        # Dizini bilerek otomatik yaratmıyoruz; yanlış/ephemeral hedeflere sessiz yazmayalım.
        con = sqlite3.connect(self.database_path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        return con

    def initialize(self):
        with closing(self._connect()) as con, con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS fx_rate_snapshots (
                    published_date TEXT NOT NULL,
                    rate_type TEXT NOT NULL CHECK(rate_type IN ('ForexBuying','ForexSelling')),
                    usd_try TEXT NOT NULL,
                    eur_try TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (published_date, rate_type)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS fx_fetch_guard (
                    target_date TEXT NOT NULL,
                    rate_type TEXT NOT NULL,
                    next_attempt_epoch REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(target_date, rate_type)
                )
            """)

    def reserve_fetch(self, target: date, rate_type: str, now_epoch: float, lease_seconds: int = 180) -> bool:
        """Atomik SQLite rezervasyonu; farklı worker'lar aynı anda kur indirmez."""
        self.initialize()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT next_attempt_epoch FROM fx_fetch_guard WHERE target_date=? AND rate_type=?",
                (target.isoformat(), rate_type),
            ).fetchone()
            if row is not None and float(row[0]) > now_epoch:
                con.rollback()
                return False
            con.execute("""
                INSERT INTO fx_fetch_guard(target_date, rate_type, next_attempt_epoch) VALUES(?,?,?)
                ON CONFLICT(target_date, rate_type) DO UPDATE SET
                    next_attempt_epoch=excluded.next_attempt_epoch
            """, (target.isoformat(), rate_type, now_epoch + lease_seconds))
            con.commit()
            return True

    def has_guard(self, target: date, rate_type: str) -> bool:
        self.initialize()
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT 1 FROM fx_fetch_guard WHERE target_date=? AND rate_type=?",
                (target.isoformat(), rate_type),
            ).fetchone()
        return row is not None

    def set_retry_delay(self, target: date, rate_type: str, next_epoch: float):
        """Başarı/hata ardından en erken sonraki ağ denemesi (kalıcı)."""
        self.initialize()
        with closing(self._connect()) as con, con:
            con.execute("""
                INSERT INTO fx_fetch_guard(target_date, rate_type, next_attempt_epoch) VALUES(?,?,?)
                ON CONFLICT(target_date, rate_type) DO UPDATE SET
                    next_attempt_epoch=excluded.next_attempt_epoch
            """, (target.isoformat(), rate_type, next_epoch))

    @staticmethod
    def _validated(snapshot: RateSnapshot):
        if snapshot.rate_type not in RATE_TYPES:
            raise FXError("Geçersiz kur türü")
        if not isinstance(snapshot.published_date, date) or isinstance(snapshot.published_date, datetime):
            raise FXError("Geçersiz kur tarihi")
        if not str(snapshot.source_url).startswith("https://www.tcmb.gov.tr/kurlar/"):
            raise FXError("Yalnızca TCMB kaynaklı bülten saklanabilir")
        if snapshot.try_per_unit.get("TRY") != Decimal("1"):
            raise FXError("TRY temel kuru 1 olmalı")
        try:
            usd = Decimal(str(snapshot.try_per_unit["USD"]))
            eur = Decimal(str(snapshot.try_per_unit["EUR"]))
        except (KeyError, InvalidOperation) as exc:
            raise FXError("USD/EUR kuru eksik veya geçersiz") from exc
        if not usd.is_finite() or not eur.is_finite() or usd <= 0 or eur <= 0:
            raise FXError("USD/EUR kuru pozitif, sonlu olmalı")
        return str(usd), str(eur)

    def save(self, snapshot: RateSnapshot):
        usd, eur = self._validated(snapshot)
        self.initialize()
        with closing(self._connect()) as con, con:
            con.execute("""
                INSERT INTO fx_rate_snapshots
                    (published_date, rate_type, usd_try, eur_try, source_url)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(published_date, rate_type) DO UPDATE SET
                    usd_try=excluded.usd_try,
                    eur_try=excluded.eur_try,
                    source_url=excluded.source_url,
                    saved_at=CURRENT_TIMESTAMP
            """, (snapshot.published_date.isoformat(), snapshot.rate_type,
                  usd, eur, snapshot.source_url))

    def get(self, requested_day: date, *, rate_type: str = "ForexSelling", max_age_days: int = 7):
        """İstenen gün veya önceki <= max_age_days içindeki en yakın saklanan bülten."""
        if rate_type not in RATE_TYPES:
            raise FXError("Geçersiz kur türü")
        if not isinstance(requested_day, date) or isinstance(requested_day, datetime):
            raise FXError("Geçersiz sorgu tarihi")
        if not 0 <= max_age_days <= 14:
            raise FXError("Önbellek geriye bakış aralığı 0–14 gün olmalı")
        self.initialize()
        with closing(self._connect()) as con, con:
            row = con.execute("""
                SELECT published_date, rate_type, usd_try, eur_try, source_url
                FROM fx_rate_snapshots
                WHERE rate_type = ? AND published_date <= ?
                ORDER BY published_date DESC LIMIT 1
            """, (rate_type, requested_day.isoformat())).fetchone()
        if row is None:
            return None
        published = date.fromisoformat(row["published_date"])
        if (requested_day - published).days > max_age_days:
            return None
        result = RateSnapshot(
            published,
            {"TRY": Decimal("1"), "USD": Decimal(row["usd_try"]),
             "EUR": Decimal(row["eur_try"])},
            row["rate_type"], row["source_url"],
        )
        self._validated(result)
        return result


def _is_cache_current(cached: RateSnapshot, target: date, *, historical: bool, now_local: datetime) -> bool:
    """Yayımlanma takvimine göre gereksiz güncelleme isteklerini kes."""
    if historical:
        # Geçmiş iş günü: tam o günün bülteni; hafta sonu: önceki iş günü.
        if target.weekday() < 5:
            return cached.published_date == target
        return cached.published_date <= target and cached.published_date.weekday() < 5
    # Türkiye saati (UTC+03:00). İş günleri 16:00 öncesi dünkü son bülten geçerli olabilir.
    if target.weekday() >= 5:
        return cached.published_date <= target and cached.published_date.weekday() < 5
    if now_local.hour < 16:
        return cached.published_date <= target
    return cached.published_date == target


def get_rates_cached(
    cache: FXRateCache,
    day: date | None = None,
    *,
    rate_type: str = "ForexSelling",
    max_age_days: int = 7,
    fetcher=None,
    today: date | None = None,
    now: datetime | None = None,
):
    """İsteğe bağlı yenileme: ortak SQLite kaydı en fazla 24 saatte bir kontrol edilir.

    Arka plan görevi yoktur. İlk aktif kullanıcı isteğinde tek worker indirir;
    diğerleri doğrulanmış ortak önbelleği kullanır.
    Returns (RateSnapshot, 'tcmb' | 'cache').
    """
    if rate_type not in RATE_TYPES:
        raise FXError("Geçersiz kur türü")
    local_now = now or datetime.now(timezone(timedelta(hours=3)))
    if local_now.tzinfo is None:
        raise FXError("'now' saat dilimi içermeli")
    local_now = local_now.astimezone(timezone(timedelta(hours=3)))
    target = day if day is not None else (today or local_now.date())
    if not isinstance(target, date) or isinstance(target, datetime):
        raise FXError("Geçersiz sorgu tarihi")
    if target > (today or local_now.date()):
        raise FXError("Gelecek tarihli kur kullanılamaz")
    if not 0 <= max_age_days <= 14:
        raise FXError("Önbellek geriye bakış aralığı 0–14 gün olmalı")

    cached = cache.get(target, rate_type=rate_type, max_age_days=max_age_days)
    now_epoch = local_now.timestamp()

    # Geçmiş tarihli raporlar için bir kez alınmış kesin tarihli bülten kalıcıdır.
    if day is not None and cached and _is_cache_current(
        cached, target, historical=True, now_local=local_now
    ):
        return cached, "cache"

    # Güncel raporun 24 saatlik kontrol süresi tüm kullanıcılara/worker'lara ortaktır.
    # target_date'e değil sabit anahtara bağlanır: gece yarısı tekrar sorgu olmaz.
    guard_target = date(1970, 1, 1) if day is None else target
    # Önceki sürümün günlük bültenleri, henüz ilk 24-saatlik kontrol kaydı
    # oluşmamışsa da kullanılabilir (geçişte gereksiz indirme yapılmaz).
    if day is None and cached and _is_cache_current(
        cached, target, historical=False, now_local=local_now
    ) and not cache.has_guard(guard_target, rate_type):
        cache.set_retry_delay(guard_target, rate_type, now_epoch + 24 * 3600)
        return cached, "cache"

    if not cache.reserve_fetch(guard_target, rate_type, now_epoch):
        if cached:
            return cached, "cache"
        raise FXError("TCMB sorgusu sürüyor veya tekrar kontrol süresi dolmadı; kayıtlı geçerli kur yok")

    loader = fetcher or fetch_rates
    try:
        snapshot = loader(day=day, rate_type=rate_type, max_previous_days=max_age_days)
        if (snapshot.rate_type != rate_type or snapshot.published_date > target
                or (target - snapshot.published_date).days > max_age_days):
            raise FXError("TCMB bülteni istenen tarihe uygun değil")
        cache.save(snapshot)
    except (FXError, HTTPError, URLError, OSError, TimeoutError, sqlite3.Error) as exc:
        # Birbiri ardına başarısız API çağrılarının önüne geç.
        cache.set_retry_delay(guard_target, rate_type, now_epoch + 30 * 60)
        if cached is not None:
            return cached, "cache"
        raise FXError("TCMB erişimi başarısız; doğrulanmış kayıtlı kur yok (30 dk sorgu beklemesi)") from exc

    # Son başarılı kontrolün üzerinden 24 saat geçince, ancak yeni kullanıcı
    # isteği geldiğinde TCMB yeniden sorgulanabilir.
    cache.set_retry_delay(guard_target, rate_type, now_epoch + 24 * 3600 if day is None else now_epoch + 60 * 60)
    return snapshot, "tcmb"
