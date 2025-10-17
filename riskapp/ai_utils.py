# riskapp/ai_utils.py
from __future__ import annotations
from typing import Any, Dict, List

# Paketten doğrudan (absolute) import
from riskapp.ai_local.engine import AILocal

# Tek bir yerel motor örneğini cache’le
_engine_singleton: AILocal | None = None

def _get_local() -> AILocal:
    global _engine_singleton
    if _engine_singleton is not None:
        return _engine_singleton
    try:
        _engine_singleton = AILocal.load_or_create()  # engine.py içinde olmalı
    except Exception:
        # Güvenli fallback: boş indeksli basit motor
        _engine_singleton = AILocal()
    return _engine_singleton


def ai_complete(prompt: str, *, max_tokens: int = 256, **kwargs) -> str:
    """
    Yerel motordan 'tamamlama benzeri' yanıt.
    AILocal.answer varsa onu kullanır; yoksa en iyi eşleşmelerden kısa özet üretir.
    """
    eng = _get_local()

    # A) LLM benzeri cevaplayıcı varsa onu kullan
    if hasattr(eng, "answer") and callable(getattr(eng, "answer")):
        try:
            out = eng.answer(prompt, **kwargs)
            if isinstance(out, str) and out.strip():
                return out
        except Exception:
            pass

    # B) Fallback: arama + özet
    try:
        hits = eng.search(prompt, k=3) or []
    except Exception:
        hits = []

    if not hits:
        return "Şu an yerel AI indeksinde uygun içerik bulunamadı."

    ctx = "\n\n".join([str(h.get("text", "")).strip() for h in hits if h.get("text")])
    return (f"Aşağıdaki bağlama göre kısa bir yanıt:\n\n{ctx}\n\n"
            f"Soru/İstek: {prompt}\n"
            f"Özet: {ctx[:max_tokens]}...")


def ai_json(schema_desc: str, prompt: str, **kwargs) -> Dict[str, Any]:
    """
    JSON biçiminde yerel arama sonuçları döndürür (basit şema + kayıtlar).
    """
    eng = _get_local()
    out: Dict[str, Any] = {
        "schema": schema_desc,
        "query": prompt,
        "records": [],
    }
    try:
        hits = eng.search(prompt, k=5) or []
        out["records"] = [
            {
                "id": h.get("id"),
                "text": h.get("text"),
                "label": h.get("label"),
                "score": float(h.get("score", 0.0)) if h.get("score") is not None else 0.0,
            }
            for h in hits
        ]
    except Exception:
        pass
    return out


def best_match(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Vektör indeksinden en iyi eşleşmeleri döndürür: [{id, text, label, score}, ...]
    """
    eng = _get_local()
    try:
        hits = eng.search(query, k=top_k) or []
        for h in hits:
            if "score" in h:
                try:
                    h["score"] = float(h["score"])
                except Exception:
                    h["score"] = 0.0
        return hits
    except Exception:
        return []
