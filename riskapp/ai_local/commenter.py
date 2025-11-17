# riskapp/ai_local/commenter.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple
import re as _re

from flask import current_app

from .ps_estimator import PSEstimator
from .engine import AILocal, ai_complete
from ..models import db, Risk, Comment, Suggestion


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
}

# Kategori -> aksiyon şablonları (metin, due_gun)
ACTION_TEMPLATES = {
    "insaat": [
        ("Dokum oncesi Kalip & Donati Checklist %100 tamamlansin", 7),
        ("ITP ve Muayene-Kabul plani revize edilip saha ekibine brief verilsin", 10),
        ("TS EN 206’a gore numune alma-kur plani ve tedarikci denetimi yapilsin", 14),
        ("Ustalara beton yerlestirme & vibrasyon toolbox talk (egitim)", 5),
    ],
    "satinalma": [
        ("Kritik malzemeler icin ikincil tedarikci onayi (dual sourcing)", 14),
        ("Satinalma sozlesmelerine gecikme cezasi & SLA maddeleri eklensin", 10),
        ("Lojistikte emniyet stok seviyesi ve takip KPI’lari tanimlansin", 7),
    ],
    "sozlesme": [
        ("Kritik izin/onaylar icin izleme matrisi ve sorumlu atamasi", 5),
        ("Sozlesme risk maddeleri (ceza/force majeure) gozden gecirme", 10),
        ("Isveren/danisman iletisim plani ve haftalik durum raporu", 7),
    ],
    "isg_cevre": [
        ("Cevresel Etki Plani guncelleme (toz, gurultu, atik yonetimi)", 7),
        ("Izleme ekipmani (gurultu/toz) kalibrasyon ve kayit duzeni", 10),
        ("Yerel otoriteye raporlama periyotlari ve sorumlular netlesin", 14),
    ],
    "geoteknik": [
        ("Zemin parametreleri guncellenip tasarim emniyet katsayilari teyit", 10),
        ("Iksa/sev stabilitesi gunluk izleme ve tetik degerleri", 5),
        ("Beklenmeyen zemin kosul proseduru (claim/KEsIF) hazir", 14),
    ],
    "kalite": [
        ("Kritik sureclere ic tetkik (haftalik) ve NCR/CCR takibi", 7),
        ("ITP’lerde muayene tutanaklari dijital arsive islesin", 10),
    ],
    "pmo": [
        ("Paydas haritasi ve iletisim frekansi (RACI ile hizali) guncellensin", 7),
        ("Aylik proje performans raporu (KPI/Trend) standardize edilsin", 10),
    ],
    "planlama": [
        ("Kritik yol (CPM) ve kaynak yukleri yeniden hesaplanip yayimlansin", 7),
        ("Hava/deniz kosullari icin program tamponlari (float) revize edilsin", 5),
        ("Gecikme nedenleri analizi ve toparlama plani (recovery) paylasilsin", 10),
    ],
    "mep_elektrik": [
        ("Test & Devreye Alma (T&C) planlari ve checklist’leri yayinlansin", 7),
        ("Topraklama/izolasyon (megger) testleri takvime baglansin", 10),
        ("Kritik ekipman icin yedek parca/stok plani olussun", 14),
    ],
    "mep_mekanik": [
        ("Hidrostatik/basinç test programi ve kabul kriterleri netlestsin", 7),
        ("Komisyoning sirasi (HVAC balancing vb.) planla ve ekip ata", 10),
        ("Yangin hatlari icin devreye alma proseduru ve tatbikat", 14),
    ],
    "marine": [
        ("Deniz calismalari icin metocean pencereleri ve izinler teyit", 5),
        ("Barge/vinc rigging planlari ve emniyet brifingi", 7),
        ("Batimetri/posizyonlama kayitlari gunluk arsivlensin", 10),
    ],
    "tasarim": [
        ("RFI/Shop drawing akisi ve onay SLA’lari netlestsin", 7),
        ("Clash detection (Navis) raporu ve cozum takip listesi", 10),
    ],
    "teknik_ofis": [
        ("Metraj-BOQ eslestirme ve fark analizi (variance) yayinlansin", 7),
        ("Hak edis dokumantasyonu (atasman/foto) standardize edilsin", 10),
    ],
    "finans": [
        ("Aylik nakit akis projeksiyonu ve sapma analizi (EV/MS) paylas", 7),
        ("Teminat/avans/kesinti takvimleri risk matrisi ile hizalansin", 10),
    ],
    "makine_bakim": [
        ("Periyodik bakim planlari (OEM) CMMS’e islenip hatirlatici ac", 7),
        ("Kritik ekipman icin ariza MTBF/MTTR KPI’lari takip edilsin", 10),
    ],
    "bim_bt": [
        ("Model versiyonlama ve yedekleme politikalari uygulanir olsun", 7),
        ("IFC cikti standartlari ve clash threshold degerleri sabitlensin", 10),
    ],
    "izin_ruhsat": [
        ("Ruhsat/izin takip matrisi ve sorumlu listesi guncellensin", 5),
        ("Resmi yazisma sablonlari ve dosyalama agaci standardize edilsin", 10),
    ],
    "laboratuvar": [
        ("Numune alma/kur/raporlama zinciri (traceability) garanti altina alınsın", 7),
        ("Cihaz kalibrasyon planlari ve sertifika arsivi kontrol edilsin", 10),
    ],
    "depo": [
        ("Stok sayim ve emniyet stogu esik degerleri (min/max) tanimlansin", 7),
        ("Giris-cikis ve lot/seri takibi icin barkod/etiket duzeni kurulsun", 10),
    ],
}


