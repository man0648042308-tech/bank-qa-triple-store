> 本仓库为个人作品集公开版：AI 大模型应用开发实战项目，模拟数据，非生产系统。更多项目见作品集主页。

# 银行智能问答系统

> 2026-09-04 最新：指定VM已由AI启动，三库部署、初始化、5组真实集成验证、4/4在线问答评估通过；55项pytest、9项VM身份检查、Ruff及4/4离线评估通过。先读 [最新验收记录](evidence/验收记录.md) 与 [阶段总结](docs/09_阶段总结与下一阶段_2026-09-04.md)。这是“真实三库＋确定性回答”的教学基础版，不是完整生产级RAG或真实LLM验收；PDF/ZIP生成结果以output目录及交付清单为准。

这是 作业的可提交、可运行、可测试和可学习版本，覆盖原题四项要求：

1. 用 Typora 可直接打开的学习总结；
2. Elasticsearch 与 Redis 高频面试题各 10 道；
3. Elasticsearch“练习五：复合查询与高亮显示”；
4. 基于 Elasticsearch、Redis、Neo4j 与 LangChain 思路的银行智能问答系统。

> 重要：本轮AI已完成真实三库联调，但不等于学习者已经掌握。独立能力必须通过“自己运行 → 故障恢复 → 合上资料重写 → 口述解释”留下证据。

## 先看哪个文件

- 交作业：`作业_提交版.md`
- 不知道项目在做什么：`docs/00_项目全景与阅读索引.md`
- 从零运行：`docs/01_从零复现操作手册.md`
- 看懂关键代码：`docs/02_核心代码逐行逐词讲解.md`
- 单独复习当天内容：`docs/03_当天学习总结.md`
- ES 面试：`docs/04_ES高频面试题10道.md`
- Redis 面试：`docs/05_Redis高频面试题10道.md`
- 出错时：`docs/06_常见报错与排查.md`
- 练习独立完成：`docs/07_独立复现训练.md`
- 交作业前核对：`docs/08_提交清单.md`
- 实际验收与未覆盖范围：`evidence/验收记录.md`；打包产物：`output/`

## 项目的一句话流程

系统先从 Neo4j 读取**最新客户画像**并分类问题；领域外问题立即拒答。其余问题把“客户编号 + 最新画像指纹（当前含姓名、风险等级、可用金额）+ 产品目录指纹 + 规范化问题摘要 + 数据版本”组成缓存合同；未命中时才执行 Elasticsearch 与 Neo4j 双路检索和 RRF 融合，随后事实问答定位明确产品，个性化推荐执行状态、风险、金额硬过滤，最后生成回答并写入限时缓存。

## 先运行不依赖数据库的版本

在 VS Code 的 PowerShell 终端中执行：

```powershell
Set-Location "./_Bank_QA_project"
$env:PYTHONIOENCODING = "utf-8"
uv sync --python 3.12
uv run python -m pytest -q
uv run python -m _bank_qa.evaluation
uv run python -m _bank_qa.main --offline --customer-id C001 --question "我有5000元，请推荐稳健产品" --top-k 3
```

说明：

- `--offline` 显式使用内存中的教学数据；即使省略它也默认离线，不要求 Elasticsearch、Redis 或 Neo4j 已启动；
- 离线结果用于先学业务流程和运行测试，不代表三库已经连通；
- 2026-08-31本地离线验收：47项pytest通过、Ruff通过、compileall通过、固定评估集4/4且分数1.0；这不等于VM三库已经真实联调。

## 真实三库版本

本项目采用“Windows 运行 Python，VMware 虚拟机运行 Docker 数据库”的分层方式：

```text
Windows: ./_Bank_QA_project
   |
   +-- SSH隧道 127.0.0.1:19200 -> VM回环:19200 -> Elasticsearch
   +-- SSH隧道 127.0.0.1:6380  -> VM回环:6380  -> Redis
   +-- SSH隧道 127.0.0.1:7476  -> VM回环:7476  -> Neo4j HTTP
   +-- SSH隧道 127.0.0.1:7689  -> VM回环:7689  -> Neo4j Bolt
```

