# 台北場次通

自用的跨戲院電影場次查詢：誠品電影院、西門國賓、長春國賓、京站威秀、新店威秀、巨蛋秀泰、真善美。

- `scraper/`：各家爬蟲，`run.py` 輸出 `docs/data/showtimes.json`
- `docs/`：網頁（GitHub Pages）
- `.github/workflows/update.yml`：台北時間 07:00–01:00 每 2 小時自動更新
- `.github/workflows/probe.yml`：開發用，研究某家網站時手動跑

某家抓失敗時，網頁會保留上一次的資料並標示「舊資料」，不會默默變成沒場次。
