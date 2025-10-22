# riskapp/ai_local/engine.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any, TYPE_CHECKING

import numpy as np

# ---- Opsiyonel bağımlılıklar (runtime)
try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
except Exception:
    SentenceTransformer = None  # runtime'da yoksa None
try:
    import faiss  # optional hızlandırma
except Exception:
    faiss = None

from sklearn.neighbors import NearestNeighbors
from sklearn.feature_extraction.text import TfidfVectorizer

# ---- Tip denetimi için güvenli import (Pylance hatasını önler)
if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer
else:
    _SentenceTransformer = Any

# Ortam değişkenleri
MODEL_NAME = os.getenv("EMB_LOCAL_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
DATA_DIR   = os.getenv("AI_DATA_DIR", "ai_data")  # vektör ve meta dosyaları

# İndeks dosya adları (storage ile uyumlu)
VEC_FILE   = "embeddings.npy"
META_FILE  = "meta.json"


# ============================
#  Makale Temelli Bilgi Kartları
# ============================
DEFAULT_PAPER_FACTS: List[Dict[str, Any]] = [
    # --- Yazılım risk yönetimi / SoftRisk çizgisi ---
    {
        "id": 900001,
        "label": "paper_rule",
        "source": "SoftRisk yaklaşımı",
        "text": (
            "Yazılım projelerinde risk önceliği için iki temel ölçü: "
            "Risk Exposure (RE = Olasılık × Etki) ve FMEA tabanlı RPN (Olasılık × Şiddet × Tespit edilebilirlik). "
            "Takip, Top-10 risk listesi ve kırmızı-sarı-yeşil bölgelerle görselleştirme."
        ),
        "tags": ["software", "RE", "RPN", "top10"]
    },
    {
        "id": 900002,
        "label": "paper_rule",
        "source": "Risk Mitigasyon Prototipi (Anti-Ageing)",
        "text": (
            "RPN aralığına göre öneri seti: RPN çok yüksek ise hızla uygulanabilir düşük maliyetli mitigasyonlar "
            "(tedarikçi çeşitlendirme, ek testler) önce gelir; orta seviye RPN için planlı süreç iyileştirme; "
            "düşük RPN'de izleme yeterli olabilir."
        ),
        "tags": ["software", "mitigation", "RPN_policy"]
    },

    # --- İnşaat / IRMS çizgisi ---
    {
        "id": 900101,
        "label": "paper_rule",
        "source": "IRMS – International Construction",
        "text": (
            "HRBS↔WBS eşlemesiyle riskin kaynağı (HRBS) ilgili iş paketi (WBS) ile bağlanmalı. "
            "Önce/sonra/final risk puanı üç kademede izlenmeli; kurumsal hafıza için benzer proje eşlemesi (CBR)."
        ),
        "tags": ["construction", "HRBS", "WBS", "CBR"]
    },
    {
        "id": 900102,
        "label": "paper_rule",
        "source": "IRMS – Maliyet belirsizliği",
        "text": (
            "Proje maliyet/süre belirsizliği için Monte Carlo simülasyonu: "
            "kritik riskler üçgen/PERT dağılımları ile modellenir; sonuçlar P50/P80/P95 özetleriyle raporlanır."
        ),
        "tags": ["construction", "MCS", "P50", "P95"]
    },

    # --- Rüzgâr projeleri / Doktora çalışması ---
    {
        "id": 900201,
        "label": "paper_rule",
        "source": "Onshore Wind – FAHP + FTOPSIS",
        "text": (
            "Rüzgâr çiftliği inşaatında kritik risk seçimi için FAHP ile kriter ağırlıkları, FTOPSIS ile "
            "alternatiflerin sıralaması birlikte kullanılabilir."
        ),
        "tags": ["wind", "FAHP", "FTOPSIS", "MCDM"]
    },
    {
        "id": 900202,
        "label": "paper_rule",
        "source": "Onshore Wind – Hava riski",
        "text": (
            "Hava durumu (özellikle rüzgâr hızları) için faaliyet bazlı eşikler tanımlanmalı. "
            "Eşik aşımında üretkenlik sıfıra düşer; look-ahead çizelgeleme bu kısıtı göz önünde bulundurmalı."
        ),
        "tags": ["wind", "weather", "lookahead", "thresholds"]
    },

    # --- Katılımcı web-tabanlı DSS / MCE ---
    {
        "id": 900301,
        "label": "paper_rule",
        "source": "Participative Web DSS",
        "text": (
            "Çok ölçütlü değerlendirme (MCE/TOPSIS/Compromise Programming) ile paydaş tercihleri "
            "senaryo/alternatif seçiminde ağırlıklandırılmalı. Web tabanlı arayüzde katılımcı geribildirim toplanmalı."
        ),
        "tags": ["DSS", "MCE", "stakeholder"]
    },
]


# ============================
#  Sentence Bank Loader (opsiyonel)
# ============================
def _load_sentence_bank(data_dir: str = DATA_DIR) -> List[Dict[str, Any]]:
    """
    ai_data/sentences.json beklenen şema:
      {
        "category_aliases": { "...": ["..."] , ... },
        "phrases": { "anahtar": ["cümle1","cümle2", ...], ... }
      }
    'phrases' altındaki her cümleyi 'paper_rule' etiketiyle ekleriz (source: SB:<anahtar>).
    Böylece yeni anahtar/cümle eklendiğinde yeniden build ile aramaya girer.
    """
    path = os.path.join(data_dir, "sentences.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    next_id = 910000
    phrases = data.get("phrases") or {}
    for key, items in phrases.items():
        for s in items or []:
            out.append({
                "id": next_id,
                "label": "paper_rule",      # arama sırasında paper_rule ile birlikte gelir
                "source": f"SB:{key}",
                "text": str(s),
                "tags": [str(key)]
            })
            next_id += 1
    return out


# -------------------------------
#  Embedding & İndeks Bileşenleri
# -------------------------------
def _l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-8
    return x / n


class EmbIndex:
    """
    Metinleri embed edip yakın komşu araması yapar.
    FAISS varsa onu, yoksa sklearn KNN kullanır.
    """
    def __init__(self, dim: int, use_faiss: bool = False):
        self.dim = int(dim)
        self.use_faiss = bool(use_faiss and (faiss is not None))
        self.ids: List[int] = []
        self.texts: List[str] = []
        self.labels: List[str] = []
        self._X: Optional[np.ndarray] = None

        if self.use_faiss:
            # cosine ~ inner product (normlanmış vektörler)
            self.index = faiss.IndexFlatIP(self.dim)
        else:
            self.index = NearestNeighbors(n_neighbors=10, metric="cosine")

    def fit(self, X: np.ndarray, ids: List[int], texts: List[str], labels: List[str]):
        if X.ndim != 2 or X.shape[1] != self.dim:
            raise ValueError(f"Boyut uyuşmazlığı: beklenen {self.dim}, gelen {X.shape}")
        self.ids, self.texts, self.labels = list(ids), list(texts), list(labels)
        X = _l2_normalize(X.astype("float32"))
        if self.use_faiss:
            self.index.add(X)
        else:
            self._X = X
            self.index.fit(X)

    def search(self, q: np.ndarray, k: int = 5) -> List[Tuple[int, float]]:
        if q.ndim == 1:
            q = q.reshape(1, -1)
        q = _l2_normalize(q.astype("float32"))
        if self.use_faiss:
            D, I = self.index.search(q, k)  # (1,k)
            out: List[Tuple[int, float]] = []
            for j in range(I.shape[1]):
                i = int(I[0, j])
                if i == -1:
                    continue
                out.append((int(self.ids[i]), float(D[0, j])))
            return out
        else:
            k = min(k, len(self.ids)) if self.ids else 0
            if k == 0:
                return []
            dist, idx = self.index.kneighbors(q, n_neighbors=k)
            sim = 1.0 - dist[0]  # cosine distance -> similarity
            return [(int(self.ids[int(i)]), float(sim[j])) for j, i in enumerate(idx[0])]


class LocalEncoder:
    """
    Öncelik: SentenceTransformer. Yoksa TF-IDF fallback.
    """
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.st_model: Optional[_SentenceTransformer] = None  # <-- TYPE_CHECKING uyumlu
        self.tfidf: Optional[TfidfVectorizer] = None
        self.tfidf_fit = False

        # runtime'da varsa SBERT modelini dene
        if SentenceTransformer is not None:
            try:
                self.st_model = SentenceTransformer(model_name)  # type: ignore[call-arg,assignment]
            except Exception:
                self.st_model = None

        # yoksa TF-IDF
        if self.st_model is None:
            self.tfidf = TfidfVectorizer(
                lowercase=True,
                ngram_range=(1, 2),
                max_features=50_000
            )

    def dim(self) -> int:
        if self.st_model is not None:
            try:
                return int(self.st_model.get_sentence_embedding_dimension())  # type: ignore[attr-defined]
            except Exception:
                return 384
        if self.tfidf is not None and self.tfidf_fit:
            return int(len(self.tfidf.get_feature_names_out()))
        return 1024  # fit edilmeden önce yaklaşık

    def fit_tfidf(self, corpus: List[str]):
        if self.tfidf is None:
            return
        _ = self.tfidf.fit_transform(corpus)
        self.tfidf_fit = True

    def encode(self, texts: List[str]) -> np.ndarray:
        if self.st_model is not None:
            # not: batch_size ayarlanabilir (örn. 512) — burada varsayılan kalsın
            vecs = self.st_model.encode(texts, convert_to_numpy=True, normalize_embeddings=False)  # type: ignore[call-arg]
            return vecs.astype("float32")
        if not self.tfidf_fit:
            self.fit_tfidf(texts)
        X = self.tfidf.transform(texts)  # type: ignore[union-attr]
        return X.toarray().astype("float32")


# -------------------------------
#  AILocal: uçtan uca yardımcı
# -------------------------------
@dataclass
class MetaItem:
    id: int
    text: str
    label: str
    extra: Dict[str, Any]


class AILocal:
    """
    - risks / suggestions / paper_rule metinlerinden arama indeksi
    - answer(): en alakalı K bağlamı birleştirip düzenli cevap taslağı döndürür
    """
    def __init__(self, enc: Optional[LocalEncoder] = None,
                 idx: Optional[EmbIndex] = None,
                 meta: Optional[Dict[int, Dict]] = None):
        self.enc = enc or LocalEncoder(MODEL_NAME)
        self.idx = idx
        self.meta = meta or {}  # {id: {text, label, ...}}

    # ---------- Persistence (Storage üzerinden) ----------
    @classmethod
    def load_or_create(cls, data_dir: str = DATA_DIR) -> "AILocal":
        from .storage import Storage  # dairesel importu önlemek için burada
        st = Storage(data_dir)
        try:
            idx, meta = st.load_index()
            enc = LocalEncoder(MODEL_NAME)
            return cls(enc, idx, meta)
        except Exception:
            # boş motor—kullanıcı build_from_tables çağıracak
            return cls(LocalEncoder(MODEL_NAME), None, {})

    def save(self, data_dir: str = DATA_DIR):
        from .storage import Storage
        if not self.idx or not self.meta:
            raise RuntimeError("Kaydedilecek indeks yok.")
        st = Storage(data_dir)
        st.save_index(self.idx, self.meta)

    # ---------- Build / Rebuild ----------
    def ingest_paper_facts(self, facts: List[Dict[str, Any]]):
        """
        Dışarıdan makale özet/kural kartları eklemek için.
        facts: [{id:int, text:str, label:'paper_rule', ...}]
        Not: Bu sadece meta'yı günceller; aramada görünmesi için build sırasında
        rows'a ekle veya yeniden build et.
        """
        for f in facts:
            fid = int(f["id"])
            self.meta[fid] = {k: v for k, v in f.items() if k != "id"}

    def build_from_tables(self, rows: List[Dict[str, Any]],
                          include_paper_facts: bool = True,
                          include_sentence_bank: bool = True):
        """
        rows: [{id, text, label, ...}]  -> indeks + meta kurar.
        include_paper_facts=True ise DEFAULT_PAPER_FACTS’i de ekler.
        include_sentence_bank=True ise ai_data/sentences.json’daki cümleleri ekler.
        """
        rows = list(rows or [])
        if include_paper_facts:
            for f in DEFAULT_PAPER_FACTS:
                rows.append(f.copy())

        if include_sentence_bank:
            for f in _load_sentence_bank(DATA_DIR):
                rows.append(f)

        if not rows:
            raise ValueError("İndeks oluşturmak için satır yok.")

        ids = [int(r["id"]) for r in rows]
        texts = [str(r["text"] or "") for r in rows]
        labels = [str(r.get("label", "")) for r in rows]

        # TF-IDF ise önce fit
        if self.enc.st_model is None:
            self.enc.fit_tfidf(texts)
        X = self.enc.encode(texts)
        dim = X.shape[1]
        use_faiss = bool(int(os.getenv("USE_FAISS", "0")) == 1)
        self.idx = EmbIndex(dim=dim, use_faiss=use_faiss)
        self.idx.fit(X, ids, texts, labels)
        # meta
        self.meta = {int(r["id"]): {k: v for k, v in r.items() if k != "id"} for r in rows}

    # ---------- Query ----------
    def search(self, text: str, k: int = 5):
        if not self.idx or not self.meta:
            return []
        q = self.enc.encode([text])
        hits = self.idx.search(q, k=k)
        out = []
        for rid, score in hits:
            m = self.meta.get(int(rid), {})
            out.append({
                "id": int(rid),
                "text": m.get("text", ""),
                "label": m.get("label", ""),
                "score": float(score),
                **{k: v for k, v in m.items() if k not in ("text", "label")}
            })
        return out

    def answer(self, prompt: str, k: int = 5, style: str = "full") -> str:
        """
        style:
          - "full": bölümlü detaylı çıktı
          - "mini": sade 3-5 madde (eko/ayraç yok)
        """
        hits = self.search(prompt, k=k)
        if not hits:
            return ""

        # Basit label gruplama
        parts = {"risk": [], "suggestion": [], "paper_rule": [], "other": []}
        for h in hits:
            lbl = h.get("label") or "other"
            parts.get(lbl, parts["other"]).append(h)

        if style == "mini":
            # yalnızca en anlamlı 3-5 madde, tekrarları azaltmak için kısa çeşitlendirme
            bag: List[str] = []
            seen: set = set()
            for grp in ("suggestion", "risk", "paper_rule", "other"):
                for a in parts[grp]:
                    t = (a["text"] or "").strip()
                    tnorm = t.lower()
                    if not t or tnorm in seen:
                        continue
                    seen.add(tnorm)
                    bag.append(f"- {t}")
                    if len(bag) >= 5:
                        break
                if len(bag) >= 5:
                    break
            return "\n".join(bag).strip()

        # full: bölümlü çıktı
        def join_section(title: str, arr: List[Dict[str, Any]]) -> str:
            if not arr:
                return ""
            # küçük tekrar azaltma
            acc, seen = [], set()
            for a in arr:
                t = (a["text"] or "").strip()
                if not t:
                    continue
                key = t.lower()
                if key in seen:
                    continue
                seen.add(key)
                acc.append(f"- {t}")
            if not acc:
                return ""
            body = "\n".join(acc)
            return f"### {title}\n{body}\n"

        sections = []
        sections.append(join_section("Benzer Risk Kayıtları", parts["risk"]))
        sections.append(join_section("İlgili Öneriler", parts["suggestion"]))
        sections.append(join_section("Makalelerden Kurallar", parts["paper_rule"]))
        body = "\n".join([s for s in sections if s])

        return body.strip() if body else ""