def _match_keys(text: str) -> List[str]:
    """Metni KEYSETS'e gore tarar, eslesen anahtar listesi dondurur."""
    hits: List[str] = []
    for key, kw in KEYSETS.items():
        if _any_in(text, kw):
            hits.append(key)
    return hits


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


def _propose_actions(risk: "Risk") -> List[Dict[str, Any]]:
    """
    Her aksiyon: {dept, R, A, C, I, action, due}
    base RACI: _dept_raci_defaults(cat)
    """
    cat_raw = (risk.category or "")
    base = _dept_raci_defaults(cat_raw)

    matched = _match_keys(cat_raw)
    actions: List[Dict[str, Any]] = []

    # Eşleşme yoksa genel set
    if not matched:
        actions += [
            {
                **base,
                "action": "Risk icin ayrintili metod beyanı ve kontrol listesi hazirlanmasi",
                "due": _smart_due(7),
            },
            {
                **base,
                "action": "Haftalik izleme formu ac; trend/KPI takibi baslasin",
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


def _kpis_default(cat_lower: str) -> List[str]:
    cat_lower_norm = _normalize(cat_lower or "")

    common = [
        "Uygunsuzluk (NCR) sayisi = 0 / ay",
        "Rework saatleri ≤ toplam isçilik saatinin %2’si",
    ]

    if "beton" in cat_lower_norm or "kalip" in cat_lower_norm or "donati" in cat_lower_norm or _any_in(cat_lower_norm, KEYSETS["insaat"]):
        return common + [
            "Beton basinç testi basarisizlik orani ≤ %1",
            "Slump/sicaklik tolerans disi orani ≤ %2",
        ]
    if _any_in(cat_lower_norm, KEYSETS["satinalma"]):
        return common + [
            "OTD (On-Time Delivery) ≥ %95",
            "Emniyet stogu altina dusus olay sayisi = 0 / ay",
        ]
    if _any_in(cat_lower_norm, KEYSETS["sozlesme"]):
        return common + [
            "Kritik izin/onay gecikmesi = 0",
            "Sozlesme ihlal/NCR sayisi = 0",
        ]
    if _any_in(cat_lower_norm, KEYSETS["isg_cevre"]):
        return common + [
            "Toz/gurultu limit asimlari = 0",
            "Atik bertaraf uygunsuzlugu = 0",
        ]
    if _any_in(cat_lower_norm, KEYSETS["geoteknik"]):
        return common + [
            "Sev stabilitesi ihlal (trigger asimi) = 0",
            "Zemin parametre guncelleme gecikmesi = 0",
        ]
    if _any_in(cat_lower_norm, KEYSETS["kalite"]):
        return common + [
            "NCR kapama ort. suresi ≤ 10 gun",
            "ITP adim uyum orani ≥ %98",
        ]
    if _any_in(cat_lower_norm, KEYSETS["planlama"]):
        return common + [
            "Kritik faaliyet gecikme orani ≤ %3",
            "Gantt/P6 haftalik guncelleme tamamlama orani = %100",
        ]
    if _any_in(cat_lower_norm, KEYSETS["mep_elektrik"]):
        return common + [
            "Izolasyon (megger) test basari orani ≥ %99",
            "T&C (elektrik) punch sayisi ≤ 5 / alan",
        ]
    if _any_in(cat_lower_norm, KEYSETS["mep_mekanik"]):
        return common + [
            "Hidrostatik/basinç test basari orani ≥ %99",
            "HVAC balancing sapma ≤ %5",
        ]
    if _any_in(cat_lower_norm, KEYSETS["marine"]):
        return common + [
            "Metocean pencere disi calisma olayi = 0",
            "Barge/rigging plan uygunsuzlugu = 0",
        ]
    if _any_in(cat_lower_norm, KEYSETS["tasarim"]):
        return common + [
            "RFI ort. kapanma suresi ≤ 7 gun",
            "Shop drawing onay zamaninda tamamlama ≥ %95",
        ]
    if _any_in(cat_lower_norm, KEYSETS["teknik_ofis"]):
        return common + [
            "Metraj–BOQ fark orani ≤ %1",
            "Hak edis teslim gecikmesi = 0",
        ]
    if _any_in(cat_lower_norm, KEYSETS["finans"]):
        return common + [
            "Nakit akis sapma (plan vs gercek) ≤ %5",
            "Fatura gecikme orani ≤ %2",
        ]
    if _any_in(cat_lower_norm, KEYSETS["makine_bakim"]):
        return common + [
            "MTBF artisi (aylik) ≥ %5",
            "Planli bakim gerceklesme orani ≥ %95",
        ]
    if _any_in(cat_lower_norm, KEYSETS["bim_bt"]):
        return common + [
            "Clash sayisi (kritik) ≤ X/hafta (hedef belirlenmeli)",
            "Model versiyonlari yedekleme uyumu = %100",
        ]
    if _any_in(cat_lower_norm, KEYSETS["izin_ruhsat"]):
        return common + [
            "Kritik izin gecikmesi = 0",
            "Resmi yazisma SLA uyum orani ≥ %95",
        ]
    if _any_in(cat_lower_norm, KEYSETS["laboratuvar"]):
        return common + [
            "Numune izlenebilirlik (traceability) hatasi = 0",
            "Kalibrasyon gecikmesi = 0",
        ]
    if _any_in(cat_lower_norm, KEYSETS["depo"]):
        return common + [
            "Stok sayim uyumsuzluk orani ≤ %1",
            "Lot/seri izlenebilirlik hatasi = 0",
        ]

    return common


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
    close_criteria = "Arka arkaya 8 hafta KPI’lar hedefte + 2 ay uygunsuzluk (NCR) sıfır"

    # 4) Metni derle
    lines: List[str] = []
    lines.append(f"🤖 **AI Önerisi — {r.title or 'Risk'}**")
    lines.append(f"**Kategori:** {r.category or '—'}")
    lines.append(f"**Açıklama:** {r.description or '—'}\n")

    # --- Sayısal özet ---
    lines.append("### 1) Sayısal Özet")
    if hint:
        try:
            n_cat = hint.get("n_cat") or (0, 0)
            n_all = hint.get("n_all") or (0, 0)
            lines.append(
                f"- Tahmini Olasılık **P={hint.get('p', '-')}**, "
                f"Şiddet **S={hint.get('s', '-')}** "
                f"(kaynak: {hint.get('source', '-')} "
                f"örnek: P {n_cat[0]}/{n_all[0]}, "
                f"S {n_cat[1]}/{n_all[1]})"
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
    lines.append("\n### 2) Departman & RACI")
    if actions:
        ex = actions[0]
        C0 = ", ".join(ex["C"]) if isinstance(ex["C"], list) else ex["C"]
        I0 = ", ".join(ex["I"]) if isinstance(ex["I"], list) else ex["I"]
        lines.append(f"- **Departman:** {ex['dept']}")
        lines.append(f"- **R:** {ex['R']}  | **A:** {ex['A']}  | **C:** {C0}  | **I:** {I0}")
    else:
        lines.append("- Bu kategori için hazır RACI bulunamadı, manuel belirlenmeli.")

    # --- Aksiyon Planı ---
    lines.append("\n### 3) Ne Yapılacak? (Aksiyon Planı)")
    if actions:
        for i, a in enumerate(actions, 1):
            C = ", ".join(a["C"]) if isinstance(a["C"], list) else a["C"]
            I = ", ".join(a["I"]) if isinstance(a["I"], list) else a["I"]
            lines.append(
                f"{i}. **{a['action']}** — **Termin:** {a['due']}  \n"
                f"   R:{a['R']} · A:{a['A']} · C:{C} · I:{I}"
            )
    else:
        lines.append("- Otomatik aksiyon üretilmedi, proje ekibi ile aksiyon seti netleştirilmeli.")

    # --- KPI'lar ---
    lines.append("\n### 4) İzleme Göstergeleri (KPI)")
    if kpis:
        for k in kpis:
            lines.append(f"- {k}")
    else:
        lines.append("- Bu kategori için hazır KPI önerisi bulunamadı.")

    # --- Kapanış kriteri ---
    lines.append("\n### 5) Kapanış Kriteri")
    lines.append(f"- {close_criteria}")

    # --- Makale bağlamı ---
    if rules:
        lines.append("\n### 6) Makale Bağlamı")
        for rr in rules:
            lines.append(f"- {rr.get('text', '')}")

    return "\n".join(lines)
