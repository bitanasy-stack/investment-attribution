"""运行方式：python -m streamlit run app.py"""
import html
import json
from datetime import date, timedelta
import pandas as pd
import plotly.express as px
import streamlit as st
import storage as db
from core import analyze, narrative, validate_assets
from data_source import load
from allocation import TEMPLATES, editor_frame, parse_frame, preview
from tushare_source import get_token
from historical_comparison import build_comparisons
from contribution_view import breakdown, style_table, static_html, COLORS

DATA_MODES = ['离线演示', '在线行情', '本地行情缓存', 'Tushare行情', 'Tushare缓存']

st.set_page_config(page_title='投资决策归因器', page_icon='📈', layout='wide')
st.markdown('''<style>
.stApp {background:#f5f7fb} h1,h2,h3{color:#152b46}
[data-testid="stMetric"] {background:white;padding:18px;border-radius:12px;border:1px solid #e5eaf2}
[data-testid="stSidebar"]{background:#eaf0f8} .block-container{padding-top:2rem}
</style>''', unsafe_allow_html=True)
db.init()

EXAMPLES = {
    '均衡组合': [dict(kind='股票', code='600519', name='示例股票A', weight=.3),
                  dict(kind='股票', code='000001', name='示例股票B', weight=.2),
                  dict(kind='基金', code='110011', name='示例基金A', weight=.5)],
    '股票进取组合': [dict(kind='股票', code='600519', name='示例股票A', weight=.7),
                    dict(kind='股票', code='000001', name='示例股票B', weight=.3)],
    '基金组合': [dict(kind='基金', code='110011', name='示例基金A', weight=.6),
                 dict(kind='基金', code='161725', name='示例基金B', weight=.4)]}


def default_config(assets):
    return dict(assets=assets, start='2024-01-02', end='2024-12-31', capital=100000,
                risk_free=.02, mode='离线演示')


def show_percent(v):
    return '不适用' if pd.isna(v) else f'{v:.2%}'


