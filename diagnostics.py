"""Bounded rotating logs with credential redaction."""
import logging
from logging.handlers import RotatingFileHandler
import re
import threading
import queue
from logging.handlers import QueueHandler, QueueListener
from storage import data_dir

_logger = None
_listener = None
_lock = threading.Lock()


def redact(text):
    text = str(text)
    text = re.sub(r'(?i)([?&]key=)[^&\s]+', r'\1[REDACTED]', text)
    text = re.sub(r"(?i)(authorization|cookie)[\"']?\s*[:=]\s*[^\r\n]+", r'\1=[REDACTED]', text)
    text = re.sub(r"(?i)(client[-_ ]?secret|access[-_ ]?token|refresh[-_ ]?token|password|api[-_ ]?key)[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)", r'\1=[REDACTED]', text)
    return re.sub(r'(?i)\bBearer\s+[^\s,;]+', 'Bearer [REDACTED]', text)


class QuietQueueHandler(QueueHandler):
    def enqueue(self, record):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            pass


def log_kind(text):
    if any(w in text for w in ('실패', '오류', 'error', 'ERROR')):
        return '오류'
    for token, kind in (('업데이트', '업데이트'), ('Chrome', '확장프로그램 통신'),
                        ('연결', '치지직 연결'), ('검색', '카테고리 검색'), ('매칭', '자동 매칭'),
                        ('적용', '카테고리 변경'), ('변경', '카테고리 변경')):
        if token in text:
            return kind
    return '게임 감지'


def record_log(text):
    global _logger, _listener
    try:
        if _logger is None:
            with _lock:
                if _logger is None:
                    folder = data_dir() / 'logs'
                    folder.mkdir(exist_ok=True)
                    logger = logging.getLogger('chzzk.activity')
                    logger.setLevel(logging.INFO)
                    logger.propagate = False
                    handler = RotatingFileHandler(folder / 'activity.log', maxBytes=1024*1024,
                                                  backupCount=3, encoding='utf-8')
                    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
                    records = queue.Queue(maxsize=1000)
                    logger.addHandler(QuietQueueHandler(records))
                    _listener = QueueListener(records, handler)
                    _listener.start()
                    _logger = logger
        _logger.info('[%s] %s', log_kind(text), redact(text))
    except OSError:
        pass  # Disk errors must not stop automation.
