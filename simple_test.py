"""Minimal Flask for Vercel testing."""

from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/api/test")
def test():
    return jsonify(ok=True, message="Simple Flask works!")

@app.get("/api/health")
def health():
    return jsonify(ok=True, platform="vercel")