def result_panel(result, config, name, notes):
    st.subheader(name + ' · 分析结果')
    st.caption(f"{result['start']} → {result['end']} ｜ {result['observations']} 个共同观测日 ｜ {config['mode']}")
    m = result['metrics']
    if config.get('construction'):
        st.info('本组合按同一历史区间的已知收益事后筛选。展示结果含前视偏差，不是样本外回测，也不是未来收益预测。')
    cols = st.columns(4)
    for c, label in zip(cols, ['累计收益率', '超额收益率', '最大回撤', '年化波动率']):
        c.metric(label, show_percent(m[label]))
    c1, c2, c3 = st.columns(3)
    c1.metric('期末资产', f"¥{result['curve']['组合'].iloc[-1]:,.2f}")
    c2.metric('年化收益率', show_percent(m['年化收益率']))
    c3.metric('夏普比率', '不适用' if pd.isna(m['夏普比率']) else f"{m['夏普比率']:.2f}")
    t1, t2, t3 = st.tabs(['收益走势', '收益贡献', '风险与结论'])
    with t1:
        chart = result['curve'] / config['capital'] - 1
        fig = px.line(chart, labels={'value': '累计收益率', 'index': '日期', 'variable': '对象'},
                      color_discrete_sequence=['#167d9a', '#e7a23b'])
        fig.update_layout(yaxis_tickformat='.1%', legend_title_text='')
        st.plotly_chart(fig, width='stretch')
    with t2:
        c,detail,split = breakdown(result,config['capital'])
        st.subheader('整个投资期的静态收益拆分')
        st.caption(f"{result['start']} 至 {result['end']}，按期初权重买入并持有。红色为正贡献，绿色为负贡献，灰色为持平。")
        a,b,d=st.columns(3)
        a.metric('正贡献合计',f"{split['positive']*100:+.2f} 个百分点")
        b.metric('负贡献合计',f"{split['negative']*100:+.2f} 个百分点")
        d.metric('正负相抵后的净贡献',f"{split['net']*100:+.2f} 个百分点")
        st.write(f"正贡献 {split['positive_count']} 项，负贡献 {split['negative_count']} 项，持平 {split['flat_count']} 项；合计盈亏 ¥{split['profit']:+,.2f}。")
        c['贡献标签']=c['贡献 百分点'].map(lambda v:f'{v:+.2f} 个百分点')
        fig = px.bar(c,x='贡献 百分点',y='显示名称',orientation='h',color='方向',
                     text='贡献标签',color_discrete_map=COLORS,
                     category_orders={'显示名称':c['显示名称'].tolist(),'方向':['正贡献','负贡献','持平']})
        fig.update_traces(textposition='outside',cliponaxis=False)
        fig.update_layout(height=max(340,len(c)*42+100),xaxis_title='对组合收益的贡献 百分点',
                          yaxis_title='',margin=dict(l=10,r=135,t=20,b=40))
        fig.add_vline(x=0,line_color='#8895a7',line_width=1)
        st.plotly_chart(fig, width='stretch')
        st.markdown('**逐项拆分明细**')
        st.table(style_table(detail))
        st.caption('自身涨跌幅看资产本身；贡献百分点看它对整个组合的影响。贡献百分点＝期初比例×自身涨跌幅百分数。正负贡献之和等于组合收益；总数使用未四舍五入数据，显示值可能有尾差。')
        st.write('例如：一只股票占本金20%，投资期上涨10%，它对组合贡献的是+2个百分点；10万元本金对应盈利2000元。')
        st.download_button('下载静态收益拆分报告 HTML',static_html(result,config,name,notes).encode('utf-8'),
                           '投资期逐项收益拆分.html','text/html')
        st.download_button('下载详细收益拆分 CSV',detail.to_csv(index=False).encode('utf-8-sig'),
                           '投资期逐项收益拆分.csv','text/csv')
    with t3:
        fig = px.area(result['drawdown'].rename('回撤'), labels={'value':'回撤', 'index':'日期'})
        fig.update_layout(yaxis_tickformat='.1%', showlegend=False)
        st.plotly_chart(fig, width='stretch')
        st.write(narrative(result, config['mode']))
        for note in notes:
            st.caption(note)
    text = narrative(result, config['mode'])
    if config.get('construction'):
        text += ' 本组合按同区间已知收益事后筛选，存在前视偏差，不是可事先实现的策略回测。'
    report = '<!doctype html><meta charset="utf-8"><title>组合分析报告</title>'
    report += '<style>body{font-family:Microsoft YaHei,sans-serif;max-width:1000px;margin:40px auto;line-height:1.8}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #ddd}</style>'
    report += '<h1>' + html.escape(name) + '</h1><p>' + html.escape(text) + '</p>'
    report += '<p>数据说明：' + html.escape('；'.join(notes)) + '</p>'
    report += '<p>方法：期初配置后持有，允许虚拟份额，不含手续费。股票后复权；基金累计净值变化仅为近似；基准为价格指数，不含股息。</p>'
    report += result['contribution'].to_html(index=False, escape=True, float_format=lambda v:f'{v:.6f}')
    report += '<p>上表比例为小数，例如 0.05 表示 5%。</p>'
    a, b, c = st.columns(3)
    a.download_button('下载分析报告 HTML', report.encode('utf-8'), '组合分析报告.html', 'text/html')
    b.download_button('下载收益贡献 CSV', result['contribution'].to_csv(index=False).encode('utf-8-sig'),
                      '收益贡献.csv', 'text/csv')
    c.download_button('下载每日资产 CSV', result['curve'].to_csv().encode('utf-8-sig'), '每日资产.csv', 'text/csv')


