# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple, Iterable, Optional
import os, json, re, unicodedata, random

# =========================
#  Basit metin normalizasyonu
# =========================
_TRMAP = str.maketrans({
    "ç":"c","ğ":"g","ı":"i","ö":"o","ş":"s","ü":"u",
    "Ç":"c","Ğ":"g","İ":"i","Ö":"o","Ş":"s","Ü":"u"
})
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "").strip())
    s = s.translate(_TRMAP).lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _any_in(text: str, keys: Iterable[str]) -> bool:
    t = _norm(text)
    return any(_norm(k) in t for k in keys)

# =========================
#  Kategori alias'ları (geniş)
# =========================
CATEGORY_ALIASES: Dict[str, List[str]] = {
    "İNŞAAT UYGULAMA RİSKLERİ": [
        "uygulama","insaat","santiye","imalat","beton","kalip","donati","boru",
        "kazik","kazik testi","kazik yukleme","topografik","olcum","is ilerlemesi",
        "verimlilik","ekipman","makine","vinc","duba","dalgic","lojistik",
        "yapi hasari","kalite","tasarimci/uygulama","iletisim","montaj","komisyoning",
        "scaffold","rigging","katodik koruma","iskele","rihtim"
    ],
    "ÇEVRESEL RİSKLER": [
        "ced","cevre","dogal afet","dogalafeti","deniz dibi tarama","deniz trafigi",
        "deniz seviyesi","deprem","pandemi","yangin","patlama","hava sartlari",
        "yakit dolum","sokum","bertaraf","emisyon","gurultu","atık","spill"
    ],
    "DİZAYN TASARIM RİSKLERİ": [
        "dizayn","tasarim","revizyon","saha inceleme","standart","sartname",
        "hesap raporu","simulasyon","osinografi","imar","ruzgAr","tide","veri yetersiz",
        "rfi","ifc","shop drawing","clash","model"
    ],
    "FİNANSAL RİSKLER": [
        "maliyet","nakit","kredi","demoraj","sigorta","enflasyon","doviz","capex","opex","fatura","tahsilat"
    ],
    "GEOTEKNİK RİSKLERİ": [
        "zemin","jeolojik","geoteknik","foraj","laboratuvar","kaya","yumusak zemin",
        "zayif arastirma","katman","patlatma","catlatma","sew","sev","iksa"
    ],
    "POLİTİK RİSKLER": [
        "grev","gumruk","mevzuat","politik","yargi","savas","salgin","baski"
    ],
    "SÖZLEŞME ve ONAY RİSKLERİ": [
        "sozlesme","onay","hakedis","garanti","yetersiz teknik detay",
        "proje onay sorumlulugu","change order","yuksek standart","claim","variation","vo"
    ],
    "TEDARİKÇİ VE ALTYÜKLENİCİ RİSKLERİ": [
        "tedarik","altyuklenici","stok","mobilizasyon","demobilizasyon",
        "garanti suresi","calinma","hasarlanma","yurt disi","uretim periyodu",
        "muhendislik kapasitesi","malzeme yetersizligi","rfq","otd"
    ],
    "YÖNETSEL RİSKLER": [
        "yonetim","koordinasyon","proje yoneticisi","yetkinlik","talimat",
        "onay sureci","paydas","risk plani","finansman eksikligi","partner catismasi",
        "yonetim modeli","kisisel guven","organizasyon","pmo"
    ],
}

