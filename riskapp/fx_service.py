"""TCMB kaynaklı TRY/USD/EUR kur dönüşüm çekirdeği.

Bu modül veritabanına yazmaz. URL yalnızca tcmb.gov.tr sabit adreslerinden
oluşturulur. Üretimde tarihli kalıcı önbellek sonraki entegrasyon adımıdır.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

SUPPORTED = frozenset({"TRY", "USD", "EUR"})
TCMB_TODAY = "https://www.tcmb.gov.tr/kurlar/today.xml"


class FXError(ValueError):
    """Kur eksik, geçersiz veya doğrulanamıyorsa yükseltilir."""


@dataclass(frozen=True)
class RateSnapshot:
    published_date: date
    try_per_unit: dict[str, Decimal]
    rate_type: str
    source_url: str

    def convert(self, amount: Decimal | str | int | float, source: str, target: str) -> Decimal:
        """Orijinal tutarı değiştirmeden hedef para birimine dönüştürür."""
        src, dst = source.upper().strip(), target.upper().strip()
        if src not in SUPPORTED or dst not in SUPPORTED:
            raise FXError(f"Desteklenmeyen para birimi: {src} / {dst}")
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError) as exc:
            raise FXError("Geçersiz maliyet tutarı") from exc
        if not value.is_finite():
            raise FXError("Sonsuz/NaN tutar kullanılamaz")
        if src == dst:
            return value
        try:
            src_rate = self.try_per_unit[src]
            dst_rate = self.try_per_unit[dst]
        except KeyError as exc:
            raise FXError(f"Eksik TCMB kuru: {exc.args[0]}") from exc
        if src_rate <= 0 or dst_rate <= 0:
            raise FXError("Kur sıfır veya negatif olamaz")
        return value * src_rate / dst_rate


def parse_tcmb_xml(data: bytes, source_url: str, rate_type: str = "ForexSelling") -> RateSnapshot:
    """Bülten tarihini XML'den alır; USD/EUR için döviz alış veya satışı okur."""
    if rate_type not in ("ForexBuying", "ForexSelling"):
        raise FXError("Kur tipi ForexBuying veya ForexSelling olmalı")
    try:
        root = ET.fromstring(data)
        date_text = root.attrib.get("Date", "").strip()
        published_date = datetime.strptime(date_text, "%m/%d/%Y").date()
    except (ET.ParseError, ValueError, TypeError) as exc:
        raise FXError("TCMB XML biçimi veya bülten tarihi geçersiz") from exc

    rates: dict[str, Decimal] = {"TRY": Decimal("1")}
    for item in root.findall("Currency"):
        code = (item.get("Kod") or item.get("CurrencyCode") or "").upper()
        if code not in ("USD", "EUR"):
            continue
        raw = (item.findtext(rate_type) or "").strip().replace(",", ".")
        try:
            unit = Decimal((item.findtext("Unit") or "1").strip())
            rate = Decimal(raw) / unit
        except (InvalidOperation, ZeroDivisionError) as exc:
            raise FXError(f"{code} için geçersiz {rate_type} kuru") from exc
        if not rate.is_finite() or rate <= 0:
            raise FXError(f"{code} kuru geçersiz")
        rates[code] = rate
    if "USD" not in rates or "EUR" not in rates:
        raise FXError("TCMB bülteninde USD veya EUR kuru eksik")
    return RateSnapshot(published_date, rates, rate_type, source_url)


def historical_url(day: date) -> str:
    return f"https://www.tcmb.gov.tr/kurlar/{day:%Y%m}/{day:%d%m%Y}.xml"


def _download_xml(url: str, timeout_seconds: int = 8) -> bytes:
    req = Request(url, headers={"User-Agent": "RiskApp-FX/1.0", "Accept": "application/xml,text/xml"})
    with urlopen(req, timeout=timeout_seconds) as response:
        data = response.read(512_001)
    if len(data) > 512_000:
        raise FXError("TCMB yanıtı beklenenden büyük")
    return data


def fetch_rates(
    day: date | None = None,
    *,
    rate_type: str = "ForexSelling",
    max_previous_days: int = 7,
    downloader=None,
) -> RateSnapshot:
    """Belli tarihin yayımlanmış kurunu al; tatilde geçmiş 7 güne kadar bak.

    day=None olduğunda today.xml okunur. Geçmiş sorgular için date
    parametresi ve resmî TCMB arşivi kullanılır. Otomatik canlı ağ çağrısı
    yapılması yalnızca bu fonksiyonun açıkça çağrılmasıyla gerçekleşir.
    """
    download = downloader or _download_xml
    if rate_type not in ("ForexBuying", "ForexSelling"):
        raise FXError("Geçersiz kur tipi")
    if day is None:
        try:
            return parse_tcmb_xml(download(TCMB_TODAY), TCMB_TODAY, rate_type)
        except (HTTPError, URLError, OSError, TimeoutError, ET.ParseError) as exc:
            raise FXError("Güncel TCMB kuruna erişilemedi") from exc
    if not isinstance(day, date) or isinstance(day, datetime):
        raise FXError("Tarih datetime.date olmalı")
    if day > date.today():
        raise FXError("Gelecek tarihe ait kur henüz yayımlanmadı")
    if not 0 <= max_previous_days <= 14:
        raise FXError("Geriye dönük arama aralığı 0–14 gün olmalı")
    for back in range(max_previous_days + 1):
        candidate = day - timedelta(days=back)
        url = historical_url(candidate)
        try:
            result = parse_tcmb_xml(download(url), url, rate_type)
            if result.published_date == candidate:
                return result
        except (HTTPError, URLError, OSError, TimeoutError, FXError):
            continue
    raise FXError(f"{day.isoformat()} için TCMB kuru bulunamadı (son {max_previous_days} gün kontrol edildi)")
