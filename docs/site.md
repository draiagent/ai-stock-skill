# 手機互動頁（GitHub Pages）

`site/` 是一個純靜態的手機網頁：讀取 `site/data/latest.json`，把 ai-stock-skill 算好的盤後數字排成可點選的卡片。網頁本身不抓行情、不做計算。

狀態：版面與互動已用手機尺寸實測；目前附的資料是**模擬資料**（`mode: MOCK`，亂數合成），頁面會顯示「模擬」提示列。真實資料的每日排程尚未建立。

## 上線

1. 合併本分支到 `main`。
2. Repo → Settings → Pages → Source 選 **GitHub Actions**。
3. Actions 分頁的「Deploy site to GitHub Pages」跑完後，網址是 `https://draiagent.github.io/ai-stock-skill/`。

## 檔案

|路徑|內容|
|---|---|
|`site/index.html`|單一檔案的頁面（樣式與程式都在裡面）|
|`site/data/latest.json`|頁面讀取的資料，格式 `ai-stock-site/1`|
|`tools/build_site_data.py`|把一份或多份 `report.json` 整併成 `latest.json`；只搬欄位，不重算|
|`tools/make_mock_data.py`|產生模擬報告；合成的日行情會經過 `agent.py` 的 `indicators()` 與 `comparison()`|
|`.github/workflows/pages.yml`|把 `site/` 發佈到 GitHub Pages|

## 換成真實資料

在已安裝好環境的地端（見 README）逐檔執行，再整併：

```powershell
.venv/Scripts/python.exe agent.py '查 2330' --out runs/site/2330
.venv/Scripts/python.exe agent.py '查 2454' --out runs/site/2454
.venv/Scripts/python.exe tools/build_site_data.py runs/site/2330/report.json runs/site/2454/report.json
```

每檔單獨查詢，該檔才會有自己的同日大盤比較。整併時各報告的查詢日與模式必須一致，否則拒絕合併。`--no-series` 可以不輸出近 20 日收盤序列。

公開網頁上放行情數字屬於對外再散布，本 Repo 的 MIT 授權不涵蓋行情資料（見 docs/sources.md）。確認授權前請維持模擬資料，或改放在有登入管制的環境。

## 頁面行為

- 同日比較的閘門與 `agent.py` 的 `comparison()` 相同：任一檔 STALE、缺收盤或漲跌幅、或資料日不同，就不比較並說明原因。
- 缺值顯示「無資料」，不以 0 或其他數字代替；NO_DATA 的股票不顯示任何數字。
- 選取的股票寫在網址 `#codes=2330,2454`，同一個連結貼到群組會開出同一組。
- 漲跌顏色採台股慣例：紅漲綠跌，並同時用 ▲▼ 與正負號標示。
- 來自外部的名稱與文字一律以純文字顯示。
