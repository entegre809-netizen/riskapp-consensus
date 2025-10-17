# riskapp/ai_local/ai_commenter.py
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Any, List, Optional

from .ps_estimator import PSEstimator
from .engine import AILocal
from ..models import db, Risk

def _smart_due(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()

def _propose_actions(risk: Risk) -> List[Dict[str, str]]:
    cat = (risk.category or "").lower()
    actions: List[Dict[str, str]] = []
    if "beton" in cat:
        actions += [
            {"owner": "Saha Şefi", "action": "Döküm öncesi kalıp & donatı checklist %100", "due": _smart_due(14)},
            {"owner": "Kalite Müh.", "action": "Numune alma & kür planı revizyonu (TS EN 206)", "due": _smart_due(7)},
            {"owner": "Satınalma", "action": "Tedarikçi denetimi; alternatif onayı", "due": _smart_due(21)},
        ]
    else:
        actions.append({"owner": "Risk Sahibi", "action": "Haftalık izleme formu aç; sorumlu ata", "due": _smart_due(7)})
    return actions

def _kpis_default() -> List[str]:
    return [
        "Hata oranı ≤ %1 (48 saat sonrası ölçüm)",
        "Rework saatleri ≤ toplamın %2’si (aylık)",
        "Uygunsuzluk sayısı = 0 (aylık)"
    ]

def make_ai_risk_comment(risk_id: int) -> str:
    risk: Risk = Risk.query.get(risk_id)
    if not risk:
        return "⚠️ Risk bulunamadı."

    # 1) P/S tahmini (DB + Excel priors + makale heuristik)
    ps = PSEstimator(alpha=5.0); ps.fit(db.session)
    hint = ps.suggest(risk.category or None)

    # 2) Benzer kayıtlar / makale kuralları (bağlam)
    ai = AILocal.load_or_create()
    query = f"{risk.category or ''} {risk.title or ''} {risk.description or ''}"
    hits = ai.search(query, k=5)
    rules = [h for h in hits if h.get("label") == "paper_rule"]

    # 3) Aksiyonlar / KPI’lar
    actions = _propose_actions(risk)
    kpis = _kpis_default()
    close_criteria = "2 ay 0 uygunsuzluk + KPI’lar 8 hafta üst üste tutturulmuş"

    # 4) Metni derle
    lines = []
    lines.append(f"🤖 **AI Önerisi — {risk.title or 'Risk'}**")
    lines.append(f"**Kategori:** {risk.category or '—'}")
    lines.append(f"**Açıklama:** {risk.description or '—'}\n")
    lines.append("### 1) Sayısal Özet")
    lines.append(f"- Tahmini Olasılık **P={hint['p']}**, Şiddet **S={hint['s']}** "
                 f"(kaynak: {hint['source']}, örnek: P {hint['n_cat'][0]}/{hint['n_all'][0]}, "
                 f"S {hint['n_cat'][1]}/{hint['n_all'][1]})")
    if hint.get("applied_rules"):
        lines.append(f"- Uygulanan makale kuralları: " + ", ".join(hint["applied_rules"]))
    lines.append("\n### 2) Önerilen Aksiyonlar (RACI/Termin)")
    for a in actions:
        lines.append(f"- [**{a['owner']}**] {a['action']} — **Termin:** {a['due']}")
    lines.append("\n### 3) KPI’lar")
    for k in kpis:
        lines.append(f"- {k}")
    lines.append("\n### 4) Kapanış Kriteri")
    lines.append(f"- {close_criteria}")
    if rules:
        lines.append("\n### 5) Makale Bağlamı")
        for r in rules:
            lines.append(f"- {r.get('text','')}")
    return "\n".join(lines)