# =========================
#  Kalıp havuzları (çok seçenekli)
#  Not: Aynı anahtar için birden fazla cümle → çeşitlilik.
# =========================
PHRASES: Dict[str, List[str]] = {
    # İnşaat/Uygulama
    "beton": [
        "Beton imalatlarında kalite sapması riski; döküm öncesi check-list ve tedarikçi denetimi güçlendirilsin.",
        "TS EN 206’a uyum ve numune/kür planı eksikliği ret veya rework doğurabilir; planı görünür kılın.",
        "Döküm koşulları (ısı, slump, vibrasyon) kontrol edilmezse dayanım kaybı görülebilir; saha kontrolü sıklaştırılsın."
    ],
    "kalip": [
        "Kalıp/iskelenin uygunsuzluğu göçme ve yüzey hataları üretir; onaylı checklist ve yetkili imza şart.",
        "Kalıp kaçakları ve rijitlik sorunları bitmiş yüzey kalitesini düşürür; pre-pour muayenesi zorunlu olsun."
    ],
    "donati": [
        "Donatı detay hataları çatlak ve dayanım kaybı yaratır; shop-drawing uyum denetimi ve NCR takibi yapılmalı."
    ],
    "boru": [
        "Boru birleşim/hat hasar riski; kaynak WPS/PQR ve NDT/hidrostatik test planı uygulanmalı.",
        "Hatalı malzeme/conta seçimi sızıntı riski doğurur; malzeme eşleşmesi ve izlenebilirlik teyit edilmeli."
    ],
    "kazik": [
        "Kazık imalatında hasar ve sehim; yükleme testleri ve yerleşim toleransları sahada doğrulansın.",
        "Katodik koruma ve kaplama ihmali uzun vadede korozyon riski; koruma planı devreye alınsın."
    ],
    "ekipman": [
        "Kritik ekipman arızası ilerlemeyi durdurur; yedek parça ve bakım planı (MTBF/MTTR) devrede olsun.",
        "Operatör yetkinliği ve vardiya planı boşlukları darboğaz üretir; sertifikasyon ve yedekleme planlayın."
    ],
    "lojistik": [
        "Lojistik aksaklıkları gecikme üretir; alternatif rota/tedarik ve emniyet stok eşiği tanımlansın.",
        "Gümrük/geçiş izinleri gecikmeleri için tampon süre ve evrak kontrol listesi oluşturulmalı."
    ],
    "vinc": [
        "Vinç/duba operasyonlarında devrilme-çarpma riski; rigging planı ve rüzgâr eşiği netleştirilsin.",
        "Kaldırma planı, ekipman sertifikaları ve saha yetkilendirmesi olmadan işe başlanmamalı."
    ],
    "dalgic": [
        "Dalgıç operasyonları için görüş, akıntı ve acil durum protokolü olmadan dalış başlatılmamalı."
    ],
    "topografik": [
        "Topografik ölçüm hataları yayılma etkisi gösterir; kalibrasyon ve bağımsız kontrol noktaları şart."
    ],

    # Çevresel
    "ced": [
        "ÇED gereklilikleri programda kritik kilometre taşı olmalı; şartlar iş programına işlenmeli.",
        "ÇED koşulları için sorumluluk matrisi ve raporlama periyodu netleştirilsin."
    ],
    "deprem": [
        "Deprem etkisi altında kalıcı hasar riski; güncel yönetmeliğe göre performans doğrulaması yapılmalı.",
        "Sismik dayanım ve detaylar (ankraj, dilatasyon) sahada teyit edilmeli."
    ],
    "hava": [
        "Elverişsiz hava pencereleri tamponla yönetilsin; rüzgâr/yağış eşikleri ve durdur-başlat kriterleri tanımlansın.",
        "Hava kaynaklı kayıp günler için kurtarma (recovery) planı hazırlanmalı."
    ],
    "yangin": [
        "Yakıt dolum/boşaltma alanında yangın/patlama riski; T&C ve acil durum tatbikatı zorunlu.",
        "Sıcak çalışma izni ve gaz ölçüm prosedürü uygulanmadan işe başlanmamalı."
    ],
    "sokum": [
        "Söküm ve bertaraf süreçleri için atık yönetimi ve lisanslı taşıma planı hazırlanmalı."
    ],

    # Tasarım
    "tasarim": [
        "Tasarım değişikliği ve revizyon gecikmesi rework üretir; onay SLA ve versiyon kontrolü uygulansın.",
        "RFI akışı ve disiplinler arası koordinasyon toplantıları düzenli işletilmeli."
    ],
    "sartname": [
        "Çelişen/eksik şartnameler uygulamada hata üretir; uyum matrisi ve muafiyet kayıtları oluşturulmalı.",
        "Tedarik teknik şartnamesi ile saha uygulama şartnamesi hizalanmalı."
    ],
    "veri": [
        "Yetersiz saha verisi tasarım riskini artırır; ilave sondaj/ölçüm ve model kalibrasyonu planlanmalı.",
        "As-built veriler toplanmadıkça sonraki paketler başlatılmamalı."
    ],
    "simulasyon": [
        "Dalga/iklim ve köprü üstü simülasyon gereksinimleri zamanında tetiklenmezse program sapar; erken başlatın."
    ],

    # Finans
    "maliyet": [
        "Maliyet artışı riski; aylık sapma analizi ve değer mühendisliği döngüsü kurulmalı.",
        "Fiyat farkı ve eskalasyon maddeleri sözleşmeye eklenmeli."
    ],
    "nakit": [
        "Nakit akışı kırılgan; avans/teminat ve hakediş takvimiyle uyumlu tahsilat planı yapılmalı.",
        "Likidite tamponu ve risk bazlı ödeme planı oluşturulmalı."
    ],
    "enflasyon": [
        "Enflasyon/döviz dalgalanması; hedge ve fiyat farkı mekanizmaları devreye alınmalı."
    ],

    # Geoteknik
    "zemin": [
        "Beklenmeyen zemin davranışı; parametre güncellemesi ve şev/iksa tetik değerleri ile izlenmeli.",
        "Yumuşak zemin ve taşıma gücü riskinde etaplama ve pre-load seçenekleri değerlendirilmeli."
    ],
    "jeolojik": [
        "Jeolojik belirsizlik; ek sondaj ve laboratuvar test planı ile belirsizlik daraltılmalı."
    ],

    # Politik
    "mevzuat": [
        "Mevzuat/gümrük/grev etkileri; senaryo planı ve alternatif tedarik kurgusu oluşturulmalı.",
        "Yeni düzenlemeler için sözleşmesel uyarlama (variation) ve bildirim süreçleri çalıştırılmalı."
    ],

    # Sözleşme/Onay
    "sozlesme": [
        "Belirsiz sözleşme koşulları; kapsam netleştirme, değişiklik yönetimi ve claim dokümantasyonu şart.",
        "Onay sorumlulukları ve SLA’lar net değilse program riski artar; RACI oluşturulmalı."
    ],
    "hakedis": [
        "Hakediş gecikmesi; evrak/atasman süreci ve onay SLA’ları netleştirilerek izlenmeli.",
        "Kesinti/teminat ve tahsilat takvimi finans planıyla hizalanmalı."
    ],

    # Tedarik/Alt yüklenici
    "tedarik": [
        "Tedarik gecikmesi/eksikliği; emniyet stok, alternatif tedarik ve teslim KPI’ları tanımlansın.",
        "Kritik malzemelerde dual-sourcing ve kalite kabul kriterleri net olmalı."
    ],
    "altyuklenici": [
        "Alt yüklenici kapasite/sirkülasyon riski; yeterlilik denetimi ve eğitim planı devreye alınmalı.",
        "Performans KPI’ları (OTD, kalite, HSE) sözleşmeye bağlanmalı."
    ],

    # Yönetim
    "koordinasyon": [
        "Koordinasyon/yönetim zafiyeti; RACI, iletişim planı ve haftalık durum toplantılarıyla giderilmeli.",
        "Disiplinler arası arayüz listesi ve karar kayıtları tutulmalı."
    ],
    "risk plani": [
        "Yetersiz risk yönetim planı; üst risk listesi, tetikleyiciler ve gözden geçirme döngüsü kurulmalı.",
        "Erken uyarı göstergeleri ve sahiplik (owner) ataması net olmalı."
    ],
}

