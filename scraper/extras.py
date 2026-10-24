"""IMDb / 爛番茄分數（OMDb）。"""
import os

from common import _session


def _q(params):
    r = _session.get("https://www.omdbapi.com/", params=params, timeout=15)
    try:
        j = r.json()
    except ValueError:
        j = {}
    if r.status_code != 200:
        # 401 = 金鑰無效或還沒到信箱點啟用連結
        raise RuntimeError(f"HTTP {r.status_code} {j.get('Error', r.text[:80])}")
    return j


def omdb(imdb_id=None, en_title=None, year=None):
    """優先用 IMDb 編號查（最準）；沒有編號才用英文片名＋年份。沒有金鑰或查不到回 None。"""
    key = os.environ.get("OMDB_API_KEY")
    if not key or not (imdb_id or en_title):
        return None
    if imdb_id:
        r = _q({"apikey": key, "i": imdb_id})
        if r.get("Response") != "True" and en_title:
            imdb_id = None
    if not imdb_id:
        params = {"apikey": key, "t": en_title, "type": "movie"}
        if year:
            params["y"] = year
        r = _q(params)
        if r.get("Response") != "True" and year:
            params["y"] = int(year) - 1  # 台灣上映常比原產地晚一年
            r = _q(params)
    if r.get("Response") != "True":
        return None
    out = {"imdb_id": r.get("imdbID")}
    if (r.get("Year") or "")[:4].isdigit():
        out["year"] = r["Year"][:4]  # 原產地首映年份（重映片也是原本那年）
    if r.get("imdbRating") not in (None, "N/A"):
        out["imdb"] = r["imdbRating"]
        out["imdb_votes"] = r.get("imdbVotes")
    for x in r.get("Ratings", []):
        if x.get("Source") == "Rotten Tomatoes":
            out["rt"] = x["Value"]
    return out
