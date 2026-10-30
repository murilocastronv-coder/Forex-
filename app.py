import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return jsonify({
        "service": "Forex D1 Grid Bot",
        "status": "online",
        "trading_enabled": False,
        "message": "Serviço online. Trading permanece desativado até concluir a conexão XM demo e validar os dados D1."
    })

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
