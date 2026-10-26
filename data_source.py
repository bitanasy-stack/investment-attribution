"""明确区分在线行情、缓存和合成演示数据，不静默替换。"""
from datetime import datetime
from pathlib import Path
import json
import re
import requests
import os
import pandas as pd

ROOT = Path(__file__).parent
DEMO_CODES = {'股票:600519': '示例股票A', '股票:000001': '示例股票B',
              '基金:110011': '示例基金A', '基金:161725': '示例基金B'}


def clean_series(df, date_col, value_col, key):
    s = pd.Series(pd.to_numeric(df[value_col], errors='coerce').to_numpy(),
                  index=pd.to_datetime(df[date_col], errors='coerce'), name=key)
    s = s[~s.index.isna()].dropna().sort_index()
    return s[~s.index.duplicated(keep='last')]


def fetch_series(kind, code):
    import akshare as ak
    key = kind + ':' + code
    if kind == '股票':
        df = ak.stock_zh_a_hist(symbol=code, period='daily', start_date='19900101',
                              end_date=datetime.now().strftime('%Y%m%d'), adjust='hfq', timeout=12)
        s = clean_series(df, '日期', '收盘', key)
    elif kind == '基金':
        # 累计净值只是分红加回，不能严格代替分红再投资收益，界面明确该限制。
        # 东方财富公开净值文件中的 JSON 数组；不执行远端 JavaScript。
        response = requests.get(f'https://fund.eastmoney.com/pingzhongdata/{code}.js', timeout=20)
        response.raise_for_status()
        match = re.search(r'var Data_ACWorthTrend\s*=\s*(\[.*?\]);', response.text, re.S)
        if not match:
            raise ValueError('基金累计净值字段不存在，该基金可能不受支持。')
        df = pd.DataFrame(json.loads(match.group(1)), columns=['timestamp', '累计净值'])
        df['净值日期'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None).dt.normalize()
        s = clean_series(df, '净值日期', '累计净值', key)
    else:
        df = ak.index_zh_a_hist(symbol='000300', period='daily', start_date='19900101',
                               end_date=datetime.now().strftime('%Y%m%d'))
        s = clean_series(df, '日期', '收盘', key)
    if len(s) < 3 or (s <= 0).any():
        raise ValueError(f'{key} 未返回有效正值序列。')
    return s


def load(assets, start, end, mode):
    if mode in ('Tushare行情', 'Tushare缓存'):
        from tushare_source import load as load_tushare
        return load_tushare(assets, start, end, cached=mode == 'Tushare缓存')
    keys = [a['kind'] + ':' + a['code'] for a in assets] + ['基准:000300']
    notes = []
    if mode == '离线演示':
        df = pd.read_csv(ROOT / 'data' / 'demo_prices.csv', index_col=0, parse_dates=True)
        missing = set(keys) - set(df.columns)
        if missing:
            raise ValueError('离线模式仅支持随附四项示例资产，请使用示例组合。缺少：' + ', '.join(sorted(missing)))
        notes.append('合成教学数据，固定随机种子生成，不是真实历史行情；代码仅用于演示输入。')
    else:
        series = []
        cache = Path(os.environ.get('APP_DATA_DIR',str(ROOT / 'data'))) / 'cache'
        cache.mkdir(parents=True,exist_ok=True)
        for key in keys:
            kind, code = key.split(':')
            path = cache / f'{"stock" if kind == "股票" else "fund" if kind == "基金" else "index"}_{code}.csv'
            if mode == '本地行情缓存':
                if not path.exists():
                    raise ValueError(f'{key} 尚无真实行情缓存，请先在线分析。')
                frame = pd.read_csv(path, index_col=0, parse_dates=True)
                s = frame.iloc[:, 0].rename(key)
                meta = path.with_suffix('.json')
                stamp = json.loads(meta.read_text(encoding='utf-8'))['fetched_at'] if meta.exists() else '未知'
                notes.append(f'{key} 缓存获取时间：{stamp}')
            else:
                try:
                    s = fetch_series(kind, code)
                except Exception as e:
                    raise ValueError(f'{key} 在线获取失败：{type(e).__name__}。请检查代码/网络，或明确切换离线演示。') from e
                s.to_frame().to_csv(path)
                stamp = datetime.now().isoformat(timespec='seconds')
                path.with_suffix('.json').write_text(json.dumps({'fetched_at': stamp, 'key': key}), encoding='utf-8')
                notes.append(f'{key} 在线获取：{stamp}')
            series.append(s)
        df = pd.concat(series, axis=1)
    sliced = df.loc[pd.Timestamp(start):pd.Timestamp(end), keys]
    common = sliced.dropna()
    if len(common) < 3:
        raise ValueError('该区间共同数据少于 3 个观测日。离线数据区间为 2024 年全年。')
    notes.append(f'区间内日期并集 {len(sliced)} 天，共同有效 {len(common)} 天；不前向填充。')
    return common, notes
