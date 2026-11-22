"""Risk listesi icin salt-okunur para birimi gorunumu.

Maliyet kayitlarini ASLA degistirmez. Her riskin mevcut para birimi
kumesini, tek bir secilmis goruntuleme birimine cevirir.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from .fx_service import FXError

SUPPORTED = frozenset(("TRY", "USD", "EUR"))


def converted_risk_costs(cost_map, target_currency, snapshot):
    """Return ({risk_id: Decimal sum}, Decimal grand total).

    Fail whole conversion for unsupported/invalid inputs; no partial totals.
    The original cost_map remains unchanged.
    """
    target = str(target_currency).upper().strip()
    if target not in SUPPORTED:
        raise FXError(f"Desteklenmeyen hedef para birimi: {target}")
    totals_by_risk = {}
    total = Decimal("0")
    for risk_id, entries in cost_map.items():
        subtotal = Decimal("0")
        for currency, amount in entries:
            source = str(currency).upper().strip()
            if source not in SUPPORTED:
                raise FXError(f"Desteklenmeyen kaynak para birimi: {source}")
            try:
                value = Decimal(str(amount))
            except (ValueError, TypeError, InvalidOperation) as exc:
                raise FXError("Geçersiz maliyet tutarı") from exc
            if not value.is_finite():
                raise FXError("Geçersiz maliyet tutarı")
            subtotal += snapshot.convert(value, source, target) if source != target else value
        totals_by_risk[risk_id] = subtotal
        total += subtotal
    return totals_by_risk, total
