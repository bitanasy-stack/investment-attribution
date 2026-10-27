"""Tushare Pro 股票日线适配。令牌仅从服务端环境或 Streamlit secrets 读取。"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests


def get_token():
    token = os.environ.get('TUSHARE_TOKEN', '').strip()
    if not token:
        try:
            import streamlit as st
            token = str(st.secrets.get('TUSHARE_TOKEN', '')).strip()
        except (FileNotFoundError, KeyError):
            pass
    if not token:
        raise ValueError('尚未配置 TUSHARE_TOKEN。请在服务器私密配置中设置，不要写入源码。')
    return token


def query(api_name, params, fields, token):
    problem='连接异常'
    for attempt in range(3):
        try:
            response = requests.post('https://api.tushare.pro', json={
                'api_name':api_name, 'token':token, 'params':params, 'fields':fields},
                timeout=(5, 18), allow_redirects=False)
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValueError('unexpected redirect')
            payload = response.json()
            if not isinstance(payload,dict):
                raise ValueError('unexpected response')
        except requests.Timeout:
            problem='请求超时'
        except requests.HTTPError as err:
            status=err.response.status_code if err.response is not None else None
            if status is not None and status not in (408,429,500,502,503,504):
                raise ValueError(f'Tushare {api_name} HTTP响应异常（{status}），请检查服务状态或配置。') from None
            problem=f'上游HTTP异常（{status}）'
        except requests.RequestException:
            problem='网络连接异常'
        except ValueError:
            problem='接口未返回有效JSON数据'
        else:
            if payload.get('code') == 0:
                break
            message=str(payload.get('msg') or '')
            if any(word in message for word in ('频率','频次','每分钟','稍后','繁忙')):
                problem='达到接口调用频率或上游服务繁忙'
            else:
                # 不回显完整响应或令牌；权限和认证失败不反复请求。
                raise ValueError(f'Tushare {api_name} 调用未成功，请检查Token及该接口权限。未替换为模拟数据。') from None
        if attempt < 2:
            time.sleep(1+attempt)
    else:
        raise ValueError(f'Tushare {api_name} {problem}，已尝试3次。若此前同一区间分析成功，可切换“Tushare缓存”；否则稍后重试。') from None
    data = payload.get('data') or {}
    frame = pd.DataFrame(data.get('items') or [], columns=data.get('fields') or [])
    if not frame.empty and not set(fields.split(',')).issubset(frame.columns):
        raise ValueError(f'Tushare {api_name} 返回字段不完整。')
    return frame


def stock_code(code):
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        raise ValueError('股票代码必须为六位数字。')
    if code.startswith(('60', '68')):
        return code + '.SH'
    if code.startswith(('00', '30')):
        return code + '.SZ'
    if code.startswith(('4', '8', '92')):
        return code + '.BJ'
    raise ValueError('暂不支持该股票代码格式，请使用沪深北 A 股代码。')


def fetch(kind, code, start, end, token):
    """每年一段，避免日线接口单次行数上限导致历史数据被截断。"""
    if kind == '基金':
        # 当前接入范围为股票行情，基金继续使用已验证的公开净值来源。
        from data_source import fetch_series
        return fetch_series(kind, code), '东方财富累计净值（基金仍使用原数据源）'
    begin, finish = pd.Timestamp(start), pd.Timestamp(end)
    if begin >= finish:
        raise ValueError('开始日期必须早于结束日期。')
    blocks = []
    while begin <= finish:
        stop = min(begin + pd.DateOffset(years=1) - pd.Timedelta(days=1), finish)
        params = dict(ts_code=stock_code(code) if kind == '股票' else '000300.SH',
                      start_date=begin.strftime('%Y%m%d'), end_date=stop.strftime('%Y%m%d'))
        api = 'daily' if kind == '股票' else 'index_daily'
        prices = query(api, params, 'trade_date,close', token)
        if not prices.empty:
            if kind == '股票':
                factors = query('adj_factor', params, 'trade_date,adj_factor', token)
                if factors.empty:
                    raise ValueError('Tushare 未返回复权因子，无法进行一致口径的股票收益分析。')
                prices = prices.merge(factors, on='trade_date', how='left', validate='one_to_one')
                if prices['adj_factor'].isna().any():
                    raise ValueError('Tushare 部分股票日期缺少复权因子，停止计算。')
                prices['close'] = pd.to_numeric(prices['close']) * pd.to_numeric(prices['adj_factor'])
            blocks.append(prices[['trade_date','close']])
        begin = stop + pd.Timedelta(days=1)
    if not blocks:
        raise ValueError('Tushare 未返回所选区间的行情，请检查代码与上市日期。')
    from data_source import clean_series
    s = clean_series(pd.concat(blocks, ignore_index=True), 'trade_date','close',kind+':'+code)
    if s.empty or (s <= 0).any():
        raise ValueError('Tushare 行情包含无效值。')
    return s, ('Tushare daily × adj_factor 复权价格比例' if kind=='股票' else 'Tushare 沪深300价格指数')


def load(assets, start, end, cached=False):
    from data_source import ROOT
    data_root = Path(os.environ.get('APP_DATA_DIR', str(ROOT / 'data')))
    cache = data_root / 'cache' / 'tushare'
    cache.mkdir(parents=True, exist_ok=True)
    token = None if cached else get_token()
    series, notes = [], []
    identifiers = [(a['kind'], a['code']) for a in assets] + [('基准','000300')]
    for kind, code in identifiers:
        key = kind+':'+code
        # 每次请求区间单独缓存，避免覆盖其他区间后悄悄缩短结果。
        filename = f'{"stock" if kind=="股票" else "fund" if kind=="基金" else "index"}_{code}_{str(start)}_{str(end)}'
        path = cache / (filename + '.csv')
        meta = cache / (filename + '.json')
        fresh=False
        if not cached and path.exists() and meta.exists():
            try:
                fetched=json.loads(meta.read_text(encoding='utf-8'))['fetched_at']
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(fetched)).total_seconds()
                fresh=0 <= age <= 900
                if fresh:
                    candidate=pd.read_csv(path,index_col=0,parse_dates=True)
                    fresh=len(candidate)>=3 and candidate.iloc[:,0].notna().all() and (candidate.iloc[:,0]>0).all()
            except (ValueError,KeyError,TypeError,OSError):
                fresh=False
        if cached or fresh:
            if not path.exists() or not meta.exists():
                raise ValueError(f'{key} 在该日期区间没有Tushare模式缓存，请先完成在线分析。')
            s = pd.read_csv(path,index_col=0,parse_dates=True).iloc[:,0].rename(key)
            info = json.loads(meta.read_text(encoding='utf-8'))
        else:
            s, source = fetch(kind, code, start, end, token)
            info = dict(source=source, fetched_at=datetime.now(timezone.utc).isoformat())
            s.to_frame().to_csv(path)
            meta.write_text(json.dumps(info,ensure_ascii=False),encoding='utf-8')
        reuse='；复用15分钟内同区间缓存' if fresh else ('；手动选择历史缓存' if cached else '')
        notes.append(f"{key}：{info['source']}；获取时间 {info['fetched_at']}{reuse}")
        series.append(s)
    combined = pd.concat(series,axis=1).loc[pd.Timestamp(start):pd.Timestamp(end)]
    common = combined.dropna()
    if len(common)<3:
        raise ValueError('共同有效行情少于3个观测日，请调整时间或资产。')
    notes.append(f'日期并集 {len(combined)} 天，共同有效 {len(common)} 天；不填充缺失数据。')
    return common, notes
