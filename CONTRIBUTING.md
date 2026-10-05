# 貢獻方式

先以 Issue 說明查詢、作業系統、Python 版本、資料日期及預期／實際行為；請勿貼金鑰、完整個人路徑或未授權原始資料。

修改後於隔離環境執行 `python -m unittest -v test_agent`，新增防護需搭配能證明錯誤的測試。標示合成測試與真實 API，未執行不得寫 PASS。保留來源、日期一致性、缺值拒絕與成交量口徑規則。

以分支與 Pull Request 提交，說明改動原因、影響及驗證限制；同步更新 CHANGELOG。保留既有 LICENSE 與作者聲明，不提交 runs/ 或 .venv/。
