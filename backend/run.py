#!/usr/bin/env python3
"""
Simple run script for the Flask API server.

Usage:
    python run.py
"""

from app.api import app

if __name__ == '__main__':
    print("Starting Lease Extraction API server...")
    print("Server running at http://localhost:5000")
    print("Press CTRL+C to stop")
    print()
    app.run(debug=True, host='0.0.0.0', port=5000)