# =========================
#  Dış dosyadan genişletme (opsiyonel)
#  Ortam: AI_SENTENCE_FILE (JSON)
#  Format:
#  {
#    "category_aliases": {"KATEGORI": ["alias1","alias2", ...]},
#    "phrases": {"anahtar": ["cumle1","cumle2", ...]}
#  }
# =========================
def _merge_external():
    path = os.getenv("AI_SENTENCE_FILE", os.path.join("ai_data", "sentences.json"))
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ext_alias = data.get("category_aliases") or {}
        ext_phr = data.get("phrases") or {}
        for k, arr in ext_alias.items():
            if not isinstance(arr, list): continue
            CATEGORY_ALIASES.setdefault(k, [])
            # yeni alias'ları ekle (tekrarları önle)
            cur = set(map(_norm, CATEGORY_ALIASES[k]))
            for v in arr:
                if _norm(v) not in cur:
                    CATEGORY_ALIASES[k].append(v)
        for k, arr in ext_phr.items():
            if not isinstance(arr, list): continue
            PHRASES.setdefault(k, [])
            cur = set(PHRASES[k])
            for v in arr:
                if v not in cur:
                    PHRASES[k].append(v)
    except Exception:
        # sessiz düş — uygulamayı engelleme
        pass

_merge_external()

