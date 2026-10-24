"""IMDb / 爛番茄分數（OMDb）。"""
import os

from common import get


def omdb(imdb_id=None, en_title=None, year=None):
    """優先用 IMDb 編號查（最準）；沒有編號才用英文片名＋年份。沒有金鑰或查不到回 None。"""
    key = os.environ.get("OMDB_API_KEY")
    if not key or not (imdb_id or en_title):
        return None
    if imdb_id:
        r = get("https://www.omdbapi.com/", params={"apikey": key, "i": imdb_id}).json()
    else:
        params = {"apikey": key, "t": en_title, "type": "movie"}
        if year:
            params["y"] = year
        r = get("https://www.omdbapi.com/", params=params).json()
        if r.get("Response") != "True" and year:
            params["y"] = int(year) - 1  # 台灣上映常比原產地晚一年
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
