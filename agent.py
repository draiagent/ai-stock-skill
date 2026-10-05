"""Local, deterministic TWSE analysis. No model API, keys, orders or deployment."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, math, re, sys, time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
import requests
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from twstock.analytics import Analytics

TZ = timezone(timedelta(hours=8), 'Asia/Taipei')
MCP_URL = 'https://twse-mcp.taux.io/mcp'
BASE = Path(__file__).resolve().parent
ALIASES = {'台積電':'2330', '聯發科':'2454', 'TSMC':'2330'}
FORMULAS = {
    'change_pct':'(收盤或成交價 / 前收盤 - 1) × 100；不比價時不算',
    'amplitude_pct':'(最高 - 最低) / 前收盤 × 100',
    'ma5_ma20':'最近 5 / 20 筆有效交易日收盤算術平均；視窗有缺值則不計算',
    'volume_ratio':'本日官方成交股數 / 前一筆官方日成交股數；僅完整日資料',
    'relative_pp':'同一交易日個股漲跌幅 - 加權指數漲跌幅（百分點）',
}

def now(): return datetime.now(TZ)

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def num(v):
    if v is None or isinstance(v,bool): return None
    try:
        n=float(str(v).replace(',','').strip())
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None

def roc(v):
    bits=str(v).split('/')
    if len(bits)==3:
        y,m,d=map(int,bits); return date(y+1911 if y<1911 else y,m,d).isoformat()
    return date.fromisoformat(str(v)).isoformat()

def parse_query(query):
    # Date must be explicit via --date, so date digits cannot be mistaken for codes.
    text=re.sub(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', '', query)
    codes=re.findall(r'(?<![0-9A-Za-z])\d{4,10}(?![0-9A-Za-z])',text)
    named=[v for k,v in ALIASES.items() if k.lower() in text.lower()]
    if codes and any(x not in codes for x in named):
        raise ValueError('名稱與代號不一致，請確認後重查')
    codes=list(dict.fromkeys(codes or named))
    if not codes or len(codes)>5: raise ValueError('請提供 1–5 個上市股票代號；名稱目前支援台積電、聯發科')
    return codes

def validate_quote(payload,code,asof):
    rows=[q for q in payload.get('quotes',[]) if q.get('code')==code]
    if len(rows)!=1: return {'code':code,'status':'NO_DATA','issues':['無精確匹配代號；不使用候選或空白代號']}
    q=rows[0]; issues=[]
    try:
        dt=date.fromisoformat(q.get('date',''))
        if dt>asof: raise ValueError()
        datetime.strptime(q.get('time',''),'%H:%M:%S')
    except (TypeError,ValueError):
        return {'code':code,'status':'INVALID_DATA','issues':['資料日期／時間缺失、非法或超出查詢日']}
    values={k:num(q.get(k)) for k in ['last','open','high','low','prev_close','volume']}
    for k,v in values.items():
        if v is None or v<0 or (k!='volume' and v==0):
            issues.append(k+' 缺漏或非法'); values[k]=None
    if all(values[k] is not None for k in ['last','open','high','low']):
        if not values['low']<=min(values['last'],values['open'])<=max(values['last'],values['open'])<=values['high']:
            return {'code':code,'status':'INVALID_DATA','issues':['OHLC 不一致']}
    p,c=values['prev_close'],values['last']
    return {'code':code,'name':q.get('name'), 'status':'PARTIAL' if issues else 'OK',
            'date':dt.isoformat(),'time':q['time'],'price_twd':c,'previous_close_twd':p,
            'change_twd':c-p if c is not None and p else None,
            'change_pct':(c/p-1)*100 if c is not None and p else None,
            'amplitude_pct':(values['high']-values['low'])/p*100 if p and values['high'] is not None and values['low'] is not None else None,
            'volume_lots':values['volume'],'issues':issues,
            'source':MCP_URL+' → quote.realtime → https://mis.twse.com.tw/',
            'scope':'MIS 累計成交量（張），與官方盤後全日成交股數的範圍可能不同，不混合算量比'}

def parse_history(payload,asof,code=None):
    if payload.get('stat')!='OK': raise ValueError('官方未回 OK：'+str(payload.get('stat')))
    if code and not re.search(r'(?<!\d)'+re.escape(code)+r'(?!\d)',str(payload.get('title',''))):
        raise ValueError('官方歷史資料標題代號不匹配')
    fields=payload.get('fields',[])
    required=['日期','成交股數','開盤價','最高價','最低價','收盤價','漲跌價差']
    if not all(f in fields for f in required): raise ValueError('日行情欄位不符合預期')
    result=[]
    for raw in payload.get('data',[]):
        row=dict(zip(fields,raw)); d=roc(row['日期'])
        if d>asof.isoformat(): continue
        r={'date':d, 'volume_shares':num(row['成交股數']), 'open':num(row['開盤價']),
           'high':num(row['最高價']), 'low':num(row['最低價']), 'close':num(row['收盤價']),
           'change':num(row['漲跌價差']), 'note':row.get('註記','')}
        for k in ['open','high','low','close']:
            if r[k] is not None and r[k]<=0: raise ValueError('價格非正數')
        if r['volume_shares'] is not None and (r['volume_shares']<0 or not r['volume_shares'].is_integer()):
            raise ValueError('成交股數非法')
        if all(r[k] is not None for k in ['open','high','low','close']):
            if not r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high']:
                raise ValueError('歷史 OHLC 不一致')
        result.append(r)
    return sorted(result,key=lambda x:x['date'])

def indicators(rows):
    if not rows: return {'status':'NO_DATA','issues':['沒有可用日行情']}
    if len({r['date'] for r in rows})!=len(rows): raise ValueError('重複交易日')
    r=rows[-1]; c=r['close']; change=r['change']
    prev=c-change if c is not None and change is not None else None
    if prev is not None and prev<=0: prev=None
    out={**r,'status':'OK','previous_close':prev,'change_pct':change/prev*100 if prev else None,
         'amplitude_pct':(r['high']-r['low'])/prev*100 if prev and r['high'] is not None and r['low'] is not None else None,
         'ma5':None,'ma20':None,'volume_ratio':None,'issues':[]}
    for n in [5,20]:
        window=rows[-n:]
        if len(window)==n and all(x['close'] is not None for x in window):
            out[f'ma{n}']=Analytics().moving_average([x['close'] for x in window],n)[-1]
        else: out['issues'].append(f'MA{n}：資料不足或視窗缺值')
    if len(rows)>=2 and rows[-2]['volume_shares'] and r['volume_shares'] is not None:
        out['volume_ratio']=r['volume_shares']/rows[-2]['volume_shares']
    else: out['issues'].append('量比：缺少前一筆有效日成交量')
    if any(out[k] is None for k in ['close','change_pct','amplitude_pct','volume_shares']):
        out['issues'].append('價量或前收盤基準缺漏／不比價')
    if out['issues']: out['status']='PARTIAL'
    out['window_start']=rows[max(0,len(rows)-20)]['date']
    out['observations']=len(rows)
    return out

def comparison(stocks,index):
    daily=[s.get('daily',{}) for s in stocks]
    if any(d.get('status')=='STALE' for d in daily):
        return {'status':'UNAVAILABLE','reason':'資料可能過期，不判讀當前相對強弱'}
    if not daily or any(d.get('close') is None or d.get('change_pct') is None for d in daily):
        return {'status':'UNAVAILABLE','reason':'部分股票缺少完整日收盤或漲跌幅'}
    if len({d.get('date') for d in daily})!=1:
        return {'status':'UNAVAILABLE','reason':'股票資料日期不一致，禁止直接比較'}
    dt=daily[0]['date']; rows=[]
    benchmark=index.get(dt)
    for s,d in zip(stocks,daily):
        b=benchmark.get('change_pct') if benchmark else None
        diff=d['change_pct']-b if b is not None else None
        rows.append({'code':s['code'],'change_pct':d['change_pct'],'relative_pp':diff,
                     'inference':('強於' if diff>0 else '弱於' if diff<0 else '持平於')+'同日大盤' if diff is not None else '缺少同日大盤，無法判讀相對強弱'})
    return {'status':'OK' if benchmark and benchmark.get('change_pct') is not None else 'PARTIAL',
            'date':dt,'benchmark':benchmark,'rows':rows,'basis':'同日完整日收盤；價量描述不預測未來漲跌'}

class Recorder:
    def __init__(self,directory): self.directory=directory; self.i=0; self.entries=[]
    def record(self,kind,request,response):
        self.i+=1; path=self.directory/f'{self.i:03d}-{kind}.json'
        obj={'retrieved_at':now().isoformat(),'request':request,'response':response}
        save(path,obj)
        self.entries.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),**{k:obj[k] for k in ['retrieved_at','request']}})
        save(self.directory/'manifest.json',self.entries)

async def tool_call(s,rec,name,args):
    try:
        r=await asyncio.wait_for(s.call_tool(name,args),40)
        raw=r.model_dump(mode='json',by_alias=True)
        rec.record('mcp',{'tool':name,'arguments':args},raw)
        if raw.get('isError'): raise ValueError('MCP tool error: '+str(raw.get('content'))[:300])
        data=raw.get('structuredContent')
        if data is None: data=json.loads(next(x['text'] for x in raw['content'] if x['type']=='text'))
        return data
    except Exception as e:
        rec.record('mcp-error',{'tool':name,'arguments':args},{'error':str(e)})
        raise

def fetch_json(url,rec):
    try:
        r=requests.get(url,timeout=(8,25)); r.raise_for_status(); data=r.json()
        rec.record('official',{'url':url,'http_status':r.status_code},data)
        return data
    except Exception as e:
        rec.record('official-error',{'url':url},{'error':str(e)})
        raise

def months(asof,n=3):
    first=asof.replace(day=1); out=[]
    for _ in range(n):
        out.append(first.strftime('%Y%m%d')); first=(first-timedelta(days=1)).replace(day=1)
    return list(reversed(out))

async def run(query,asof,outdir):
    codes=parse_query(query); started=now(); rec=Recorder(outdir/'raw'); errors=[]
    if asof>started.date(): raise ValueError('不接受未來日期')
    quotes={}; info={}; market={}
    try:
        async with asyncio.timeout(150):
            async with streamable_http_client(MCP_URL) as (r,w):
                async with ClientSession(r,w) as s:
                    init=await s.initialize(); info=init.model_dump(mode='json',by_alias=True)
                    rec.record('initialize',{'url':MCP_URL},info)
                    try:
                        raw=await tool_call(s,rec,'quote.realtime',{'codes':codes,'market':'tse'})
                        quotes={c:validate_quote(raw,c,started.date()) for c in codes}
                    except Exception as e: errors.append('MCP 報價失敗：'+str(e))
                    try: market=await tool_call(s,rec,'snapshot.market',{'scope':'stock'})
                    except Exception as e: errors.append('MCP 大盤失敗：'+str(e))
    except Exception as e: errors.append('MCP 連線失敗：'+str(e))
    stocks=[]
    for code in codes:
        rows=[]; urls=[]; issues=[]
        # Four-digit listed stocks only; unknown codes are not mapped to near matches.
        if not re.fullmatch(r'\d{4}',code):
            stocks.append({'code':code,'quote':quotes.get(code),'daily':{'status':'NO_DATA'},'issues':['本程式僅支援四碼上市股票；不替換錯誤代號']}); continue
        for month in months(asof):
            url=f'https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={month}&stockNo={code}'
            urls.append(url)
            try:
                data=await asyncio.to_thread(fetch_json,url,rec)
                rows.extend(parse_history(data,asof,code))
            except Exception as e: issues.append(month+'：'+str(e))
            await asyncio.sleep(2)
        # Do not label a partial live day a complete daily bar.
        if asof==started.date() and started.hour*60+started.minute<14*60:
            rows=[r for r in rows if r['date']<asof.isoformat()]
        daily=indicators(sorted(rows,key=lambda x:x['date']))
        if issues:
            daily['status']='PARTIAL' if rows else 'NO_DATA'
            # A failed month can break continuity. No moving average / ratio on a gapped download.
            daily.update(ma5=None,ma20=None,volume_ratio=None)
            daily.setdefault('issues',[]).append('月份取得不完整：停算均線與量比')
        if rows:
            lag=(asof-date.fromisoformat(daily['date'])).days
            daily['freshness']='落後超過 7 個日曆日，可能過期' if lag>7 else '來源可取得的最近交易日；不以工作日推算休市'
            if lag>7: daily['status']='STALE'
        q=quotes.get(code,{'code':code,'status':'NO_DATA','issues':['MCP 報價不可用']})
        if asof<started.date(): q={'status':'NOT_APPLICABLE','issues':['歷史查詢不混入目前 MIS 報價；原始回應僅留證據']}
        cross='無同日有效價格可核對'
        if q.get('date')==daily.get('date') and q.get('price_twd') is not None and daily.get('close') is not None:
            cross='同日 MIS 成交價與官方收盤一致' if q['price_twd']==daily['close'] else '同日價格不一致，保留兩來源，需人工確認'
            if q['price_twd']!=daily['close']: issues.append(cross)
        stocks.append({'code':code,'name':q.get('name') or next((k for k,v in ALIASES.items() if v==code),None),
                       'quote':q,'daily':daily,'history':rows,'sources':urls,'issues':issues,'cross_check':cross})
    index={}; index_url=f'https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date={asof:%Y%m}01'
    try:
        data=await asyncio.to_thread(fetch_json,index_url,rec)
        if data.get('stat')!='OK': raise ValueError('大盤無 OK 回應')
        fields=data['fields']
        for raw in data.get('data',[]):
            r=dict(zip(fields,raw)); dt=roc(r['日期'])
            c=num(r.get('發行量加權股價指數')); delta=num(r.get('漲跌點數'))
            if dt<=asof.isoformat(): index[dt]={'close':c,'change':delta,'change_pct':delta/(c-delta)*100 if c is not None and delta is not None and c-delta>0 else None,'source':index_url}
    except Exception as e: errors.append('官方大盤失敗：'+str(e))
    cmp=comparison(stocks,index)
    report={'mode':'REAL_API','query':query,'as_of':asof.isoformat(),'retrieved_at':started.isoformat(),
            'market_state':('歷史日期查詢，採截至查詢日的最近可用交易日' if asof<started.date() else
                            '盤後查詢' if started.hour*60+started.minute>=13*60+30 else '盤前或盤中，請依交易日曆核對'),
            'mcp_server':info.get('serverInfo',info.get('server_info')), 'stocks':stocks,'comparison':cmp,
            'mcp_market':market,'errors':errors,'formulas':FORMULAS,
            'limitations':['價格未還原權息；公司行動可能使跨日報酬與均線失真。','MIS 張數與官方全日股數分列，不混用。','只描述已取得價量，不保證漲跌；未啟用付費模型、交易或部署。','官方資料缺漏時顯示不可用，不以 0、買賣報價或猜測值補齊。']}
    save(outdir/'report.json',report)
    (outdir/'report.md').write_text(render(report),encoding='utf-8')
    return report

def fmt(x): return '無資料' if x is None else f'{x:,.2f}' if isinstance(x,(int,float)) else str(x)

def render(r):
    lines=['# 台股分析（真實 API）','',f"查詢：{r['query']}  ",f"查詢日：{r['as_of']}｜擷取時間：{r['retrieved_at']}｜{r['market_state']}",'',
           '日行情採 TWSE 官方完整日資料；MIS 快照另列。最近交易日以各來源實際日期為準。','',
           '|股票|最近取得交易日|收盤 元|漲跌 元|漲跌 %|成交股數|振幅 %|MA5|MA20|量比|狀態|',
           '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for s in r['stocks']:
        d=s['daily']; lines.append('|'+ '|'.join([s['code']+' '+str(s.get('name') or ''),str(d.get('date','無資料'))]+[fmt(d.get(k)) for k in ['close','change','change_pct','volume_shares','amplitude_pct','ma5','ma20','volume_ratio']]+[d['status']])+'|')
    lines+=['','## MIS 快照與分析依據','']
    for s in r['stocks']:
        q=s.get('quote') or {}; d=s['daily']
        lines += [f"- {s['code']}：MIS {q.get('date','無資料')} {q.get('time','')}，成交價 {fmt(q.get('price_twd'))} 元，累計 {fmt(q.get('volume_lots'))} 張。{s.get('cross_check','')}"]
        if d.get('close') is not None and d.get('ma20') is not None:
            lines += [f"  - 事實：收盤 {fmt(d['close'])}，MA20 {fmt(d['ma20'])}；推論：收盤{'高於' if d['close']>d['ma20'] else '低於或等於'}20 日均線，僅為技術位置描述。"]
        if d.get('volume_ratio') is not None:
            lines += [f"  - 事實：官方全日成交量為前一交易日的 {fmt(d['volume_ratio'])} 倍；不拿盤中累計量與全日量比較。"]
        issues=s.get('issues',[])+d.get('issues',[])+q.get('issues',[])
        if issues: lines+=['  - 限制：'+'；'.join(issues)]
        lines+=['  - '+str(d.get('freshness','無法確認最近交易日'))]
    c=r['comparison']; lines+=['','## 同日比較','',f"狀態：{c['status']}；日期：{c.get('date','無資料')}"]
    if c.get('reason'): lines += [c['reason']]
    for x in c.get('rows',[]): lines += [f"- {x['code']} 漲跌 {fmt(x['change_pct'])}%；較大盤 {fmt(x['relative_pp'])} 個百分點。推論：{x['inference']}。"]
    lines += ['','## 公式與來源','']+[f'- {k}：{v}' for k,v in r['formulas'].items()]
    lines += ['','- MCP：https://twse-mcp.taux.io/mcp → quote.realtime / snapshot.market','- MIS：https://mis.twse.com.tw/']
    for s in r['stocks']: lines += ['- '+u for u in s.get('sources',[])]
    if c.get('benchmark'): lines+=['- 大盤：'+c['benchmark']['source']]
    lines+=['','所有原始回應、擷取時間及 SHA-256 見同目錄 raw/manifest.json。','','## 限制','']+['- '+s for s in r['limitations']]+['- '+s for s in r['errors']]
    return '\n'.join(lines)+'\n'

def main():
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('query'); p.add_argument('--date',type=date.fromisoformat,default=None); p.add_argument('--out',type=Path)
    a=p.parse_args(); dates=re.findall(r'\d{4}-\d{2}-\d{2}',a.query)
    asof=a.date or (date.fromisoformat(dates[0]) if len(dates)==1 else now().date())
    if len(dates)>1: p.error('一次僅支援一個查詢日期')
    out=a.out or BASE/'runs'/now().strftime('%Y%m%d-%H%M%S-%f')
    try:
        result=asyncio.run(run(a.query,asof,out)); print(render(result)); print('報告：',out.resolve())
        return 0 if all(s['daily'].get('close') is not None for s in result['stocks']) else 2
    except (ValueError,requests.RequestException) as e:
        save(out/'error.json',{'mode':'REAL_API','error':str(e),'retrieved_at':now().isoformat()}); print('查詢失敗：',e); return 2

if __name__=='__main__': raise SystemExit(main())