不要直接复制固定虚拟机 IP。先执行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\01_检查VM.ps1"
```

本机2026-09-04实测：vmrun不能通过Tools返回IP，但SSH可用。已增加安全替代路径：显式传入本次核验的 `-VmIp 192.168.220.77`，脚本会比较SSH远端DMI UUID与指定VMX的BIOS UUID，匹配才继续。它不是盲信固定IP。后续02/03/04/06脚本也传同一参数；其他电脑或地址变化后必须重新核验。虚拟机和隧道当前已经启动，无需重复安装数据库。

部署后必须启动本地SSH隧道，Windows应用不得直接连接VMnet8上的数据库端口：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\06_启动SSH隧道.ps1"
```

结束实验时先运行 `scripts/07_停止SSH隧道.ps1`，再按需停止Day37容器。完整顺序见 `docs/01_从零复现操作手册.md`。

真实银行问答还需初始化独立的中文银行知识索引：

```powershell
uv run python -m _bank_qa.prepare_bank_index
```

## 练习五最短入口

数据库启动并初始化产品索引后：

```powershell
uv run python -m exercise05.prepare_product_index
uv run python -m exercise05.run_exercise05 --keyword "phone" --min-price 100 --max-price 800 --category "electronics"
```

需要理解的合同：练习商品名使用空格，例如 `phone model 001`；价格是 `float`；关键词进入 `bool.must`；价格和品类进入 `bool.filter`；结果最多 10 条；同时返回总命中数，并用 `<em>...</em>` 标出名称中的关键词。若同名索引已经存在但 mapping、文档ID、数量、字段、值或类型不符，初始化必须拒绝继续，不能删除未知索引制造通过。

## FastAPI 可选加分入口

```powershell
$env:_API_KEY = Read-Host "请为本次终端输入临时API密钥"
uv run uvicorn _bank_qa.api:app --host 127.0.0.1 --port 8000
```

启动后浏览器访问：

```text
http://127.0.0.1:8000/docs
```

`/health`、`/products/search`、`/qa/ask`三个业务端点都要求请求头 `X-API-Key`。密钥只保存在当前PowerShell进程的 `_API_KEY` 环境变量中，不写进源码、Markdown、命令历史示例或提交包。示例请求：

```powershell
$headers = @{ "X-API-Key" = $env:_API_KEY }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Headers $headers
Invoke-RestMethod -Uri "http://127.0.0.1:8000/qa/ask" -Method Post -Headers $headers -ContentType "application/json" -Body '{"customer_id":"C001","question":"安心存款的起投金额是多少？","top_k":3}'
```

未带密钥或密钥错误必须返回401；正确密钥才返回200。API是求职加分项，不应阻塞Day37四项必交内容。

## 三种问题必须分开

- **事实问答**：例如“安心存款的起投金额是多少？”——依据产品资料回答特点、风险等级或起投金额，不把事实查询伪装成个性化推荐。
- **个性化推荐**：例如“我有5000元，请推荐低风险产品”——必须结合最新客户画像并通过状态、风险和金额硬过滤。
- **无关问题**：例如“今天天气怎么样？”——明确拒答，不返回任何产品ID或来源。

## 安全边界

- 项目数据均为虚构教学数据，不是真实银行客户数据。
- `.env`、密码、API Key、Token 不进入提交包。
- Neo4j 查询必须参数化，禁止拼接客户输入。
- 金融适配规则是硬门槛：风险越级、金额不足、产品非在售均不得推荐。
- Redis 缓存键必须包含客户编号、最新画像指纹、产品目录指纹、规范化问题摘要和数据版本；画像或产品目录变化后不得命中旧推荐。
- ES、Redis、Neo4j的Docker端口只绑定VM的`127.0.0.1`；Windows只通过SSH隧道访问。
- Elasticsearch服务器固定`8.18.0`，Python客户端锁定`8.18.1`（依赖合同`>=8.18,<8.19`）。
- FastAPI三个业务端点必须校验`X-API-Key`，真实值只放`_API_KEY`当前进程环境变量。
- 容器、网络和数据卷使用隔离名称；不得删除 ～36 的旧资源。
- Milvus 不属于 最低交付范围，本项目不依赖其启动。

## 学习完成标准

“看到懂”只算第一层。真正完成至少需要：

1. 自己从根目录运行全部测试；
2. 自己运行练习五并解释查询体；
3. 自己制造一次数据库连接错误并恢复；
4. 合上资料重写 `build_product_search_body()` 的核心条件；
5. 不看稿口述 Redis、ES、Neo4j 各自的职责以及硬过滤为什么不能交给 LLM。