def historical_panel(result, config, name):
    if config['mode']=='离线演示':
        return
    st.divider()
    st.subheader('从本次真实结果生成两个历史对照组合')
    st.caption(f"候选池仅限“{name}”已经分析的资产，使用 {result['start']} 至 {result['end']} 同一份行情，不另外请求数据。")
    st.write('前三项集中对照按35%、35%、30%配置；前五项等权对照每项20%。先看计算结果，再保存到你的账户。')
    st.info('这是已知结果后的教学对照，含前视偏差。收益更高不等于回撤更小，也不能说明当时可以提前选中。')
    try:
        outputs,table=build_comparisons(result,config,name)
    except ValueError as e:
        st.caption(str(e))
        return
    st.dataframe(table.style.format({k:('{:.2f}' if k=='夏普比率' else '{:.2%}')
        for k in result['metrics']}),hide_index=True,width='stretch')
    for output in outputs:
        with st.expander(output['name']):
            st.write(f"本区间累计收益 {output['result']['metrics']['累计收益率']:.2%}，比原组合高 {output['uplift']*100:.2f} 个百分点。")
            frame=editor_frame(output['config']['assets'])
            frame['配置金额 元']=frame['比例 %']/100*config['capital']
            st.dataframe(frame.style.format({'比例 %':'{:.2f}','配置金额 元':'{:,.2f}'}),hide_index=True,width='stretch')
    st.download_button('下载两个历史对照的配置 JSON',
        json.dumps([dict(name=o['name'],config=o['config']) for o in outputs],ensure_ascii=False,indent=2).encode('utf-8'),
        '历史对照组合配置.json','application/json')
    if st.button('将两个历史对照保存到我的账户',type='primary'):
        existing={r['name'] for r in db.portfolios(st.session_state.uid)}
        created=[]
        for output in outputs:
            if output['name'] in existing:
                continue
            db.save_portfolio(st.session_state.uid,output['name'],output['config'])
            db.save_analysis(st.session_state.uid,output['name'],output['config'],output['result'])
            created.append(output['name'])
        st.session_state['comparison_defaults']=[name]+[o['name'] for o in outputs]
        st.session_state['comparison_period']=dict(start=result['start'],end=result['end'],mode=config['mode'])
        st.success(f'已新增 {len(created)} 个历史对照组合（同名组合保留不覆盖）。在侧栏点击多组合对比，即可与原组合按本次区间比较。')


if 'uid' not in st.session_state:
    st.title('投资决策归因器')
    st.markdown('### 看清组合表现，理解收益来自哪里')
    st.caption('Python × Streamlit × SQLite ｜ 股票与基金组合分析课程项目')
    left, right = st.columns([1, 1])
    with left:
        login_tab, register_tab = st.tabs(['登录', '注册'])
        with login_tab:
            with st.form('login'):
                username = st.text_input('用户名')
                password = st.text_input('密码', type='password')
                if st.form_submit_button('进入工作台', type='primary'):
                    uid = db.login(username, password)
                    if uid:
                        st.session_state.update(uid=uid, username=username.strip())
                        st.rerun()
                    else:
                        st.error('用户名或密码不正确。')
        with register_tab:
            with st.form('register'):
                user = st.text_input('新用户名')
                pw = st.text_input('新密码', type='password')
                confirm = st.text_input('确认密码', type='password')
                if st.form_submit_button('创建账户'):
                    try:
                        if pw != confirm:
                            raise ValueError('两次密码不一致。')
                        db.register(user, pw)
                        st.success('注册成功，请切换到登录。')
                    except ValueError as e:
                        st.error(str(e))
    with right:
        st.subheader('三步完成一次分析')
        st.write('① 登录后创建三个示例组合。\n\n② 打开组合配置，点击开始分析。\n\n③ 查看收益贡献，并比较多个组合。')
        st.info('首次使用请注册账户。也可运行初始化演示账户.py，创建 demo / Demo2026!。')
        st.warning('离线示例为合成数据，仅用于展示程序功能，不代表真实市场表现。')
    st.stop()

uid = st.session_state.uid
with st.sidebar:
    st.title('📈 归因工作台')
    st.caption('当前用户：' + st.session_state.username)
    page = st.radio('功能导航', ['组合分析', '多组合对比', '历史记录', '使用说明'])
    st.divider()
    if st.button('创建三个示例组合', width='stretch'):
        for name, assets in EXAMPLES.items():
            db.save_portfolio(uid, name, default_config(assets))
        st.success('示例组合已保存，可在列表选择。')
    if st.button('退出登录', width='stretch'):
        st.session_state.clear()
        st.rerun()
    st.caption('组合分析教学应用 · 无真实交易')

