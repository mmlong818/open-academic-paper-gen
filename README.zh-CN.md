<div align="center">

# Open Academic Paper Gen

**从一个研究主题，到每条引用都对照原文核验过的论文初稿**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-pipeline-1C3C3C?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)

[English](./README.md) · 中文

</div>

> 多 Agent 流水线，将一个研究主题转化为基于真实文献的论文初稿，内置引用幻觉检测与论断支撑核验。

---

## 为什么做这个

语言模型能写出流畅的论文，但也会编造参考文献，或者给一条真实存在的文献安上它从未提出过的论断。一篇看起来引用齐全的草稿，仍可能完全不能用。

本项目不信任写作模型。它先检索真实文献（有开放获取版本时抓取全文），要求草稿中的每条引用都指向这个文献池里的某篇论文，然后从三个层面核验每条引用：key 必须可解析，DOI 与元数据必须对得上真实记录，被引论文必须确实支撑引用它的那句话。没通过的会被标记，在严格约束下修订，或留给你审阅。每个阶段之后都有人工审批闸门。

产出是一份带有可核验参考文献列表的初稿。它是研究者的起点，不是成品论文。

## 功能

- **多源检索与开放获取全文。** 检索 OpenAlex、Crossref、Semantic Scholar 与 arXiv；有开放获取版本时抓取 PDF 全文，而不只是摘要。
- **LLM 筛选与引用链扩展。** 逐篇对照主题筛选；沿最强论文的引用链追溯领域经典。
- **证据表。** 每篇文献一行（任务、方法、数据、指标、主要发现、局限），只依据该文献自己的文本抽取，可导出 Markdown 或 CSV。
- **创新点诊断。** 在问题、方法、数据、视角四个层面评估研究角度，列出文献池中最接近的已有工作，并给出审稿人最可能的反对意见。
- **分节写作与 `[cite:KEY]` 标记。** 每条引用都是文献池中的一个 key，因此可以被机械地核验。
- **每条引用三道检查。** key 必须可解析；DOI 与元数据必须对得上真实记录；被引论文必须支撑该论断，有全文时给出最匹配段落所在的 PDF 页码。
- **受约束修订。** 被标记的句子在严格规则下改写，然后重新核验。
- **模拟三审稿人审稿。** 三位侧重点不同的审稿人独立通读终稿；每条意见必须逐字引用原文。
- **写作风格检查。** 标出机器腔表达，仅作建议，不改写正文。
- **导出。** Markdown 或 LaTeX，支持 GB/T 7714、APA 7、数字编号三种参考文献格式，另可导出 RIS 与 BibTeX。参考文献只列实际引用且可解析的论文。
- **人工审批闸门。** 每个阶段都可以暂停供你审阅修改（`key_gates`），也可以整个流程无人值守（`full_auto`）。
- **中英文写作，文献比例可调。** 可分别选择写作语言与中文文献所占的比例。

## 工作原理

```
┌──────────┐   ┌──────────┐   ┌───────────┐   ┌──────────────────┐
│ Next.js  │──▶│ FastAPI  │──▶│ LangGraph │──▶│ PostgreSQL       │
│ frontend │   │ + WS     │   │ pipeline  │   │ Redis (optional) │
└──────────┘   └──────────┘   └─────┬─────┘   └──────────────────┘
                                    │
                                    ▼
             ┌────────────────────────────────────────────────┐
             │ OpenAlex · Crossref · Semantic Scholar · arXiv │
             │ OpenAI / Zhipu GLM                             │
             └────────────────────────────────────────────────┘
```

流水线是一个 9 阶段的 LangGraph 状态机。进度通过 WebSocket 推送到前端；Redis 可选，仅用于进度推送。

