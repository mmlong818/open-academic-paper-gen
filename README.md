# Open Academic Paper Gen

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](./LICENSE)

> A multi-agent pipeline that turns a research topic into a draft academic paper grounded in real literature, with built-in citation hallucination detection and claim-support checking.

中文版：[README.zh-CN.md](./README.zh-CN.md)

---

## Why

Language models write fluent papers, but they also invent references, and they attach real references to claims the cited paper never made. A draft that looks well cited can still be unusable.

This project does not trust the writer. It retrieves real papers first (with open-access full text where available), forces every citation in the draft to point at a paper in that pool, and then checks each citation three ways: the key must resolve, the DOI and metadata must match a real record, and the cited paper must actually support the sentence that cites it. Whatever fails is flagged, revised under strict constraints, or left for you to review. A human approval gate sits after every stage.

The output is a draft with a verifiable reference list. It is a starting point for a researcher, not a finished paper.

## Features

- **Multi-source retrieval with open-access full text.** Searches OpenAlex, Crossref, Semantic Scholar and arXiv, and fetches PDF full text where an open-access copy exists, not only abstracts.
- **LLM screening and citation-chain expansion.** Each paper is screened against the topic; the citation links of the strongest papers are followed to recover the field's classics.
- **Evidence table.** One row per paper (task, method, data, metric, finding, limitation) extracted only from that paper's own text, exportable as Markdown or CSV.
- **Novelty diagnosis.** Grades the research angle on problem, method, data and perspective, names the closest existing papers in the pool, and states the objection a reviewer would most likely raise.
- **Section-by-section writing with `[cite:KEY]` markers.** Every citation is a key into the literature pool, so it can be checked mechanically.
- **Three checks on every citation.** The key must resolve; the DOI and metadata must match a real record; and the cited paper must support the claim, with the PDF page of the best-matching passage when full text is available.
- **Constrained revision.** Flagged sentences are rewritten under strict rules, then verified again.
- **Simulated three-reviewer review.** Three reviewers with different focuses read the final draft independently; comments must quote the draft verbatim.
- **Writing-style check.** Flags machine-flavoured prose as suggestions; nothing is rewritten.
- **Export.** Markdown or LaTeX in GB/T 7714, APA 7 or numeric reference style, plus RIS and BibTeX. Only papers that were actually cited and resolvable are listed.
- **Human approval gates.** Every stage can pause for review and editing (`key_gates`), or the whole run can go unattended (`full_auto`).
- **Chinese and English writing, with a configurable literature mix.** Choose the writing language and how much of the literature should be Chinese.

## How it works

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

The pipeline is a nine-stage LangGraph state machine. Progress is pushed to the frontend over WebSocket; Redis is optional and only used for progress pub-sub.

| # | Phase | Role |
|---|-------|------|
| 1 | Scoping | Topic to research questions and Chinese and English keywords, according to the literature mix |
| 2 | Literature | Multi-source search by keyword language, deduplication, scoring, split by the literature mix |
| 3 | Cleaning | Abstract lookup by DOI, full-text fetch, LLM screening, citation-chain expansion; a PRISMA flow built from the real counts |
| 4 | Trends | Chunked synthesis across the screened pool; evidence table |
| 5 | Angle | Research angle, gap and hypothesis; novelty diagnosis |
| 6 | Outline | Section structure with summaries |
| 7 | Writing | Per-section drafting; a fast model picks each section's papers |
| 8 | Verification | Citation checks, constrained revision, simulated review, style checks |
| 9 | Export | Markdown / LaTeX in a reference style, RIS / BibTeX, cited-only references |

### Literature handling

- **Full text.** PDFs are tried in order: the open-access PDF reported by Semantic Scholar, the PDF URL returned by the searcher (OpenAlex), then the arXiv PDF derived from an arXiv id or a `10.48550/arXiv` DOI. Text starts at the Abstract heading, skipping title pages and license notices. Full text is used for verification and is never returned in API responses.
- **Abstract lookup.** A record whose abstract is too short to screen on is looked up on OpenAlex by DOI; a longer abstract replaces the one held and the record is marked `abstract_via: openalex`.
- **Screening.** Each paper is judged against the topic from its excerpt or abstract, or from its title alone when there is no text, leaning to include. Each screening row records its basis.
- **Citation chaining.** The highest-scoring papers become seeds; their references and citations are pulled from Semantic Scholar, ranked by how many seeds link to them, and screened like searched papers.
- **Citation keys.** Keys are first author + year + first title word, assigned once the pool is final. Distinct papers that compute the same key get `b`, `c`, ... suffixes, so every key is unique.
- **Paper cache.** Fetched abstracts, excerpts, full text and bibliographic metadata are cached by DOI or arXiv id and reused by later tasks. No task data is stored in the cache.
- **Methodology text.** The Methodology, Abstract and Introduction describe the search only from facts the pipeline recorded (sources, search terms, citation chaining, screening, year span, PRISMA counts). The writer is told not to invent databases, search dates, query strings, reviewers or counts; an unrecorded detail is left out or stated as not recorded.

