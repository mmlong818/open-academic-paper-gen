from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://papergen:papergen_dev@localhost:5432/papergen"
    redis_url: str = "redis://:redis_dev@localhost:6379/0"
    secret_key: str = "dev_secret"

    # LLM provider: "openai" | "zhipu" | "auto"
    llm_provider: str = "openai"

    # OpenAI
    openai_api_key: str = ""
    # 2026-10-02 against the 5.6 models on the labelled sets: gpt-6-luna judged layer 3 right 85.0 of 99
    # (80.3) and misplaced 3 evidence cells (8); gpt-6.1-sol is the 6.x strong model, half the price.
    openai_model_fast: str = "gpt-6-luna"
    openai_model_strong: str = "gpt-6.1-sol"

    # 智谱 AI（OpenAI 兼容接口）
    zhipu_api_key: str = ""
    # glm-5.3-flash 筛选与 glm-5.1（关闭思考）持平：两者分歧的 37 篇判对 18 对 19，480 篇 106 秒对 301 秒。
    # strong 只在 OpenAI 写作失败时兜底，未评测，保持 glm-5.1。
    zhipu_model_fast: str = "glm-5.3-flash"
    zhipu_model_strong: str = "glm-5.1"
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"

    # Literature API keys. Read here, not with os.getenv: .env reaches Settings only.
    openalex_api_key: str = ""
    semantic_scholar_api_key: str = ""
    # Crossref / OpenAlex polite pool; nothing is sent when empty
    contact_email: str = ""

    # 各步骤算力分配：fast | strong
    model_tier_scoping: str = "fast"
    model_tier_synthesis: str = "fast"
    model_tier_outline: str = "fast"
    model_tier_writing: str = "strong"

    # Layer 3 citation-support check costs one LLM call per cited paper; set false to skip.
    verify_citation_support: bool = True
    # 5.2: reuse abstracts, full text and metadata fetched by earlier tasks (paper_cache table)
    paper_cache: bool = True
    # Layer 3 also grades partial and misaligned support. Off until blind labels show no precision loss.
    l3_fine_grades: bool = False
    # 4.1: give the section writer each paper's evidence-table row. Off until replay shows no rise
    # in unsupported claims: a row is a lossy retelling of the abstract.
    evidence_table_in_writing: bool = False
    # Uncited-claim check (one LLM call per section). Off until its false-alarm rate is measured.
    verify_uncited_claims: bool = False
    # T1.2: rewrite flagged sentences under constraints (full_auto applies, key_gates proposes).
    revise_flagged_claims: bool = True
    # Screening is 92% of the cleaning phase, and glm-5.1 spends 88% of its output reasoning.
    # Off: about 5 s a call instead of 15-18 (2 pools, 480 papers: 1040 s -> 301 s). Blind labels
    # on the 34 papers the modes split on: off right on 28, on right on 6; on threw out 25 relevant
    # papers (GPT-3, LLaMA, SelfCheckGPT), off 5. The 60 sampled agreements: 55 right in both.
    screening_thinking: bool = False
    # glm-5.1: no 429s at ten concurrent calls, 5 of 15 at fifteen. glm-5.3-flash: none at sixteen.
    screening_concurrency: int = 8
    # T2.2: pull references and citations of the strongest screened papers from Semantic Scholar.
    expand_citation_chain: bool = True
    # T2.1: a fast model picks each section's papers from a word-overlap shortlist. On the eval
    # pools it cut uncited statements ~30% (71-73 -> 49) for ~10 extra fast-model calls a paper.
    rerank_section_papers: bool = True
    # Stage 3: one strong-model review of the final draft, shown as suggestions; never edits text.
    review_draft: bool = True
    # 4.3: three blind reviewers with different focuses instead of one; about 3x the cost.
    # On the same four drafts: 50 valid comments against 37 at 0.94 vs 0.95 precision (107 blind labels).
    review_panel: bool = True
    # Review papers: outline the body around citation-graph groups of the pool.
    # Off: on the eval review topic it moved no measure (theme coverage, cohesion, citations).
    citation_graph_outline: bool = False


settings = Settings()


def polite_pool_params() -> dict:
    """The mailto for Crossref / OpenAlex, only when CONTACT_EMAIL is set."""
    return {"mailto": settings.contact_email} if settings.contact_email else {}
