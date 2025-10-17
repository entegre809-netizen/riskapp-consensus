# ai_local/ps_estimator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import json, os

# Projedeki mevcut modeller (SQLAlchemy)
# Not: import hatası olmaması için bu isimler korunuyor.
# riskapp/ai_local/ps_estimator.py
from riskapp.models import db, Risk, Evaluation
 # type: ignore

# -----------------------------
#  Heuristik Kurallar (Makalelerden)
# -----------------------------
# - IRMS çizgisi: "legal/regülasyon" risklerinde şiddet (severity) artma eğilimi
# - SoftRisk/Anti-ageing çizgisi: "tedarik/supply" risklerinde tespit güçlüğü → gerçekleşme olasılığı etkilenebilir
# - Rüzgâr şantiyesi: "weather/wind" temalı risklerde p artışı (eşik aşımlarında üretkenlik düşüyor)
# Buradaki katsayılar PoC için hafiftir ve Bayes ortalamasına sonradan uygulanır.
PAPER_RULE_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
    # category_substring: {"p_mul": x, "s_mul": y}
    "legal":   {"p_mul": 1.00, "s_mul": 1.10},
    "reg":     {"p_mul": 1.00, "s_mul": 1.10},
    "izin":    {"p_mul": 1.00, "s_mul": 1.08},
    "supply":  {"p_mul": 1.08, "s_mul": 1.00},
    "tedarik": {"p_mul": 1.08, "s_mul": 1.00},
    "weather": {"p_mul": 1.10, "s_mul": 1.00},
    "wind":    {"p_mul": 1.10, "s_mul": 1.00},
    "hava":    {"p_mul": 1.08, "s_mul": 1.00},
}

# -----------------------------
#  Excel/JSON Öncel (Prior) Dosyası Ayarları
# -----------------------------
PRIORS_ENV = "PS_PRIORS_PATH"  # istersen özel yol ver
PRIORS_DEFAULT_PATH = os.path.join(os.getenv("AI_DATA_DIR", "ai_data"), "category_ps_priors.json")


def _apply_paper_rules(category: Optional[str], p: float, s: float) -> Tuple[float, float, List[str]]:
    """
    Kategori adına göre hafif çarpanlar uygular (makale temelli heuristik).
    Çıktı: (p_adj, s_adj, [uygulanan_kurallar])
    """
    if not category:
        return p, s, []
    cat_low = category.lower()
    applied: List[str] = []
    p_adj, s_adj = p, s
    for key, muls in PAPER_RULE_ADJUSTMENTS.items():
        if key in cat_low:
            p_mul = muls.get("p_mul", 1.0)
            s_mul = muls.get("s_mul", 1.0)
            p_adj *= p_mul
            s_adj *= s_mul
            applied.append(f"{key}:p×{p_mul:.2f},s×{s_mul:.2f}")
    # Puanları 1–5 aralığına “hafifçe” sıkıştır
    p_adj = max(1.0, min(5.0, p_adj))
    s_adj = max(1.0, min(5.0, s_adj))
    return p_adj, s_adj, applied


@dataclass
class FitStats:
    global_p: float = 3.0
    global_s: float = 3.0
    n_all_p: int = 0
    n_all_s: int = 0
    n_by_cat_p: Dict[str, int] = None
    n_by_cat_s: Dict[str, int] = None

    def __post_init__(self):
        if self.n_by_cat_p is None:
            self.n_by_cat_p = {}
        if self.n_by_cat_s is None:
            self.n_by_cat_s = {}


