"""投资组合计算。无 UI 依赖，便于单独测试与课堂讲解。"""
import numpy as np
import pandas as pd


def validate_assets(assets):
    if not assets:
        raise ValueError('至少配置一项资产。')
    keys = []
    for a in assets:
        if a['kind'] not in ('股票', '基金'):
            raise ValueError('资产类型只能是股票或基金。')
        if len(a['code']) != 6 or not a['code'].isascii() or not a['code'].isdigit():
            raise ValueError('代码必须为六位数字，保留前导零。')
        if not np.isfinite(a['weight']) or a['weight'] <= 0:
            raise ValueError('权重必须是大于零的有限数值。')
        keys.append(a['kind'] + ':' + a['code'])
    if len(keys) != len(set(keys)):
        raise ValueError('同一类型的资产代码不能重复。')
    if not np.isclose(sum(a['weight'] for a in assets), 1, atol=1e-8):
        raise ValueError('配置比例合计必须等于 100%。')


def metrics(values, risk_free=0.02):
    """按实际历日年化收益，按 252 个观测交易日年化风险。"""
    values = values.astype(float)
    days = (values.index[-1] - values.index[0]).days
    returns = values.pct_change().dropna()
    total = values.iloc[-1] / values.iloc[0] - 1
    annual = (1 + total) ** (365.25 / days) - 1 if days > 0 else np.nan
    vol = returns.std(ddof=1) * np.sqrt(252) if len(returns) >= 2 else np.nan
    sharpe = ((returns.mean() - ((1 + risk_free) ** (1/252) - 1)) * 252 / vol
              if np.isfinite(vol) and vol > 1e-12 else np.nan)
    dd = values / values.cummax() - 1
    return {'累计收益率': total, '年化收益率': annual, '年化波动率': vol,
            '最大回撤': -dd.min(), '夏普比率': sharpe}


def analyze(prices, assets, capital=100000, risk_free=0.02):
    validate_assets(assets)
    if not np.isfinite(capital) or capital <= 0:
        raise ValueError('本金必须大于零。')
    keys = [a['kind'] + ':' + a['code'] for a in assets]
    required = keys + ['基准:000300']
    p = prices[required].copy().sort_index()
    p = p[~p.index.duplicated(keep='last')]
    p = p.replace([np.inf, -np.inf], np.nan).dropna()
    if len(p) < 3:
        raise ValueError('共同有效日期少于 3 个，请扩大时间范围或调整资产。')
    if (p <= 0).any().any():
        raise ValueError('价格或净值必须大于零。')
    norm = p / p.iloc[0]
    weights = np.array([a['weight'] for a in assets])
    # 期初固定份额，之后权重自然漂移；不是每日再平衡。
    values = norm[keys].mul(weights, axis=1) * capital
    portfolio = values.sum(axis=1).rename('组合')
    benchmark = (norm['基准:000300'] * capital).rename('沪深300')
    rows = []
    for i, a in enumerate(assets):
        r = norm[keys[i]].iloc[-1] - 1
        rows.append({'资产': a['name'] or a['code'], '类型': a['kind'], '代码': a['code'],
                     '初始权重': a['weight'], '资产收益率': r, '收益贡献': a['weight'] * r,
                     '盈亏金额': capital * a['weight'] * r,
                     '期末市值': values[keys[i]].iloc[-1]})
    stat = metrics(portfolio, risk_free)
    stat['基准收益率'] = benchmark.iloc[-1] / capital - 1
    stat['超额收益率'] = stat['累计收益率'] - stat['基准收益率']
    return {'curve': pd.concat([portfolio, benchmark], axis=1),
            'prices': p.copy(),
            'drawdown': portfolio / portfolio.cummax() - 1,
            'contribution': pd.DataFrame(rows), 'metrics': stat,
            'observations': len(p), 'start': str(p.index[0].date()), 'end': str(p.index[-1].date())}


def narrative(result, mode):
    m = result['metrics']
    c = result['contribution'].sort_values('收益贡献', ascending=False)
    top, bottom = c.iloc[0], c.iloc[-1]
    return (f"数据模式：{mode}。实际分析区间 {result['start']} 至 {result['end']}，"
            f"共 {result['observations']} 个共同观测日。组合累计收益 {m['累计收益率']:.2%}，"
            f"沪深300同期收益 {m['基准收益率']:.2%}，相差 {m['超额收益率']:.2%}（百分点口径）。"
            f"最大回撤 {m['最大回撤']:.2%}。收益贡献最高的是 {top['资产']}"
            f"（{top['收益贡献']:.2%}），最低的是 {bottom['资产']}（{bottom['收益贡献']:.2%}）。"
            "贡献为初始权重乘以资产区间收益，合计等于组合收益；这不构成配置效应或选股能力证明。"
            "未计交易费用，允许虚拟份额，不构成投资建议。")
