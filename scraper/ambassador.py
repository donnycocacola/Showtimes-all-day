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

    官網結構：div.showtime-item > 海報 img + div.theater-box
      h3 > a(片名 + span.eng 英文名) + p.info(分級|片長)
      p.tag-seat「(數位‧英文版)片名」→ 下一個 ul.seat-list > li > h6 時間 + span.info「2廳 97席」(+ D-BOX 圖示)
    """
    soup = BeautifulSoup(html, "lxml")
    movies, shows, seen = {}, [], set()
    for box in soup.select("div.theater-box"):
        a = box.select_one("h3 a[href*='MovieContent']")
        if not a:
            continue
        mid = re.search(r"MID=([0-9a-f-]+)", a["href"]).group(1)
        eng = a.select_one("span.eng")
        en = eng.get_text(" ", strip=True) if eng else ""
        if eng:
            eng.extract()
        zh = a.get_text(" ", strip=True)
        info = box.select_one("p.info")
        info_t = info.get_text(" ", strip=True) if info else ""
        item = box.find_parent("div", class_="showtime-item") or box
        img = item.select_one("img[src*='/assets/img/movies/']")
        src = img["src"] if img else None
        if src and not src.startswith("http"):
            src = BASE + "/" + src.lstrip("./")
        movies[mid] = {
            "title": clean_title(zh), "raw_title": zh, "en": en,
            "rating": norm_rating(info_t), "runtime": parse_runtime(info_t),
            "poster": src, "url": BASE + "/home/MovieContent?MID=" + mid,
        }
        for tag in box.select("p.tag-seat"):
            vm = VER_RE.match(tag.get_text(" ", strip=True))
            ver = vm.group(1).replace("‧", " ").replace("・", " ") if vm else ""
            ul = tag.find_next_sibling("ul")
            if not ul:
                continue
            for li in ul.select("li"):
                h6 = li.find("h6")
                t = h6.get_text(strip=True) if h6 else ""
                if not TIME_RE.match(t):
                    continue
                hm = HALL_RE.search(li.get_text(" ", strip=True))
                imgs = " ".join(i.get("src", "") for i in li.find_all("img")).lower()
                flags = [f for k, f in (("dbox", "D-BOX"), ("prime", "尊爵席")) if k in imgs]
                row = (mid, ver, hm.group(1) if hm else "", int(hm.group(2)) if hm else None, t.zfill(5), flags)
                k = row[:5]
                if k not in seen:
                    seen.add(k)
                    shows.append(row)
    return movies, shows


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


def movie_detail(url, date):
    """電影介紹頁：簡介、演員、類型、上映日。網址一定要帶 DT 日期，不然官網回錯誤頁。

    版面：片名 → 英文名 → 「限制級(R)1時48分」→ 簡介 → 主要演員：… → 影片類型：… → 上映日期：…
    """
    if "DT=" not in url:
        url += "&DT=" + date.replace("-", "%2F")
    soup = BeautifulSoup(get(url).text, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    lines = [x for x in soup.get_text("\n", strip=True).split("\n") if x.strip()]
    if any("處理您的要求時發生錯誤" in x for x in lines):
        raise RuntimeError("國賓介紹頁回傳錯誤頁")
    out, start = {}, None
    for i, ln in enumerate(lines):
        if start is None and re.search(r"級.*\d+\s*時\s*\d+\s*分", ln):
            start = i + 1
            continue
        m = re.match(r"^(主要演員|演員|導演|影片類型|上映日期)\s*[:：]\s*(.*)$", ln)
        if m:
            key = {"主要演員": "cast", "演員": "cast", "導演": "director", "影片類型": "genre", "上映日期": "release"}[m.group(1)]
            out.setdefault(key, m.group(2).strip())
            if start is not None and "synopsis" not in out:
                out["synopsis"] = "\n".join(lines[start:i]).strip()
    if out.get("release"):
        out["release"] = out["release"].replace("/", "-")
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