class PSEstimator:
    """
    P/S (Probability/Severity) için Bayes harmanlı tahmin.
    - fit: veritabanından probability & severity ortalamalarını toplar
    - suggest(category): kategoriye özel tahmin (Bayes shrinkage + makale heuristikleri + opsiyonel Excel priors)
    Skala varsayımı: 1..5 (ya da 1..10 → proje verinizde hangisi kullanılıyorsa otomatik normalize edebilirsiniz).
    """

    def __init__(self, alpha: float = 5.0, round_to: int = 1):
        """
        alpha: kategori örnek sayısı az olduğunda global ortalamaya çekme gücü (Bayes prior ağırlığı)
        round_to: yuvarlama hassasiyeti (ondalık basamak)
        """
        self.alpha = float(alpha)
        self.round_to = int(round_to)

        self.cat_p: Dict[str, float] = {}
        self.cat_s: Dict[str, float] = {}
        self.global_p: float = 3.0
        self.global_s: float = 3.0
        self.stats = FitStats()

    # --------- Yardımcılar ---------
    @staticmethod
    def _safe_mean(xs: List[float]) -> Optional[float]:
        xs2 = [float(x) for x in xs if x is not None]
        if not xs2:
            return None
        return sum(xs2) / len(xs2)

    def _bayes_blend(self, sample_mean: float, sample_n: int, global_mean: float) -> float:
        """(n*mean + alpha*global) / (n + alpha)"""
        return (sample_n * sample_mean + self.alpha * global_mean) / (sample_n + self.alpha)

    def _load_priors_if_any(self, path: Optional[str] = None) -> None:
        """
        Excel'den ürettiğimiz kategori öncel değerlerini (P/S) yükler.
        Şema: { "KATEGORI_ADI": {"p_mean": 2.73, "s_mean": 3.91, "n": 35}, ... }
        """
        priors_path = path or os.getenv(PRIORS_ENV, PRIORS_DEFAULT_PATH)
        try:
            with open(priors_path, "r", encoding="utf-8") as f:
                priors = json.load(f)
        except Exception:
            return  # dosya yoksa sessizce geç

        # kategori bazlı override
        for cat, d in priors.items():
            if isinstance(d, dict):
                if "p_mean" in d:
                    self.cat_p[cat] = round(float(d["p_mean"]), self.round_to)
                if "s_mean" in d:
                    self.cat_s[cat] = round(float(d["s_mean"]), self.round_to)

        # global tahmini de güncelle (opsiyonel ama faydalı)
        try:
            vals_p = [float(v["p_mean"]) for v in priors.values() if "p_mean" in v]
            vals_s = [float(v["s_mean"]) for v in priors.values() if "s_mean" in v]
            if vals_p:
                self.global_p = round(sum(vals_p) / len(vals_p), self.round_to)
            if vals_s:
                self.global_s = round(sum(vals_s) / len(vals_s), self.round_to)
        except Exception:
            pass

    # --------- Eğitim ---------
    def fit(self, session=None) -> None:
        """
        Veritabanından probability/severity değerlerini okuyup
        global ve kategori bazlı Bayes ortalamalarını hesaplar.
        """
        sess = session or db.session

        # ORM varsa kullan; yoksa raw SQL fallback
        try:
            # ORM sorgusu
            q = (
                sess.query(Risk.category, Evaluation.probability, Evaluation.severity)
                .join(Evaluation, Evaluation.risk_id == Risk.id)
                .filter(Evaluation.probability.isnot(None))
                .filter(Evaluation.severity.isnot(None))
            )
            rows = [(cat, p, s) for cat, p, s in q.all()]
        except Exception:
            # Raw SQL fallback
            rows = sess.execute("""
                SELECT rr.category, e.probability, e.severity
                FROM evaluations e
                JOIN risks rr ON rr.id = e.risk_id
                WHERE e.probability IS NOT NULL AND e.severity IS NOT NULL
            """).fetchall()

        p_all: List[float] = []
        s_all: List[float] = []
        by_cat_p: Dict[str, List[float]] = defaultdict(list)
        by_cat_s: Dict[str, List[float]] = defaultdict(list)

        for cat, p, s in rows:
            if p is not None:
                p_all.append(float(p))
                if cat:
                    by_cat_p[str(cat)].append(float(p))
            if s is not None:
                s_all.append(float(s))
                if cat:
                    by_cat_s[str(cat)].append(float(s))

        g_p = self._safe_mean(p_all)
        g_s = self._safe_mean(s_all)
        self.global_p = round(g_p, self.round_to) if g_p is not None else 3.0
        self.global_s = round(g_s, self.round_to) if g_s is not None else 3.0

        # kategori bazlı Bayes harmanı
        self.cat_p.clear()
        self.cat_s.clear()

        for cat, arr in by_cat_p.items():
            local_mean = self._safe_mean(arr)
            if local_mean is None:
                continue
            val = self._bayes_blend(local_mean, len(arr), self.global_p)
            self.cat_p[cat] = round(val, self.round_to)

        for cat, arr in by_cat_s.items():
            local_mean = self._safe_mean(arr)
            if local_mean is None:
                continue
            val = self._bayes_blend(local_mean, len(arr), self.global_s)
            self.cat_s[cat] = round(val, self.round_to)

        self.stats = FitStats(
            global_p=self.global_p,
            global_s=self.global_s,
            n_all_p=len(p_all),
            n_all_s=len(s_all),
            n_by_cat_p={k: len(v) for k, v in by_cat_p.items()},
            n_by_cat_s={k: len(v) for k, v in by_cat_s.items()},
        )

        # Excel/JSON öncel değerleri varsa uygula (override)
        self._load_priors_if_any()

    # --------- Tahmin ---------
    def suggest(self, category: Optional[str]) -> Dict[str, object]:
        """
        Kategori verilirse kategoriye özgü Bayes harman + makale heuristikleri uygular.
        Yoksa global döner.
        Dönen yapı:
        {
          "p": olasılık (float),
          "s": şiddet (float),
          "n_cat": (p_n, s_n),
          "n_all": (P_toplam, S_toplam),
          "applied_rules": [ ... ],   # hangi heuristikler uygulandı
          "source": "category|global"
        }
        """
        # Global default
        base_p = self.global_p
        base_s = self.global_s
        n_cat_p = 0
        n_cat_s = 0
        src = "global"

        if category:
            # kategori için Bayes sonuçları varsa onları al
            if category in self.cat_p:
                base_p = self.cat_p[category]
                n_cat_p = self.stats.n_by_cat_p.get(category, 0)
                src = "category"
            if category in self.cat_s:
                base_s = self.cat_s[category]
                n_cat_s = self.stats.n_by_cat_s.get(category, 0)
                src = "category"

        # Makale tabanlı küçük heuristik ayarı
        p_adj, s_adj, applied = _apply_paper_rules(category, base_p, base_s)

        return {
            "p": round(p_adj, self.round_to),
            "s": round(s_adj, self.round_to),
            "n_cat": (n_cat_p, n_cat_s),
            "n_all": (self.stats.n_all_p, self.stats.n_all_s),
            "applied_rules": applied,
            "source": src
        }
