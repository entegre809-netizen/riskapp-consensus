# riskapp/ai_local/trainer.py
from __future__ import annotations

from typing import List, Tuple, Dict, Set

# Proje içi relative importlar
from ..models import db, Suggestion, Risk  # type: ignore
from .engine import LocalEncoder, EmbIndex
from .storage import Storage

# (opsiyonel) Makale bazlı bilgi kartlarını korpusa eklemek için:
try:
    from .engine import DEFAULT_PAPER_FACTS  # type: ignore
except Exception:
    DEFAULT_PAPER_FACTS = []

import os

ID_OFFSET = 1_000_000  # Risk ve Suggestion id'leri çakışmasın diye


def fetch_corpus(kind: str = "suggestions", min_len: int = 5) -> List[Tuple[int, str, str]]:
    """
    Veritabanından eğitim/indeks korpusunu çeker.

    Parameters
    ----------
    kind : {'suggestions', 'risks', 'both'}
        Hangi tablolardan metin çekileceği.
    min_len : int
        Bu uzunluğun altındaki metinler filtrelenir.

    Returns
    -------
    List[Tuple[id:int, text:str, label:str]]
        id: benzersiz integer (risklerde çakışmayı önlemek için offset uygulanır)
        text: indekslenecek metin
        label: örn. kategori (isteğe bağlı etiket)
    """
    rows: List[Tuple[int, str, str]] = []

    if kind in ("suggestions", "both"):
        for s in Suggestion.query.all():
            txt = (s.text or "").strip()
            if len(txt) >= min_len:
                rows.append((int(s.id), txt, s.category or ""))

    if kind in ("risks", "both"):
        for r in Risk.query.all():
            # Açıklama yoksa başlık kullan
            txt = (r.description or r.title or "").strip()
            if len(txt) >= min_len:
                rows.append((ID_OFFSET + int(r.id), txt, r.category or ""))

    # Tekrar edenleri at (aynı text + label)
    seen: Set[Tuple[str, str]] = set()
    deduped: List[Tuple[int, str, str]] = []
    for rid, t, lab in rows:
        key = (t, lab)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((rid, t, lab))
    return deduped


def build_index(
    kind: str = "suggestions",
    use_faiss: bool | None = None,
    include_paper_facts: bool = False,
    min_len: int = 5,
) -> int:
    """
    Metinleri gömme (embedding) vektörlerine çevirir, indeksi kurar ve diske kaydeder.

    Parameters
    ----------
    kind : {'suggestions', 'risks', 'both'}
        Korpus kaynağı.
    use_faiss : bool | None
        FAISS destekliyse True yaparak hızlı ANN indeksi kurabilirsiniz.
        None ise env: USE_FAISS=1 okunur.
    include_paper_facts : bool
        True ise, makale özet/kural kartları (DEFAULT_PAPER_FACTS) da indekse eklenir.
    min_len : int
        Bu uzunluğun altındaki metinler filtrelenir.

    Returns
    -------
    int
        İndekse eklenen kayıt adedi.
    """
    if use_faiss is None:
        use_faiss = bool(int(os.getenv("USE_FAISS", "0")) == 1)

    corpus = fetch_corpus(kind, min_len=min_len)

    # İstenirse makale bilgilerini da ekle (paper_rule olarak)
    if include_paper_facts and DEFAULT_PAPER_FACTS:
        for f in DEFAULT_PAPER_FACTS:
            fid = int(f.get("id", 0)) or 0
            text = str(f.get("text", "")).strip()
            if not text:
                continue
            label = str(f.get("label", "paper_rule"))
            corpus.append((fid, text, label))

    if not corpus:
        raise RuntimeError("Korpus boş. Önce öneri veya risk ekleyin (ya da include_paper_facts=True deneyin).")

    ids   = [rid for rid, _, _ in corpus]
    texts = [t   for _, t, _ in corpus]
    labs  = [c   for _, _, c in corpus]

    # 1) Encode
    encoder = LocalEncoder()
    X = encoder.encode(texts)  # shape: (N, dim)
    dim = X.shape[1]

    # 2) Index
    index = EmbIndex(dim=dim, use_faiss=use_faiss)
    index.fit(X, ids, texts, labs)

    # 3) Persist — yeni storage imzasıyla UYUMLU:
    #    - meta haritasını (yeni şema) yaz
    #    - vektörleri vecs=X ile yaz
    meta_map: Dict[int, Dict[str, str]] = {
        int(rid): {"text": t, "label": lab} for rid, t, lab in corpus
    }
    Storage().save_index(index, meta=meta_map, vecs=X)

    return len(ids)