| # | 阶段 | 职责 |
|---|------|------|
| 1 | Scoping 立题 | 主题 → 研究问题 + 中英文关键词（按文献比例） |
| 2 | Literature 检索 | 按关键词语种多源检索、去重、评分，按文献比例分配中英文名额 |
| 3 | Cleaning 清洗 | 按 DOI 补摘要、抓取全文、LLM 筛选、引用链扩展；按真实计数生成 PRISMA 流程 |
| 4 | Trends 趋势综合 | 对筛选后的文献池分批综合；生成证据表 |
| 5 | Angle 切入角度 | 研究角度、空白、假设；创新点诊断 |
| 6 | Outline 大纲 | 章节结构与摘要 |
| 7 | Writing 写作 | 按章节撰写；快模型为每节挑选参考文献 |
| 8 | Verification 核验 | 引用核验、受约束修订、模拟审稿、风格检查 |
| 9 | Export 导出 | 按参考文献格式导出 Markdown / LaTeX，RIS / BibTeX，仅列实际引用 |

### 文献处理

- **全文。** 依次尝试：Semantic Scholar 给出的开放获取 PDF、检索源（OpenAlex）给出的 PDF 地址、由 arXiv 编号或 `10.48550/arXiv` DOI 推出的 arXiv PDF。正文从 Abstract / 摘要标题处开始，跳过标题页与版权声明。全文用于核验，不会出现在 API 响应中。
- **补摘要。** 摘要过短、不足以据此筛选的记录，按 DOI 到 OpenAlex 查询；查到更长的摘要才替换，记录标注 `abstract_via: openalex`。
- **筛选。** 依据正文节选或摘要逐篇判断与主题的相关性；没有文本时仅凭标题判断，倾向纳入。每条筛选记录注明判断依据。
- **引用链扩展。** 质量分最高的若干篇作为种子，从 Semantic Scholar 取其参考文献与施引文献，按"关联种子数"等排序，与检索到的文献走同样的筛选。
- **引用 key。** key 由第一作者 + 年份 + 标题首词组成，在文献池定稿后统一分配。不同论文算出同一个 key 时依次加 `b`、`c` 等后缀，保证 key 唯一。
- **文献缓存。** 已抓取的摘要、节选、全文与书目元数据按 DOI 或 arXiv id 缓存，供之后的任务复用；缓存中不存任何任务数据。
- **方法描述。** 方法、摘要与引言只依据流水线记录的事实描述检索过程（来源、检索词、引用链追溯、筛选、年份范围、PRISMA 计数）。提示词禁止编造数据库、检索日期、检索式、筛选人员或任何数量；未记录的细节省略或注明未记录。

## 引用核验

核验聚焦在**幻觉检测**与**论断核对**，而非元数据完整性打分。

**检查一：标记解析。** 正文中每个 `[cite:KEY]` 必须能在文献池里找到对应论文。找不到的 key 被标为幻觉，并在输出中渲染为 `[?KEY]`，方便搜索修正。一个标记可以含多个 key（`[cite:A, cite:B]`），逐个核验。

**检查二：存在性与元数据**（结果中记为 `layer1`）。有 DOI 的论文对照 Crossref 核验。

- 返回 404 时再到 doi.org 查询（覆盖 DataCite 注册的 arXiv 等 DOI）；doi.org 也不认识该 DOI 才判定移除。
- 标题不匹配为警告。标题匹配后，还要核对是否描述同一篇论文：是否有共同作者、第一作者、年份（在线优先出版允许差 1 年）、起始页。DOI 格式不对、年份在未来、记录带撤稿或撤回声明，同样为警告。
- 既无 DOI 也无 arXiv id 的论文，按标题到另一个数据库查询；都查不到则警告。
- 网络错误与无 DOI 默认通过：无法验证不等于无效。
- 同一篇论文用两个 key 引用，或预印本与其正式发表版本同时被引，在第二个 key 或预印本一侧警告。

**检查三：论断支撑**（结果中记为 `layer3`）。对每篇被引论文，由快模型判断原文是否支撑句子归给它的内容。

