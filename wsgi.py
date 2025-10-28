# wsgi.py  (repo kökü)
from riskapp.app import app  # riskapp/app.py içinde app = Flask(__name__)
if __name__ == "__main__":
    app.run()
