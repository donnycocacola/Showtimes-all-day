"""開發用：用真的瀏覽器打開各家官網，把網頁原始碼和背後載入的資料（XHR/JSON）存到 debug/。

正式爬蟲不會跑這個；只在研究某家網站怎麼抓時手動觸發（Actions → probe）。
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "debug"
KEYWORDS = re.compile(r"(時刻|場次|showtime|ShowTime|theater|Theater|cinema|Cinema|影城|戲院|movie|film|booking|訂票|京站|新店|裕隆|巨蛋|松菸|誠品|真善美)", re.I)

SITES = {
    "vieshow": ["https://www.vscinemas.com.tw/vsweb/theater/index.aspx",
                "https://www.vscinemas.com.tw/vsweb/film/index.aspx"],
    "showtimes": ["https://www.showtimes.com.tw/", "https://www.showtimes.com.tw/programs"],
    "eslite": ["https://www.eslitecinema.com/", "https://www.eslite.com/"],
    "zhenshanmei": ["https://www.cmpc.com.tw/"],
    "atmovies": ["https://www.atmovies.com.tw/showtime/a02/"],
    "ambassador": ["https://www.ambassador.com.tw/home/MovieContent?MID=74a37a70-92f7-42c8-8809-b69f94ee3453",
                   "https://www.ambassador.com.tw/home/Showtime?ID=84b87b82-b936-4a39-b91f-e88328d33b4e"],
}


def run(only=None, max_pages=10):
    with sync_playwright() as p:
        b = p.chromium.launch()
        for site, seeds in SITES.items():
            if only and site not in only:
                continue
            d = OUT / site
            d.mkdir(parents=True, exist_ok=True)
            ctx = b.new_context(locale="zh-TW", user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"))
            page = ctx.new_page()
            net, queue, seen, n = [], list(seeds), set(), 0

            def on_resp(r):
                ct = r.headers.get("content-type", "")
                if r.request.resource_type in ("xhr", "fetch") or "json" in ct:
                    try:
                        body = r.text()
                    except Exception:  # noqa: BLE001
                        body = ""
                    i = len(net)
                    net.append({"url": r.url, "method": r.request.method, "status": r.status,
                                "type": ct, "post": r.request.post_data, "size": len(body), "file": f"xhr_{i:03d}.txt"})
                    (d / f"xhr_{i:03d}.txt").write_text(body[:400000], "utf-8")

            page.on("response", on_resp)
            while queue and n < max_pages:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    page.goto(url, wait_until="networkidle", timeout=45000)
                    page.wait_for_timeout(2500)
                except Exception as e:  # noqa: BLE001
                    (d / f"page_{n:02d}_ERROR.txt").write_text(f"{url}\n{e}", "utf-8")
                    n += 1
                    continue
                (d / f"page_{n:02d}.html").write_text(f"<!-- {page.url} -->\n" + page.content(), "utf-8")
                links = page.eval_on_selector_all("a[href]", "els => els.map(e => [e.href, e.innerText.trim().slice(0,40)])")
                (d / f"page_{n:02d}_links.txt").write_text("\n".join(f"{h}\t{t}" for h, t in links), "utf-8")
                host = urlparse(page.url).netloc
                for h, t in links:
                    if urlparse(h).netloc == host and (KEYWORDS.search(h) or KEYWORDS.search(t)) and h not in seen:
                        queue.append(urljoin(page.url, h.split("#")[0]))
                n += 1
            (d / "network.json").write_text(json.dumps(net, ensure_ascii=False, indent=1), "utf-8")
            ctx.close()
        b.close()


if __name__ == "__main__":
    run(sys.argv[1:] or None)
