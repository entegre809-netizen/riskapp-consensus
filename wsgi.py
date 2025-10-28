# wsgi.py
from riskapp.app import create_app

app = create_app()  # gunicorn buradaki 'app'i arıyor

if __name__ == "__main__":
    # Lokal çalışma için (Render bunu kullanmaz)
    app.run(host="0.0.0.0", port=5000, debug=False)
