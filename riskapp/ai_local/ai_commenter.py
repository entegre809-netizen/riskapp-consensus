# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple
import re as _re

from .ps_estimator import PSEstimator
from .engine import (
    AILocal,
    KEYSETS,                 # alan anahtar kümeleri
    ACTION_TEMPLATES,        # alan -> aksiyon şablonları
    _kpis_default as _kpis_by_text,   # metne göre KPI önericisi
    _dept_raci_defaults      # alan ipuçlarına göre tipik RACI
)
from ..models import db, Risk


# -----------------------------
# Yardımcılar
# -----------------------------
def _smart_due(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()

def _normalize(s: str) -> str:
    if not s:
        return ""
    tr_map = str.maketrans({
        "ç":"c","Ç":"c","ğ":"g","Ğ":"g","ı":"i","İ":"i",
        "ö":"o","Ö":"o","ş":"s","Ş":"s","ü":"u","Ü":"u"
    })
    return s.translate(tr_map).lower()

def _unique(seq: List[Dict[str, Any]], key=("action","due")) -> List[Dict[str, Any]]:
    seen = set(); out = []
    for x in seq:
        k = tuple(x.get(k) for k in key)
        if k not in seen:
            seen.add(k); out.append(x)
    return out

def _strip_light(txt: str) -> str:
    """Emoji, 3+ boş satır ve gereksiz whitespace temizliği."""
    if not txt:
        return ""
    txt = _re.sub(r"[\U0001F300-\U0001FAFF]", "", txt)    # emoji
    txt = _re.sub(r"\n{3,}", "\n\n", txt)                 # 3+ boş satır
    return txt.strip()

def _ps_bucket(p: Optional[int], s: Optional[int]) -> Tuple[str,str,str]:
    """
    P,S → (seviyetxt, probtxt, risk_düzeyi)
    """
    try:
        p = int(p) if p is not None else None
        s = int(s) if s is not None else None
    except Exception:
        p = s = None

    sev = "düşük" if (s and s <= 2) else "orta" if (s and s <= 3) else "yüksek" if (s and s <= 4) else "çok yüksek" if s else "-"
    prb = "düşük" if (p and p <= 2) else "orta" if (p and p <= 3) else "yüksek" if (p and p <= 4) else "çok yüksek" if p else "-"
    if p and s:
        rpn = p * s
        if rpn >= 15: lvl = "çok yüksek"
        elif rpn >= 9: lvl = "yüksek"
        elif rpn >= 4: lvl = "orta"
        else:          lvl = "düşük"
    else:
        lvl = "-"
    return sev, prb, lvl

# KEYSETS anahtarlarının Türkçe kısa etiketleri
_LABELS_TR = {
    "insaat": "İnşaat/Şantiye",
    "satinalma": "Satınalma/Lojistik",
    "sozlesme": "Sözleşme/Onay",
    "isg_cevre": "İSG/Çevre",
    "geoteknik": "Geoteknik",
    "kalite": "Kalite (QA/QC)",
    "pmo": "PMO/Paydaş",
    "planlama": "Planlama",
    "mep_elektrik": "MEP/Elektrik",
    "mep_mekanik": "MEP/Mekanik",
    "marine": "Deniz/Marine",
    "tasarim": "Tasarım",
    "teknik_ofis": "Teknik Ofis",
    "finans": "Finans",
    "makine_bakim": "Makine-Bakım",
    "bim_bt": "BIM/BT",
    "izin_ruhsat": "İzin/Ruhsat",
    "laboratuvar": "Laboratuvar",
    "depo": "Depo/Ambar",
}

def _infer_keys_from_text(text: str) -> List[str]:
    """
    Tüm metni (kategori+başlık+açıklama) KEYSETS'e göre tarayıp
    eşleşen alan anahtarlarını döndürür.
    """
    t = _normalize(text)
    hits = []
    for key, kws in KEYSETS.items():
        if any(k in t for k in kws):
            hits.append(key)
    return hits

def _compose_headline(title: str, blob: str, p: Optional[int], s: Optional[int], hits: List[str]) -> str:
    """
    Her yeni kategori/faktörde de çalışacak tek cümlelik özet.
    - alan etiketi (varsa)
    - P,S'ye göre kısa şiddet/olasılık ifadesi
    """
    sev_txt, prb_txt, lvl = _ps_bucket(p, s)
    area = _LABELS_TR.get(hits[0], None) if hits else None

    # Başlık cümlesini sadeleştir (son nokta vs. at)
    ttl = (title or "Risk").strip()
    ttl = ttl[:-1] if ttl.endswith((".", ":", ";")) else ttl

    parts = []
    if area:
        parts.append(f"{area} kapsamında")
    parts.append(f"“{ttl}” riski için")
    if sev_txt != "-" or prb_txt != "-":
        parts.append(f"{sev_txt} etki, {prb_txt} olasılık beklenir")
    if lvl != "-":
        parts.append(f"(düzey: {lvl}).")
    else:
        parts[-1] = parts[-1] + "."
    return " ".join(parts)

def _pick_actions(title: str, category: str, description: str) -> List[Dict[str, str]]:
    """
    Yeni kategori geldiğinde bile mantıklı aksiyon çıkarır:
    - KEYSETS eşleşmesi varsa: ACTION_TEMPLATES'ten derler
    - Hiç eşleşme yoksa: RACI'yi metinden tahmin edip genel aksiyon yazar
    """
    blob = f"{category or ''} {title or ''} {description or ''}"
    hits = _infer_keys_from_text(blob)
    actions: List[Dict[str, str]] = []

    # Eşleşme var: ilgili şablonlardan topla
    if hits:
        base_raci = _dept_raci_defaults(_normalize(blob))
        for key in hits:
            for text, days in ACTION_TEMPLATES.get(key, []):
                actions.append({
                    **base_raci,
                    "action": text,
                    "due": _smart_due(days)
                })
        actions = _unique(actions)
        if actions:
            return actions[:8]

    # Eşleşme yok: genel ama makul bir set
    base_raci = _dept_raci_defaults(_normalize(blob))
    fallback = [
        {**base_raci, "action": "Risk için ayrıntılı kontrol listesi ve metod beyanı yayımla", "due": _smart_due(7)},
        {**base_raci, "action": "Haftalık izleme formu aç; trend/KPI takibini başlat",        "due": _smart_due(7)},
        {**base_raci, "action": "Sahip/hesap verecek kişi (R/A) atamasını yazılı teyit et",    "due": _smart_due(5)},
    ]
    return fallback

def _pick_kpis(title: str, category: str, description: str) -> List[str]:
    """
    KPI’lar metnin tamamına göre türetilir.
    KEYSETS yakalayamazsa 'common' set döner → yeni kategorilerde bile mantıklı.
    """
    blob = _normalize(f"{category or ''} {title or ''} {description or ''}")
    return _kpis_by_text(blob)


# -----------------------------
# Ana giriş: yorum üretici
# -----------------------------
def make_ai_risk_comment(risk_id: int, style: str = "oz") -> str:
    """
    Kısa ve net yorum üretir; yeni kategorilerde de mantıklı kalır.
    Stil: 'oz' (en kısa), 'net' (madde madde), 'kurumsal' (resmi kısa).
    """
    risk: Optional[Risk] = Risk.query.get(risk_id)
    if not risk:
        return "⚠️ Risk bulunamadı."

    title = risk.title or "Risk"
    category = risk.category or ""
    description = risk.description or ""

    # 1) P/S tahmini (veri tabanından)
    ps = PSEstimator(alpha=5.0)
    try:
        ps.fit(db.session)
        hint = ps.suggest(category or None)
    except Exception:
        hint = {"p": None, "s": None, "source": "veri"}

    p, s = hint.get("p"), hint.get("s")
    sev_txt, prb_txt, lvl_txt = _ps_bucket(p, s)

    # 2) Bağlam (opsiyonel) — makale kuralları
    rule_sources: List[str] = []
    try:
        ai = AILocal.load_or_create()
        hits = ai.search(f"{category} {title} {description}", k=5)
        rule_sources = [h.get("source","") for h in hits if h.get("label") == "paper_rule" and h.get("source")]
        rule_sources = list(dict.fromkeys(rule_sources))[:2]  # uniq + ilk 2
    except Exception:
        rule_sources = []

    # 3) Dinamik alan sezgisi + tek cümlelik headline
    blob = f"{category} {title} {description}"
    key_hits = _infer_keys_from_text(blob)
    headline = _compose_headline(title, blob, p, s, key_hits)

    # 4) Aksiyonlar & KPI’lar (tamamen dinamik)
    actions = _pick_actions(title, category, description)
    kpis = _pick_kpis(title, category, description)
    close_criteria = "8 hafta KPI hedefi + 2 ay NCR=0"

    def line_ps() -> str:
        src = hint.get("source") or "veri"
        pp = p if p is not None else "-"
        ss = s if s is not None else "-"
        return f"P={pp}, S={ss} (kaynak: {src}, düzey: {lvl_txt})"

    S = (style or "oz").lower()
    if S not in {"oz", "net", "kurumsal"}:
        S = "oz"

    # -------- öz (en kısa) --------
    if S == "oz":
        out: List[str] = []
        out.append(f"**{title}** | Kategori: {category or '—'}")
        out.append(headline)
        out.append(line_ps())
        if actions:
            out.append("Aksiyonlar:")
            for a in actions[:3]:
                out.append(f"- {a['action']} (Termin: {a['due']})")
        if kpis:
            out.append("KPI:")
            for k in kpis[:2]:
                out.append(f"- {k}")
        out.append(f"Kapanış: {close_criteria}")
        return _strip_light("\n".join(out))

    # -------- net (madde madde) --------
    if S == "net":
        out: List[str] = []
        out.append(f"**{title}** (Kategori: {category or '—'})")
        out.append(f"Özet: {headline}")
        out.append(f"Sayısal: {line_ps()}")
        if actions:
            out.append("• Aksiyon (ilk 3):")
            for a in actions[:3]:
                out.append(f"  - {a['action']} — Termin: {a['due']}")
        if kpis:
            out.append("• KPI (ilk 2):")
            for k in kpis[:2]:
                out.append(f"  - {k}")
        if rule_sources:
            out.append(f"• Bağlam: {', '.join(rule_sources)}")
        out.append(f"• Kapanış: {close_criteria}")
        return _strip_light("\n".join(out))

    # -------- kurumsal (resmi kısa) --------
    out: List[str] = []
    out.append(f"**Risk:** {title}")
    out.append(f"**Kategori:** {category or '—'}")
    out.append(f"**Özet:** {headline}")
    out.append(f"**Sayısal Özet:** {line_ps()}")
    if actions:
        out.append("**Aksiyon Planı (ilk 4):**")
        for a in actions[:4]:
            out.append(f"- {a['action']} (Termin: {a['due']})")
    if kpis:
        out.append("**KPI (ilk 3):**")
        for k in kpis[:3]:
            out.append(f"- {k}")
    if rule_sources:
        out.append(f"**Bağlam:** {', '.join(rule_sources)}")
    out.append(f"**Kapanış Kriteri:** {close_criteria}")
    return _strip_light("\n".join(out))