- 有全文时，证据是论文开头加上与论断最相关的段落；否则用正文节选或摘要。
- 只核对该标记所附着的内容。作者自己的评价、局限性分析和对比不算被引文献的主张。表格按行、按单元格核对，并剔除作者评述列。
- 原文中找不到的细节判为"无法判断"，不判"不支撑"。不支撑会产生一条附原句的警告；这一检查从不删除引用。
- 有页码数据时，警告会注明与论断最匹配的段落所在的 PDF 页，如 `(PDF p. 7)`。页码是 PDF 物理页，不是印刷页码。
- 摘要与全文都太短、无法核对的被引论文，标为 `unverified`，不计入通过；核验面板单独计数。写作时这类文献标为「仅标题」，只能作为某类研究的例子引用。
- 每处论断都会被判定，被引次数多的文献分批判定。核验面板会列出每篇被引文献的论断依据什么判定（全文、正文节选或摘要），以及已判定、无法判断、未判定（无文本或调用失败）各多少处。
- 可选的细分档（`L3_FINE_GRADES`）把部分支撑作为备注、方向相反作为警告。可选的该引未引检查（`VERIFY_UNCITED_CLAIMS`）列出没有引用的事实性陈述。

**修订。** 含被标记句子的段落交给写作模型改一次。它只能改被标记的句子、引用本节候选文献或弱化说法；回复只有在不引入其他 key、且大部分未标记句子逐字保留时才被采用。`full_auto` 下，针对"不支撑"的修订自动应用并复核；`key_gates` 下，所有修订都是建议，面板显示改前改后并附"采纳"按钮。针对"该引未引"的修订始终只是建议。

**输出。** 每条问题标注其最可能的来源阶段（写作或检索）。导出的参考文献列表只包含被实际引用且可解析的论文，按首次出现顺序排列。

## 快速开始

### 前置条件