st.title('投资决策归因器')
st.caption('股票 × 基金 ｜ 组合表现 · 收益贡献 · 基准对比')
st.warning('离线演示数据是合成数据。在线基金采用累计净值变化近似收益；不代表严格的分红再投资总回报。')
saved = db.portfolios(uid)

if page == '组合分析':
    options = {r['name']: r for r in saved}
    chosen = st.selectbox('打开已保存组合', ['新建组合'] + list(options))
    if chosen == '新建组合':
        template = st.selectbox('配置模板', list(TEMPLATES) + ['离线教学组合 3项'])
        if template == '离线教学组合 3项':
            cfg = default_config(EXAMPLES['均衡组合'])
        else:
            try:
                get_token()
                preferred_mode = 'Tushare行情'
            except ValueError:
                preferred_mode = '在线行情'
            cfg = dict(assets=TEMPLATES[template],start=str(date.today()-timedelta(days=365)),
                       end=str(date.today()),capital=100000,risk_free=.02,mode=preferred_mode)
        st.caption('模板权重仅用于功能演示，可自行修改，不代表投资建议。行业和配置角色是可编辑教学标签，不是实时分类，也不代表基金穿透持仓。')
    else:
        cfg = json.loads(options[chosen]['config'])
        template = ''
    # key 按组合区分，使切换组合立即显示对应配置。
    key = str(options[chosen]['id']) if chosen != '新建组合' else 'new_' + template
    with st.container(border=True):
        a, b, c = st.columns([2, 1, 1])
        name = a.text_input('组合名称', value=chosen if chosen != '新建组合' else template,key='name_'+key)
        capital = b.number_input('初始本金 元', min_value=100.0, value=float(cfg['capital']), step=1000.0,key='capital_'+key)
        mode = c.selectbox('数据模式', DATA_MODES, index=DATA_MODES.index(cfg['mode']),key='mode_'+key)
        st.caption('Tushare模式：股票日线与复权因子、沪深300由Tushare提供；基金继续使用东方财富净值。需要服务端Token和相应接口权限。历史日线不等于盘中实时行情。')
        a, b, c = st.columns(3)
        start = a.date_input('开始日期', date.fromisoformat(cfg['start']),key='start_'+key)
        end = b.date_input('结束日期', date.fromisoformat(cfg['end']),key='end_'+key)
        rf = c.number_input('年化无风险利率 %', min_value=0.0, max_value=20.0, value=cfg['risk_free']*100, step=.1,key='rf_'+key)
        st.subheader('资产明细与配置权重')
        st.caption('可增加或删除资产；编辑后权重与配置金额自动更新。代码为六位，名称为自定义标签，不会自动校验证券名称。')
        frame = editor_frame(cfg['assets'])
        edited = st.data_editor(frame, num_rows='dynamic', hide_index=True, width='stretch',
            key='editor_'+key,
            column_config={'类型':st.column_config.SelectboxColumn(options=['股票', '基金'], required=True),
                           '代码':st.column_config.TextColumn(required=True, max_chars=6),
                           '配置角色':st.column_config.SelectboxColumn(options=['核心','卫星'],required=True),
                           '比例 %':st.column_config.NumberColumn(min_value=.01, max_value=100.0, required=True)})
        allocation, summary = preview(edited, capital)
        a,b,c,d = st.columns(4)
        a.metric('资产数量',str(len(allocation)))
        b.metric('权重合计',f"{summary['total']:.2f}%")
        c.metric('股票 / 基金',f"{summary['stock']:.0f}% / {summary['fund']:.0f}%")
        d.metric('最大单项权重',f"{summary['largest']:.2f}%")
        if abs(summary['total']-100) > 1e-6:
            st.warning(f"权重须合计100%。当前待配置金额：¥{summary['unallocated']:,.2f}（负数表示超配）；不自动归一化。")
        else:
            st.success(f'权重合计100%，已分配本金 ¥{capital:,.2f}。')
        if summary['largest']>30:
            st.info('单项资产权重大于30%，请留意集中度；这是配置提示，不是风险评级。')
        with st.expander('查看配置金额与资产分布',expanded=True):
            st.dataframe(allocation.style.format({'比例 %':'{:.2f}','配置金额 元':'{:,.2f}'}),hide_index=True,width='stretch')
            valid = allocation[allocation['比例 %'].notna() & (allocation['比例 %']>0)].copy()
            if not valid.empty:
                valid['展示标签'] = valid['名称'].fillna(valid['代码']).astype(str)+' · '+valid['代码'].astype(str)
                a,b = st.columns(2)
                with a:
                    st.plotly_chart(px.pie(valid,names='展示标签',values='比例 %',hole=.5,title='单项资产分布'),width='stretch')
                with b:
                    grouped = valid.groupby('行业 / 策略',dropna=False)['比例 %'].sum().reset_index()
                    st.plotly_chart(px.bar(grouped,x='行业 / 策略',y='比例 %',title='教学分类分布'),width='stretch')
                st.caption('图表按当前正权重占比展示；权重未达100%时仍需修正才能分析。基金分类不等于底层行业暴露。')
        st.caption('假设：期初买入后持有，允许虚拟份额，不含交易费用。离线数据覆盖 2024 年工作日，并非真实交易日历。')
        a, b = st.columns(2)
        save = a.button('保存组合配置', width='stretch')
        run = b.button('开始分析并保存记录', type='primary', width='stretch')
    if save or run:
        try:
            assets = parse_frame(edited)
            validate_assets(assets)
            if start >= end:
                raise ValueError('开始日期必须早于结束日期。')
            if end > date.today():
                raise ValueError('结束日期不能晚于今天。')
            config = dict(assets=assets, capital=capital, start=str(start), end=str(end), risk_free=rf/100, mode=mode)
            db.save_portfolio(uid, name, config)
            if run:
                with st.spinner('正在读取数据并计算…'):
                    prices, notes = load(assets, start, end, mode)
                    result = analyze(prices, assets, capital, rf/100)
                    db.save_analysis(uid, name, config, result)
                    st.session_state['last'] = (result, config, name, notes)
                st.success('分析完成，配置和分析摘要已保存。')
            else:
                st.success('配置已保存，重新打开列表即可选择。')
        except (ValueError, KeyError, TypeError) as e:
            st.error(str(e))
    if 'last' in st.session_state:
        result_panel(*st.session_state['last'])
        historical_panel(*st.session_state['last'][:3])
    if chosen != '新建组合':
        with st.expander('删除当前组合'):
            confirmed = st.checkbox('确认删除此组合配置，历史分析记录保留')
            if st.button('删除组合', disabled=not confirmed):
                db.delete_portfolio(uid, options[chosen]['id'])
                st.session_state.pop('last', None)
                st.rerun()