## Citation verification

Verification is aimed at hallucination detection and claim checking, not at grading metadata completeness.

**Check 1: marker resolution.** Every `[cite:KEY]` in the body must resolve to a paper in the literature pool. An unresolved key is flagged as hallucinated and rendered as `[?KEY]` in the output so it is easy to search for and fix. One marker may hold several keys (`[cite:A, cite:B]`); each is checked on its own.

**Check 2: existence and metadata** (reported as `layer1`). Papers with a DOI are checked against Crossref.

- On a 404 the DOI is looked up on doi.org, which also covers DataCite (arXiv) and other registrars. The paper is removed only if doi.org does not know the DOI either.
- A title mismatch is a warning. A matching title is then checked for the same paper: authors in common, first author, year (one year apart is allowed for online-first), and start page. A DOI that is not shaped like a DOI, a future year, and a retraction or withdrawal notice on the record are warnings too.
- A paper with neither a DOI nor an arXiv id is looked up by title in a second database; if it is found nowhere, it is a warning.
- Network errors and missing DOIs pass: being unable to verify is not the same as being invalid.
- The same paper cited under two keys, or a preprint cited beside its published version, is warned on the second key or the preprint.

**Check 3: claim support** (reported as `layer3`). For each cited paper, a fast model checks whether the source backs what the sentence attributes to it.

- With full text, the evidence is the paper's opening plus the passages that best match the claims; otherwise it is the excerpt or abstract.
- Only the part of the sentence tied to that marker is judged. The writer's own evaluation, limitations and contrasts are not claims of the source. Table rows are judged cell by cell, minus columns of the writer's commentary.
- A detail missing from the text shown is "unclear", not "unsupported". An unsupported claim is a warning that quotes the sentence; this check never removes a citation.
- When page data is available, a warning names the PDF page of the best-matching passage, for example `(PDF p. 7)`. These are PDF pages, not printed ones.
- A cited paper whose abstract and full text are too short to check is marked `unverified` instead of passed, and the verification panel counts it separately. The writer sees such references marked "Title only" and may cite them only as examples of a kind of work.
- Optional finer grades (`L3_FINE_GRADES`) also report partial support as a note and misaligned support as a warning. An optional uncited-claims check (`VERIFY_UNCITED_CLAIMS`) lists factual statements that cite nothing.

**Revision.** Paragraphs holding a flagged sentence are sent to the writer once. It may only fix the flagged sentences, cite the section's candidate papers, or hedge a claim, and a reply is kept only if it adds no other keys and leaves most unflagged sentences verbatim. In `full_auto`, fixes for unsupported claims are applied and re-verified; in `key_gates`, every revision is a proposal with before and after and an accept button. Fixes for uncited statements are always proposals.

**Output.** Each issue is tagged with the stage it most likely came from (writing or retrieval). The exported reference list contains only cited, resolvable papers, in order of first appearance.

## Quick start

### Prerequisites

