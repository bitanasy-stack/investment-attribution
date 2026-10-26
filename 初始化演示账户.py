"""幂等地创建演示账户与组合，不覆盖已有账户密码。"""
import storage as db

db.init()
if db.login('demo', 'Demo2026!') is None:
    try:
        db.register('demo', 'Demo2026!')
    except ValueError:
        print('已有同名账户，未改动。请使用自行设置的密码。')
        raise SystemExit(0)
uid = db.login('demo', 'Demo2026!')
examples = {
 '均衡组合': [('股票','600519','示例股票A',.3),('股票','000001','示例股票B',.2),('基金','110011','示例基金A',.5)],
 '股票进取组合': [('股票','600519','示例股票A',.7),('股票','000001','示例股票B',.3)],
 '基金组合': [('基金','110011','示例基金A',.6),('基金','161725','示例基金B',.4)]}
existing = {r['name'] for r in db.portfolios(uid)}
for name, rows in examples.items():
    if name in existing:
        continue
    assets = [dict(zip(['kind','code','name','weight'],row)) for row in rows]
    db.save_portfolio(uid,name,dict(assets=assets,start='2024-01-02',end='2024-12-31',
                                  capital=100000,risk_free=.02,mode='离线演示'))
if (db.DB.parent / 'cache' / 'fund_110011.csv').exists() and '真实行情缓存示例' not in existing:
    assets=[dict(kind='股票',code='600519',name='贵州茅台',weight=.5),
            dict(kind='基金',code='110011',name='基金110011',weight=.5)]
    db.save_portfolio(uid,'真实行情缓存示例',dict(assets=assets,start='2024-01-02',end='2024-12-31',
                 capital=100000,risk_free=.02,mode='本地行情缓存'))
print('演示账户：demo    密码：Demo2026!    已创建三个示例组合。')
