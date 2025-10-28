# wsgi.py — sağlam giriş: modül denk gelirse içinden app/application/create_app arar
import importlib
from types import ModuleType

CANDIDATES = [
    ("riskapp.app",  "app"),
    ("riskapp.app",  "application"),
    ("riskapp.app",  "create_app"),
    ("riskapp",      "app"),           # burası genelde modül döndürürse içini açacağız
    ("riskapp",      "application"),
    ("riskapp",      "create_app"),
]

def _is_flask_app(obj):
    # Flask instance basit kontrol: __call__ var ve genelde wsgi_app niteliği bulunur
    return callable(getattr(obj, "__call__", None)) and hasattr(obj, "wsgi_app")

def _extract_from_module(mod: ModuleType):
    """riskapp (paket) ya da riskapp.app (modül) dönerse içinden gerçek uygulamayı bul."""
    # 1) app / application doğrudan Flask instance ise
    for name in ("app", "application"):
        inner = getattr(mod, name, None)
        if inner is not None and _is_flask_app(inner):
            return inner
    # 2) create_app() varsa çağır
    create_app = getattr(mod, "create_app", None)
    if callable(create_app):
        created = create_app()
        if _is_flask_app(created):
            return created
    # 3) modül içinde bir alt modül ise (örn: riskapp.app modülü), yine aynı denemeleri yap
    # (çoğu durumda buraya gerek kalmaz ama güvence)
    return None

def _load_app():
    last_err = None
    for mod_name, attr in CANDIDATES:
        try:
            mod = importlib.import_module(mod_name)
            obj = getattr(mod, attr, None)
            if obj is None:
                # attr yoksa, modülün içinden deneyelim
                found = _extract_from_module(mod)
                if found:
                    return found
                continue

            # Eğer obj bir modül ise içinden gerçek Flask app'ini çıkarmayı dene
            if isinstance(obj, ModuleType):
                found = _extract_from_module(obj)
                if found:
                    return found
                # modül ama içinde app yoksa sıradaki adaya geç
                continue

            # create_app fonksiyonu ise çağır
            if callable(obj) and attr == "create_app":
                created = obj()
                if _is_flask_app(created):
                    return created
                continue

            # doğrudan Flask app ise al
            if _is_flask_app(obj):
                return obj

            # app değilse, modülün içini de bir ihtimal kontrol et
            if hasattr(obj, "__dict__"):
                maybe_mod = getattr(obj, "__dict__", None)
                # ekstra güvence gerekmez; sıradaki adaya geç
                continue

        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"WSGI app bulunamadı ya da geçersiz. Son hata: {last_err}")

app = _load_app()

if __name__ == "__main__":
    # Lokal hızla test için: python wsgi.py
    app.run(host="0.0.0.0", port=5000)
