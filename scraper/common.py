"""共用工具：抓網頁、片名正規化、台北時間。"""
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

TPE = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})


def get(url, retries=2, **kw):
    """抓網頁，失敗重試；回傳 requests.Response。"""
    last = None
    for i in range(retries + 1):
        try:
            r = _session.get(url, timeout=25, **kw)
            r.raise_for_status()
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def now_tpe():
    return datetime.now(TPE)


def next_days(n=3):
    """今天起 n 天的日期字串 YYYY-MM-DD（台北時間）。"""
    d = now_tpe().date()
    return [(d + timedelta(days=i)).isoformat() for i in range(n)]


# 片名裡這些標記代表場次類型，不是不同的電影
_TAGS = r"(特別場|海報場|首映場|試映場|午夜場|口碑場|搶先場|早鳥場|聯合首映|全台聯合首映|INFINITY VISION|IMAX|ATMOS|4DX|SCREENX|MX4D|D-BOX|數位|3D|2D)"


def clean_title(t):
    """去掉片名裡的場次標記，保留給人看的片名。"""
    t = unicodedata.normalize("NFKC", t or "").strip()
    t = re.sub(r"[（(]\s*" + _TAGS + r"[^）)]*[）)]", "", t)
    t = re.sub(r"[.。]+$", "", t)  # 國賓有些片名結尾多一個點
    return re.sub(r"\s+", " ", t).strip()


def movie_key(t):
    """跨戲院比對用的 key：去標記、去標點空白、轉小寫。"""
    t = clean_title(t)
    t = re.sub(r"(4K)?(數位修復版|重映版|重映|特別版|加碼重映)", "", t)
    t = re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)
    return t.lower()


RATING_MAP = {
    "普遍": "G", "保護": "P", "輔12": "PG12", "輔導12": "PG12",
    "輔15": "PG15", "輔導15": "PG15", "限制": "R",
}


def norm_rating(s):
    s = unicodedata.normalize("NFKC", s or "")
    for k, v in RATING_MAP.items():
        if k in s:
            return v
    m = re.search(r"\b(G|P|PG12|PG15|R)\b", s)
    return m.group(1) if m else None


def parse_runtime(s):
    """'1時48分' / '108分' / '1h48m' → 分鐘數。"""
    s = s or ""
    m = re.search(r"(\d+)\s*(?:時|小時|h)\s*(\d+)\s*(?:分|m)", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r"(\d{2,3})\s*分", s)
    return int(m.group(1)) if m else None
