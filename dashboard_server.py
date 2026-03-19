#!/usr/bin/env python3
"""
Dashboard Server per il Trading Bot
Uso: python3 dashboard_server.py [porta]
"""

import http.server
import socketserver
import sys
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

if __name__ == '__main__':
    print(f"🚀 Dashboard avviata su http://localhost:{PORT}")
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()
