# riskapp/models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# -------------------------------------------------
# P×S EŞİKLERİ  (1..25 ölçeği)
# -------------------------------------------------
# Öneri (P×S):
#   0..5   → acceptable
#   6..11  → low
#   12..19 → moderate
#   20..25 → critical
PS_CRITICAL_MIN  = 20
PS_MODERATE_MIN  = 12
PS_LOW_MIN       = 6


# --------------------------------
# Kategori (RiskCategory)
# --------------------------------
class RiskCategory(db.Model):
    """
    Kategorileri ayrı bir tabloda tutuyoruz. Şimdilik Suggestion.category
    string alanı kullanılmaya devam ediyor; bu tablo yönetim/rapor tarafında
    kategori CRUD ve meta (kod, renk, açıklama) içindir.
    """
    __tablename__ = "risk_categories"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), unique=True, nullable=False, index=True)  # görünen ad
    code        = db.Column(db.String(32), unique=True)                                # kısa kod (opsiyonel)
    color       = db.Column(db.String(16))                                             # #RRGGBB (opsiyonel)
    description = db.Column(db.Text)                                                   # açıklama (opsiyonel)
    is_active   = db.Column(db.Boolean, default=True, nullable=False)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<RiskCategory {self.name}>"


# --------------------------------
# Çoklu kategori eşleme tablosu
# --------------------------------
class RiskCategoryRef(db.Model):
    """
    Bir risk ile bir veya daha fazla kategori arasındaki ilişki.
    Geriye uyumluluk için Risk.category string alanı da tutulur.
    """
    __tablename__ = "risk_category_ref"

    risk_id = db.Column(db.Integer, db.ForeignKey("risks.id"), primary_key=True)
    name    = db.Column(db.String(120), primary_key=True, index=True)

    def __repr__(self) -> str:
        return f"<RiskCategoryRef risk_id={self.risk_id} name={self.name!r}>"


