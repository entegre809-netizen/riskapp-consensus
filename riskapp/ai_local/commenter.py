# riskapp/ai_local/commenter.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import re as _re

from flask import current_app

from .ps_estimator import PSEstimator
from .engine import AILocal          # ⬅️ DİKKAT: sadece AILocal, ai_complete YOK
from ..models import db, Risk


# ============================
# Yardımcılar (AI + RACI + KPI)
# ============================

def _smart_due(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _normalize(s: str) -> str:
    """Türkçe karakterleri sadeleştir + lower."""
    if not s:
        return ""
    tr_map = str.maketrans({
        "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i",
        "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u"
    })
    return s.translate(tr_map).lower()


def _any_in(text: str, keywords) -> bool:
    t = _normalize(text)
    return any(k in t for k in keywords)


def _unique(seq: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for x in seq:
        key = (x.get("action"), x.get("due"))
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


# ============================
# 1) Keyword kümeleri
# ============================

# Kategori anahtar kümeleri (normalize edilmiş aramayla eşleşir)
KEYSETS = {
    "insaat": [
        "beton", "kalip", "donati", "dokum", "vibrator", "santiye", "saha",
        "betonarme", "formwork", "rebar", "pour", "scaffold"
    ],
    "satinalma": [
        "satinalma", "tedarik", "malzeme", "lojistik", "irsaliye", "siparis",
        "po", "rfq", "tedarikci", "nakliye", "sevkiyat", "warehouse", "supply"
    ],
    "sozlesme": [
        "sozlesme", "legal", "hukuk", "onay", "izin", "reg", "regulasyon",
        "idari sartname", "teknik sartname", "claim", "variation", "vo"
    ],
    "isg_cevre": [
        "isg", "is guvenligi", "kaza", "ramak kala", "cevre", "emisyon", "atik",
        "toz", "gurultu", "ppe", "acil durum", "ced", "emission", "waste", "noise", "spill"
    ],
    "geoteknik": [
        "zemin", "geoteknik", "kazi", "iksa", "zayif zemin", "oturma", "sev", "sev stabilitesi",
        "cpt", "spt", "sonder", "forekazik", "ankraj"
    ],
    "kalite": [
        "kalite", "denetim", "tetkik", "audit", "muayene", "itp", "tutanak", "numune",
        "slump", "ndt", "wps", "pqr", "kalibrasyon", "inspection", "hold point"
    ],
    "pmo": [
        "politik", "organizasyonel", "paydas", "stakeholder", "iletisim plani",
        "raporlama", "kpi", "koordinasyon", "komite"
    ],
    "planlama": [
        "planlama", "program", "zaman cizelgesi", "kritik yol", "cpm",
        "ms project", "primavera", "p6", "gant", "delay", "erteleme",
        "hava", "ruzgar", "yagis", "sicaklik", "weather", "wind", "rain", "temperature", "storm"
    ],
    "mep_elektrik": [
        "elektrik", "og", "ag", "trafo", "scada", "pano", "kablo", "tray", "aydinlatma",
        "topraklama", "kesici", "jenerator", "ups", "megger", "loop test", "komisyoning", "commissioning"
    ],
    "mep_mekanik": [
        "mekanik", "hvac", "chiller", "kazan", "pompa", "yangin", "sprinkler", "tesisat",
        "borulama", "pnid", "basinc testi", "hidrostatik", "duct", "valf", "esanjör", "esanjör"
    ],
    "marine": [
        "deniz", "marine", "rihtim", "iskele", "kazik", "celik kazik", "dolfen", "samandira",
        "batimetri", "akinti", "dalga", "romorkor", "barge", "vinc barge", "mendirek", "dalgakiran", "kran"
    ],
    "tasarim": [
        "tasarim", "cizim", "revizyon", "ifc", "shop drawing", "shopdrawing", "statik",
        "mimari", "clash", "detay", "kesit", "rfi"
    ],
    "teknik_ofis": [
        "teknik ofis", "metraj", "hakedis", "atasman", "boq", "kesif", "birim fiyat",
        "poz", "revize kesif", "maliyet analizi", "progress"
    ],
    "finans": [
        "finans", "butce", "nakit akisi", "cash flow", "fatura", "tahsilat", "teminat",
        "kesinti", "avans", "kur riski", "maliyet", "capex", "opex"
    ],
    "makine_bakim": [
        "ekipman", "makine", "bakim", "ariza", "yedek parca", "operator", "vinc",
        "excavator", "loader", "forklift", "servis", "periyodik kontrol", "rigging", "lifting plan", "winch"
    ],
    "bim_bt": [
        "bim", "model", "revit", "navisworks", "ifc dosyasi", "clash detection",
        "veri tabani", "sunucu", "yedekleme", "network", "cad", "gis"
    ],
    "izin_ruhsat": [
        "ruhsat", "belediye", "imar", "fenni mesul", "tutanak", "resmi yazi", "dilekce",
        "trafik kesme izni", "enkaz izin", "izin sureci"
    ],
    "laboratuvar": [
        "laboratuvar", "numune", "slump", "karot", "cekme testi", "basinc testi",
        "agrega", "granulometri", "ndt", "ultrasonik test"
    ],
    "depo": [
        "depo", "ambar", "stok", "stok sayim", "emniyet stogu", "raf",
        "malzeme teslim", "giris cikis", "stok devir", "ambar fisi"
    ],
    "trafik_lojistik": [
        "trafik", "yol kapama", "yol izin", "guzergah", "güzergah", "servis yolu",
        "site access", "access road", "mobilizasyon", "demobilizasyon", "kamyon",
        "tir", "tır", "nakliye planı", "trafik yönetimi", "traffic management"
    ],
    "paydas_iletisim": [
        "paydas", "paydaş", "stakeholder", "halk", "mahalle", "sikayet", "şikayet",
        "toplanti", "toplantı", "bilgilendirme", "iletişim", "communication",
        "kamuoyu", "yerel halk", "muhtar", "community"
    ],
    "taseron_yonetimi": [
        "taseron", "taşeron", "alt yuklenici", "alt yüklenici", "subcontractor",
        "sub-contractor", "ekip performansi", "ekip performansı", "yetersiz ekip",
        "niteliksiz personel", "vasifsiz", "vasıfsız", "isci", "işçi"
    ],
    "insan_kaynaklari": [
        "personel", "isgucu", "işgücü", "labour", "labor", "operator eksikligi",
        "operatör eksikliği", "vardiya", "fazla mesai", "egitim", "eğitim",
        "yetkinlik", "sertifika", "oryantasyon", "devamsizlik", "devamsızlık"
    ],
    "saha_erisim": [
        "saha erisimi", "saha erişimi", "alan teslimi", "yer teslimi", "mobilizasyon",
        "erişim kısıtı", "access restriction", "kamulaştırma", "kamulastirma",
        "gecis hakki", "geçiş hakkı", "right of way", "parsel", "mülkiyet"
    ],
    "arkeoloji_kultur": [
        "arkeoloji", "arkeolojik", "tarihi eser", "kultur varligi", "kültür varlığı",
        "sit alani", "sit alanı", "koruma kurulu", "heritage", "cultural heritage"
    ],
    "komsu_yapilar": [
        "komsu yapi", "komşu yapı", "bina hasari", "bina hasarı", "çatlak",
        "vibrasyon hasari", "vibrasyon hasarı", "oturma", "deformasyon",
        "settlement", "adjacent building", "third party damage"
    ],
    "enerji_yakit": [
        "enerji", "elektrik kesintisi", "power outage", "yakit", "yakıt",
        "jenerator", "jeneratör", "mazot", "akaryakit", "akaryakıt",
        "enerji maliyeti", "fuel", "diesel"
    ],
    "dijital_veri": [
        "veri", "data", "dokuman", "doküman", "document control", "dokuman kontrol",
        "doküman kontrol", "versiyon", "revizyon takibi", "yanlis dosya",
        "yanlış dosya", "arsiv", "arşiv", "dms", "edms"
    ],
    "hava_deniz": [
        "hava", "hava durumu", "yagis", "yağış", "ruzgar", "rüzgar", "firtina",
        "fırtına", "dalga", "akıntı", "akınti", "sis", "visibility", "metocean",
        "weather window", "deniz kosulu", "deniz koşulu"
    ],
    "maliyet_artisi": [
        "maliyet artisi", "maliyet artışı", "fiyat artisi", "fiyat artışı",
        "enflasyon", "kur", "doviz", "döviz", "price escalation",
        "cost escalation", "butce", "bütçe", "bütçe aşımı", "butce asimi"
    ],
    "tedarik_kritik": [
        "kritik ekipman", "long lead", "uzun teslim", "ithalat", "gümrük",
        "gumruk", "customs", "teslim gecikmesi", "malzeme gecikmesi",
        "tedarik gecikmesi", "procurement delay"
    ],
    "dokumantasyon": [
        "rapor", "form", "tutanak", "checklist", "kontrol listesi", "as-built",
        "as built", "redline", "metod beyanı", "method statement", "prosedür",
        "prosedur", "kayıt", "kayit"
    ],
    "acil_durum": [
        "acil durum", "emergency", "yangin", "yangın", "tahliye", "ilk yardim",
        "ilk yardım", "tatbikat", "kriz", "kaza", "incident", "near miss",
        "ramak kala"
    ],
    "test_devreye_alma": [
        "test", "devreye alma", "commissioning", "pre-commissioning", "sat",
        "fat", "performans testi", "punch", "snag", "kalibrasyon",
        "acceptance test"
    ],
    "tasarim_koordinasyon": [
        "tasarim koordinasyon", "tasarım koordinasyon", "multidisiplin",
        "interface", "arayuz", "arayüz", "koordinasyon", "çakışma",
        "clash", "model koordinasyonu", "ifc koordinasyon"
    ],
    "tedarikci_performans": [
        "tedarikci performansi", "tedarikçi performansı", "supplier performance",
        "gec teslim", "geç teslim", "kalitesiz tedarik", "tedarikci kalite",
        "vendor", "imalatci", "imalatçı"
    ],
    "sozlesme_claim": [
        "claim", "hak talebi", "variation", "vo", "değişiklik emri",
        "degisiklik emri", "süre uzatımı", "sure uzatimi", "ek süre",
        "ek sure", "uyuşmazlık", "uyusmazlik", "dispute"
    ],
    "kalite_malzeme": [
        "malzeme kalite", "kusurlu malzeme", "defolu malzeme", "uygunsuz malzeme",
        "material defect", "nonconforming material", "sertifika eksik",
        "mill test", "mtr", "certificate"
    ],
    "cevre_izin": [
        "çed", "ced", "çevre izni", "cevre izni", "deşarj", "desarj",
        "emisyon izni", "atik izin", "atık izin", "hafriyat döküm",
        "hafriyat dokum", "çevre mevzuatı", "cevre mevzuati"
    ],
}


# ============================
# 2) Kategori -> aksiyon şablonları
# ============================

# Kategori -> aksiyon şablonları (metin, due_gun)
ACTION_TEMPLATES = {
    "insaat": [
        ("Döküm öncesi kalıp ve donatı kontrol listesi eksiksiz tamamlanmalıdır.", 7),
        ("ITP ve muayene-kabul planı revize edilerek saha ekibine bilgilendirme yapılmalıdır.", 10),
        ("TS EN 206 standardına göre numune alma, kür planı ve tedarikçi denetimi yapılmalıdır.", 14),
        ("Ustalara beton yerleştirme ve vibrasyon uygulamaları hakkında kısa saha eğitimi verilmelidir.", 5),
    ],
    "satinalma": [
        ("Kritik malzemeler için alternatif tedarikçi onayı alınmalıdır.", 14),
        ("Satınalma sözleşmelerine gecikme cezası ve hizmet seviyesi şartları eklenmelidir.", 10),
        ("Lojistik süreçlerinde emniyet stok seviyesi ve takip göstergeleri tanımlanmalıdır.", 7),
    ],
    "sozlesme": [
        ("Kritik izin ve onay süreçleri için izleme matrisi oluşturulmalı ve sorumlular atanmalıdır.", 5),
        ("Sözleşmedeki ceza ve mücbir sebep maddeleri gözden geçirilmelidir.", 10),
        ("İşveren ve danışman ile iletişim planı oluşturulmalı, haftalık durum raporu paylaşılmalıdır.", 7),
    ],
    "isg_cevre": [
        ("Çevresel etki planı; toz, gürültü ve atık yönetimi başlıklarını kapsayacak şekilde güncellenmelidir.", 7),
        ("Gürültü ve toz izleme ekipmanlarının kalibrasyonu yapılmalı, kayıt düzeni oluşturulmalıdır.", 10),
        ("Yerel otoritelere yapılacak raporlamaların periyotları ve sorumluları netleştirilmelidir.", 14),
    ],
    "geoteknik": [
        ("Zemin parametreleri güncellenmeli ve tasarım emniyet katsayıları teyit edilmelidir.", 10),
        ("İksa ve şev stabilitesi günlük olarak izlenmeli, tetik değerler tanımlanmalıdır.", 5),
        ("Beklenmeyen zemin koşulları için hak talebi ve keşif prosedürü hazırlanmalıdır.", 14),
    ],
    "kalite": [
        ("Kritik süreçler için haftalık iç tetkik yapılmalı, NCR/CCR kayıtları takip edilmelidir.", 7),
        ("ITP kapsamındaki muayene tutanakları dijital arşive düzenli olarak işlenmelidir.", 10),
    ],
    "pmo": [
        ("Paydaş haritası ve iletişim sıklığı RACI dağılımıyla uyumlu olacak şekilde güncellenmelidir.", 7),
        ("Aylık proje performans raporu, KPI ve trend takibini içerecek şekilde standardize edilmelidir.", 10),
    ],
    "planlama": [
        ("Kritik yol (CPM) ve kaynak yükleri yeniden hesaplanarak güncel program yayımlanmalıdır.", 7),
        ("Hava ve deniz koşulları dikkate alınarak program tamponları revize edilmelidir.", 5),
        ("Gecikme nedenleri analiz edilmeli ve toparlama planı ilgili ekiplerle paylaşılmalıdır.", 10),
    ],
    "mep_elektrik": [
        ("Test ve devreye alma planları ile kontrol listeleri yayımlanmalıdır.", 7),
        ("Topraklama ve izolasyon testleri takvime bağlanmalıdır.", 10),
        ("Kritik ekipmanlar için yedek parça ve stok planı oluşturulmalıdır.", 14),
    ],
    "mep_mekanik": [
        ("Hidrostatik ve basınç test programı ile kabul kriterleri netleştirilmelidir.", 7),
        ("Komisyoning sırası planlanmalı ve ilgili ekipler atanmalıdır.", 10),
        ("Yangın hatları için devreye alma prosedürü hazırlanmalı ve tatbikat yapılmalıdır.", 14),
    ],
    "marine": [
        ("Deniz çalışmaları için metocean çalışma pencereleri ve gerekli izinler teyit edilmelidir.", 5),
        ("Barge, vinç ve rigging planları hazırlanmalı; ekiplerle emniyet brifingi yapılmalıdır.", 7),
        ("Batimetri ve pozisyonlama kayıtları günlük olarak arşivlenmelidir.", 10),
    ],
    "tasarim": [
        ("RFI ve shop drawing onay süreçleri için süre hedefleri netleştirilmelidir.", 7),
        ("Navisworks clash detection raporu hazırlanmalı ve çözüm takip listesi oluşturulmalıdır.", 10),
    ],
    "teknik_ofis": [
        ("Metraj ve BOQ eşleştirmesi yapılarak fark analizi yayımlanmalıdır.", 7),
        ("Hakediş dokümantasyonu, ataşman ve fotoğraf kayıtlarını içerecek şekilde standardize edilmelidir.", 10),
    ],
    "finans": [
        ("Aylık nakit akış projeksiyonu ve sapma analizi ilgili ekiplerle paylaşılmalıdır.", 7),
        ("Teminat, avans ve kesinti takvimleri risk matrisiyle uyumlu hale getirilmelidir.", 10),
    ],
    "makine_bakim": [
        ("Periyodik bakım planları CMMS sistemine işlenmeli ve hatırlatıcılar oluşturulmalıdır.", 7),
        ("Kritik ekipmanlar için MTBF ve MTTR göstergeleri takip edilmelidir.", 10),
    ],
    "bim_bt": [
        ("Model versiyonlama ve yedekleme politikaları uygulanabilir hale getirilmelidir.", 7),
        ("IFC çıktı standartları ve clash threshold değerleri sabitlenmelidir.", 10),
    ],
    "izin_ruhsat": [
        ("Ruhsat ve izin takip matrisi ile sorumlu listesi güncellenmelidir.", 5),
        ("Resmi yazışma şablonları ve dosyalama yapısı standardize edilmelidir.", 10),
    ],
    "laboratuvar": [
        ("Numune alma, kür ve raporlama zincirinde izlenebilirlik güvence altına alınmalıdır.", 7),
        ("Cihaz kalibrasyon planları ve sertifika arşivi kontrol edilmelidir.", 10),
    ],
    "depo": [
        ("Stok sayımı ve emniyet stoğu için minimum/maksimum eşik değerleri tanımlanmalıdır.", 7),
        ("Giriş-çıkış işlemleri ile lot/seri takibi için barkod ve etiket düzeni kurulmalıdır.", 10),
    ],
    "trafik_lojistik": [
        ("Trafik yönetim planı hazırlanmalı ve ilgili kurum onayları alınmalıdır.", 7),
        ("Malzeme sevkiyat saatleri, güzergâh ve araç bekleme alanları netleştirilmelidir.", 10),
        ("Saha giriş-çıkış noktaları için günlük takip ve güvenlik kontrol listesi oluşturulmalıdır.", 5),
    ],
    "paydas_iletisim": [
        ("Paydaş iletişim planı güncellenmeli ve bilgilendirme sıklığı netleştirilmelidir.", 7),
        ("Şikâyet ve geri bildirim kayıtları için tek bir takip listesi oluşturulmalıdır.", 5),
        ("Yerel paydaşlarla düzenli bilgilendirme toplantıları planlanmalıdır.", 14),
    ],
    "taseron_yonetimi": [
        ("Taşeron performansı haftalık olarak ölçülmeli ve eksik kalan işler aksiyon listesine alınmalıdır.", 7),
        ("Taşeron ekipleri için işe başlamadan önce oryantasyon ve saha kuralları bilgilendirmesi yapılmalıdır.", 5),
        ("Kritik taşeronlar için alternatif ekip veya ikinci kaynak planı hazırlanmalıdır.", 14),
    ],
    "insan_kaynaklari": [
        ("Kritik pozisyonlar için yetkinlik matrisi hazırlanmalı ve eksik eğitimler planlanmalıdır.", 10),
        ("Vardiya, devamsızlık ve fazla mesai verileri haftalık olarak takip edilmelidir.", 7),
        ("Sertifika gerektiren görevler için belge kontrolü yapılmadan saha görevlendirmesi yapılmamalıdır.", 5),
    ],
    "saha_erisim": [
        ("Saha erişimi ve alan teslim koşulları için sorumlular ve hedef tarihler netleştirilmelidir.", 7),
        ("Kamulaştırma, geçiş hakkı veya parsel kısıtları için resmi takip matrisi oluşturulmalıdır.", 10),
        ("Erişim kısıtı olan alanlar için alternatif çalışma sırası ve program tamponu hazırlanmalıdır.", 14),
    ],
    "arkeoloji_kultur": [
        ("Olası kültür varlığı bulguları için durdurma ve bildirim prosedürü hazırlanmalıdır.", 7),
        ("Koruma kurulu ve ilgili resmi kurumlarla iletişim sorumluları netleştirilmelidir.", 10),
        ("Saha ekiplerine arkeolojik bulgu farkındalık bilgilendirmesi yapılmalıdır.", 5),
    ],
    "komsu_yapilar": [
        ("Komşu yapılar için başlangıç durum tespiti, fotoğraf kaydı ve çatlak ölçüm planı yapılmalıdır.", 7),
        ("Titreşim ve oturma ölçümleri için izleme noktaları ve alarm eşikleri tanımlanmalıdır.", 10),
        ("Üçüncü taraf hasar bildirimleri için kayıt ve müdahale prosedürü oluşturulmalıdır.", 5),
    ],
    "enerji_yakit": [
        ("Kritik ekipmanlar için yakıt ve enerji sürekliliği planı hazırlanmalıdır.", 7),
        ("Jeneratör, yakıt stoku ve enerji kesintisi senaryoları haftalık olarak kontrol edilmelidir.", 10),
        ("Enerji tüketimi ve yakıt maliyetleri için sapma takibi başlatılmalıdır.", 14),
    ],
    "dijital_veri": [
        ("Doküman kontrol sistemi içinde versiyonlama ve onay akışı netleştirilmelidir.", 7),
        ("Yanlış veya eski revizyon kullanımını önlemek için güncel doküman listesi yayımlanmalıdır.", 5),
        ("Kritik proje dokümanları için düzenli yedekleme ve erişim yetkisi kontrolü yapılmalıdır.", 10),
    ],
    "hava_deniz": [
        ("Hava ve deniz koşullarına göre çalışma pencereleri günlük olarak takip edilmelidir.", 5),
        ("Olumsuz hava koşulları için alternatif iş sırası ve toparlama planı hazırlanmalıdır.", 10),
        ("Rüzgâr, yağış, dalga ve görüş limitleri için durdurma kriterleri tanımlanmalıdır.", 7),
    ],
    "maliyet_artisi": [
        ("Fiyat artışı ve kur riski için maliyet sapma analizi haftalık olarak güncellenmelidir.", 7),
        ("Kritik kalemler için erken satınalma, alternatif tedarik ve fiyat sabitleme seçenekleri değerlendirilmelidir.", 10),
        ("Kontenjan bütçe kullanımı ve onay limitleri proje yönetimi tarafından netleştirilmelidir.", 14),
    ],
    "tedarik_kritik": [
        ("Uzun teslim süreli ekipmanlar için satınalma takip listesi ve kritik tarih planı oluşturulmalıdır.", 7),
        ("Gümrük, ithalat ve lojistik riskleri için alternatif teslim senaryoları hazırlanmalıdır.", 14),
        ("Kritik tedarikler için haftalık tedarikçi ilerleme raporu alınmalıdır.", 5),
    ],
    "dokumantasyon": [
        ("Zorunlu saha kayıtları, tutanaklar ve kontrol listeleri için standart format belirlenmelidir.", 7),
        ("As-built ve redline kayıtları haftalık olarak kontrol edilmelidir.", 10),
        ("Eksik dokümanlar için sorumlu, hedef tarih ve kapanış durumu içeren takip listesi açılmalıdır.", 5),
    ],
    "acil_durum": [
        ("Acil durum planı güncellenmeli ve ekiplerin görev dağılımı netleştirilmelidir.", 7),
        ("Yangın, tahliye ve ilk yardım tatbikatları için uygulama takvimi hazırlanmalıdır.", 14),
        ("Ramak kala ve olay kayıtları kök neden analiziyle birlikte takip edilmelidir.", 5),
    ],
    "test_devreye_alma": [
        ("Test ve devreye alma planı, sorumlular ve kabul kriterleriyle birlikte yayımlanmalıdır.", 7),
        ("Punch list kayıtları önceliklendirilerek kapanış hedef tarihleri belirlenmelidir.", 5),
        ("FAT, SAT ve performans testleri için gerekli dokümanlar önceden kontrol edilmelidir.", 10),
    ],
    "tasarim_koordinasyon": [
        ("Disiplinler arası tasarım koordinasyon toplantıları düzenli hale getirilmelidir.", 7),
        ("Arayüz ve çakışma konuları için tek bir takip listesi oluşturulmalıdır.", 5),
        ("IFC ve model revizyonları için onaylı yayın takvimi hazırlanmalıdır.", 10),
    ],
    "tedarikci_performans": [
        ("Tedarikçi performansı teslimat, kalite ve doküman uygunluğu üzerinden haftalık izlenmelidir.", 7),
        ("Zayıf performans gösteren tedarikçiler için düzeltici faaliyet planı istenmelidir.", 10),
        ("Kritik tedarikçiler için alternatif kaynak ve hızlandırma planı hazırlanmalıdır.", 14),
    ],
    "sozlesme_claim": [
        ("Hak talebi ve değişiklik emri kayıtları için kanıt dosyası düzenli tutulmalıdır.", 5),
        ("Süre uzatımı veya ek maliyet doğuran konular için sözleşme bildirim tarihleri takip edilmelidir.", 7),
        ("Uyuşmazlıkları azaltmak için işveren ve danışmanla erken uyarı toplantıları planlanmalıdır.", 10),
    ],
    "kalite_malzeme": [
        ("Malzeme kabul kriterleri ve sertifika kontrol listesi netleştirilmelidir.", 5),
        ("Uygunsuz malzemeler için karantina alanı ve iade prosedürü uygulanmalıdır.", 7),
        ("Kritik malzemelerde giriş kalite kontrolü ve tedarikçi denetimi yapılmalıdır.", 10),
    ],
    "cevre_izin": [
        ("Çevre izinleri ve mevzuat gereklilikleri için resmi takip matrisi oluşturulmalıdır.", 7),
        ("Hafriyat, deşarj, emisyon ve atık süreçleri için kayıt düzeni oluşturulmalıdır.", 10),
        ("Çevresel uygunsuzluklar için düzeltici faaliyet ve sorumlu takibi yapılmalıdır.", 5),
    ],
}


def _match_keys(text: str) -> List[str]:
    """Metni KEYSETS'e göre tarar ve eşleşen anahtar listesini döndürür."""
    hits: List[str] = []
    for key, kw in KEYSETS.items():
        if _any_in(text, kw):
            hits.append(key)
    return hits


# ============================
# 3) RACI / Departman varsayılanları
# ============================

def _dept_raci_defaults(cat_lower: str) -> Dict[str, Any]:
    """
    Kategori ipuçlarına göre ilgili departmanları ve tipik RACI rollerini öner.
    R: Responsible, A: Accountable, C: Consulted, I: Informed
    """
    rules = [
        (
            [
                "beton", "kalıp", "donatı", "döküm", "vibratör", "şantiye", "saha", "imalat",
                "betoniyer", "fore kazık", "tünel", "kalıp iskelesi", "betonarme", "yapı",
                "uygulama", "derz", "kür", "scaffold", "formwork", "rebar", "pour", "site"
            ],
            {
                "dept": "İnşaat/Şantiye",
                "R": "Saha Şefi",
                "A": "Proje Müdürü",
                "C": ["Kalite Müh.", "Planlama"],
                "I": ["İSG", "Satınalma"],
            },
        ),
        (
            [
                "satınalma", "tedarik", "malzeme", "lojistik", "irsaliye", "sipariş", "po", "rfq",
                "tedarikçi", "nakliye", "kargo", "sevkiyat", "logistics", "procurement",
                "purchase", "supply", "warehouse",
            ],
            {
                "dept": "Satınalma/Lojistik",
                "R": "Satınalma Uzmanı",
                "A": "Satınalma Müdürü",
                "C": ["İnşaat", "Kalite"],
                "I": ["Finans", "Depo"],
            },
        ),
        (
            [
                "sözleşme", "legal", "hukuk", "onay", "izin", "reg", "regülasyon", "yasal",
                "idari şartname", "teknik şartname", "claim", "hak talebi", "itiraz",
                "contract", "subcontract", "variation", "vo", "ek protokol",
            ],
            {
                "dept": "Sözleşme/Hukuk",
                "R": "Sözleşme Uzmanı",
                "A": "Hukuk Müdürü",
                "C": ["Proje Müdürü", "Satınalma"],
                "I": ["İşveren", "Paydaşlar"],
            },
        ),
        (
            [
                "isg", "iş güvenliği", "kaza", "ramak kala", "çevre", "emisyon", "atık", "toz",
                "gürültü", "ppe", "risk analizi", "acil durum", "çed", "cevre", "emission",
                "waste", "noise", "spill",
            ],
            {
                "dept": "İSG/Çevre",
                "R": "İSG/Çevre Müh.",
                "A": "İSG Müdürü",
                "C": ["Şantiye", "Kalite"],
                "I": ["İşveren", "Yerel Otorite"],
            },
        ),
        (
            [
                "zemin", "geoteknik", "kazı", "iksa", "zayıf zemin", "oturma", "şev",
                "şev stabilitesi", "cpt", "spt", "sonder", "forekazık", "ankraj",
            ],
            {
                "dept": "Geoteknik",
                "R": "Geoteknik Müh.",
                "A": "Teknik Ofis Müd.",
                "C": ["Şantiye", "Kalite"],
                "I": ["Danışman"],
            },
        ),
        (
            [
                "kalite", "denetim", "tetkik", "audit", "muayene", "itp", "test planı", "karot",
                "numune", "slump", "ndt", "wps", "pqr", "welder", "kalibrasyon",
                "inspection", "hold point", "surveillance",
            ],
            {
                "dept": "Kalite (QA/QC)",
                "R": "Kalite Müh.",
                "A": "Kalite Müdürü",
                "C": ["Şantiye", "Sözleşme"],
                "I": ["İşveren", "Danışman"],
            },
        ),
        (
            [
                "politik", "organizasyonel", "paydaş", "stakeholder", "iletişim planı",
                "raporlama", "kpi", "yönetim kurulu", "koordinasyon", "komite",
            ],
            {
                "dept": "PMO/Paydaş Yönetimi",
                "R": "PMO Uzmanı",
                "A": "Proje Müdürü",
                "C": ["Hukuk", "İletişim"],
                "I": ["İşveren", "Yerel Yönetim"],
            },
        ),
        (
            [
                "planlama", "program", "zaman çizelgesi", "kritik yol", "cpm", "ms project",
                "primavera", "p6", "gant", "hava", "rüzgar", "yağış", "sıcaklık",
                "hava durumu", "weather", "wind", "delay", "erteleme",
            ],
            {
                "dept": "Planlama",
                "R": "Planlama Uzmanı",
                "A": "Proje Müdürü",
                "C": ["Şantiye", "İSG"],
                "I": ["İşveren"],
            },
        ),
        (
            [
                "elektrik", "og", "ag", "trafo", "kumanda", "scada", "pano", "kablo", "trays",
                "aydınlatma", "topraklama", "kesici", "jenerator", "ups", "elektrifikasyon",
                "test devreye alma", "energize", "megger", "loop test",
            ],
            {
                "dept": "MEP/Elektrik",
                "R": "Elektrik Şefi",
                "A": "MEP Müdürü",
                "C": ["Kalite", "Planlama"],
                "I": ["Satınalma", "İşveren"],
            },
        ),
        (
            [
                "mekanik", "hvac", "chiller", "kazan", "pompa", "yangın", "sprinkler",
                "tesisat", "borulama", "pnid", "basınç testi", "hidrostatik", "commissioning",
                "duct", "blower", "valf", "kolektör", "eşanjör",
            ],
            {
                "dept": "MEP/Mekanik",
                "R": "Mekanik Şefi",
                "A": "MEP Müdürü",
                "C": ["Kalite", "Planlama"],
                "I": ["Satınalma", "İşveren"],
            },
        ),
        (
            [
                "deniz", "marine", "rıhtım", "iskele", "kazık", "çelik kazık", "dolfen",
                "şamandıra", "batimetri", "akıntı", "dalga", "römorkör", "barge", "vinç barge",
                "fener", "mendirek", "dalgakıran", "rıhtım kreni",
            ],
            {
                "dept": "Deniz/Marine İşleri",
                "R": "Marine Şantiye Şefi",
                "A": "Deniz Yapıları Müdürü",
                "C": ["Geoteknik", "Kalite"],
                "I": ["Liman Başkanlığı", "Kıyı Emniyeti"],
            },
        ),
        (
            [
                "tasarım", "çizim", "revizyon", "ifc", "shop drawing", "shopdrawing", "statik",
                "mimari", "koordine", "clash", "detay", "kesit", "proje onayı", "rfi",
            ],
            {
                "dept": "Tasarım/Statik-Mimari",
                "R": "Tasarım Koordinatörü",
                "A": "Teknik Ofis Müd.",
                "C": ["MEP", "Kalite"],
                "I": ["Danışman", "İşveren"],
            },
        ),
        (
            [
                "teknik ofis", "metraj", "hakediş", "ataşman", "boq", "keşif", "birim fiyat",
                "poz", "revize keşif", "progress", "maliyet analizi", "yıllık plan",
            ],
            {
                "dept": "Teknik Ofis",
                "R": "Teknik Ofis Müh.",
                "A": "Teknik Ofis Müd.",
                "C": ["Planlama", "Sözleşme"],
                "I": ["Finans", "Şantiye"],
            },
        ),
        (
            [
                "finans", "bütçe", "nakit akışı", "cash flow", "fatura", "tahsilat",
                "teminat", "kesinti", "avans", "kur riski", "maliyet", "capex", "opex",
            ],
            {
                "dept": "Finans/Bütçe",
                "R": "Finans Uzmanı",
                "A": "Finans Müdürü",
                "C": ["Teknik Ofis", "Satınalma"],
                "I": ["Proje Müdürü"],
            },
        ),
        (
            [
                "ekipman", "makine", "bakım", "arıza", "yedek parça", "operatör", "vinç",
                "excavator", "loader", "forklift", "servis", "kalibrasyon",
                "periyodik kontrol", "lifting plan", "rigging", "winch",
            ],
            {
                "dept": "Makine-Bakım",
                "R": "Bakım Şefi",
                "A": "Makine/Ekipman Müdürü",
                "C": ["İSG", "Şantiye"],
                "I": ["Satınalma", "Depo"],
            },
        ),
        (
            [
                "bim", "model", "revit", "navisworks", "ifc dosyası", "clash detection",
                "veri tabanı", "sunucu", "yedekleme", "network", "cad", "gis",
            ],
            {
                "dept": "BIM/BT",
                "R": "BIM Uzmanı",
                "A": "BIM/BT Müdürü",
                "C": ["Tasarım", "Planlama"],
                "I": ["Tüm Birimler"],
            },
        ),
        (
            [
                "ruhsat", "izin", "belediye", "imar", "fenni mesul", "asgari şantiye",
                "tutanak", "resmi yazı", "dilekçe", "enkaz izin", "trafik kesme izni",
            ],
            {
                "dept": "İzin/Ruhsat",
                "R": "Resmi İşler Sorumlusu",
                "A": "Proje Müdürü",
                "C": ["Hukuk", "PMO"],
                "I": ["Yerel Otorite", "İşveren"],
            },
        ),
        (
            [
                "laboratuvar", "numune", "slump", "karot", "çekme testi", "basınç testi",
                "agrega", "granülometri", "çelik çekme", "ndt", "ultrasonik test",
            ],
            {
                "dept": "Laboratuvar/Test",
                "R": "Lab Teknisyeni",
                "A": "Kalite Müdürü",
                "C": ["Şantiye", "Geoteknik"],
                "I": ["Danışman", "İşveren"],
            },
        ),
        (
            [
                "depo", "ambar", "stok", "stok sayım", "emniyet stoğu", "raf",
                "malzeme teslim", "giriş çıkış", "irsaliye kontrol", "stok devir",
                "ambar fişi",
            ],
            {
                "dept": "Depo/Ambar",
                "R": "Depo Sorumlusu",
                "A": "Lojistik/Depo Müdürü",
                "C": ["Satınalma", "Kalite"],
                "I": ["Finans", "Şantiye"],
            },
        ),
        (
            [
                "hava durumu", "hava", "rüzgar", "yağış", "sıcaklık", "fırtına", "dalga",
                "akıntı", "visibility", "sis", "weather", "wind", "rain",
                "temperature", "storm",
            ],
            {
                "dept": "Planlama",
                "R": "Planlama Uzmanı",
                "A": "Proje Müdürü",
                "C": ["Şantiye", "İSG", "Deniz/Marine İşleri"],
                "I": ["İşveren"],
            },
        ),
    ]

    cat_lower_norm = _normalize(cat_lower or "")

    for keys, cfg in rules:
        if any(k in cat_lower_norm for k in keys):
            return cfg

    # genel varsayılan
    return {
        "dept": "Proje Yönetimi",
        "R": "Risk Sahibi",
        "A": "Proje Müdürü",
        "C": ["Kalite", "Planlama"],
        "I": ["İSG", "Satınalma"],
    }


# ============================
# 4) Aksiyon önerileri
# ============================

def _propose_actions(risk: "Risk") -> List[Dict[str, Any]]:
    """
    Her aksiyon: {dept, R, A, C, I, action, due}
    base RACI: _dept_raci_defaults(cat)
    """
    cat_raw = (risk.category or "")
    text_blob = " ".join([
        risk.category or "",
        risk.title or "",
        risk.description or "",
        getattr(risk, "mitigation", "") or "",
    ])
    base = _dept_raci_defaults(text_blob)

    matched = _match_keys(text_blob)
    actions: List[Dict[str, Any]] = []

    # Eşleşme yoksa genel set
    if not matched:
        actions += [
            {
                **base,
                "action": "Risk için ayrıntılı yöntem beyanı ve kontrol listesi hazırlanmalıdır.",
                "due": _smart_due(7),
            },
            {
                **base,
                "action": "Haftalık izleme formu açılarak trend ve KPI takibi başlatılmalıdır.",
                "due": _smart_due(7),
            },
        ]
        return actions

    # Eşleşmelerin aksiyonlarını topla (en fazla 8 aksiyon, tekrar sil)
    MAX_ACTIONS = 8
    for key in matched:
        for text, days in ACTION_TEMPLATES.get(key, []):
            actions.append({**base, "action": text, "due": _smart_due(days)})
            if len(actions) >= MAX_ACTIONS:
                break
        if len(actions) >= MAX_ACTIONS:
            break

    return _unique(actions)


# ============================
# 5) KPI varsayılanları
# ============================

def _kpis_default(cat_lower: str) -> List[str]:
    cat_lower_norm = _normalize(cat_lower or "")

    common = [
        "Aylık uygunsuzluk (NCR) sayısı 0 olmalıdır.",
        "Yeniden işleme (rework) süresi, toplam işçilik süresinin %2’sini aşmamalıdır.",
    ]

    if "beton" in cat_lower_norm or "kalip" in cat_lower_norm or "donati" in cat_lower_norm or _any_in(cat_lower_norm, KEYSETS["insaat"]):
        return common + [
            "Beton basınç testi başarısızlık oranı %1’i aşmamalıdır.",
            "Slump ve sıcaklık tolerans dışı oranı %2’yi aşmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["satinalma"]):
        return common + [
            "Zamanında teslimat oranı (OTD) en az %95 olmalıdır.",
            "Aylık emniyet stoğu altına düşme olayı 0 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["sozlesme"]):
        return common + [
            "Kritik izin ve onay süreçlerinde gecikme olmamalıdır.",
            "Sözleşme ihlali veya NCR sayısı 0 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["isg_cevre"]):
        return common + [
            "Toz ve gürültü limit aşımı olmamalıdır.",
            "Atık bertarafında uygunsuzluk olmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["geoteknik"]):
        return common + [
            "Şev stabilitesi tetik değer aşımı olmamalıdır.",
            "Zemin parametrelerinin güncellenmesinde gecikme olmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["kalite"]):
        return common + [
            "NCR kapama ortalama süresi 10 günü aşmamalıdır.",
            "ITP adımlarına uyum oranı en az %98 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["planlama"]):
        return common + [
            "Kritik faaliyetlerde gecikme oranı %3’ü aşmamalıdır.",
            "Gantt/P6 haftalık güncelleme tamamlama oranı %100 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["mep_elektrik"]):
        return common + [
            "İzolasyon (megger) test başarı oranı en az %99 olmalıdır.",
            "Elektrik test ve devreye alma sürecinde alan başına punch sayısı 5’i aşmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["mep_mekanik"]):
        return common + [
            "Hidrostatik ve basınç test başarı oranı en az %99 olmalıdır.",
            "HVAC balancing sapması %5’i aşmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["marine"]):
        return common + [
            "Metocean çalışma penceresi dışında çalışma yapılmamalıdır.",
            "Barge ve rigging planlarında uygunsuzluk olmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["tasarim"]):
        return common + [
            "RFI ortalama kapanma süresi 7 günü aşmamalıdır.",
            "Shop drawing onaylarının zamanında tamamlanma oranı en az %95 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["teknik_ofis"]):
        return common + [
            "Metraj ve BOQ fark oranı %1’i aşmamalıdır.",
            "Hakediş tesliminde gecikme olmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["finans"]):
        return common + [
            "Planlanan ve gerçekleşen nakit akışı arasındaki sapma %5’i aşmamalıdır.",
            "Fatura gecikme oranı %2’yi aşmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["makine_bakim"]):
        return common + [
            "Aylık MTBF artışı en az %5 olmalıdır.",
            "Planlı bakım gerçekleşme oranı en az %95 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["bim_bt"]):
        return common + [
            "Haftalık kritik clash sayısı belirlenen hedefin altında tutulmalıdır.",
            "Model versiyonlarının yedekleme uyumu %100 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["izin_ruhsat"]):
        return common + [
            "Kritik izinlerde gecikme olmamalıdır.",
            "Resmi yazışma SLA uyum oranı en az %95 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["laboratuvar"]):
        return common + [
            "Numune izlenebilirlik hatası olmamalıdır.",
            "Kalibrasyon süreçlerinde gecikme olmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["depo"]):
        return common + [
            "Stok sayım uyumsuzluk oranı %1’i aşmamalıdır.",
            "Lot ve seri izlenebilirlik hatası olmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["trafik_lojistik"]):
        return common + [
            "Plan dışı sevkiyat gecikmesi haftalık 0 olmalıdır.",
            "Saha giriş-çıkış kayıt uyumu %100 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["paydas_iletisim"]):
        return common + [
            "Paydaş şikâyetlerine ilk dönüş süresi 2 iş gününü aşmamalıdır.",
            "Açık paydaş aksiyonu sayısı haftalık olarak azaltılmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["taseron_yonetimi"]):
        return common + [
            "Taşeron haftalık iş tamamlama oranı en az %95 olmalıdır.",
            "Taşeron kaynaklı tekrar iş oranı %2’yi aşmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["saha_erisim"]):
        return common + [
            "Alan teslimi veya erişim kaynaklı program sapması haftalık izlenmelidir.",
            "Erişim engeli nedeniyle duran iş sayısı 0 olmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["maliyet_artisi"]):
        return common + [
            "Maliyet sapması aylık %5’i aşmamalıdır.",
            "Kritik maliyet kalemlerinde güncel teklif kontrolü %100 tamamlanmalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["test_devreye_alma"]):
        return common + [
            "Punch list kapanış oranı haftalık en az %90 olmalıdır.",
            "Test tekrar oranı %5’i aşmamalıdır.",
        ]
    if _any_in(cat_lower_norm, KEYSETS["dokumantasyon"]):
        return common + [
            "Eksik doküman sayısı haftalık olarak azaltılmalıdır.",
            "Güncel revizyon kullanım uyumu %100 olmalıdır.",
        ]

    return common


# ============================
# 6) Makale tabanlı manuel kurallar
# ============================

def _risk_text_blob(risk: "Risk") -> str:
    """Kategori + başlık + açıklamayı normalize edilmiş tek text olarak birleştir."""
    parts = [risk.category or "", risk.title or "", risk.description or ""]
    return _normalize(" ".join(parts))


def _paper_rule_summaries(risk: "Risk") -> List[str]:
    """
    Yüklediğin makalelerden çıkarılmış bazı sabit kuralları,
    risk metniyle eşleşirse döndürür.
    Tamamen lokalde, AILocal'den bağımsız çalışır.
    """
    t = _risk_text_blob(risk)
    out: List[str] = []

    # --- Genc 2021: Turkish construction sector, RII/EFA ---

    # Kalifiye olmayan taşeron / işçi / personel
    if any(k in t for k in [
        "alt yuklenici", "altyuklenici", "tasaron", "tasaron", "subcontractor",
        "vasifsiz", "niteliksiz", "unqualified", "yetersiz personel"
    ]):
        out.append(
            "Genc 2021 çalışması, kalifiye olmayan taşeron/işçi/personel kullanımını "
            "Türk inşaat sektöründe en yüksek olasılıklı risklerden biri olarak değerlendirmektedir; "
            "bu nedenle taşeron seçimi, oryantasyon ve düzenli denetim süreçleri kritik önem taşır."
        )

    # Ödeme gecikmeleri / hakediş
    if any(k in t for k in [
        "odeme gecikmesi", "geciken odeme", "gecikmis odeme",
        "hak edis", "hakedis", "payment delay", "delayed payment"
    ]):
        out.append(
            "Aynı çalışmada, ödemelerde gecikme ve hakediş sorunları en olası riskler arasında; "
            "bu nedenle sözleşmede net ödeme takvimi, gecikme faizi ve nakit akış planı tanımlanmalıdır."
        )

    # Enflasyon / fiyat spekülasyonu / kur riski
    if any(k in t for k in [
        "enflasyon", "fiyat artis", "fiyat artis", "fiyat spekulasyon",
        "speku", "kur riski", "doviz", "price escalation", "inflation"
    ]):
        out.append(
            "Genc 2021 sonuçlarına göre enflasyon ve fiyat dalgalanmaları yüksek olasılıklı "
            "dışsal riskler arasında; fiyat farkı maddeleri, kısa vadeli alım sözleşmeleri "
            "ve kur riskini azaltacak finansal araçlar önerilmektedir."
        )

    # Geç change-order / son dakika revizyon
    if any(k in t for k in [
        "change order", "degisiklik emri", "revizyon talebi", "gec gelen revizyon",
        "late change", "gecikmis change"
    ]):
        out.append(
            "Çalışma, geç gelen change-order/değişiklik taleplerinin hem süre hem maliyet "
            "üzerinde kritik etki yaptığını vurguluyor; onaylı değişiklik prosedürü ve "
            "kapsam dondurma tarihleri tanımlanmalıdır."
        )

    # Bütçe aşımı / cost overrun
    if any(k in t for k in [
        "butce asimi", "maliyet artisi", "cost overrun", "budget overrun",
        "butce disi", "butceyi asmasi"
    ]):
        out.append(
            "Genc 2021'de işin beklenen bütçe sınırları içinde tamamlanamaması, en olası "
            "üst seviye risklerden biri; erken aşamada ayrıntılı maliyet kırılımı ve "
            "kontenjan bütçe yönetimi önerilmektedir."
        )

    # --- Satpal 2022: Kurumsal bina projeleri, risk tahsisi ---

    # İş kazası / zayıf İSG
    if any(k in t for k in [
        "is kazasi", "kaza", "safety", "guvenlik", "isg", "poor safety"
    ]):
        out.append(
            "Satpal 2022, kurumsal bina işlerinde iş kazaları ve zayıf iş güvenliğini "
            "ağırlıklı olarak yüklenicinin yönetmesi gereken riskler olarak sınıflandırıyor; "
            "sistematik İSG planı, kısa saha eğitimleri ve düzenli saha denetimleri kritik önem taşır."
        )

    # Malzeme kalitesi / kusurlu malzeme
    if any(k in t for k in [
        "kusurlu malzeme", "defolu malzeme", "malzeme hatasi", "defective material"
    ]):
        out.append(
            "Aynı çalışmada kusurlu malzeme tedariki, tedarik zinciri ve yüklenici "
            "sorumluluğu altında ele alınıyor; tedarikçi onay süreci ve giriş kalite kontrolü "
            "önemli azaltıcı tedbirler olarak belirtilmektedir."
        )

    # İşgücü / ekipman / malzeme bulunabilirliği
    if any(k in t for k in [
        "iscinin bulunmamasi", "iscinin yetersizligi", "isgucu eksikligi", "labour shortage",
        "equipment", "ekipman yok", "malzeme yok", "unavailability of labour", "unavailability of material"
    ]):
        out.append(
            "Satpal 2022, işgücü/ekipman/malzeme bulunabilirliğini yüklenici tarafında "
            "yoğunlaşan önemli bir üretim riski olarak veriyor; alternatif tedarikçiler ve "
            "yedek kapasite planı önerilmektedir."
        )

    # Hava koşulları
    if any(k in t for k in [
        "hava muhalefeti", "unpredictable weather", "siddetli hava", "yagis", "storm", "firtina"
    ]):
        out.append(
            "Çalışmada öngörülemeyen hava koşulları, iş programı ve maliyet üzerinde "
            "önemli etkiye sahip; süre tamponları ve mevsimsellik analizi ile yönetilmesi önerilmektedir."
        )

    # --- Shelake 2022: Tünel projeleri ---

    if any(k in t for k in [
        "tunel", "tunnel", "metro tünel", "tbm", "delgi tünel", "shaft", "lining"
    ]):
        out.append(
            "Shelake 2022, tünel projelerinde jeoteknik belirsizlikler ve yeraltı koşullarının "
            "yetersiz analizinin ciddi süre ve maliyet aşımlarına yol açtığını gösteriyor; "
            "erken jeoteknik kampanya, kademeli tasarım ve senaryo bazlı programlama tavsiye ediliyor."
        )

    # --- Ke et al. 2010: PPP risk allocation ---

    if any(k in t for k in [
        "ppp", "public private", "yap islet devret", "bot", "concession",
        "imtiyaz sozlesmesi", "ozel finansman"
    ]):
        out.append(
            "Ke vd. 2010, PPP projelerinde politik/hukuki makro risklerin genelde kamu "
            "tarafında tutulduğunu, proje-özel meso risklerin daha çok özel sektöre "
            "aktarılabildiğini, operasyonel mikro risklerin ise çoğunlukla yüklenicide "
            "toplandığını raporlamaktadır; bu risk için taraflara göre adil paylaşım kurgulanmalı."
        )

    # --- Genel metodoloji makaleleri: Akintoye 1997, Dziadosz 2015 vs. ---

    # Eğer hiçbir spesifik tetik yoksa ya da çok genel bir riskse, metodoloji notları ekle
    if not out:
        out.append(
            "Akintoye & MacLeod 1997, inşaat projelerinde risklerin çoğunlukla maliyet, süre "
            "ve kalite hedeflerine etkisi üzerinden algılandığını ve yönetimin çoğu zaman "
            "sezgiye bırakıldığını belirtiyor; yapılandırılmış risk analizi (senaryo, hassasiyet, "
            "olasılık-etki matrisleri) ile daha sağlam kararlar alınabiliyor."
        )
        out.append(
            "Dziadosz & Rejment 2015, risk yönetim sürecini üç çekirdeğe indiriyor: tanımla, "
            "nicelleştir, tepki ver; projede hem nitel uzman görüşü hem RII gibi nicel araçların "
            "beraber kullanılması önerilmektedir."
        )

    # Aynı cümleleri tekrar yazmamak için uniq yap
    seen: set[str] = set()
    uniq: List[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


# ============================
# 7) Ana fonksiyon
# ============================

def make_ai_risk_comment(risk_id: int) -> str:
    r = Risk.query.get(risk_id)
    if not r:
        return "⚠️ Risk bulunamadı."

    # 1) P/S (DB + Excel priors + makale heuristikleri) — HATALARA DAYANIKLI
    hint: Optional[Dict[str, Any]] = None
    try:
        ps = PSEstimator(alpha=5.0)
        ps.fit(db.session)
        hint = ps.suggest(r.category or None)
    except Exception as e:
        current_app.logger.exception("PSEstimator hata verdi: %s", e)
        hint = None

    # 2) Benzer kayıtlar / makale kuralları (bağlam) — lokal AI yoksa sessizce devam et
    rules: List[Dict[str, Any]] = []
    try:
        ai = AILocal.load_or_create()
        query = f"{r.category or ''} {r.title or ''} {r.description or ''}"
        hits = ai.search(query, k=5)
        rules = [h for h in hits if h.get("label") == "paper_rule"]
    except Exception as e:
        current_app.logger.exception("AILocal.search hata verdi: %s", e)
        rules = []

    # 3) Aksiyonlar / KPI’lar (departman + RACI dahil)
    cat_lower = (r.category or "").lower()
    actions = _propose_actions(r)
    kpis = _kpis_default(cat_lower)
    close_criteria = "Risk, arka arkaya 8 hafta boyunca KPI hedefleri sağlandığında ve son 2 ayda uygunsuzluk (NCR) oluşmadığında kapatılabilir."

    # 4) Metni derle
    lines: List[str] = []
    lines.append(f"🤖 **AI Önerisi — {r.title or 'Risk'}**")
    lines.append(f"**Kategori:** {r.category or '—'}")
    lines.append(f"**Açıklama:** {r.description or '—'}\n")

    # --- Sayısal özet ---
    lines.append("### 1) Risk Skoru Özeti")
    if hint:
        try:
            n_cat = hint.get("n_cat") or (0, 0)
            n_all = hint.get("n_all") or (0, 0)
            lines.append(
                f"- Sistem, bu risk için tahmini olasılığı **P={hint.get('p', '-')}** "
                f"ve tahmini şiddeti **S={hint.get('s', '-')}** olarak önermektedir. "
                f"Bu tahmin; kategori geçmişi, benzer risk kayıtları ve mevcut veri örnekleri dikkate alınarak oluşturulmuştur "
                f"(kaynak: {hint.get('source', '-')}, P örneği: {n_cat[0]}/{n_all[0]}, S örneği: {n_cat[1]}/{n_all[1]})."
            )
            if hint.get("applied_rules"):
                lines.append(
                    "- Uygulanan makale kuralları: "
                    + ", ".join(hint.get("applied_rules", []))
                )
        except Exception as e:
            current_app.logger.exception("hint formatı bozuk: %s", e)
            lines.append("- P/S tahmini üretilemedi (format hatası).")
    else:
        lines.append("- P/S tahmini üretilemedi (yeterli veri yok ya da model hatası).")

    # --- Departman & RACI ---
    lines.append("\n### 2) Sorumlu Departman ve RACI Dağılımı")
    if actions:
        ex = actions[0]
        C0 = ", ".join(ex["C"]) if isinstance(ex["C"], list) else ex["C"]
        I0 = ", ".join(ex["I"]) if isinstance(ex["I"], list) else ex["I"]
        lines.append(f"- **Departman:** {ex['dept']}")
        lines.append(
            f"- **R (Sorumlu):** {ex['R']} | "
            f"**A (Hesap Veren):** {ex['A']} | "
            f"**C (Danışılan):** {C0} | "
            f"**I (Bilgilendirilen):** {I0}"
        )
    else:
        lines.append("- Bu kategori için hazır RACI bulunamadı, manuel belirlenmeli.")

    # --- Aksiyon Planı ---
    lines.append("\n### 3) Aksiyon Planı")
    if actions:
        for i, a in enumerate(actions, 1):
            C = ", ".join(a["C"]) if isinstance(a["C"], list) else a["C"]
            I = ", ".join(a["I"]) if isinstance(a["I"], list) else a["I"]
            lines.append(
                f"{i}. **{a['action']}**\n"
                f"   - **Termin:** {a['due']}\n"
                f"   - **RACI:** R: {a['R']} · A: {a['A']} · C: {C} · I: {I}"
            )
    else:
        lines.append("- Otomatik aksiyon üretilmedi, proje ekibi ile aksiyon seti netleştirilmeli.")

    # --- KPI'lar ---
    lines.append("\n### 4) İzleme Göstergeleri")
    if kpis:
        for k in kpis:
            lines.append(f"- {k}")
    else:
        lines.append("- Bu kategori için hazır KPI önerisi bulunamadı.")

    # --- Kapanış kriteri ---
    lines.append("\n### 5) Kapanış Kriteri")
    lines.append(f"- {close_criteria}")

    # --- Makale / literatür bağlamı ---
    paper_notes = _paper_rule_summaries(r)
    if paper_notes or rules:
        lines.append("\n### 6) Literatür ve Akademik Bağlam")

        if paper_notes:
            lines.append("**Seçilmiş akademik bulgular (manuel gömülü kurallar):**")
            for note in paper_notes:
                lines.append(f"- {note}")

        if rules:
            lines.append("\n**Lokal AI indeksinden eşleşen kurallar:**")
            for rr in rules:
                txt = rr.get("text", "")
                src = rr.get("source", "")
                if src:
                    lines.append(f"- {txt} _(kaynak: {src})_")
                else:
                    lines.append(f"- {txt}")

    return "\n".join(lines)