elif page == '多组合对比':
    st.subheader('同一时段，同一数据模式，公平比较')
    options = {r['name']: json.loads(r['config']) for r in saved}
    preferred=[n for n in st.session_state.get('comparison_defaults',[]) if n in options]
    selected = st.multiselect('选择 2～5 个已保存组合', list(options), default=preferred[:5] or list(options)[:3], max_selections=5)
    period=st.session_state.get('comparison_period',dict(start='2024-01-02',end='2024-12-31',mode='离线演示'))
    a, b, c = st.columns(3)
    start = a.date_input('统一开始日期', date.fromisoformat(period['start']))
    end = b.date_input('统一结束日期', date.fromisoformat(period['end']))
    mode = c.selectbox('统一数据模式', DATA_MODES,index=DATA_MODES.index(period['mode']))
    st.caption('统一按 10 万元归一化，按全部资产和基准共同日期计算。无风险利率固定 2%。')
    if any(options[n].get('construction') for n in selected):
        st.info('所选组合包含按同一历史区间事后筛选的教学对照。与原组合的收益差异包含前视偏差，不代表样本外能力。')
    if st.button('比较组合', type='primary'):
        try:
            if len(selected) < 2:
                raise ValueError('请至少选择两个组合。')
            if start >= end or end > date.today():
                raise ValueError('请检查比较日期范围。')
            union = {}
            for name in selected:
                for a in options[name]['assets']:
                    union[a['kind'] + ':' + a['code']] = a
            with st.spinner('正在统一比较区间…'):
                prices, notes = load(list(union.values()), start, end, mode)
                results = {name:analyze(prices, options[name]['assets']) for name in selected}
            curves = pd.DataFrame({name:r['curve']['组合']/100000-1 for name,r in results.items()})
            curves['沪深300'] = next(iter(results.values()))['curve']['沪深300']/100000-1
            fig = px.line(curves, labels={'value':'累计收益率', 'index':'日期', 'variable':'组合'})
            fig.update_layout(yaxis_tickformat='.1%', legend_title_text='')
            st.plotly_chart(fig, width='stretch')
            table = pd.DataFrame({name:r['metrics'] for name,r in results.items()}).T
            st.dataframe(table.style.format({k: ('{:.2f}' if k=='夏普比率' else '{:.2%}') for k in table.columns}), width='stretch')
            r = next(iter(results.values()))
            st.caption(f"共同区间：{r['start']} 至 {r['end']}，{r['observations']} 个观测日；数据模式：{mode}。")
            for note in notes:
                st.caption(note)
            st.download_button('下载对比表 CSV', table.to_csv().encode('utf-8-sig'), '组合对比.csv', 'text/csv')
        except (ValueError, KeyError) as e:
            st.error(str(e))