- Python 3.12+
- Node.js 20+ 与 pnpm
- PostgreSQL：可用 Docker 一键启动，也可以本地安装，见[不用 Docker 运行](#不用-docker-运行)。Redis 可选。
- OpenAI API key，论断核验与审稿需要它。智谱 GLM key 可选（见[配置](#配置)）。

### 1. 克隆和安装

```bash
git clone https://github.com/mmlong818/open-academic-paper-gen.git
cd open-academic-paper-gen

# 后端
cd backend
pip install -e .
cd ..

# 前端
cd frontend
pnpm install
cd ..
```

### 2. 配置环境变量

把 `.env.example` 复制为项目根目录下的 `.env` 并填写。切勿提交此文件。

```env
# 须与 docker-compose.yml 一致（POSTGRES_* 与 REDIS_PASSWORD，下面为默认值）
DATABASE_URL=postgresql+asyncpg://papergen:papergen_dev@localhost:5558/papergen
REDIS_URL=redis://:redis_dev@localhost:6400/0

# 论断核验与审稿需要 OpenAI；智谱可选
OPENAI_API_KEY=your_key_here
ZHIPU_API_KEY=your_key_here

# 以下为模型默认值
OPENAI_MODEL_FAST=gpt-6-luna
OPENAI_MODEL_STRONG=gpt-6.1-sol
ZHIPU_MODEL_FAST=glm-5.3-flash
ZHIPU_MODEL_STRONG=glm-5.1

# 可选：提高开放获取 PDF 的抓取成功率
SEMANTIC_SCHOLAR_API_KEY=

# 推荐：OpenAlex 按每日预算计费，免费 key（openalex.org/settings/api）可提高预算；
# 没有 key 时，长时间运行会频繁遇到 429
OPENALEX_API_KEY=

# 可选：联系邮箱，作为 Crossref / OpenAlex polite pool 的标识发送；
# 留空则不发送
CONTACT_EMAIL=
```

### 3. 启动基础设施

```bash
docker compose up -d postgres redis
```

这会在容器中启动 PostgreSQL（端口 5558）和 Redis（端口 6400）。不想用 Docker，见[不用 Docker 运行](#不用-docker-运行)。

### 4. 启动应用

**Windows（PowerShell）：**

```powershell
.\start.ps1   # 后台启动前后端
.\stop.ps1    # 停止
```

`stop.ps1` 只结束监听 8080 与 3000 端口的进程，以及启动它们的 uvicorn / pnpm / next 进程链；其他 Python、Node 进程不受影响。

**macOS / Linux：**

```bash
# 后端（在项目根目录）
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8080

# 前端（另开终端）
cd frontend && pnpm dev
```

打开 <http://localhost:3000>。

### 不用 Docker 运行

Docker 只负责提供两个数据库，应用本身始终在你的机器上运行。PostgreSQL 必需，Redis 可选。

**PostgreSQL**（已在 16 版上测试）。从 [postgresql.org](https://www.postgresql.org/download/) 下载安装，macOS 可用 `brew install postgresql@16`，Linux 用系统包管理器。然后以 PostgreSQL 超级用户身份（Windows 安装版为 `postgres`，Linux 用 `sudo -u postgres psql`，Homebrew 为你自己的用户）创建用户和数据库：

```bash
psql -U postgres -c "CREATE USER papergen WITH PASSWORD 'papergen_dev';"
psql -U postgres -c "CREATE DATABASE papergen OWNER papergen;"
```

把 `DATABASE_URL` 指向它。本地安装默认监听 5432，而不是 5558：

```env
DATABASE_URL=postgresql+asyncpg://papergen:papergen_dev@localhost:5432/papergen
```

后端首次启动时会自动建表。云端托管的 PostgreSQL 同理：把它的连接串改成 `postgresql+asyncpg://` 开头即可。

**Redis** 可以不装。`REDIS_URL` 保持原样：连不上 Redis 时，后端会记一条警告，改用内存推送进度，单机使用完全够用。

## 配置

所有设置都在 `.env` 中（名称是 `backend/core/config.py` 字段名的大写形式），表中为默认值。

| 设置 | 默认 | 作用 |
|------|------|------|
| `VERIFY_CITATION_SUPPORT` | `true` | 论断支撑检查（检查三），每篇被引论文一次快模型调用 |
| `VERIFY_UNCITED_CLAIMS` | `false` | 该引未引检查，每节一次快模型调用 |
| `REVISE_FLAGGED_CLAIMS` | `true` | 受约束修订被标记的句子 |
| `EXPAND_CITATION_CHAIN` | `true` | 筛选后沿引用链扩展 |
| `RERANK_SECTION_PAPERS` | `true` | 快模型为每节挑选参考文献 |
| `REVIEW_DRAFT` | `true` | 对终稿做模拟审稿 |
| `REVIEW_PANEL` | `true` | 三位独立审稿人（成本约为单审稿人的三倍）；关闭则为单审稿人 |
| `CITATION_GRAPH_OUTLINE` | `false` | 综述类论文：按文献池的引用图主题群组织主体章节 |
| `L3_FINE_GRADES` | `false` | 检查三增加部分支撑与方向相反两档 |
| `EVIDENCE_TABLE_IN_WRITING` | `false` | 把每篇文献的证据表行交给写作模型 |
| `PAPER_CACHE` | `true` | 跨任务复用已抓取的摘要、全文与元数据 |
| `SCREENING_THINKING` | `false` | 让筛选模型先推理再回答（更慢） |
| `SCREENING_CONCURRENCY` | `8` | 筛选时同时进行的调用数 |

任务级选项在新建任务页选择：写作语言、文献比例（`zh_major` 中文约 70%、`balanced` 约 50%、`en_major` 约 20%）以及协作模式（`key_gates` 在每个主要阶段暂停，为默认；`full_auto` 全程运行）。参考文献格式在任务页导出时选择，默认中文论文用 GB/T 7714、英文论文用 APA 7。

**模型与分档。** 分为 fast 与 strong 两档，每个提供方分别用 `OPENAI_MODEL_FAST/STRONG` 与 `ZHIPU_MODEL_FAST/STRONG` 设置。各步骤使用的档位由 `MODEL_TIER_SCOPING`、`MODEL_TIER_SYNTHESIS`、`MODEL_TIER_OUTLINE`（默认均为 `fast`）与 `MODEL_TIER_WRITING`（`strong`）决定。

- fast 档：先用智谱，失败时降级到 OpenAI fast 模型。
- strong 档：先用 OpenAI，失败时降级到智谱。
- 论断支撑检查、该引未引检查与模拟审稿需要 OpenAI key；智谱备用只覆盖其余阶段。审稿使用 OpenAI strong 模型，没有备用模型。
- 某阶段模型调用失败时，任务标为失败并提供重试按钮；不会有占位文本进入审批闸门。
- `LLM_PROVIDER`（默认 `openai`，也可设为 `zhipu`）只决定启动检查与健康检查接口探测哪个 key。

上面的模型 ID 只是默认值；设置 `*_MODEL_*` 变量即可换用你的账号可用的其他模型。

## 评测

`evals/` 在固定题目上离线回放，使改动前后可以在同一文献池上对比。回放报告幻觉 key 率、按证据类型拆分的论断支撑判定、修订前后的该引未引数、修订的应用与解决数、审稿意见数，以及各模型的 LLM 调用数。

```bash
python -m evals.capture                       # 把 evals/topics.json 中的题目冻结到写作之前（耗时数小时，产生 API 费用）
python -m evals.replay --label mychange --compare evals/results/<earlier>.json
python -m evals.replay --set rerank_section_papers=false   # 单次运行临时覆盖配置
```

fixture、结果与标注文件含论文原文，因此不随仓库分发（已加入 gitignore）；请自行运行 `evals.capture` 生成。标注辅助脚本（`evals.sample_l3`、`evals.sample_uncited`、`evals.sample_review`）用于人工抽查判定。

## 局限性

- 核验依赖模型一致使用 `[cite:KEY]` 标记格式。`(作者, 年份)` 这类行文式引用不会被核验。
- 检查二按字符比较标题相似度，跨语言记录（Crossref 的英文标题对本地存的中文标题）可能合理地触发警告。
- 中文期刊很少提供开放获取 PDF 或引用数据，全文证据与引用链扩展对中文题目的帮助远小于英文题目。
- 开放数据源中切题的中文文献相对较少，且很多没有摘要，所以草稿中的中文引用可能偏少且重复。
- 检查三的"不支撑"判定只是筛查辅助，不是裁决：误报并不罕见，不同运行之间结果也会波动。请把每条警告当作需要对照原文核实的线索。
- 论断支撑检查、该引未引检查与审稿需要 OpenAI key。
- 证据表由模型从摘要抽取，有全文时还读取结果、讨论、局限与结论各节；综述类论文的「发现」「局限」有时会填错栏。
- 审稿的推理偶尔会耗尽整个预算；降低推理强度的重试可以兜底，但质量略低。
- Semantic Scholar 在无 API key 时限速激进。
- OpenAlex 需要 API key 才有可用的每日预算。未配置 `OPENALEX_API_KEY` 时，预算用尽后，检索、按 DOI 补摘要与跨库确认都会返回更少的结果。
- 中文数据库检索器（CNKI、万方、维普）是占位，需要机构访问权限，本仓库未提供。
- LaTeX 输出会检查常见问题，但不会编译。

## 免责声明与负责任使用

- 生成的文本只是**草稿**。即使经过核验，也可能含有错误、无依据的论断与对原文的误读。依赖其内容之前，请阅读被引原文并逐条核实论断。
- 你对用本工具产出的任何内容的学术诚信负责：在所在机构、出版方或会议要求时披露 AI 辅助，不要把未经审阅的生成文本作为原创成果提交。
- 本项目与 OpenAlex、Crossref、Semantic Scholar、arXiv、OpenAI、智谱 AI 无任何隶属、认可或赞助关系，仅作为集成的服务被支持。你对这些服务的使用受其各自条款与速率限制约束，你有责任遵守，包括所检索论文自身的许可。
- 切勿提交 API key 或 `.env` 文件。

## 许可

基于 [GNU AGPL-3.0](./LICENSE) 发布。若将修改后的版本作为网络服务运行，必须向其用户提供源代码。第三方依赖的许可证列在 [NOTICE](./NOTICE) 文件中。