- Python 3.12+
- Node.js 20+ and pnpm
- PostgreSQL: Docker starts one for you, or see [Running without Docker](#running-without-docker). Redis is optional.
- An OpenAI API key, which claim checking and the review need. A Zhipu GLM key is optional (see [Configuration](#configuration)).

### 1. Clone and install

```bash
git clone https://github.com/mmlong818/open-academic-paper-gen.git
cd open-academic-paper-gen

# Backend
cd backend
pip install -e .
cd ..

# Frontend
cd frontend
pnpm install
cd ..
```

### 2. Configure the environment

Copy `.env.example` to `.env` in the project root and fill it in. Never commit this file.

```env
# Must match docker-compose.yml (POSTGRES_* and REDIS_PASSWORD, with the defaults below)
DATABASE_URL=postgresql+asyncpg://papergen:papergen_dev@localhost:5558/papergen
REDIS_URL=redis://:redis_dev@localhost:6400/0

# OpenAI is needed for claim checking and the review; Zhipu is optional
OPENAI_API_KEY=your_key_here
ZHIPU_API_KEY=your_key_here

# Model defaults shown
OPENAI_MODEL_FAST=gpt-6-luna
OPENAI_MODEL_STRONG=gpt-6.1-sol
ZHIPU_MODEL_FAST=glm-5.3-flash
ZHIPU_MODEL_STRONG=glm-5.1

# Optional: improves the open-access PDF fetch rate
SEMANTIC_SCHOLAR_API_KEY=

# Recommended: OpenAlex bills calls against a daily budget; a free key
# (openalex.org/settings/api) raises it. Without one, a long day of runs ends in 429s.
OPENALEX_API_KEY=

# Optional: contact email sent to Crossref / OpenAlex as the polite-pool
# identifier. Leave empty to send none.
CONTACT_EMAIL=
```

### 3. Start the infrastructure

```bash
docker compose up -d postgres redis
```

This starts PostgreSQL (port 5558) and Redis (port 6400) in containers. To run without Docker, see [Running without Docker](#running-without-docker).

### 4. Run the app

**Windows (PowerShell):**

```powershell
.\start.ps1   # start backend and frontend in the background
.\stop.ps1    # stop them
```

`stop.ps1` ends only what serves ports 8080 and 3000, together with the uvicorn / pnpm / next processes that launched it; other Python and Node processes are left alone.

**macOS / Linux:**

```bash
# Backend (from the project root)
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8080

# Frontend (in a separate terminal)
cd frontend && pnpm dev
```

Open <http://localhost:3000>.

### Running without Docker

Docker only provides the two databases; the app itself always runs on your machine. PostgreSQL is required, Redis is not.

**PostgreSQL** (tested with 16). Install it from [postgresql.org](https://www.postgresql.org/download/), with `brew install postgresql@16` on macOS, or with your Linux package manager. Then, as a PostgreSQL superuser (`postgres` on Windows installs, `sudo -u postgres psql` on Linux, your own user with Homebrew), create a user and a database:

```bash
psql -U postgres -c "CREATE USER papergen WITH PASSWORD 'papergen_dev';"
psql -U postgres -c "CREATE DATABASE papergen OWNER papergen;"
```

Point `DATABASE_URL` at it. A local install listens on 5432, not 5558:

```env
DATABASE_URL=postgresql+asyncpg://papergen:papergen_dev@localhost:5432/papergen
```

The backend creates its tables on first start. A hosted PostgreSQL works the same way: use its connection string with the `postgresql+asyncpg://` scheme.

**Redis** can be skipped. Leave `REDIS_URL` as it is: when Redis cannot be reached, the backend logs one warning and pushes progress from memory, which is all a single machine needs.

## Configuration

Everything is set in `.env` (names are the upper-case form of the field names in `backend/core/config.py`). Defaults shown.

| Setting | Default | Effect |
|---------|---------|--------|
| `VERIFY_CITATION_SUPPORT` | `true` | Claim-support check (check 3), one fast-model call per cited paper |
| `VERIFY_UNCITED_CLAIMS` | `false` | Uncited-claim check, one fast-model call per section |
| `REVISE_FLAGGED_CLAIMS` | `true` | Constrained revision of flagged sentences |
| `EXPAND_CITATION_CHAIN` | `true` | Citation-chain expansion after screening |
| `RERANK_SECTION_PAPERS` | `true` | A fast model picks each section's papers |
| `REVIEW_DRAFT` | `true` | Simulated review of the final draft |
| `REVIEW_PANEL` | `true` | Three independent reviewers instead of one (about three times the cost) |
| `CITATION_GRAPH_OUTLINE` | `false` | Review papers: outline the body around citation-graph groups of the pool |
| `L3_FINE_GRADES` | `false` | Check 3 also grades partial and misaligned support |
| `EVIDENCE_TABLE_IN_WRITING` | `false` | Give the writer each paper's evidence-table row |
| `PAPER_CACHE` | `true` | Reuse fetched abstracts, full text and metadata across tasks |
| `SCREENING_THINKING` | `false` | Let the screening model reason before answering (slower) |
| `SCREENING_CONCURRENCY` | `8` | Screening calls in flight at once |

Task-level options are chosen on the new-task page: writing language, literature mix (`zh_major` about 70% Chinese, `balanced` about 50%, `en_major` about 20%), and collaboration mode (`key_gates` pauses at every major phase and is the default; `full_auto` runs end to end). The reference style is chosen when exporting, on the task page; it defaults to GB/T 7714 for Chinese papers and APA 7 for English ones.

**Models and tiers.** There are two tiers, fast and strong, set per provider with `OPENAI_MODEL_FAST/STRONG` and `ZHIPU_MODEL_FAST/STRONG`. Each step is assigned a tier with `MODEL_TIER_SCOPING`, `MODEL_TIER_SYNTHESIS`, `MODEL_TIER_OUTLINE` (all `fast` by default) and `MODEL_TIER_WRITING` (`strong`).

- Fast tier: Zhipu first, falling back to the OpenAI fast model.
- Strong tier: OpenAI first, falling back to Zhipu.
- Claim checking, the uncited-claim check and the simulated review need an OpenAI key; the Zhipu fallback covers the other stages only. The review uses the OpenAI strong model with no fallback.
- If a phase's model call fails, the task is marked failed with a retry button; no placeholder text reaches an approval gate.
- `LLM_PROVIDER` (`openai` by default, or `zhipu`) only chooses which key the startup check and the health endpoint probe.

The model IDs above are defaults; set the `*_MODEL_*` variables to use any other model your account can access.

## Evaluation

`evals/` replays fixed topics offline, so a change can be measured against the same literature pool before and after. Replays report the hallucinated-key rate, claim-support verdicts by evidence type, uncited statements before and after revision, revisions applied and resolved, review comments, and LLM calls per model.

```bash
python -m evals.capture                       # freeze the topics in evals/topics.json up to writing (hours; API costs)
python -m evals.replay --label mychange --compare evals/results/<earlier>.json
python -m evals.replay --set rerank_section_papers=false   # override a setting for one run
```

Fixtures, results and labels embed paper text, so they are not distributed with the repository (they are gitignored); run `evals.capture` to build your own. The labelling helpers (`evals.sample_l3`, `evals.sample_uncited`, `evals.sample_review`) support hand-checking verdicts.

## Limitations

- Verification depends on the model consistently using the `[cite:KEY]` marker format. Prose citations such as `(Author, year)` are not verified.
- Check 2 compares titles character by character, so a cross-language record (an English Crossref title against a stored Chinese one) can legitimately trigger a warning.
- Chinese journals rarely offer open-access PDFs or citation data, so full-text evidence and citation chaining help Chinese-language topics much less than English ones.
- Open sources hold relatively few on-topic Chinese papers, and many lack an abstract, so Chinese citations in a draft can be sparse and repetitive.
- "Unsupported" verdicts from check 3 are a screening aid, not a ruling: false alarms are common and results vary from run to run. Treat every warning as something to check against the source.
- Claim checking, the uncited-claim check and the review require an OpenAI key.
- The evidence table is extracted by a model from the abstract and, with full text, the results, discussion, limitations and conclusion sections. For review papers in particular, a finding or a limitation can end up in the wrong column.
- The review's reasoning occasionally uses its whole budget; a lower-effort retry covers this at slightly lower quality.
- Semantic Scholar rate-limits aggressively without an API key.
- OpenAlex requires an API key for a usable daily budget. Without `OPENALEX_API_KEY`, search, the DOI abstract lookup and the cross-source check return fewer results once the budget runs out.
- Chinese-database searchers (CNKI, Wanfang, VIP) are stubs: they need institutional access and are not provided.
- LaTeX output is checked for common problems but never compiled.

## Disclaimer and responsible use

- Generated text is a **draft**. It can contain errors, unsupported claims and misread sources, even after verification. Read the cited sources and check every claim before relying on it.
- You are responsible for the academic integrity of anything you produce with this tool: disclose AI assistance where your institution, publisher or venue requires it, and do not submit generated text as unreviewed original work.
- This project is not affiliated with, endorsed by, or sponsored by OpenAlex, Crossref, Semantic Scholar, arXiv, OpenAI or Zhipu AI. These services are supported as integrations only. Your use of them is governed by their own terms and rate limits, and you are responsible for complying with them, including the licenses of any papers you retrieve.
- Do not commit API keys or `.env` files.

## License

Released under the [GNU AGPL-3.0](./LICENSE). If you run a modified version as a network service, you must offer its source to its users. Licenses of third-party dependencies are listed in the [NOTICE](./NOTICE) file.