# =========================
#  Seçim yardımcıları
# =========================
def _collect_keys_from_title(title: str) -> List[str]:
    """
    Başlıktan yakalanan anahtarlar (PHRASES anahtarlarına göre).
    'kaldırma planı' gibi bileşikler için basit içerir kontrolü kullanıyoruz.
    """
    t = _norm(title)
    hits = []
    for kw in PHRASES.keys():
        if _norm(kw) in t:
            hits.append(kw)
    # ek: bazı eşanlamlı minik haritalar
    synonyms = {
        "vinc": ["kran","kaldirma","rigging","barge vinc","duba vinc"],
        "beton": ["dokum","concrete"],
        "kalip": ["kalip/iskelet","formwork","scaffold"],
        "donati": ["rebar","hasir"],
        "sozlesme": ["contract"],
        "hakedis": ["progress payment","interim payment"],
        "tedarik": ["procurement","satin alma","satinalma"],
        "altyuklenici": ["tasaron","tasaron"],
        "tasarim": ["design","revizyon"],
        "sartname": ["spec","specification"],
        "deprem": ["sismik","earthquake"],
        "yangin": ["patlama","fire","explosion"],
        "hava": ["ruzgar","yagis","firtina","weather"],
        "zemin": ["geoteknik","soft soil","yumusak zemin"],
    }
    for canon, syns in synonyms.items():
        if canon in hits: 
            continue
        if _any_in(t, syns):
            hits.append(canon)
    return hits

def _weighted_sample(pool: List[str], k: int, rnd: random.Random) -> List[str]:
    """
    Havuzdan tekrarsız örnekleme; k büyükse tümünü döner.
    Basit karıştırma yeterli; kısıtlı ortamlar için deterministik RNG destekli.
    """
    if k >= len(pool):
        return pool[:]
    items = pool[:]
    rnd.shuffle(items)
    return items[:k]

# =========================
#  Public API
# =========================
def normalize_category_by_title(title: str, fallback: str) -> str:
    """
    Başlıktaki ipuçlarına göre kanonik kategori öner.
    Eşleşme yoksa fallback (ya da 'GENEL').
    """
    t = _norm(title)
    for canon, keys in CATEGORY_ALIASES.items():
        if _any_in(t, keys):
            return canon
    return fallback or "GENEL"

