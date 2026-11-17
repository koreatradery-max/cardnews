"""텔레그램 승인 요청. 봇 토큰은 기존 Cloudflare Worker 에만 있으므로 Worker 를 거쳐 보낸다."""
import json, urllib.error, urllib.request
from . import config


def worker(path, payload, timeout=120):
    if not (config.WORKER_URL and config.WORKER_KEY):
        raise RuntimeError("CARDNEWS_WORKER_URL / CARDNEWS_KEY 가 설정되지 않았습니다.")
    req = urllib.request.Request(config.WORKER_URL + path, data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json", "x-cardnews-key": config.WORKER_KEY,
                                          "user-agent": "cardnews-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code} {e.read()[:300].decode('utf-8', 'replace')}"}


def submit(set_id):
    """세트 1개를 관리자 텔레그램으로 보낸다 (사진 + 본문 + 승인/반려/다른 사진)."""
    return worker("/cardnews/submit", {"id": set_id})


def auto_approve(set_id):
    """아직 승인도 반려도 안 된 세트면 자동 승인(업로드)한다."""
    return worker("/cardnews/auto", {"id": set_id})


def send_text(text):
    return worker("/cardnews/notice", {"text": text})
