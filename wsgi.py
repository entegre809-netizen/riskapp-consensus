# wsgi.py  (repo kökü)
import importlib

mod = importlib.import_module("riskapp.app")

# 1) app veya application var mı?
app = getattr(mod, "app", None) or getattr(mod, "application", None)

# 2) yoksa create_app() var mı? varsa instantiate et
if app is None:
    create_app = getattr(mod, "create_app", None)
    if callable(create_app):
        app = create_app()
    else:
        raise RuntimeError(
            "riskapp.app içinde 'app', 'application' ya da 'create_app()' bulunamadı."
        )

# opsiyonel: basit health check route'u yoksa ekle
try:
    from flask import Blueprint

    # sadece yoksa eklenir
    if not any(r.rule == "/healthz" for r in app.url_map.iter_rules()):
        @app.get("/healthz")
        def _healthz():
            return "ok"
except Exception:
    pass
