# train_ai.py
from riskapp.app import create_app
from riskapp.ai_local.trainer import build_index

app = create_app()
with app.app_context():
    n = build_index(kind="both", use_faiss=False)
    print(f"AI index hazır: {n} kayıt.")