# --------------------------------
# Risk
# --------------------------------
class Risk(db.Model):
    __tablename__ = "risks"

    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), nullable=False, index=True)
    category    = db.Column(db.String(100), nullable=True, index=True)  # not: string olarak kalıyor (geri uyumluluk)
    description = db.Column(db.Text, nullable=True)
    owner       = db.Column(db.String(120), nullable=True)
    status      = db.Column(db.String(50), default="Open", index=True)

    # --- Ek alanlar ---
    risk_type   = db.Column(db.String(20), nullable=True)   # "product" | "project" | ...
    responsible = db.Column(db.String(120), nullable=True)  # Sorumlu kişi/ekip
    mitigation  = db.Column(db.Text, nullable=True)         # Önlemler / faaliyetler

    # İş Programı / Etki Süresi alanları
    duration    = db.Column(db.String(100), nullable=True)  # Etki süresi (örn: 6 ay, proje boyunca)
    start_month = db.Column(db.String(20),  nullable=True)  # Başlangıç ayı (YYYY-MM)
    end_month   = db.Column(db.String(20),  nullable=True)  # Bitiş ayı (YYYY-MM)

    # Çoklu proje desteği
    project_id  = db.Column(db.Integer, index=True)         # ProjectInfo.id ile eşleştirilir (FK opsiyonel)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- İlişkiler ---
    evaluations = db.relationship(
        "Evaluation", backref="risk", cascade="all, delete-orphan", lazy=True
    )
    comments = db.relationship(
        "Comment", backref="risk", cascade="all, delete-orphan", lazy=True
    )

    # Çoklu kategori ilişkisi
    categories_m = db.relationship(
        "RiskCategoryRef",
        cascade="all, delete-orphan",
        lazy="joined",
        backref="risk"
    )

    # Mitigation ilişkisi (YENİ)
    mitigations = db.relationship(
        "Mitigation",
        backref="risk",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Mitigation.id.desc()"
    )

    # ---------- Yardımcılar: Çoklu kategori ----------
    @property
    def categories_list(self):
        """Riskin tüm kategorilerini liste olarak döner."""
        return [rc.name for rc in (self.categories_m or [])]

    def set_categories(self, names):
        """
        Çoklu kategori set et. Boşlukları temizler, yinelenenleri atar.
        İlk kategori geriye uyumluluk için self.category'ye de yazılır.
        """
        uniq = sorted({(n or "").strip() for n in names if n and n.strip()})
        self.categories_m = [RiskCategoryRef(name=n) for n in uniq]
        self.category = uniq[0] if uniq else None  # geri uyumluluk

    # ---------- 2D METRİKLER (P×S) ----------
    def avg_prob(self):
        vals = [e.probability for e in self.evaluations if e.probability is not None]
        return (sum(vals) / len(vals)) if vals else None

    def avg_sev(self):
        vals = [e.severity for e in self.evaluations if e.severity is not None]
        return (sum(vals) / len(vals)) if vals else None

    def avg_det(self):
        # D artık kullanılmıyor (geriye uyum için metod var ama hep None döner)
        return None

    def score(self):
        """
        Olasılık × Şiddet (1–25). P×S ortalamalarından hesaplanır.
        """
        ap, asv = self.avg_prob(), self.avg_sev()
        if ap is None or asv is None:
            return None
        return round(ap * asv, 2)

    # ---------- GERİYE UYUMLULUK: "RPN" adları P×S'yi temsil ediyor ----------
    def last_rpn(self):
        """
        Eski API'yi bozmamak için: son değerlendirmenin P×S değeri (Detection yok sayılır).
        """
        if not self.evaluations:
            return None
        last = sorted(
            self.evaluations,
            key=lambda e: e.created_at or datetime.min
        )[-1]
        return last.rpn()  # Evaluation.rpn() artık P×S döner

    def avg_rpn(self):
        """
        Eski API ismiyle ortalama P×S.
        Tablolarda/raporlarda "RPN" gösterimi kullanan yerleri kırmamak için isim değişmedi.
        """
        vals = [e.rpn() for e in self.evaluations if e.rpn() is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def score_band(self):
        """
        UI'da renk/şiddet bandı: low / mid / high (P×S skoruna göre)
        (Bu proje içinde /schedule görünümünde kullanılabilir)
        """
        s = self.score()
        if s is None:
            return None
        if s <= 6:
            return "low"
        if s <= 15:
            return "mid"
        return "high"

    def grade(self):
        """
        Eski 'grade' çağrılarını da P×S eşiklerine uyarladık.
        Dönüş: 'critical' / 'moderate' / 'low' / 'acceptable'
        """
        ps = self.avg_rpn()  # artık P×S
        if ps is None:
            return None
        if ps >= PS_CRITICAL_MIN:
            return "critical"
        if ps >= PS_MODERATE_MIN:
            return "moderate"
        if ps >= PS_LOW_MIN:
            return "low"
        return "acceptable"

    def __repr__(self):
        return f"<Risk id={self.id} title={self.title!r} status={self.status}>"


# --------------------------------
# Mitigation (YENİ)
# --------------------------------
class Mitigation(db.Model):
    """
    Bir Risk için tanımlanan somut önlemler/aksiyonlar.
    """
    __tablename__ = "mitigation"

    id = db.Column(db.Integer, primary_key=True)
    risk_id = db.Column(db.Integer, db.ForeignKey("risks.id"), nullable=False, index=True)

    title = db.Column(db.String(200), nullable=False)
    owner = db.Column(db.String(120), nullable=True)           # sorumlu kişi/ekip
    status = db.Column(db.String(32), nullable=False, default="planned")
    # planned | in_progress | done | not_applicable

    due_date = db.Column(db.Date, nullable=True)
    cost = db.Column(db.Float, nullable=True)                  # tahmini maliyet
    effectiveness = db.Column(db.Integer, nullable=True)       # 1–5 (etkinlik puanı)

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Mitigation id={self.id} risk_id={self.risk_id} title={self.title!r}>"


# --------------------------------
# Değerlendirme (Evaluation)
# --------------------------------
class Evaluation(db.Model):
    __tablename__ = "evaluations"

    id        = db.Column(db.Integer, primary_key=True)
    risk_id   = db.Column(db.Integer, db.ForeignKey("risks.id"), nullable=False, index=True)
    evaluator = db.Column(db.String(120), nullable=True)

    probability = db.Column(db.Integer, nullable=False)  # 1..5
    severity    = db.Column(db.Integer, nullable=False)  # 1..5
    detection   = db.Column(db.Integer, nullable=True)   # 1..5 (ARTIK KULLANILMIYOR)
    comment     = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def rpn(self):
        """
        GERİYE UYUMLULUK: P×S döner (D kullanılmıyor).
        Eski adı 'rpn' ama yeni mantık P×S.
        """
        if self.probability is None or self.severity is None:
            return None
        return self.probability * self.severity

    def __repr__(self):
        return f"<Eval risk={self.risk_id} P={self.probability} S={self.severity}>"


# --------------------------------
# Yorum (Comment)
# --------------------------------
class Comment(db.Model):
    __tablename__ = "comments"

    id         = db.Column(db.Integer, primary_key=True)
    risk_id    = db.Column(db.Integer, db.ForeignKey("risks.id"), nullable=False, index=True)
    text       = db.Column(db.Text, nullable=False)
    is_system  = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Comment risk={self.risk_id} system={self.is_system}>"


# --------------------------------
# Öneri (Suggestion)
# --------------------------------
class Suggestion(db.Model):
    __tablename__ = "suggestions"

    id       = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False, index=True)  # not: string
    text     = db.Column(db.Text, nullable=False)

    # CSV içe aktarma ve otomatik öneri için:
    risk_code    = db.Column(db.String(32), index=True)  # örn: UYR01
    default_prob = db.Column(db.Integer)                 # 1..5 (opsiyonel)
    default_sev  = db.Column(db.Integer)                 # 1..5 (opsiyonel)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Suggestion cat={self.category!r} code={self.risk_code!r}>"


