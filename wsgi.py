# wsgi.py  (repo kökünde)
from riskapp.app import app  # app = Flask(__name__) olan yer
# opsiyonel: yerel çalıştırma
if __name__ == "__main__":
    app.run()
