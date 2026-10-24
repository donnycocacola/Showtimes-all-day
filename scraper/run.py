"""主程式：抓 7 家戲院 + 片單，輸出 docs/data/showtimes.json。

原則：
- 某家抓失敗，不會整個掛掉；保留上一次的資料並標成「舊資料」，網頁上會顯示警告。
- 簡介、IMDb/爛番茄放在 details.json 快取，不用每次重抓。
"""
import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import ambassador  # noqa: E402
import extras  # noqa: E402
from common import TPE, clean_title, movie_key, next_days, now_tpe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "showtimes.json"
DETAILS = ROOT / "docs" / "data" / "details.json"

THEATERS = [
    {"id": "es", "name": "誠品電影院", "area": "松菸", "chain": None},
    {"id": "xm", "name": "西門國賓", "area": "國賓大戲院", "chain": "ambassador"},
    {"id": "cc", "name": "長春國賓", "area": "長春廣場", "chain": "ambassador"},
    {"id": "qz", "name": "京站威秀", "area": "台北車站", "chain": None},
    {"id": "xd", "name": "新店威秀", "area": "裕隆城", "chain": None},
    {"id": "dj", "name": "巨蛋秀泰", "area": "大巨蛋", "chain": None},
    {"id": "zs", "name": "真善美", "area": "西門町", "chain": None},
]


def load(p, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return default


def main():
    prev = load(OUT, {})
    details = load(DETAILS, {})
    dates = next_days(3)
    stamp = now_tpe().strftime("%Y-%m-%dT%H:%M")
    movies, shows, theaters, errors = {}, {}, [], []

    def add_movie(info):
        k = movie_key(info["title"])
        if not k:
            return None
        m = movies.setdefault(k, {"title": info["title"]})
        for f in ("en", "rating", "runtime", "poster", "url"):
            if info.get(f) and not m.get(f):
                m[f] = info[f]
        return k

    for t in THEATERS:
        rec = {k: t[k] for k in ("id", "name", "area")}
        try:
            if t["chain"] == "ambassador":
                data = ambassador.scrape(t["id"], dates)
                idmap = {mid: add_movie(info) for mid, info in data["movies"].items()}
                shows[t["id"]] = {
                    d: [[idmap[s[0]], s[1], s[2], s[3], s[4], s[5]] for s in rows if idmap.get(s[0])]
                    for d, rows in data["shows"].items()
                }
                rec["link"] = ambassador.showtime_url(t["id"], dates[0])
                rec.update(status="ok", updated=stamp)
            else:
                rec.update(status="todo", message="這家的爬蟲還在做")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            errors.append(f"{t['name']}: {e}")
            old_t = next((x for x in prev.get("theaters", []) if x["id"] == t["id"]), None)
            old_s = prev.get("shows", {}).get(t["id"])
            if old_t and old_s:
                shows[t["id"]] = old_s
                for k in {r[0] for rows in old_s.values() for r in rows}:
                    if k in prev.get("movies", {}) and k not in movies:
                        movies[k] = prev["movies"][k]
                rec.update(status="stale", updated=old_t.get("updated"), link=old_t.get("link"),
                           message="這次沒抓到，顯示的是上次的資料")
            else:
                rec.update(status="error", message="抓取失敗")
        theaters.append(rec)

    # ---- 片單 ----
    def try_(fn, fallback):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            errors.append(f"{fn.__name__}: {e}")
            return fallback

    coming = try_(ambassador.coming_soon, prev.get("coming", []))
    for c in coming:
        c["key"] = c.get("key") or movie_key(c["title"])
    new_week = try_(extras.new_this_week, prev.get("new_week", []))
    for n in new_week:
        n["key"] = n.get("key") or movie_key(n["title"])
    boxoffice = try_(extras.taipei_weekend_boxoffice, prev.get("boxoffice", {}))
    for r in boxoffice.get("rows", []):
        r["key"] = movie_key(r["title"])

    # ---- 簡介 + 分數（快取）----
    today = now_tpe().date()
    for k, m in movies.items():
        d = details.setdefault(k, {})
        if not d.get("synopsis") and m.get("url") and "ambassador" in m["url"] and d.get("detail_tries", 0) < 3:
            try:
                d["detail_tries"] = d.get("detail_tries", 0) + 1
                d.update(ambassador.movie_detail(m["url"], dates[0]))
            except Exception as e:  # noqa: BLE001
                print("detail fail", m["title"], e)
        checked = d.get("scores_checked")
        if os.environ.get("OMDB_API_KEY") and (not checked or (today - datetime.fromisoformat(checked).date()) > timedelta(days=3)):
            try:
                year = (d.get("release") or "")[:4] or today.year
                sc = extras.omdb(m.get("en"), year)
                d["scores"] = sc or {}
                d["scores_checked"] = today.isoformat()
            except Exception as e:  # noqa: BLE001
                print("omdb fail", m["title"], e)
        for f in ("synopsis", "director", "cast", "genre", "release"):
            if d.get(f):
                m[f] = d[f]
        if d.get("scores"):
            m["scores"] = d["scores"]

    out = {
        "generated": stamp,
        "dates": dates,
        "theaters": theaters,
        "movies": movies,
        "shows": shows,
        "new_week": new_week,
        "boxoffice": boxoffice,
        "coming": coming,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    DETAILS.write_text(json.dumps(details, ensure_ascii=False, indent=0), "utf-8")
    n = sum(len(r) for t in shows.values() for r in t.values())
    print(f"完成：{len(movies)} 部電影、{n} 場；錯誤 {len(errors)} 個")
    for e in errors:
        print("  -", e)


if __name__ == "__main__":
    main()
