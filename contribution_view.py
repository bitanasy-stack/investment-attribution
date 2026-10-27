"""投资期内逐项收益拆分及独立静态HTML报告，不请求额外行情。"""
import html
import numpy as np
import pandas as pd

COLORS={'正贡献':'#c43d47','负贡献':'#18815d','持平':'#687789'}


def breakdown(result, capital):
    c=result['contribution'].copy()
    c['初始投入 元']=capital*c['初始权重']
    c['自身涨跌幅 %']=c['资产收益率']*100
    c['贡献 百分点']=c['收益贡献']*100
    c['方向']=np.select([c['收益贡献']>1e-12,c['收益贡献']< -1e-12],['正贡献','负贡献'],default='持平')
    c['显示名称']=c['资产'].astype(str)+' · '+c['代码'].astype(str)
    c=c.sort_values(['收益贡献','代码'],ascending=[False,True],kind='stable').reset_index(drop=True)
    positive=c.loc[c['方向']=='正贡献','收益贡献'].sum()
    negative=c.loc[c['方向']=='负贡献','收益贡献'].sum()
    summary=dict(positive=float(positive),negative=float(negative),net=float(c['收益贡献'].sum()),
                 profit=float(c['盈亏金额'].sum()),
                 positive_count=int((c['方向']=='正贡献').sum()),
                 negative_count=int((c['方向']=='负贡献').sum()),
                 flat_count=int((c['方向']=='持平').sum()))
    if not np.isclose(summary['net'],result['metrics']['累计收益率'],atol=1e-10):
        raise ValueError('逐项贡献合计与组合收益不一致，请重新分析。')
    table=c[['资产','类型','代码','方向','初始权重','初始投入 元','自身涨跌幅 %',
             '贡献 百分点','盈亏金额','期末市值']].rename(columns={'初始权重':'期初比例','盈亏金额':'盈亏金额 元','期末市值':'期末市值 元'})
    return c,table,summary


def style_table(table):
    def direction_color(value):
        return 'color:'+COLORS.get(value,'#152b46')+';font-weight:600'
    return table.style.format({'期初比例':'{:.2%}','初始投入 元':'{:,.2f}',
        '自身涨跌幅 %':'{:+.2f}','贡献 百分点':'{:+.2f}',
        '盈亏金额 元':'{:+,.2f}','期末市值 元':'{:,.2f}'}).map(direction_color,subset=['方向'])


def static_html(result,config,name,notes):
    c,table,s=breakdown(result,config['capital'])
    esc=lambda x: html.escape(str(x),quote=True)
    rows=[]
    for r in table.to_dict('records'):
        cells=[r['资产'],r['类型'],r['代码'],r['方向'],f"{r['期初比例']:.2%}",
               f"{r['初始投入 元']:,.2f}",f"{r['自身涨跌幅 %']:+.2f}",
               f"{r['贡献 百分点']:+.2f}",f"{r['盈亏金额 元']:+,.2f}",f"{r['期末市值 元']:,.2f}"]
        rows.append('<tr style="color:'+COLORS[r['方向']]+'">'+''.join('<td>'+esc(x)+'</td>' for x in cells)+'</tr>')
    max_abs=max(float(c['贡献 百分点'].abs().max()),1e-12)
    height=55+len(c)*34
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 {height}" role="img" aria-label="各资产正负收益贡献，单位百分点">',
         f'<line x1="620" y1="10" x2="620" y2="{height-20}" stroke="#aaa"/>']
    for i,r in c.iterrows():
        y=30+i*34
        value=r['贡献 百分点']; width=abs(value)/max_abs*210
        x=620 if value>=0 else 620-width
        svg.extend([f'<text x="8" y="{y+4}" font-size="14">{esc(r["显示名称"])}</text>',
                    f'<rect x="{x:.2f}" y="{y-11}" width="{width:.2f}" height="22" fill="{COLORS[r["方向"]]}"/>',
                    f'<text x="870" y="{y+4}" font-size="14" fill="{COLORS[r["方向"]]}">{value:+.2f} 个百分点</text>'])
    svg.append('</svg>')
    body=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{esc(name)} 收益拆分</title>
<style>body{{font-family:"Microsoft YaHei",sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;color:#152b46;line-height:1.7}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #d9dfe5;padding:8px;text-align:right}}td:first-child{{text-align:left}}th{{background:#eaf0f8}}svg{{width:100%}}@media print{{body{{margin:0;max-width:none}}tr{{break-inside:avoid}}}}</style>
<h1>{esc(name)} 投资期收益拆分</h1>
<p>{esc(result['start'])} 至 {esc(result['end'])} · 数据模式 {esc(config['mode'])} · 初始本金 ¥{config['capital']:,.2f}</p>
<p>正贡献合计 <b>{s['positive']*100:+.2f}</b> 个百分点，负贡献合计 <b>{s['negative']*100:+.2f}</b> 个百分点，净贡献 <b>{s['net']*100:+.2f}</b> 个百分点。合计盈亏 ¥{s['profit']:+,.2f}。</p>
<p>正贡献{s['positive_count']}项，负贡献{s['negative_count']}项，持平{s['flat_count']}项。红色表示正贡献，绿色表示负贡献，灰色表示持平；数值也标明正负号。</p>'''
    body+=''.join(svg)+'<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in table.columns)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
    body+='<h2>怎么理解</h2><p>自身涨跌幅表示该资产在本区间涨了或跌了多少；贡献百分点表示它把整个组合收益抬高或拉低了多少。贡献百分点 = 期初比例 × 自身涨跌幅百分数；盈亏金额 = 初始投入 × 资产收益率。正负贡献相加等于组合收益率。总数使用未四舍五入数据计算，显示值相加可能有尾差。</p>'
    body+='<p>例如：期初占比20%的股票上涨10%，会贡献+2个百分点；10万元组合中初始投入2万元，盈利2000元。</p>'
    body+='<p>期初买入后固定份额持有，无中途现金流；未计手续费。基金累计净值变化近似收益，股票使用复权估值序列；不是原始成交价收益。</p>'
    if config.get('construction'):
        body+='<p>本组合为同一历史区间已知结果后的事后筛选对照，含前视偏差，不是样本外策略回测。</p>'
    body+='<h2>数据说明</h2>'+''.join('<p>'+esc(n)+'</p>' for n in notes)
    return body+'</html>'
