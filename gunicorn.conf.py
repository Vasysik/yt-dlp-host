import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = int(os.getenv("WEB_WORKERS", "2"))
threads = int(os.getenv("WEB_THREADS", "4"))
timeout = int(os.getenv("WEB_TIMEOUT_SECONDS", "60"))
accesslog = "-"
errorlog = "-"
capture_output = True
