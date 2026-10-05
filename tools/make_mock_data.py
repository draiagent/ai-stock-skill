"""產生網頁展示用的「模擬」報告。價格、成交量與大盤全為亂數合成，不是任何一天的真實行情。

合成的日行情會送進 agent.py 自己的 indicators() 與 comparison()，
所以指標、狀態與判讀文字都由 Skill 的程式產生；這裡只造輸入。

用法：
  python tools/make_mock_data.py            # 寫入 runs/mock/<代號>/report.json
  python tools/build_site_data.py runs/mock/*/report.json
"""
from __future__ import annotations
import json, random, sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent as a  # noqa: E402

AS_OF = date(2026, 10, 2)
RETRIEVED = datetime(2026, 10, 2, 15, 0, 0, tzinfo=a.TZ)
# 代號、名稱、合成起始價、交易日筆數、最後一筆落後查詢日的天數
WATCHLIST = [
    ('2330', '台積電', 500.0, 40, 0),
    ('2454', '聯發科', 300.0, 40, 0),
    ('2317', '鴻海', 120.0, 40, 0),
    ('2308', '台達電', 200.0, 12, 0),   # 筆數不足 20 → MA20 不計算 → PARTIAL
    ('2882', '國泰金', 60.0, 40, 9),    # 最後一筆落後 9 天 → STALE
    ('9999', None, 0.0, 0, 0),          # 查無日行情 → NO_DATA
]


def weekdays_ending(last, n):
    out, d = [], last
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def synth_rows(rng, base, days):
    rows, prev = [], base
    for d in days:
        close = round(prev * (1 + rng.uniform(-0.028, 0.03)) * 2) / 2
        open_ = round(prev * (1 + rng.uniform(-0.01, 0.01)) * 2) / 2
        high = max(open_, close) + rng.choice([0, 0.5, 1, 1.5])
        low = min(open_, close) - rng.choice([0, 0.5, 1, 1.5])
        rows.append({'date': d.isoformat(), 'volume_shares': float(rng.randrange(8_000, 60_000) * 1000),
                     'open': open_, 'high': high, 'low': low, 'close': close,
                     'change': round(close - prev, 2), 'note': ''})
        prev = close
    return rows


def synth_index(rng, days):
    index, prev = {}, 20000.0
    for d in days:
        close = round(prev * (1 + rng.uniform(-0.012, 0.013)), 2)
        delta = round(close - prev, 2)
        index[d.isoformat()] = {'close': close, 'change': delta,
                                'change_pct': delta / (close - delta) * 100, 'source': '模擬資料（非 TWSE 回應）'}
        prev = close
    return index


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    rng = random.Random(20261002)
    index = synth_index(rng, weekdays_ending(AS_OF, 60))
    out_root = ROOT / 'runs' / 'mock'
    for code, name, base, n, lag in WATCHLIST:
        rows = synth_rows(rng, base, weekdays_ending(AS_OF - timedelta(days=lag), n)) if n else []
        daily = a.indicators(rows)
        if rows:  # 與 agent.run() 相同的新鮮度規則
            gap = (AS_OF - date.fromisoformat(daily['date'])).days
            daily['freshness'] = '落後超過 7 個日曆日，可能過期' if gap > 7 else '來源可取得的最近交易日；不以工作日推算休市'
            if gap > 7:
                daily['status'] = 'STALE'
        stock = {'code': code, 'name': name, 'quote': {'status': 'NOT_APPLICABLE', 'issues': ['模擬資料不含 MIS 快照']},
                 'daily': daily, 'history': rows, 'sources': [], 'issues': [], 'cross_check': '無同日有效價格可核對'}
        report = {'mode': 'MOCK', 'query': f'查 {code}', 'as_of': AS_OF.isoformat(), 'retrieved_at': RETRIEVED.isoformat(),
                  'market_state': '模擬資料：亂數合成，僅供版面與流程展示', 'mcp_server': None, 'stocks': [stock],
                  'comparison': a.comparison([stock], index), 'mcp_market': {}, 'errors': [], 'formulas': a.FORMULAS,
                  'limitations': ['本頁數字為亂數合成的模擬資料，不是任何一天的真實行情。',
                                  '價格未還原權息；公司行動可能使跨日報酬與均線失真。',
                                  '只描述已取得價量，不保證漲跌；不提供買賣建議。',
                                  '官方資料缺漏時顯示不可用，不以 0、買賣報價或猜測值補齊。']}
        a.save(out_root / code / 'report.json', report)
        print(code, daily['status'], daily.get('date'), report['comparison']['status'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
