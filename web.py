from flask import Flask, jsonify
import config
import os

app = Flask(__name__)
stats = {
    "started_at": "",
    "cycles": 0,
    "total_alerts": 0
}
paper_trades_ref = []

@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "cycles": stats["cycles"],
        "total_alerts": stats["total_alerts"],
        "started_at": stats["started_at"],
        "paper_trades": len(paper_trades_ref)
    })

@app.route("/trades")
def trades():
    return jsonify([t.__dict__ for t in paper_trades_ref[-50:]] if paper_trades_ref else [])

@app.route("/health")
def health():
    return "OK", 200

def start_server():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
