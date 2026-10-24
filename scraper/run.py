"""主程式：抓 7 家戲院 + 片單，輸出 docs/data/showtimes.json。

資料來源：
- 西門國賓、長春國賓：國賓官網（有廳別、座位數、D-BOX）
- 誠品、京站威秀、新店威秀、巨蛋秀泰、真善美：開眼電影網（威秀、秀泰官網會擋 GitHub 的主機）
- 本週新片、即將上映、台北週末票房、簡介、IMDb 編號：開眼
- IMDb / 爛番茄分數：OMDb

原則：某家抓失敗不會整個掛掉，保留上一次的資料並標成「舊資料」。
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import ambassador  # noqa: E402
import atmovies  # noqa: E402
import extras  # noqa: E402
from common import movie_key, next_days, now_tpe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "showtimes.json"
DETAILS = ROOT / "docs" / "data" / "details.json"

THEATERS = [
    {"id": "es", "name": "誠品電影院", "area": "松菸", "src": "atmovies"},
    {"id": "xm", "name": "西門國賓", "area": "國賓大戲院", "src": "ambassador"},
    {"id": "cc", "name": "長春國賓", "area": "長春廣場", "src": "ambassador"},
    {"id": "qz", "name": "京站威秀", "area": "台北車站", "src": "atmovies"},
    {"id": "xd", "name": "新店威秀", "area": "裕隆城", "src": "atmovies"},
    {"id": "dj", "name": "巨蛋秀泰", "area": "大巨蛋", "src": "atmovies"},
    {"id": "zs", "name": "真善美", "area": "西門町", "src": "atmovies"},
]
SRC_NAME = {"ambassador": "國賓官網", "atmovies": "開眼電影網"}
DETAIL_VERSION = 3
DETAIL_FIELDS = ("synopsis", "director", "cast", "genre", "release", "en", "trailer")


def load(p, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return default


def main():
    t_start = time.time()
    prev = load(OUT, {})
    details = load(DETAILS, {})
    dates = next_days(3)
    stamp = now_tpe().strftime("%Y-%m-%dT%H:%M")
    movies, shows, theaters, errors = {}, {}, [], []

    def add_movie(info):
        k = movie_key(info.get("title"))
        if not k:
            return None
        m = movies.setdefault(k, {"title": info["title"]})
        # 國賓的海報比較清楚，先到先贏；開眼 id 用來抓簡介和 IMDb
        for f in ("en", "rating", "runtime", "poster", "url", "atmovies"):
            if info.get(f) and not m.get(f):
                m[f] = info[f]
        return k

    for t in THEATERS:
        rec = {k: t[k] for k in ("id", "name", "area")}
        rec["source"] = SRC_NAME[t["src"]]
        try:
            if t["src"] == "ambassador":
                data = ambassador.scrape(t["id"], dates)
                rec["link"] = ambassador.showtime_url(t["id"], dates[0])
            else:
                data = atmovies.scrape(t["id"], dates)
                rec["link"] = atmovies.theater_url(t["id"])
                if data.get("source_updated"):
                    rec["source_updated"] = data["source_updated"]
            idmap = {mid: add_movie(info) for mid, info in data["movies"].items()}
            shows[t["id"]] = {
                d: [[idmap[s[0]], s[1], s[2], s[3], s[4], s[5]] for s in rows if idmap.get(s[0])]
                for d, rows in data["shows"].items()
            }
            rec.update(status="ok", updated=stamp)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            errors.append(f"{t['name']}: {e}")
            old_t = next((x for x in prev.get("theaters", []) if x["id"] == t["id"]), None)
            old_s = prev.get("shows", {}).get(t["id"])
            if old_t and old_s and old_t.get("updated"):
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
            errors.append(f"{fn.__module__}.{fn.__name__}: {e}")
            return fallback

    new_week = try_(atmovies.new_this_week, prev.get("new_week", []))
    coming = try_(atmovies.coming_soon, prev.get("coming", []))
    boxoffice = try_(atmovies.taipei_weekend_boxoffice, prev.get("boxoffice", {}))
    today = now_tpe().date()
    coming = [c for c in coming if c.get("date") and c["date"] > today.isoformat()]

    # 片單裡的電影也補進 movies，點進去才看得到簡介（即使這幾家沒排）
    for lst in (new_week, boxoffice.get("rows", []), coming):
        for it in lst:
            info = {"title": it["title"], "en": it.get("en"), "poster": it.get("poster"),
                    "runtime": it.get("runtime"), "atmovies": it.get("fid")}
            it["key"] = add_movie(info)
            for f in ("fid",):
                it.pop(f, None)

    # ---- 簡介 + 分數（快取在 details.json，不用每次重抓）----
    # 有場次的片優先；每輪最多補抓 40 部簡介，避免第一次跑太久
    order = sorted(movies, key=lambda k: -sum(1 for t in shows.values() for r in t.values() for x in r if x[0] == k))
    budget = 40
    t0 = time.time()
    omdb_err = None
    for k in order:
        time_ok = time.time() - t0 < 360  # 抓簡介和分數最多花 6 分鐘，剩下的下一輪再補（但已有的資料照樣套用）
        m = movies[k]
        d = details.setdefault(k, {})
        if d.get("v", 0) < 2:  # v2 改了簡介解析，舊簡介丟掉重抓
            d.pop("synopsis", None)
        if d.get("v") != DETAIL_VERSION:  # 解析方式改過（v3 加預告片），重抓一次
            d["refresh"] = True
            d["tries"] = 0
            d["v"] = DETAIL_VERSION
        tries = d.get("tries", 0)
        if time_ok and (not d.get("synopsis") or d.get("refresh")) and tries < 3 and budget > 0:
            d.pop("refresh", None)
            budget -= 1
            d["tries"] = tries + 1
            try:
                if m.get("atmovies"):
                    d.update({x: y for x, y in atmovies.movie_detail(m["atmovies"]).items() if y})
                if not d.get("synopsis") and m.get("url") and "ambassador" in m["url"]:
                    d.update({x: y for x, y in ambassador.movie_detail(m["url"], dates[0]).items() if y})
            except Exception as e:  # noqa: BLE001
                print("detail fail", m["title"], e)
        checked = d.get("scores_checked")
        stale = not checked or (today - datetime.fromisoformat(checked).date()) > timedelta(days=3)
        if d.get("scores") and "year" not in d["scores"]:  # 舊快取沒有年份，補查一次
            stale = True
        if (time_ok and not omdb_err and os.environ.get("OMDB_API_KEY") and stale
                and (d.get("imdb_id") or m.get("en") or d.get("en"))):
            try:
                year = (d.get("release") or "")[:4] or today.year
                d["scores"] = extras.omdb(d.get("imdb_id"), m.get("en") or d.get("en"), year) or {}
                d["scores_checked"] = today.isoformat()
            except Exception as e:  # noqa: BLE001
                # 金鑰沒啟用、額度用完之類的錯誤，每部都會一樣，記一次就停
                omdb_err = f"OMDb: {e}"
                errors.append(omdb_err)
        for f in DETAIL_FIELDS:
            if d.get(f) and not (f == "en" and m.get("en")):
                m[f] = d[f]
        if d.get("scores"):
            m["scores"] = d["scores"]
        elif d.get("imdb_id"):
            m["scores"] = {"imdb_id": d["imdb_id"]}

    if not os.environ.get("OMDB_API_KEY"):
        errors.append("OMDb: GitHub 上沒有設定 OMDB_API_KEY")

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
    print(f"耗時 {time.time() - t_start:.0f} 秒")
    print(f"完成：{len(movies)} 部電影、{n} 場；錯誤 {len(errors)} 個")
    for t in theaters:
        print(f"  {t['name']}: {t['status']} " + " ".join(f"{d[5:]}={len(r)}" for d, r in shows.get(t['id'], {}).items()))
    for e in errors:
        print("  -", e)


if __name__ == "__main__":
    main()
