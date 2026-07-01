import http.server, sys

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()
    def log_message(self, *a): pass

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
http.server.test(HandlerClass=NoCacheHandler, port=port, bind='')
