# wsgi.py — evrensel giriş (factory ya da doğrudan app ismini otomatik bulur)
import importlib

def _load_app():
    """
    Aşağıdaki sıralamayla dener:
    1) riskapp.app içinde app
    2) riskapp içinde app
    3) riskapp.app içinde create_app()
    4) riskapp içinde create_app()
    5) riskapp.app içinde application
    6) riskapp içinde application
    """
    candidates = [
        ("riskapp.app",  "app"),
        ("riskapp",      "app"),
        ("riskapp.app",  "create_app"),
        ("riskapp",      "create_app"),
        ("riskapp.app",  "application"),
        ("riskapp",      "application"),
    ]
    last_err = None
    for mod_name, attr in candidates:
        try:
            mod = importlib.import_module(mod_name)
            obj = getattr(mod, attr, None)
            if obj is None:
                continue
            if callable(obj) and attr == "create_app":
                return obj()  # factory pattern
            return obj       # doğrudan app/application
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"WSGI app bulunamadı. Son hata: {last_err}")

app = _load_app()

if __name__ == "__main__":
    # Lokal test için: python wsgi.py
    app.run(host="0.0.0.0", port=5000)
