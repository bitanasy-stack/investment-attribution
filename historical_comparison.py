"""在已知历史区间内创建两个事后对照组合，复用同一份行情快照。"""
from copy import deepcopy
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from core import analyze, validate_assets


def build_comparisons(result, config, reference_name):
    if config['mode'] == '离线演示':
        raise ValueError('请先用真实行情完成分析，再生成真实历史对照组合。')
    if 'prices' not in result:
        raise ValueError('这次分析尚未保留行情快照，请先重新点击一次开始分析。')
    original = config['assets']
    validate_assets(original)
    if len(original) < 5:
        raise ValueError('候选资产不足5项，无法创建前3项与前5项两个对照组合。')
    # 重算原组合，确保排名、原收益、新收益全部来自同一快照与同一观测网格。
    baseline = analyze(result['prices'],original,config['capital'],config['risk_free'])
    if not np.isclose(baseline['metrics']['累计收益率'],result['metrics']['累计收益率'],atol=1e-10):
        raise ValueError('行情快照与原结果不一致，请重新运行分析。')
    ranked = baseline['contribution'].sort_values(['资产收益率','代码'],ascending=[False,True],kind='stable')
    by_key = {(a['kind'],a['code']):a for a in original}
    stamp = datetime.now(timezone.utc).isoformat()
    outputs=[]
    specs=[('前3项集中对照',[.35,.35,.30]),('前5项等权对照',[.20]*5)]
    for label,weights in specs:
        selected=[]
        for (_,row),weight in zip(ranked.head(len(weights)).iterrows(),weights):
            asset=deepcopy(by_key[(row['类型'],row['代码'])])
            asset['weight']=weight
            selected.append(asset)
        cfg=deepcopy(config)
        cfg.update(assets=selected,start=baseline['start'],end=baseline['end'])
        cfg['construction']={
            'method':'事后区间收益排名，不是样本外策略',
            'reference_name':reference_name,'selection_start':baseline['start'],
            'selection_end':baseline['end'],'created_at_utc':stamp,
            'universe':[a['kind']+':'+a['code'] for a in original],
            'reference_return':baseline['metrics']['累计收益率'],
            'selection_observations':baseline['observations'],
            'max_weight':max(weights)}
        calculated=analyze(result['prices'],selected,config['capital'],config['risk_free'])
        uplift=calculated['metrics']['累计收益率']-baseline['metrics']['累计收益率']
        cfg['construction']['historical_uplift']=uplift
        # 不把收益未改善的样本冠以高收益组合名称。
        if uplift <= 1e-10:
            raise ValueError('该候选池无法按这两种权重构造出都严格高于原组合的历史结果；未创建组合，也未修改行情。')
        name=f"事后{label} {baseline['start'].replace('-','')}-{baseline['end'].replace('-','')} {reference_name[:8]}"
        outputs.append(dict(name=name,config=cfg,result=calculated,uplift=uplift))
    table=pd.DataFrame([
        {'组合':reference_name,'性质':'原组合','资产数':len(original),**baseline['metrics']},
        *[{'组合':o['name'],'性质':'同区间事后筛选','资产数':len(o['config']['assets']),**o['result']['metrics']} for o in outputs]])
    return outputs,table
