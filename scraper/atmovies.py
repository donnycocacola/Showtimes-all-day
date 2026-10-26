"""開眼電影網：威秀、秀泰會擋 GitHub 的主機，所以這幾家改從開眼抓。

另外本週新片、即將上映、台北週末票房、電影簡介和 IMDb 編號也都從這裡來。
"""
import re

from bs4 import BeautifulSoup

from common import clean_title, get, parse_runtime

BASE = "https://www.atmovies.com.tw"

# 開眼的戲院代碼（台北 a02）
THEATERS = {
    "es": "t02a08",  # 誠品電影院
    "qz": "t02b14",  # 台北京站威秀
    "xd": "t02e21",  # 新店裕隆城威秀影城
    "dj": "t02a13",  # 大巨蛋秀泰影城
    "zs": "t02b07",  # 真善美戲院
    "gh": "t02b16",  # 光點華山電影館
}
TIME_RE = re.compile(r"^(\d{1,2})[：:](\d{2})$")
CER = {"G": "G", "P": "P", "F2": "PG12", "F5": "PG15", "PG12": "PG12", "PG15": "PG15", "R": "R"}


def theater_url(tid, date=None, today=None):
    u = f"{BASE}/showtime/{THEATERS[tid]}/a02/"
    if date and date != today:
        u += date.replace("-", "") + "/"
    return u


def split_title(full):
    """「泥面人 Clayface」→ ("泥面人", "Clayface")；純英文或純中文就原樣。"""
    full = re.sub(r"\s+", " ", (full or "").strip())
    m = re.match(r"^(.*[㐀-鿿぀-ヿ！-～」』）》〉]\S*)\s+([A-Za-z0-9][\x20-\x7e’'–—:]*)$", full)
    if m and re.search(r"[A-Za-z]", m.group(2)):
        return m.group(1).strip(), m.group(2).strip()
    return full, ""


def film_id(href):
    m = re.search(r"/(?:movie|film)/([a-z]{2,4}\w+?)/", href or "")
    return m.group(1) if m else None


def parse_theater(html):
    """回傳 (page_date 'YYYY-MM-DD' 或 None, updated 字串, movies{fid:info}, shows[(fid, ver, '', None, 'HH:MM', [])])"""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    dm = re.search(r"^(\d{4})/(\d{2})/(\d{2})\s*\(", text, re.M)
    page_date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else None
    um = re.search(r"更新時間\s*[:：]\s*(\d{4}/\d{2}/\d{2} \d{2}:\d{2})", text)
    movies, shows = {}, []
    for ul in soup.select("ul#theaterShowtimeTable"):
        a = ul.select_one("li.filmTitle a[href*='/movie/']")
        if not a:
            continue
        fid = film_id(a["href"])
        title = a.get_text(" ", strip=True)
        inner = ul.select("li > ul")
        if not inner:
            continue
        info = inner[0]
        cer = info.find("img", src=re.compile(r"cer_"))
        rating = None
        if cer:
            cm = re.search(r"cer_([A-Z0-9]+)\.", cer["src"])
            rating = CER.get(cm.group(1)) if cm else None
        img = info.find("img", src=re.compile(r"/photo101/"))
        movies.setdefault(fid, {
            "title": clean_title(title), "rating": rating,
            "runtime": parse_runtime(info.get_text(" ", strip=True)),
            "poster": BASE + img["src"] if img else None, "atmovies": fid,
        })
        tags, times = [], []
        for u in inner[1:]:
            for li in u.find_all("li", recursive=False):
                t = li.get_text(" ", strip=True)
                if "其他戲院" in t or not t:
                    continue
                tm = TIME_RE.match(t)
                if tm:
                    times.append(f"{int(tm.group(1)):02d}:{tm.group(2)}")
                else:
                    tags.append(t)
        ver = " ".join(tags)
        for t in times:
            shows.append((fid, ver, "", None, t, []))
    return page_date, (um.group(1) if um else None), movies, shows


def scrape(tid, dates):
    today = dates[0]
    all_movies, by_date, updated = {}, {}, None
    for d in dates:
        html = get(theater_url(tid, d, today)).text
        page_date, upd, mv, sh = parse_theater(html)
        updated = updated or upd
        if page_date and page_date != d:
            # 開眼還沒排到這天（會自動跳回別天），當作沒資料，不要把別天的場次放錯日子
            continue
        all_movies.update(mv)
        by_date[d] = sh
    if not any(by_date.values()):
        raise RuntimeError("開眼頁面解析不到任何場次")
    return {"movies": all_movies, "shows": by_date, "source_updated": updated}


def new_this_week():
    """本周新片：[{title, en, date, fid, poster, runtime}]"""
    soup = BeautifulSoup(get(BASE + "/movie/new/").text, "lxml")
    out = []
    for art in soup.select("article.filmList"):
        a = art.select_one(".filmTitle a[href*='/movie/']")
        if not a:
            continue
        zh, en = split_title(a.get_text(" ", strip=True))
        rt = art.select_one(".runtime")
        rtt = rt.get_text(" ", strip=True) if rt else ""
        dm = re.search(r"上映日期\s*[:：]\s*(\d{1,2})/(\d{1,2})/(\d{4})", rtt)
        img = art.select_one("img.filmListPoster")
        out.append({
            "title": clean_title(zh), "en": en, "fid": film_id(a["href"]),
            "date": f"{dm.group(3)}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}" if dm else None,
            "runtime": parse_runtime(rtt),
            "poster": BASE + img["src"].replace("/pm_", "/pl_") if img else None,
        })
    return out


