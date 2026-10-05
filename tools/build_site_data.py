"""把 agent.py 產出的 report.json 整併成網頁用的 site/data/latest.json。

只搬運與挑選欄位，不重新計算任何指標：數字全部來自 agent.py。
唯一的衍生欄位 ma20_position 逐字對應 agent.py render() 的「高於／低於或等於」判斷。

用法：
  python tools/build_site_data.py runs/site/2330/report.json runs/site/2454/report.json
  python tools/build_site_data.py runs/site/*/report.json --no-series
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = 'ai-stock-site/1'
DAILY_KEYS = ['status', 'date', 'close', 'change', 'change_pct', 'previous_close', 'amplitude_pct',
              'ma5', 'ma20', 'volume_shares', 'volume_ratio', 'freshness', 'observations', 'window_start']


def relative_for(code, comparison):
    """從 agent.comparison() 的結果取出單一股票的同日大盤比較；不可用時原樣帶出原因。"""
    if comparison.get('status') not in ('OK', 'PARTIAL'):
        return {'status': 'UNAVAILABLE', 'reason': comparison.get('reason', '無同日比較結果')}
    row = next((r for r in comparison.get('rows', []) if r.get('code') == code), None)
    if row is None:
        return {'status': 'UNAVAILABLE', 'reason': '比較結果中沒有這檔股票'}
    return {'status': comparison['status'], 'date': comparison.get('date'),
            'benchmark': comparison.get('benchmark'), 'relative_pp': row.get('relative_pp'),
            'inference': row.get('inference'), 'basis': comparison.get('basis')}


def slim_stock(stock, comparison, with_series):
    daily = stock.get('daily') or {'status': 'NO_DATA'}
    out = {k: daily.get(k) for k in DAILY_KEYS}
    close, ma20 = out.get('close'), out.get('ma20')
    position = None
    if close is not None and ma20 is not None:
        position = 'above' if close > ma20 else 'below_or_equal'
    issues = list(dict.fromkeys((stock.get('issues') or []) + (daily.get('issues') or [])))
    item = {'code': stock['code'], 'name': stock.get('name'), 'daily': out, 'ma20_position': position,
            'relative': relative_for(stock['code'], comparison), 'issues': issues,
            'sources': stock.get('sources') or []}
    if with_series:
        history = stock.get('history') or []
        item['series'] = [{'date': r['date'], 'close': r['close']} for r in history[-20:] if r.get('close') is not None]
    return item


def build(paths, with_series=True):
    reports = [json.loads(Path(p).read_text(encoding='utf-8')) for p in paths]
    if not reports:
        raise ValueError('沒有任何 report.json')
    for key in ('mode', 'as_of'):
        values = {r.get(key) for r in reports}
        if len(values) != 1:
            raise ValueError(f'各報告的 {key} 不一致：{sorted(map(str, values))}；不合併')
    stocks, seen, errors = [], set(), []
    for r in reports:
        for s in r.get('stocks', []):
            if s['code'] in seen:
                raise ValueError(f"股票 {s['code']} 重複出現在多份報告")
            seen.add(s['code'])
            stocks.append(slim_stock(s, r.get('comparison') or {}, with_series))
        errors += r.get('errors') or []
    first = reports[0]
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip() if (ROOT / 'VERSION').exists() else None
    return {'schema': SCHEMA, 'mode': first['mode'], 'skill': 'ai-stock-skill', 'skill_version': version,
            'as_of': first['as_of'], 'retrieved_at': min(r['retrieved_at'] for r in reports),
            'market_state': first.get('market_state'), 'stocks': stocks,
            'formulas': first.get('formulas') or {}, 'limitations': first.get('limitations') or [],
            'errors': list(dict.fromkeys(errors))}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('reports', nargs='+', type=Path)
    p.add_argument('--out', type=Path, default=ROOT / 'site' / 'data' / 'latest.json')
    p.add_argument('--no-series', action='store_true', help='不輸出近 20 日收盤序列（走勢小圖會隱藏）')
    a = p.parse_args()
    try:
        data = build(a.reports, with_series=not a.no_series)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as e:
        print('整併失敗：', e)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(f"已寫入 {a.out}｜模式 {data['mode']}｜{len(data['stocks'])} 檔｜查詢日 {data['as_of']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