elif page == '历史记录':
    st.subheader('最近 50 次分析')
    for row in db.history(uid):
        with st.expander(f"#{row['id']} {row['name']} ｜ {row['created']} UTC"):
            cfg, summary = json.loads(row['config']), json.loads(row['result'])
            st.write('数据模式：' + cfg['mode'])
            st.write(f"实际区间：{summary['start']} 至 {summary['end']}")
            st.dataframe(pd.DataFrame([summary['metrics']]).style.format('{:.4f}'), hide_index=True)
            st.json(cfg)
            st.caption('历史保存配置和指标摘要；完整曲线可在分析时导出。重新分析可能因行情修订而变化。')
    if not db.history(uid):
        st.info('暂无记录，完成一次分析后会显示在这里。')

else:
    st.subheader('使用与计算说明')
    st.markdown('''
1. 注册并登录；点击侧栏“创建三个示例组合”。
2. 在组合分析中选择均衡组合，保持离线演示及 2024 年区间，点击开始分析。
3. 查看收益贡献和风险页，下载报告；在多组合对比页比较三个组合。
4. 真实分析时选择在线行情，输入有效 A 股或开放式基金代码。成功获取后可使用行情缓存。

**计算口径**：初始本金乘以初始权重，按价格或净值比例计算固定份额的每日市值；收益贡献等于初始权重乘以区间收益。

**风险口径**：年化收益使用实际历日 365.25 天；波动率及夏普使用 252 日年化。最大回撤为相对历史最高市值的最大跌幅。
夏普为日超额收益均值乘以 252 再除以年化波动率。样本不足或波动为零时不展示有效夏普。

**数据限制**：股票为后复权序列，基金为累计净值序列，其涨跌仅近似基金收益，不是严格分红再投资回报。
沪深300采用价格指数，不含股息，与资产回报口径存在差异。超额收益为两者累计收益率相减，不等同于风险调整收益。
多资产使用共同非缺失日期，不插值；停牌、基金披露频率与数据缺失会影响样本。

**演示数据**：随包 CSV 由固定种子生成，日期为工作日并包含部分市场节假日，证券代码只是输入示例。
界面不提供真实交易、选股推荐或未来预测。登录模块用于本机课程演示，不适合直接暴露公网。
''')
