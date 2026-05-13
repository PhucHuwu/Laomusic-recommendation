import multiprocessing
import os

bind = os.getenv("APP_BIND", "0.0.0.0:8000")
workers = int(os.getenv("APP_WORKERS", max(2, multiprocessing.cpu_count() // 2)))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = int(os.getenv("APP_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("APP_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("APP_KEEPALIVE", "5"))
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("APP_LOG_LEVEL", "info")