def coming_soon():
    """即將上映：[{title, date, fid, poster}]，依開眼「List All」的日期分組。"""
    soup = BeautifulSoup(get(BASE + "/movie/next/0/").text, "lxml")
    out = []
    for h2 in soup.select("h2.major"):
        dm = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", h2.get_text())
        ul = h2.find_next_sibling("ul")
        if not dm or not ul:
            continue
        date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
        for li in ul.select("li"):
            a = li.select_one(".filmtitle a") or li.find("a", href=re.compile("/movie/"))
            if not a:
                continue
            img = li.find("img")
            out.append({"title": clean_title(a.get_text(" ", strip=True)), "date": date,
                        "fid": film_id(a["href"]),
                        "poster": BASE + img["src"].replace("/pm_", "/pl_") if img else None})
    return out


def taipei_weekend_boxoffice():
    """台北週末票房：表格是兩列一組（名次+片名 / 佔比、本週、累計、上週、週數）。"""
    soup = BeautifulSoup(get("https://app2.atmovies.com.tw/boxoffice/twweekend/").text, "lxml")
    text = soup.get_text(" ", strip=True)
    pm = re.search(r"統計時間\s*[:：]\s*(\d{4})-(\d{2})-(\d{2})\s*[～~]\s*(\d{4})-(\d{2})-(\d{2})", text)
    period = f"{int(pm.group(2))}/{int(pm.group(3))}–{int(pm.group(5))}/{int(pm.group(6))}" if pm else ""
    rows, cur = [], None
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) >= 2 and cells[0].isdigit() and cells[1]:
            a = tr.find("a", href=re.compile(r"/(movie|film)/"))
            zh, en = split_title(cells[1])
            cur = {"rank": int(cells[0]), "title": clean_title(zh), "en": en,
                   "fid": film_id(a["href"]) if a else None}
            continue
        if cur and any(c.startswith("$") for c in cells):
            money = [int(c.replace("$", "").replace(",", "")) for c in cells if re.match(r"^\$[\d,]+$", c)]
            if len(money) >= 2:
                cur["week"], cur["total"] = money[0], money[1]
                rows.append(cur)
            cur = None
    return {"period": period, "source": "開眼 台北週末票房", "unit": "萬", "rows": rows[:20]}


def movie_detail(fid):
    """電影頁：英文片名、簡介、導演、演員、上映日、IMDb 編號。"""
    html = get(f"{BASE}/movie/{fid}/").text
    soup = BeautifulSoup(html, "lxml")
    out = {}
    yt = re.search(r"youtube(?:-nocookie)?\.com/embed/([\w-]{11})", html)
    if yt:
        out["trailer"] = "https://www.youtube.com/watch?v=" + yt.group(1)
    im = re.search(r"imdb\.com/title/(tt\d+)", html)
    if im:
        out["imdb_id"] = im.group(1)
    h = soup.select_one(".filmTitle") or soup.find(["h1", "h2"], string=re.compile(r"\S"))
    if h:
        zh, en = split_title(h.get_text(" ", strip=True))
        if en:
            out["en"] = en
    # 簡介：「劇情簡介」所在的 div 整塊拿出來，<br> 當換行，超連結不拆行
    node = soup.find(string=re.compile("劇情簡介"))
    div = node.find_parent("div") if node else None
    if div:
        for br in div.find_all("br"):
            br.replace_with("\n")
        t = div.get_text("")
        t = t.split("劇情簡介", 1)[1] if "劇情簡介" in t else t
        t = re.sub(r"[ \t\r　]+", " ", t)
        t = re.sub(r"\n\s*\n+", "\n\n", t).strip()
        if len(t) > 20:
            out["synopsis"] = t[:1200]
    for t in soup(["script", "style", "nav", "header", "footer", "select"]):
        t.decompose()
    lines = [x.strip() for x in soup.get_text("\n", strip=True).split("\n") if x.strip()]
    for i, ln in enumerate(lines):
        m = re.match(r"^(導演|演員|上映日期)\s*[:：]\s*(.*)$", ln)
        if m:
            val = m.group(2) or (lines[i + 1] if i + 1 < len(lines) else "")
            key = {"導演": "director", "演員": "cast", "上映日期": "release"}[m.group(1)]
            out.setdefault(key, val.strip())
    if "synopsis" not in out and "劇情簡介" in lines:
        i = lines.index("劇情簡介")
        para = []
        for ln in lines[i + 1:]:
            if re.match(r"^(相關|預告|劇照|網友|開眼|看更多|電影評分|發表|●|>)", ln) or len(para) >= 12:
                break
            para.append(ln)
        syn = "\n".join(p for p in para if len(p) > 1)
        if len(syn) > 20:
            out["synopsis"] = syn[:900]
    if out.get("release"):
        dm = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", out["release"])
        out["release"] = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}" if dm else out["release"]
    return out
