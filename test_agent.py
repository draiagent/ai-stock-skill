"""All fixtures here are synthetic: never evidence of live availability."""
import asyncio, copy, unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import requests
import agent as a

class SafetyTests(unittest.TestCase):
    def quote(self):
        return {'quotes':[{'code':'2330','name':'TEST','date':'2026-10-02','time':'13:30:00','last':'110','prev_close':'100','open':'102','high':'112','low':'101','volume':'200'}]}
    def rows(self):
        return [{'date':f'2026-09-{i:02d}','close':float(i),'open':float(i),'high':float(i+1),'low':float(i-1),'change':1.0,'volume_shares':float(i*100),'note':''} for i in range(1,21)]
    def test_missing_last_never_substitutes_bid(self):
        p=self.quote(); p['quotes'][0].update(last='-',bid='110',ask='111')
        r=a.validate_quote(p,'2330',date(2026,10,5))
        self.assertIsNone(r['price_twd']); self.assertIsNone(r['change_pct']); self.assertEqual(r['status'],'PARTIAL')
    def test_wrong_code_empty_code_rejected(self):
        p=self.quote(); p['quotes'][0]['code']=''
        self.assertEqual(a.validate_quote(p,'99999999',date(2026,10,5))['status'],'NO_DATA')
    def test_missing_timestamp_rejected(self):
        p=self.quote(); del p['quotes'][0]['time']
        self.assertEqual(a.validate_quote(p,'2330',date(2026,10,5))['status'],'INVALID_DATA')
    def test_future_quote_rejected(self):
        self.assertEqual(a.validate_quote(self.quote(),'2330',date(2026,10,1))['status'],'INVALID_DATA')
    def test_holiday_preserves_actual_date(self):
        r=a.validate_quote(self.quote(),'2330',date(2026,10,4)); self.assertEqual(r['date'],'2026-10-02')
    def test_zero_denominator(self):
        p=self.quote(); p['quotes'][0]['prev_close']='0'
        self.assertIsNone(a.validate_quote(p,'2330',date(2026,10,5))['change_pct'])
    def test_nan_not_accepted(self):
        for v in ['NaN','Infinity','--','-',None]: self.assertIsNone(a.num(v))
    def test_ohlc_rejected(self):
        p=self.quote(); p['quotes'][0]['low']='150'
        self.assertEqual(a.validate_quote(p,'2330',date(2026,10,5))['status'],'INVALID_DATA')
    def test_independent_known_arithmetic(self):
        r=a.indicators(self.rows())
        self.assertEqual(r['ma5'],18); self.assertEqual(r['ma20'],10.5)
        self.assertAlmostEqual(r['change_pct'],100/19)
        self.assertAlmostEqual(r['amplitude_pct'],200/19)
        self.assertAlmostEqual(r['volume_ratio'],20/19)
    def test_missing_history_no_skip_over(self):
        rows=self.rows(); rows[-2]['close']=None
        r=a.indicators(rows); self.assertIsNone(r['ma5']); self.assertIsNone(r['ma20'])
    def test_insufficient_history(self):
        r=a.indicators(self.rows()[-3:]); self.assertIsNone(r['ma5']); self.assertIsNone(r['ma20'])
    def test_different_dates_no_comparison(self):
        ss=[{'daily':{'date':d,'close':100,'change_pct':1}} for d in ['2026-10-01','2026-10-02']]
        self.assertEqual(a.comparison(ss,{})['status'],'UNAVAILABLE')
    def test_index_different_day_no_relative(self):
        r=a.comparison([{'code':'2330','daily':{'date':'2026-10-02','close':100,'change_pct':1}}],{'2026-10-01':{'change_pct':2}})
        self.assertIsNone(r['rows'][0]['relative_pp'])
    def test_stale_no_current_strength(self):
        r=a.comparison([{'daily':{'status':'STALE','close':100,'change_pct':1,'date':'2026-09-01'}}],{})
        self.assertEqual(r['status'],'UNAVAILABLE')
    def test_duplicate_dates_rejected(self):
        rows=self.rows(); rows.append(rows[-1])
        with self.assertRaises(ValueError): a.indicators(rows)
    def test_parser_and_conflict(self):
        self.assertEqual(a.parse_query('查台積電 2330'),['2330'])
        self.assertEqual(a.parse_query('比較台積電 2330、聯發科 2454'),['2330','2454'])
        with self.assertRaises(ValueError): a.parse_query('台積電 2454')
    def test_http_failure_recorded_not_fabricated(self):
        with TemporaryDirectory() as t:
            rec=a.Recorder(Path(t))
            with patch('agent.requests.get',side_effect=requests.ConnectionError('SIMULATED connection failure')):
                with self.assertRaises(requests.ConnectionError): a.fetch_json('https://example.invalid',rec)
            self.assertEqual(len(rec.entries),1)
    def test_missing_history_schema_rejected(self):
        with self.assertRaises(ValueError): a.parse_history({'stat':'OK','fields':[]},date(2026,10,5))
    def test_whole_pipeline_outage(self):
        async def no_sleep(*args): pass
        with TemporaryDirectory() as t:
            with patch('agent.streamable_http_client',side_effect=ConnectionError('SIMULATED MCP OFFLINE')), patch('agent.requests.get',side_effect=requests.ConnectionError('SIMULATED TWSE OFFLINE')), patch('agent.asyncio.sleep',new=no_sleep):
                r=asyncio.run(a.run('查台積電 2330',date(2026,10,5),Path(t)))
            self.assertEqual(r['stocks'][0]['daily']['status'],'NO_DATA')
            self.assertIsNone(r['stocks'][0]['daily'].get('close'))
            self.assertEqual(r['comparison']['status'],'UNAVAILABLE')
            self.assertTrue(r['errors'])

if __name__=='__main__': unittest.main(verbosity=2)