def one_liner(title: str, category: str, num: int = 1, seed: Optional[int] = None) -> str | List[str]:
    """
    Başlık + kategoriye göre 1 ya da N adet kısa öneri cümlesi döndürür.
    - num=1 -> string (geriye dönük uyum)
    - num>1 -> List[str]
    """
    rnd = random.Random(seed)
    title_norm = _norm(title)
    cat_upper = (category or "").upper()

    # 1) Başlıktan anahtarları topla
    keys = _collect_keys_from_title(title_norm)

    # 2) Havuzu oluştur
    pool: List[str] = []
    for k in keys:
        pool.extend(PHRASES.get(k, []))

    # 3) Havuz boşsa kategori tabanlı fallback üret
    if not pool:
        if "İNŞAAT" in cat_upper or "UYGULAMA" in cat_upper:
            pool = [
                "Uygulama kaynaklı kalite/ilerleme riski; kontrol listeleri ve saha denetimi sıkılaştırılsın.",
                "Operasyonel duruşları azaltmak için kritik faaliyetler için ön koşul kontrolü yapılsın."
            ]
        elif "ÇEVRESEL" in cat_upper:
            pool = [
                "Çevresel izin/koşul/afet etkileri program ve önlemlerle yönetilmelidir.",
                "Atık/emisyon/gürültü eşikleri için izleme ve raporlama periyotları netleştirilsin."
            ]
        elif "DİZAYN" in cat_upper or "TASARIM" in cat_upper:
            pool = [
                "Tasarım veri/şartname belirsizliği; RFI ve onay süreçleriyle daraltılsın.",
                "Revizyon kontrolü ve disiplinler arası koordinasyon toplantıları düzenli işletilmeli."
            ]
        elif "FİNANS" in cat_upper:
            pool = [
                "Finansal oynaklık; nakit akışı ve maliyet kontrol mekanizmalarıyla dengelenmelidir.",
                "Likidite tamponu ve sözleşmesel fiyat farkı/hedge mekanizmaları değerlendirilmeli."
            ]
        elif "GEOTEKNİK" in cat_upper:
            pool = [
                "Zemin belirsizliği; ek araştırma ve tetik değerli izlemeyle kontrol altına alınsın.",
                "Taşıma gücü ve oturma riskine karşı etaplama ve iyileştirme seçenekleri değerlendirilmeli."
            ]
        elif "POLİTİK" in cat_upper:
            pool = [
                "Politik/mevzuat etkileri için alternatif senaryo ve sözleşme korumaları gerekir.",
                "Gümrük ve düzenleme değişiklikleri için bildirim ve uyarlama prosedürleri belirlenmeli."
            ]
        elif "SÖZLEŞME" in cat_upper:
            pool = [
                "Sözleşme/onay süreçleri netleştirilmeli, SLA ve değişiklik yönetimi uygulanmalı.",
                "Claim ve değişiklik kayıtları sistematik tutulmalı; kapsam netliği sağlanmalı."
            ]
        elif "TEDARİK" in cat_upper or "ALTYÜKLENİCİ" in cat_upper:
            pool = [
                "Tedarik/altyüklenici riskleri; alternatif kaynak ve teslim KPI’larıyla yönetilsin.",
                "Kritik malzemelerde dual-sourcing ve kalite kabul kriterleri sözleşmeye bağlanmalı."
            ]
        elif "YÖNETSEL" in cat_upper:
            pool = [
                "Yönetim/koordinasyon riskleri; RACI ve düzenli raporlama ile iyileştirilsin.",
                "Karar kayıtları ve iletişim planı olmadan işe başlanmamalı."
            ]
        else:
            pool = [
                "Risk, ilgili süreç kontrolleri ve net sorumluluklarla yönetilmelidir.",
                "Ön koşullar, kalite kontrolleri ve sahiplik atamaları netleştirilsin."
            ]

    # 4) num kadar seç ve döndür
    k = max(1, int(num))
    picked = _weighted_sample(pool, k, rnd)

    if num == 1:
        return picked[0]
    return picked
