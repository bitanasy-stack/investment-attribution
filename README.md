# 投资决策归因器

基于 Python、Streamlit 和 SQLite 的本地课程项目。提供股票与基金配置、收益贡献、风险指标、基准比较、用户账户和组合持久化。

## 启动

Windows 安装 Python 3.11 或更高版本。先双击 `安装依赖.bat`，完成后双击 `启动应用.bat`。
浏览器访问 http://127.0.0.1:8501 。保持启动窗口打开，关闭程序按 Ctrl+C。
首次启动自动创建 demo / Demo2026! 演示账户及三个组合。也可自行注册。
如果电脑上的 Python 不在 PATH 中，可在命令行中用实际 Python 路径执行：

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python 初始化演示账户.py
.venv\Scripts\python -m streamlit run app.py
```

本作业目录还提供 `启动已配置应用.bat`，可使用制作时准备好的环境直接启动；换电脑请使用上述通用安装方式。

## 演示

选择“均衡组合”，保持离线演示模式与 2024 年区间，点击“开始分析并保存记录”。
进入收益贡献、风险与结论页，下载 HTML 报告和 CSV。侧栏进入多组合对比，选择三个组合后比较。
离线数据是固定种子生成的合成数据，不是真实行情。其业务日期为工作日，不是真实市场交易日。

随包还附有已实际取得的 `600519` 股票、`110011` 基金和沪深300真实行情缓存，可选择“真实行情缓存示例”组合断网查看真实数据。
缓存的获取时间写在同名JSON中，数据来自公开第三方接口，并非交易所授权行情服务。证券名称是用户标签，不用于代码身份校验。

## 数据与方法

- 股票：AKShare `stock_zh_a_hist` 后复权收盘价。
- 开放式基金：东方财富公开净值文件中的 `Data_ACWorthTrend` JSON 数组，仅解析数据而不执行脚本。涨跌近似收益，无法严格描述分红再投资总回报。
- 基准：`index_zh_a_hist` 沪深300价格指数，不含股息；与资产回报存在口径差异。
- 在线接口依赖第三方网络与服务，可能限流或失效；失败时明确报错，不静默伪造行情。
- 在线数据写入本地 CSV 缓存和带获取时间的 JSON；可明确选择“本地行情缓存”。
- 取资产与基准的共同有效日期，不前向填充，实际区间会在结果显示。
- 买入持有、允许虚拟份额、不含手续费。不是每日再平衡，不做真实交易。
- 组合收益 R=Σwᵢ(PᵢT/Pᵢ0−1)，贡献 Cᵢ=wᵢRᵢ。贡献之和严格等于组合收益。
- 年化收益按实际历日 365.25 年化；风险按252个观测日近似年化。
- 年化波动率为日收益样本标准差乘 √252；夏普为日超额收益均值乘252除以年化波动率，无风险利率默认2%。
- 最大回撤为市值相对历史高点的最大跌幅。零波动时夏普显示不适用。
- 超额收益为组合与基准累计收益率之差，不是 Brinson 配置/选股归因，也不证明管理能力。

## 文件结构

`app.py` 中文交互界面；`core.py` 计算；`storage.py` 账户与数据库；`data_source.py` 数据适配；
`data/demo_prices.csv` 离线数据；`tests/test_project.py` 核心自动测试。
`data/app.sqlite3` 在首次运行时创建，包含本机账户、组合和分析摘要。
删除数据库会清空账户及保存记录，请先备份。历史摘要不是不可变行情快照，完整曲线需在分析时导出。

## 验证

```
python -m unittest discover -s tests -v
```

登录密码使用随机盐和 PBKDF2-HMAC-SHA256（260000次）保存，参数化SQL按用户隔离。
本项目面向本机教学演示，不提供生产级登录限流、找回密码或公网部署保障。

## 官方参考

- Streamlit：https://docs.streamlit.io/
- AKShare：https://akshare.akfamily.xyz/ 及 https://github.com/akfamily/akshare
- pandas：https://pandas.pydata.org/docs/
- Python SQLite：https://docs.python.org/3/library/sqlite3.html
