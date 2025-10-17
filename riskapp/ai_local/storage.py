# riskapp/ai_local/storage.py
from __future__ import annotations

import os
import json
import numpy as np
from typing import Dict, Tuple, Optional, TYPE_CHECKING, Any

# Sadece tip kontrolü sırasında import (runtime'da import ETMEZ -> dairesel import olmaz)
if TYPE_CHECKING:
    from .engine import EmbIndex  # pragma: no cover

DATA_DIR = os.getenv("AI_DATA_DIR", "ai_data")

# Dosya adları (engine ile uyumlu + eski adla geriye dönük uyum)
NEW_VEC_NAME = "embeddings.npy"
OLD_VEC_NAME = "emb.npy"
META_NAME    = "meta.json"


class Storage:
    """
    Embedding vektörlerini ve metayı basit dosyalara yazar/okur:

      ai_data/
        - embeddings.npy  -> (N, dim) float32   (yeni)
        - emb.npy         -> (N, dim) float32   (eski; okunur ve kaydederken de güncellenir)
        - meta.json       -> (yeni) { id: {text, label, ...}, ... }
                             (eski) { ids:[], texts:[], labels:[], dim:int, use_faiss:bool }
    """
    def __init__(self, data_dir: Optional[str] = None):
        self.dir = data_dir or DATA_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.new_vec_path = os.path.join(self.dir, NEW_VEC_NAME)
        self.old_vec_path = os.path.join(self.dir, OLD_VEC_NAME)
        self.meta_path    = os.path.join(self.dir, META_NAME)

    # -------------------- SAVE --------------------
    def save_index(self, idx: "EmbIndex", meta: Optional[Dict[int, Dict]] = None, vecs: Optional[np.ndarray] = None) -> None:
        """
        İki kullanım da desteklenir:
          - save_index(idx, meta=meta_map)         -> vektörleri idx._X'ten alır
          - save_index(idx, vecs=emb_matrix)       -> metayı idx.{ids,texts,labels} ile oluşturur
        """
        # 1) Vektör matrisi
        V: Optional[np.ndarray] = None
        if vecs is not None:
            V = np.asarray(vecs, dtype=np.float32)
        else:
            V = getattr(idx, "_X", None)
            if V is not None:
                V = np.asarray(V, dtype=np.float32)
            else:
                # FAISS kullanılıyorsa _X olmayabilir; bu durumda vecs parametresi zorunlu
                raise RuntimeError(
                    "Vektör matrisi bulunamadı. FAISS ile fit ettiysen 'save_index(idx, vecs=...)' şeklinde çağır."
                )

        # 2) Meta
        if meta is None:
            # idx alanlarından yeni şema üret
            meta_dict: Dict[int, Dict[str, Any]] = {
                int(rid): {"text": txt, "label": lab}
                for rid, txt, lab in zip(getattr(idx, "ids", []), getattr(idx, "texts", []), getattr(idx, "labels", []))
            }
        else:
            # zaten yeni şema
            meta_dict = {int(k): v for k, v in meta.items()}

        # 3) Yaz
        np.save(self.new_vec_path, V.astype(np.float32))
        # Geriye dönük uyumluluk için eski ada da yaz
        try:
            np.save(self.old_vec_path, V.astype(np.float32))
        except Exception:
            pass

        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, ensure_ascii=False, indent=2)

    # -------------------- LOAD --------------------
    def load_index(self) -> Tuple["EmbIndex", Dict[int, Dict]]:
        """
        İndeksi ve meta haritasını döndürür:
          return idx, meta_map  # meta_map: {id: {...}}
        Hem yeni hem eski meta formatını tanır.
        """
        # Dairesel importu kırmak için GECİKMELİ import.
        from .engine import EmbIndex  # type: ignore

        # Vektör dosyasını bul
        if os.path.exists(self.new_vec_path):
            vec_path = self.new_vec_path
        elif os.path.exists(self.old_vec_path):
            vec_path = self.old_vec_path
        else:
            raise FileNotFoundError(
                f"AI indeks vektör dosyası bulunamadı: {self.new_vec_path} veya {self.old_vec_path}"
            )

        if not os.path.exists(self.meta_path):
            raise FileNotFoundError(f"AI indeks meta dosyası bulunamadı: {self.meta_path}")

        # Yüklemeler
        V = np.load(vec_path).astype(np.float32)
        with open(self.meta_path, "r", encoding="utf-8") as f:
            meta_any = json.load(f)

        # Meta'yı normalize et (eski & yeni şema)
        if isinstance(meta_any, dict) and "ids" in meta_any and "texts" in meta_any and "labels" in meta_any:
            # ESKİ ŞEMA
            ids = [int(x) for x in meta_any.get("ids", [])]
            texts = list(meta_any.get("texts", []))
            labels = list(meta_any.get("labels", []))
            use_faiss = bool(meta_any.get("use_faiss", False))
            dim_meta = int(meta_any.get("dim", 0))
            if dim_meta and V.shape[1] != dim_meta:
                raise ValueError(f"Vektör boyutu uyuşmuyor: V.shape[1]={V.shape[1]} meta.dim={dim_meta}")
            meta_map: Dict[int, Dict] = {int(rid): {"text": t, "label": lab} for rid, t, lab in zip(ids, texts, labels)}
        else:
            # YENİ ŞEMA: { "123": {"text": "...", "label": "...", ...}, ... }
            meta_map = {int(k): v for k, v in meta_any.items()}
            # list'leri idx'e verebilmek için çıkart
            ids   = sorted(meta_map.keys())
            texts = [str(meta_map[i].get("text", "")) for i in ids]
            labels= [str(meta_map[i].get("label", "")) for i in ids]
            # use_faiss bilgisini meta'dan alamayabiliriz; env'e bırak
            use_faiss = bool(int(os.getenv("USE_FAISS", "0")) == 1)

        # EmbIndex kur
        dim = V.shape[1]
        idx = EmbIndex(dim=dim, use_faiss=use_faiss)
        # fit sırasında hem FAISS hem sklearn tarafı düzgün çalışsın diye:
        # - sklearn: _X set + fit
        # - faiss:   add + ayrıca _X set (kaydedebilmek için)
        setattr(idx, "ids", ids)
        setattr(idx, "texts", texts)
        setattr(idx, "labels", labels)

        try:
            if getattr(idx, "use_faiss", False):
                idx.index.add(V.astype(np.float32))  # FAISS
                setattr(idx, "_X", V.astype(np.float32))  # kaydetme uyumluluğu
            else:
                setattr(idx, "_X", V.astype(np.float32))
                idx.index.fit(getattr(idx, "_X"))
        except Exception:
            # Her halükârda _X setli olsun
            setattr(idx, "_X", V.astype(np.float32))

        return idx, meta_map