# --------------------------------
# Hesap (Account)
# --------------------------------
class Account(db.Model):
    __tablename__ = "accounts"

    id            = db.Column(db.Integer, primary_key=True)
    language      = db.Column(db.String(20), default="Türkçe")
    contact_name  = db.Column(db.String(120), nullable=False)   # Yetkili Kişi
    contact_title = db.Column(db.String(120), nullable=True)    # Yetkili Ünvanı
    email         = db.Column(db.String(200), unique=True, nullable=False, index=True)
    role          = db.Column(db.String(20), default="uzman")   # admin | uzman
    password_hash = db.Column(db.String(255), nullable=False)
    # Referans / kampanya kodu
    ref_code      = db.Column(db.String(32), nullable=True, index=True)
    # Hesap durumu: pending | active | disabled
    status        = db.Column(db.String(20), default="pending", index=True)

    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Account {self.email} role={self.role} status={self.status}>"


# --------------------------------
# Proje / İş Yeri Bilgisi (ProjectInfo)
# --------------------------------
class ProjectInfo(db.Model):
    __tablename__ = "project_info"

    id                = db.Column(db.Integer, primary_key=True)
    account_id        = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    workplace_name    = db.Column(db.String(200), nullable=False)   # İş yeri unvanı
    workplace_address = db.Column(db.Text, nullable=False)          # İş yeri adresi
    project_duration  = db.Column(db.String(50), nullable=True)     # Proje süresi (örn. 12 ay)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    account = db.relationship("Account", backref="projects")

    def __repr__(self):
        return f"<ProjectInfo id={self.id} name={self.workplace_name!r}>"
