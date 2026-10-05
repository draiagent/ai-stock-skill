# ai-stock-skill｜台股分析技能

讓 Coding Agent 查詢台灣上市股票、以固定公式分析價量，並交付附來源與時間的報告。

版本 **0.1.0**｜整理日期 **2026-10-05**｜狀態：地端盤後基準版。

## 解決什麼問題

股票查詢不能只給一串數字：來源日期可能不同、成交量單位可能不同，缺成交價也不能以買賣報價補上。本專案將這些規則放進 Skill，並用 Python 執行可重現的計算，供公開教學、課程練習及企業內部研究使用。

## 功能與界線

- 查詢 1–5 個四碼上市股票代號；名稱捷徑支援台積電、聯發科與 TSMC。
- 計算漲跌幅、振幅、MA5、MA20、完整日成交量比與同日相對大盤差值。
- 量比明確指「當日官方成交股數／前一交易日官方成交股數」，不是盤中同時段量比。
- 輸出 report.md、report.json、raw/ 與 SHA-256 manifest；缺資料保留不可用狀態。
- 不支援上櫃歷史、日期區間、還原權息、預測報酬或自動下單。Dots 與 LINE 為第二階段，未包含於本 Repo。

## 流程

任務理解 → 行情取得 → 資料驗證 → 指標計算 → 價量分析 → 綜合判讀 → 結果解釋 → QA 交付。

輸入股票代號、單一日期與比較需求；輸出可核對的報告。驗收看代號、資料時間、數字、來源及缺值處理，不能只看程式退出碼。

## 快速開始：Windows PowerShell

下載並解壓完整 Repo，於包含 agent.py 的資料夾開啟 PowerShell。原交付驗證環境是 Python 3.14.4；鎖定檔含 Windows pywin32，本版不宣稱 Linux/macOS 已驗證。

```powershell
./install.ps1
./run.ps1 '查台積電 2330'
./run.ps1 '比較台積電 2330、聯發科 2454'
./run.ps1 '查台積電 2330' -Date '2026-10-04'
.venv/Scripts/python.exe -m unittest -v test_agent
```

需可存取外部 HTTPS。程式直接使用 MCP SDK，不需先設定全域 MCP、API Key 或付費模型。若安裝受網路或版本限制，應保留錯誤，不能用未驗證版本冒充鎖定版本。

## 在 Coding Agent 中使用

以完整 Repo 為工作目錄，讀取 [.agents/skills/ai-stock-skill/SKILL.md](.agents/skills/ai-stock-skill/SKILL.md)。可明確要求：

> 使用 ai-stock-skill，查台積電 2330；列出來源、資料時間及缺漏，不補造數字。

支援專案 Skill 的宿主可嘗試 `$ai-stock-skill`。新對話自動發現／觸發仍待驗證；本次沒有安裝成個人全域 Skill。

## 輸出與判讀

預設輸出到 `runs/時間戳/`。`--out` 可指定資料夾，請使用新目錄避免覆寫。退出碼 0 僅表示各股有日收盤資料，仍須檢查 `issues`、`errors` 與各區塊 `status`。`PARTIAL` 不代表完整通過；`STALE` 不應當作目前強弱；`NO_DATA` 不得補數字。

完整操作案例見 [examples/queries.md](examples/queries.md)。教案見 [docs/teaching.md](docs/teaching.md)，企業使用見 [docs/enterprise.md](docs/enterprise.md)。

## 工具與來源

|項目|原交付基準|用途|
|---|---|---|
|[taux-io/twse-mcp](https://github.com/taux-io/twse-mcp)|線上 0.15.0，依保存證據|第三方 MCP；不可與 npm 同名專案混用|
|[twstock](https://github.com/mlouielu/twstock)|1.5.1|均線計算；歷史資料由本程式以 HTTPS 擷取|
|MCP Python SDK|2.3.0|直接連線遠端服務|
|TWSE STOCK_DAY／FMTQIK|依各次回應日期|日行情及加權指數|

遠端 MCP 版本無法由本機鎖定，每次保存 initialize 回應。來源連結與資料限制見 [docs/sources.md](docs/sources.md)。此處版本是交付基準，非宣稱最新版本。

## 目錄

|路徑|內容|
|---|---|
|`.agents/skills/ai-stock-skill/SKILL.md`|Agent 任務與防護規則|
|`agent.py`、`test_agent.py`|分析程式與 19 項合成／模擬測試|
|`install.ps1`、`run.ps1`|Windows 安裝與執行|
|`requirements.lock.txt`|沿用原交付精確版本|
|`docs/`、`examples/`|教學、企業使用、VAC 文字對照、操作案例與發布說明|
|`evidence/`|原測試文字紀錄、本輪離線核對與來源識別|
|`ACCEPTANCE.md`|區分原驗收、本輪核對及未驗證項目|

## 驗證與後續

原交付記錄四種真實 API 查詢與 19 項模擬測試通過；本輪已從保存原件離線重算指標並核對 31 份原始回應雜湊。這不等於本輪重新連線交易所。詳見 [ACCEPTANCE.md](ACCEPTANCE.md)。

後續驗證：新機安裝、Skill 宿主載入、真實盤中、雲端及 LINE。完成後才更新相應驗收狀態。

## 授權與署名

本 Repo 採 [MIT License](LICENSE)，著作權人為 AI Coach 益力康陳董。行情資料、第三方套件與商標不因本 Repo 的 MIT 授權而取得再散布權。公開包未附原始行情及個股報告，使用者自行查詢產出的資料也需依來源條件處理。

AI Coach 益力康陳董 x CGM Coach 血糖教練 | 2026 AI to Agent
