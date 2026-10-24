"""國賓影城：場次頁直接把場次寫在 HTML 裡，網址是 影城ID + 日期。"""
import re

from bs4 import BeautifulSoup

from common import clean_title, get, norm_rating, parse_runtime

BASE = "https://www.ambassador.com.tw"
THEATERS = {
    "xm": "84b87b82-b936-4a39-b91f-e88328d33b4e",  # 國賓大戲院（西門）
    "cc": "453b2966-f7c2-44a9-b2eb-687493855d0e",  # 台北長春國賓
}
TIME_RE = re.compile(r"^([01]?\d|2[0-9]):[0-5]\d$")
HALL_RE = re.compile(r"(\S+廳)\s*(\d+)\s*席")
VER_RE = re.compile(r"^[（(]([^）)]+)[）)]")


def showtime_url(tid, date):
    return f"{BASE}/home/Showtime?ID={THEATERS[tid]}&DT={date.replace('-', '%2F')}"


def parse(html):
    """回傳 (movies, shows)。

    movies: {mid: {title, en, rating, runtime, poster, url}}
    shows:  [(mid, version, hall, seats, "HH:MM", flags)]

    依文件順序走過所有元素：遇到電影標題就換電影，遇到「(數位‧英文版)片名」就換版本，
    遇到時間就記一場，後面的「2廳 97席」補上廳別。這樣不依賴特定 class 名稱，官網小改版也不容易壞。
    """
    soup = BeautifulSoup(html, "lxml")
    movies, shows = {}, []
    cur_mid, cur_ver, last = None, "", None

    for el in soup.find_all(True):
        name = el.name
        if name in ("h3", "h2") and el.find("a", href=re.compile(r"MovieContent\?MID=")):
            a = el.find("a", href=re.compile(r"MovieContent\?MID="))
            mid = re.search(r"MID=([0-9a-f-]+)", a["href"]).group(1)
            full = a.get_text(" ", strip=True)
            # 標題長這樣：「泥面人Clayface」→ 中英拆開
            m = re.match(r"^(.*?[㐀-鿿＀-￯）」』!！?？0-9]+)\s*([A-Za-z].*)?$", full)
            zh, en = (m.group(1), m.group(2) or "") if m else (full, "")
            block = el.parent.get_text(" ", strip=True) if el.parent else ""
            img = None
            for anc in (el.parent, el.parent.parent if el.parent else None):
                if anc is None:
                    continue
                i = anc.find("img", src=re.compile(r"/assets/img/movies/"))
                if i:
                    img = i["src"]
                    break
            movies[mid] = {
                "title": clean_title(zh),
                "raw_title": zh.strip(),
                "en": en.strip(),
                "rating": norm_rating(block),
                "runtime": parse_runtime(block),
                "poster": (BASE + img.replace("..", "")) if img and img.startswith(("/", "..")) else img,
                "url": BASE + "/home/MovieContent?MID=" + mid,
            }
            cur_mid, cur_ver, last = mid, "", None
            continue
        if cur_mid is None:
            continue
        own = "".join(el.find_all(string=True, recursive=False)).strip()
        if not own:
            continue
        vm = VER_RE.match(own)
        if vm and name not in ("h6", "h5"):
            cur_ver = vm.group(1).replace("‧", " ").replace("・", " ")
            last = None
            continue
        if TIME_RE.match(own):
            last = [cur_mid, cur_ver, "", None, own.zfill(5), []]
            shows.append(last)
            continue
        hm = HALL_RE.search(own)
        if hm and last is not None and not last[2]:
            last[2], last[3] = hm.group(1), int(hm.group(2))
            # D-BOX / 尊爵席 圖示
            imgs = " ".join(i.get("src", "") for i in el.find_all("img"))
            if "dbox" in imgs.lower():
                last[5].append("D-BOX")
            if "prime" in imgs.lower():
                last[5].append("尊爵席")

    # 同一個時間、同廳可能因 HTML 重複出現（手機/桌機兩份），去重
    seen, out = set(), []
    for s in shows:
        k = (s[0], s[1], s[2], s[4])
        if k in seen:
            continue
        seen.add(k)
        out.append(tuple(s[:5]) + (s[5],))
    return movies, out


def scrape(tid, dates):
    """回傳 {movies, shows: {date: [...]}}。"""
    all_movies, by_date = {}, {}
    for d in dates:
        html = get(showtime_url(tid, d)).text
        mv, sh = parse(html)
        all_movies.update(mv)
        by_date[d] = sh
    if not any(by_date.values()):
        raise RuntimeError("國賓頁面抓到了但解析不到任何場次，可能改版了")
    return {"movies": all_movies, "shows": by_date}


def movie_detail(url):
    """電影介紹頁：簡介、導演、演員、上映日。"""
    soup = BeautifulSoup(get(url).text, "lxml")
    text = soup.get_text("\n", strip=True)
    out = {}
    for label, key in (("導演", "director"), ("演員", "cast"), ("上映日期", "release")):
        m = re.search(label + r"\s*[:：]?\s*\n?([^\n]+)", text)
        if m:
            out[key] = m.group(1).strip()
    og = soup.find("meta", property="og:description")
    paras = sorted((p.get_text(" ", strip=True) for p in soup.find_all("p")), key=len, reverse=True)
    syn = paras[0] if paras and len(paras[0]) > 40 else (og["content"] if og and og.get("content") else "")
    if syn and "國賓影城、國賓大戲院" not in syn:
        out["synopsis"] = syn
    return out


def coming_soon():
    """即將上映片單（MovieList?Type=0）。"""
    soup = BeautifulSoup(get(BASE + "/home/MovieList?Type=0").text, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=re.compile(r"MovieContent\?MID=")):
        t = a.get_text(" ", strip=True)
        if not t or len(t) < 2:
            continue
        mid = re.search(r"MID=([0-9a-f-]+)", a["href"]).group(1)
        if mid in seen:
            continue
        seen.add(mid)
        box = a.find_parent(["li", "div"])
        btxt = box.get_text(" ", strip=True) if box else ""
        dm = re.search(r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", btxt)
        img = box.find("img") if box else None
        out.append({
            "mid": mid, "title": clean_title(t),
            "date": f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}" if dm else None,
            "poster": (BASE + img["src"].replace("..", "")) if img and img.get("src", "").startswith(("/", "..")) else None,
            "url": BASE + "/home/MovieContent?MID=" + mid,
        })
    return out
