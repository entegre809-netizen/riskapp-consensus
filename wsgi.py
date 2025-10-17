# wsgi.py (repo kökünde)
from riskapp.app import create_app

app = create_app()  # gunicorn wsgi:app burayı arıyor

if __name__ == "__main__":
    app.run()
