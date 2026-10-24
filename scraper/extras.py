"""片單類資料：本週新片、票房（開眼）、IMDb / 爛番茄（OMDb）。"""
import os
import re

from bs4 import BeautifulSoup

from common import clean_title, get

AT = "https://www.atmovies.com.tw"


def new_this_week():
    """開眼「本周新片」：[{title, en, date}]"""
    soup = BeautifulSoup(get(AT + "/movie/new/").text, "lxml")
    out = []
    for a in soup.select("a[href*='/movie/f']"):
        t = a.get_text(" ", strip=True)
        if not t or len(t) < 2 or "預告" in t:
            continue
        box = a.find_parent("li") or a.find_parent("div")
        txt = box.get_text(" ", strip=True) if box else ""
        dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", txt)
        out.append({"title": clean_title(t), "date": f"{dm.group(3)}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}" if dm else None})
    seen, res = set(), []
    for o in out:
        if o["title"] in seen:
            continue
        seen.add(o["title"])
        res.append(o)
    return res


def taipei_weekend_boxoffice():
    """開眼台北週末票房：{period, unit, rows:[{rank,title,week,total}]}"""
    soup = BeautifulSoup(get("https://app2.atmovies.com.tw/boxoffice/twweekend/").text, "lxml")
    text = soup.get_text(" ", strip=True)
    pm = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[至~－-]\s*(\d{1,2})\s*月\s*(\d{1,2})", text)
    period = f"{int(pm.group(2))}/{int(pm.group(3))}–{int(pm.group(4))}/{int(pm.group(5))}" if pm else ""
    rows = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        nums = [c.replace(",", "") for c in cells[2:]]
        try:
            rows.append({"rank": int(cells[0]), "title": clean_title(cells[1]),
                         "week": int(float(nums[0])), "total": int(float(nums[1]))})
        except (ValueError, IndexError):
            continue
    return {"period": period, "source": "開眼 台北週末票房", "unit": "萬", "rows": rows[:20]}


def omdb(en_title, year=None):
    """用英文片名查 IMDb / 爛番茄。沒有金鑰或查不到就回 None。"""
    key = os.environ.get("OMDB_API_KEY")
    if not key or not en_title:
        return None
    params = {"apikey": key, "t": en_title, "type": "movie"}
    if year:
        params["y"] = year
    r = get("https://www.omdbapi.com/", params=params).json()
    if r.get("Response") != "True" and year:
        # 台灣上映年份常比原產地晚一年，放寬再查一次
        params["y"] = int(year) - 1
        r = get("https://www.omdbapi.com/", params=params).json()
    if r.get("Response") != "True":
        return None
    out = {"imdb_id": r.get("imdbID")}
    if r.get("imdbRating") not in (None, "N/A"):
        out["imdb"] = r["imdbRating"]
        out["imdb_votes"] = r.get("imdbVotes")
    for x in r.get("Ratings", []):
        if x.get("Source") == "Rotten Tomatoes":
            out["rt"] = x["Value"]
    return out
