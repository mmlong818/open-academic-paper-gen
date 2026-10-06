import asyncio
import logging
import uuid

from langgraph.graph import END, StateGraph

from backend.core.config import settings
from backend.core.llm import fast_llm
from backend.core.model_router import get_llm, get_provider_info
from backend.db.session import AsyncSessionLocal
from backend.literature.abstract_enricher import enrich_abstracts
from backend.literature.bibtex import assign_cite_keys, bibtex_key
from backend.literature.citation_chain import chain_and_screen
from backend.literature.citation_graph import build_taxonomy, taxonomy_block
from backend.literature.content_fetcher import PaperContentFetcher
from backend.literature.crew import LiteratureCrew
from backend.literature.screener import LiteratureScreener
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.pipeline.states import GateStatus, PaperState, Phase
from backend.services.pubsub import publish_progress
from backend.services.task_service import get_task
from backend.pipeline.verify_and_revise import verify_and_revise
from backend.verification.orchestrator import extract_cite_keys
from backend.writing.scoping import ScopingAgent
from backend.writing.synthesis import SynthesisAgent
from backend.writing.evidence_table import EVIDENCE_MAX_TOKENS, EvidenceExtractor
from backend.writing.angle import AngleAgent
from backend.writing.novelty import NOVELTY_MAX_TOKENS, NoveltyDiagnoser
from backend.writing.outline import OutlineAgent
from backend.writing.prisma import build_prisma_flow, review_process_facts
from backend.writing.ablation import AblationAgent
from backend.writing.review import ReviewAgent, reviewer_llm
from backend.writing.review_panel import ReviewPanel
from backend.writing.style_check import check_style
from backend.writing.section_writer import SectionWriter, section_selector_llm
from backend.export.latex_exporter import LatexExporter
from backend.export.markdown_exporter import MarkdownExporter
from backend.pipeline.type_configs import get_type_config
from backend.pipeline.quality_checker import check_quality

logger = logging.getLogger(__name__)


async def _save_snapshot_only(task_id: str, updates: dict) -> None:
    """仅合并 snapshot，不改变 current_phase（用于章节写作进度保存）。"""
    try:
        async with AsyncSessionLocal() as session:
            task = await get_task(session, uuid.UUID(task_id))
            if task:
                task.state_snapshot = {**(task.state_snapshot or {}), **updates}
                await session.commit()
    except Exception:
        pass


async def _save_phase_result(
    task_id: str,
    next_phase: Phase,
    updates: dict,
) -> None:
    """每个阶段完成后立即写入 DB：合并 snapshot + 推进 current_phase。"""
    try:
        async with AsyncSessionLocal() as session:
            task = await get_task(session, uuid.UUID(task_id))
            if task:
                task.state_snapshot = {**(task.state_snapshot or {}), **updates}
                task.current_phase = next_phase.value
                await session.commit()
    except Exception:
        pass


def _should_gate(state: PaperState) -> str:
    decision = (
        "wait_gate"
        if state.current_phase in state.gate_phases and state.gate_status == GateStatus.PENDING
        else "continue"
    )
    logger.info(
        "[gate] phase=%s gate_status=%s collab_mode=%s gate_phases=%s → %s",
        state.current_phase,
        state.gate_status,
        state.collab_mode,
        state.gate_phases,
        decision,
    )
    return decision


def _already_done(state: PaperState, phase: Phase) -> bool:
    """恢复模式下，resume_from_phase 之前的阶段视为已完成，直接跳过。"""
    return state.resume_from_phase is not None and phase < state.resume_from_phase


async def node_scoping(state: PaperState) -> dict:
    if _already_done(state, Phase.SCOPING):
        return {"current_phase": Phase.LITERATURE}

    if state.research_questions and state.resume_from_phase == Phase.SCOPING:
        await _save_phase_result(state.task_id, Phase.LITERATURE, {})
        await publish_progress(state.task_id, phase=Phase.LITERATURE, status="running", message="进入文献检索")
        return {"current_phase": Phase.LITERATURE, "gate_status": GateStatus.SKIPPED}

    if not state.research_questions:
        await publish_progress(state.task_id, phase=Phase.SCOPING, status="running", message="范围界定中")
        info = get_provider_info(state.topic, state.language)
        logger.info("[ModelRouter] scoping → provider=%s model=%s", info["provider"], info["models"]["scoping"])
        llm = get_llm("scoping", state.topic, state.language, max_tokens=1024)
        agent = ScopingAgent(llm=llm)
        result = await agent.run(topic=state.topic, language=state.language, source_mix=state.source_mix)
        payload = {
            "research_questions": result["research_questions"],
            "keywords": result["keywords"],
        }
        await _save_phase_result(state.task_id, Phase.SCOPING, payload)
        await publish_progress(state.task_id, phase=Phase.SCOPING, status="completed", message="主题定界完成")
    else:
        payload = {
            "research_questions": state.research_questions,
            "keywords": state.keywords,
        }

    if Phase.SCOPING in state.gate_phases:
        return {
            "current_phase": Phase.SCOPING,
            "gate_status": GateStatus.PENDING,
            **payload,
        }

    await _save_phase_result(state.task_id, Phase.LITERATURE, payload)
    return {
        "current_phase": Phase.LITERATURE,
        "gate_status": GateStatus.SKIPPED,
        **payload,
    }


async def node_literature(state: PaperState) -> dict:
    if _already_done(state, Phase.LITERATURE):
        return {"current_phase": Phase.CLEANING}

    # 已检索且已批准 → 直接继续
    if state.literature and state.resume_from_phase == Phase.LITERATURE:
        await _save_phase_result(state.task_id, Phase.CLEANING, {})
        await publish_progress(state.task_id, phase=Phase.CLEANING, status="running", message="进入文献数据清洗")
        return {"current_phase": Phase.CLEANING, "gate_status": GateStatus.SKIPPED}

    if not state.literature:
        await publish_progress(state.task_id, phase=Phase.LITERATURE, status="running", message="文献检索中")
        type_cfg = get_type_config(state.paper_type)
        query = SearchQuery(
            keywords=state.keywords if state.keywords else [state.topic],
            language=state.language,
            max_results=type_cfg.lit_count_max,
            cookie=state.chinese_cookie,
            source_mix=state.source_mix,
        )
        crew = LiteratureCrew()
        items = await crew.run(query)
        literature_payload = {"literature": [item.model_dump(exclude={"raw"}) for item in items]}
        await _save_phase_result(state.task_id, Phase.LITERATURE, literature_payload)
        await publish_progress(state.task_id, phase=Phase.LITERATURE, status="completed", message=f"文献检索完成，共 {len(items)} 篇")
    else:
        literature_payload = {"literature": state.literature}

    if Phase.LITERATURE in state.gate_phases:
        return {"current_phase": Phase.LITERATURE, "gate_status": GateStatus.PENDING, **literature_payload}

    await _save_phase_result(state.task_id, Phase.CLEANING, literature_payload)
    return {"current_phase": Phase.CLEANING, "gate_status": GateStatus.SKIPPED, **literature_payload}


async def node_cleaning(state: PaperState) -> dict:
    """文献数据清洗：去重 + 相关性过滤，门控让用户审阅后再进入综合阶段。"""
    if _already_done(state, Phase.CLEANING):
        return {"current_phase": Phase.TRENDS}

    # 已清洗且已批准 → 直接继续（立即推进 DB phase，避免前端误判）
    if state.cleaning_report and state.resume_from_phase == Phase.CLEANING:
        await _save_phase_result(state.task_id, Phase.TRENDS, {})
        await publish_progress(state.task_id, phase=Phase.TRENDS, status="running", message="进入研究趋势/空白分析")
        return {"current_phase": Phase.TRENDS, "gate_status": GateStatus.SKIPPED}

    if not state.cleaning_report:
        await publish_progress(state.task_id, phase=Phase.CLEANING, status="running", message="文献数据清洗中")

        raw = state.literature
        seen_dois: set[str] = set()
        seen_titles: set[str] = set()
        deduped: list[dict] = []
        removed_dup = 0

        for item in raw:
            doi = (item.get("doi") or "").strip().lower()
            title_key = (item.get("title") or "").strip().lower()

            if doi and doi in seen_dois:
                removed_dup += 1
                continue
            if title_key and title_key in seen_titles:
                removed_dup += 1
                continue

            if doi:
                seen_dois.add(doi)
            if title_key:
                seen_titles.add(title_key)
            deduped.append(item)

        await publish_progress(
            state.task_id, phase=Phase.CLEANING, status="running",
            message=f"规则去重完成，保留 {len(deduped)} 篇，正在抓取论文正文…"
        )

        # Convert dicts → LiteratureItem objects
        deduped_items: list[LiteratureItem] = []
        for d in deduped:
            try:
                deduped_items.append(LiteratureItem(**d))
            except Exception as exc:
                logger.warning("Skipping malformed item before screening: %s", exc)

        # Thin abstracts first: screening and the excerpt fallback both read them
        deduped_items, abstracts_filled = await enrich_abstracts(deduped_items)

        # Fetch full-text excerpts (Semantic Scholar + PDF)
        fetcher = PaperContentFetcher()
        deduped_items = await fetcher.run(deduped_items)
        await publish_progress(
            state.task_id, phase=Phase.CLEANING, status="running",
            message=f"正文抓取完成，开始 LLM 逐篇筛选…"
        )

        llm_screen = get_llm("synthesis", state.topic, state.language, max_tokens=256,
                             thinking=settings.screening_thinking)
        screener = LiteratureScreener(llm=llm_screen, concurrency=settings.screening_concurrency)
        retained_items, screening_report_rows = await screener.run(
            topic=state.topic, items=deduped_items, language=state.language
        )
        excluded_by_llm = len(deduped_items) - len(retained_items)
        if not retained_items:
            logger.warning(
                "[cleaning] screener excluded ALL %d papers — falling back to rule-based list",
                len(deduped_items),
            )
            retained_items = deduped_items
            excluded_by_llm = 0

        chained: list[LiteratureItem] = []
        chained_candidates = 0
        if settings.expand_citation_chain and retained_items:
            await publish_progress(state.task_id, phase=Phase.CLEANING, status="running", message="沿引用链追溯经典文献…")
            chained, chain_rows, chained_candidates = await chain_and_screen(
                retained_items, deduped_items, [state.topic, *state.keywords], fetcher, screener,
                state.topic, state.language,
            )
            retained_items += chained
            screening_report_rows += chain_rows
            excluded_by_llm += chained_candidates - len(chained)
        # the pool is final here: give every paper its own citation key
        retained_items = assign_cite_keys(retained_items)
        cleaned = [item.model_dump(exclude={"raw"}) for item in retained_items]

        cleaning_report = {
            "total_before": len(raw),
            "total_after": len(cleaned),
            "removed_dup": removed_dup,
            "excluded_by_llm": excluded_by_llm,
            "chained_candidates": chained_candidates,
            "chained_included": len(chained),
            "abstracts_filled": abstracts_filled,
            "screening_rows": screening_report_rows,
        }

        payload: dict = {"literature": cleaned, "cleaning_report": cleaning_report}
        await _save_phase_result(state.task_id, Phase.CLEANING, payload)
        msg = (
            f"数据清洗完成：去重 {removed_dup} 篇，"
            f"LLM 筛除 {excluded_by_llm} 篇，引用链新增 {len(chained)} 篇，最终保留 {len(cleaned)} 篇"
        )
        await publish_progress(state.task_id, phase=Phase.CLEANING, status="completed", message=msg)
    else:
        cleaning_report = state.cleaning_report
        cleaned = state.literature

    if Phase.CLEANING in state.gate_phases:
        return {
            "current_phase": Phase.CLEANING,
            "gate_status": GateStatus.PENDING,
            "literature": cleaned,
            "cleaning_report": cleaning_report,
        }

    await _save_phase_result(state.task_id, Phase.TRENDS, {"literature": cleaned, "cleaning_report": cleaning_report})
    return {
        "current_phase": Phase.TRENDS,
        "gate_status": GateStatus.SKIPPED,
        "literature": cleaned,
        "cleaning_report": cleaning_report,
    }


async def node_prisma(state: PaperState) -> dict:
    """PRISMA 流程报告 — systematic 类型或英文论文生成；只报告清洗阶段的筛选结果，不删文献。"""
    needs_prisma = state.paper_type == "systematic" or state.language == "en"
    if not needs_prisma or state.prisma_flow:
        return {}
    prisma_flow = build_prisma_flow(state.cleaning_report, len(state.literature), state.language)
    await publish_progress(
        state.task_id, phase=Phase.CLEANING, status="running",
        message=f"PRISMA 流程报告已生成，纳入 {len(state.literature)} 篇",
    )
    return {"prisma_flow": prisma_flow}


async def node_trends(state: PaperState) -> dict:
    """研究趋势/空白发现（原文献综合节点）。"""
    if _already_done(state, Phase.TRENDS):
        return {"current_phase": Phase.ANGLE}

    # 已分析且处于 TRENDS 恢复模式 → 直接继续（用 resume_from_phase 而非 gate_status，后者可能被上游节点覆写）
    if state.synthesis and state.resume_from_phase == Phase.TRENDS:
        await _save_phase_result(state.task_id, Phase.ANGLE, {})
        await publish_progress(state.task_id, phase=Phase.ANGLE, status="running", message="进入写作角度")
        return {"current_phase": Phase.ANGLE, "gate_status": GateStatus.SKIPPED}

    if not state.synthesis:
        await publish_progress(state.task_id, phase=Phase.TRENDS, status="running", message="分析研究趋势与空白中")
        items: list[LiteratureItem] = []
        for lit in state.literature:
            try:
                items.append(LiteratureItem(**lit))
            except Exception as exc:
                logger.warning("Skipping malformed literature item: %s", exc)
                continue

        info = get_provider_info(state.topic, state.language)
        logger.info("[ModelRouter] trends → provider=%s model=%s", info["provider"], info["models"]["synthesis"])
        llm = get_llm("synthesis", state.topic, state.language, max_tokens=2048)
        agent = SynthesisAgent(llm=llm)
        extractor = EvidenceExtractor(llm=fast_llm(max_tokens=EVIDENCE_MAX_TOKENS))
        synthesis, evidence_table = await asyncio.gather(
            agent.run(topic=state.topic, literature=items, language=state.language),
            extractor.run(items, state.language),
        )
        await _save_phase_result(state.task_id, Phase.TRENDS,
                                 {"synthesis": synthesis, "evidence_table": evidence_table})
        await publish_progress(state.task_id, phase=Phase.TRENDS, status="completed",
                               message=f"研究趋势/空白发现完成，证据表 {len(evidence_table)} 篇")
    else:
        synthesis, evidence_table = state.synthesis, state.evidence_table

    result = {"synthesis": synthesis, "evidence_table": evidence_table}
    if Phase.TRENDS in state.gate_phases:
        return {"current_phase": Phase.TRENDS, "gate_status": GateStatus.PENDING, **result}

    await _save_phase_result(state.task_id, Phase.ANGLE, result)
    return {"current_phase": Phase.ANGLE, "gate_status": GateStatus.SKIPPED, **result}


async def node_angle(state: PaperState) -> dict:
    if _already_done(state, Phase.ANGLE):
        return {"current_phase": Phase.OUTLINE}
    type_cfg = get_type_config(state.paper_type)
    if Phase.ANGLE.value in type_cfg.skip_phases:
        logger.info("[graph] node_angle skipped for paper_type=%s", state.paper_type)
        await publish_progress(state.task_id, phase=Phase.ANGLE, status="completed", message="写作角度（自动跳过）")
        return {"current_phase": Phase.OUTLINE, "gate_status": GateStatus.SKIPPED}

    if state.angle and state.resume_from_phase == Phase.ANGLE:
        await _save_phase_result(state.task_id, Phase.OUTLINE, {})
        await publish_progress(state.task_id, phase=Phase.OUTLINE, status="running", message="进入大纲生成")
        return {"current_phase": Phase.OUTLINE, "gate_status": GateStatus.SKIPPED}

    if not state.angle:
        await publish_progress(state.task_id, phase=Phase.ANGLE, status="running", message="发掘写作角度与创新贡献中")
        info = get_provider_info(state.topic, state.language)
        logger.info("[ModelRouter] angle → provider=%s model=%s", info["provider"], info["models"]["angle"])
        llm = get_llm("angle", state.topic, state.language, max_tokens=2048)
        agent = AngleAgent(llm=llm)
        angle = await agent.run(
            topic=state.topic,
            synthesis=state.synthesis,
            research_questions=state.research_questions,
            language=state.language,
        )
        novelty = await _diagnose_novelty(state, angle)
        await _save_phase_result(state.task_id, Phase.ANGLE, {"angle": angle, "novelty": novelty})
        await publish_progress(state.task_id, phase=Phase.ANGLE, status="completed", message="写作角度完成")
    else:
        angle, novelty = state.angle, state.novelty

    if Phase.ANGLE in state.gate_phases:
        return {"current_phase": Phase.ANGLE, "gate_status": GateStatus.PENDING, "angle": angle, "novelty": novelty}

    await _save_phase_result(state.task_id, Phase.OUTLINE, {"angle": angle, "novelty": novelty})
    return {
        "current_phase": Phase.OUTLINE,
        "gate_status": GateStatus.SKIPPED,
        "angle": angle,
        "novelty": novelty,
    }


async def _diagnose_novelty(state: PaperState, angle: dict) -> dict | None:
    """Layered novelty and the closest pool papers, for the reader at the angle gate; never edits the angle."""
    await publish_progress(state.task_id, phase=Phase.ANGLE, status="running", message="诊断写作角度的新颖性")
    items: list[LiteratureItem] = []
    for lit in state.literature:
        try:
            items.append(LiteratureItem(**lit))
        except Exception as exc:
            logger.warning("Skipping malformed literature item: %s", exc)
    llm = get_llm("angle", state.topic, state.language, max_tokens=NOVELTY_MAX_TOKENS)
    return await NoveltyDiagnoser(llm=llm).run(state.topic, angle, items, state.language)


async def node_outline(state: PaperState) -> dict:
    if _already_done(state, Phase.OUTLINE):
        return {"current_phase": Phase.WRITING}

    if state.outline and state.resume_from_phase == Phase.OUTLINE:
        await _save_phase_result(state.task_id, Phase.WRITING, {})
        await publish_progress(state.task_id, phase=Phase.WRITING, status="running", message="进入章节写作")
        return {"current_phase": Phase.WRITING, "gate_status": GateStatus.SKIPPED}

    if not state.outline:
        await publish_progress(state.task_id, phase=Phase.OUTLINE, status="running", message="生成提纲中")
        info = get_provider_info(state.topic, state.language)
        logger.info("[ModelRouter] outline → provider=%s model=%s", info["provider"], info["models"]["outline"])
        taxonomy = await _review_taxonomy(state)
        llm = get_llm("outline", state.topic, state.language, max_tokens=2048)
        agent = OutlineAgent(llm=llm)
        outline = await agent.run(
            topic=state.topic,
            synthesis=state.synthesis,
            research_questions=state.research_questions,
            language=state.language,
            angle=state.angle if state.angle else None,
            taxonomy_block=taxonomy_block(taxonomy, state.language) if taxonomy else "",
        )
        _attach_cluster_keys(outline, taxonomy)
        await _save_phase_result(state.task_id, Phase.OUTLINE, {"outline": outline, "taxonomy": taxonomy})
        await publish_progress(state.task_id, phase=Phase.OUTLINE, status="completed", message="大纲生成完成")
    else:
        outline = state.outline
        taxonomy = state.taxonomy

    if Phase.OUTLINE in state.gate_phases:
        return {"current_phase": Phase.OUTLINE, "gate_status": GateStatus.PENDING,
                "outline": outline, "taxonomy": taxonomy}

    await _save_phase_result(state.task_id, Phase.WRITING, {"outline": outline})
    return {
        "current_phase": Phase.WRITING,
        "gate_status": GateStatus.SKIPPED,
        "outline": outline,
        "taxonomy": taxonomy,
    }


async def _review_taxonomy(state: PaperState) -> list[dict] | None:
    """Citation-graph groups of the pool, for review papers only."""
    if state.paper_type != "review" or not settings.citation_graph_outline:
        return None
    items = []
    for lit in state.literature:
        try:
            items.append(LiteratureItem(**lit))
        except Exception as exc:
            logger.warning("Skipping malformed literature item: %s", exc)
    await publish_progress(state.task_id, phase=Phase.OUTLINE, status="running", message="按引用关系梳理文献主题群…")
    return await build_taxonomy(items) or None


def _attach_cluster_keys(outline: list[dict], taxonomy: list[dict] | None) -> None:
    """Resolve each section's group numbers to paper keys, so writing can draw on them first."""
    if not taxonomy:
        return
    keys_by_group = {group["id"]: group["keys"] for group in taxonomy}
    for section in outline:
        ids = [i for i in section.get("clusters") or [] if isinstance(i, int)]
        keys = [k for i in ids for k in keys_by_group.get(i, [])]
        if keys:
            section["cluster_keys"] = list(dict.fromkeys(keys))


async def node_ablation(state: PaperState) -> dict:
    """消融实验设计 — 仅 computational 类型执行，其余直接透传。"""
    if state.paper_type != "computational":
        return {}
    if state.ablation_design:
        return {}
    await publish_progress(state.task_id, phase=Phase.WRITING, status="running", message="生成消融实验设计中")

    llm = get_llm("writing", state.topic, state.language, max_tokens=2048)
    agent = AblationAgent(llm=llm)
    try:
        ablation_md = await agent.run(
            topic=state.topic,
            angle=state.angle,
            outline=state.outline,
            language=state.language,
        )
    except Exception as exc:
        logger.warning("Ablation agent failed: %s", exc)
        return {}

    await publish_progress(
        state.task_id, phase=Phase.WRITING, status="running",
        message="消融实验设计完成"
    )
    return {"ablation_design": ablation_md}


async def node_writing(state: PaperState) -> dict:
    if _already_done(state, Phase.WRITING):
        return {"current_phase": Phase.VERIFICATION}

    # 已写作且已批准 → 直接继续
    if state.sections and state.resume_from_phase == Phase.WRITING:
        await _save_phase_result(state.task_id, Phase.VERIFICATION, {})
        await publish_progress(state.task_id, phase=Phase.VERIFICATION, status="running", message="进入引文核验")
        return {"current_phase": Phase.VERIFICATION, "gate_status": GateStatus.SKIPPED}

    if state.sections and Phase.WRITING in state.gate_phases:
        # 已写作但尚未批准
        return {"current_phase": Phase.WRITING, "gate_status": GateStatus.PENDING, "sections": state.sections}

    await publish_progress(state.task_id, phase=Phase.WRITING, status="running", message="正文写作中")

    items: list[LiteratureItem] = []
    for lit in state.literature:
        try:
            items.append(LiteratureItem(**lit))
        except Exception as exc:
            logger.warning("Skipping malformed literature item: %s", exc)
            continue

    info = get_provider_info(state.topic, state.language)
    logger.info("[ModelRouter] writing → provider=%s model=%s", info["provider"], info["models"]["writing"])
    llm = get_llm("writing", state.topic, state.language, max_tokens=6144)
    writer = SectionWriter(llm=llm, selector_llm=section_selector_llm())

    async def _on_section_done(partial_sections: dict) -> None:
        await _save_snapshot_only(state.task_id, {"sections": partial_sections})
        done = len(partial_sections)
        total = len(state.outline)
        await publish_progress(
            state.task_id, phase=Phase.WRITING, status="running",
            message=f"正文写作中 ({done}/{total})"
        )

    sections = await writer.run(
        outline=state.outline,
        synthesis=state.synthesis,
        literature=items,
        language=state.language,
        angle=state.angle if state.angle else None,
        on_section_done=_on_section_done,
        review_facts=review_process_facts(state.cleaning_report, items, state.keywords, state.language),
        source_mix=state.source_mix,
        evidence={row["key"]: row for row in state.evidence_table or []}
        if settings.evidence_table_in_writing else None,
    )

    failed_sections = [t for t, c in sections.items() if c.startswith("__SECTION_FAILED__")]
    await publish_progress(state.task_id, phase=Phase.WRITING, status="completed", message="正文写作完成")

    writing_payload: dict = {"sections": sections, "failed_sections": failed_sections}

    if Phase.WRITING in state.gate_phases:
        await _save_phase_result(state.task_id, Phase.WRITING, writing_payload)
        return {"current_phase": Phase.WRITING, "gate_status": GateStatus.PENDING, **writing_payload}

    await _save_phase_result(state.task_id, Phase.VERIFICATION, writing_payload)
    return {"current_phase": Phase.VERIFICATION, "gate_status": GateStatus.SKIPPED, **writing_payload}


async def node_verification(state: PaperState) -> dict:
    if _already_done(state, Phase.VERIFICATION):
        return {"current_phase": Phase.EXPORT}

    # 已核验且已批准 → 直接继续
    if state.quality_results and state.resume_from_phase == Phase.VERIFICATION:
        await _save_phase_result(state.task_id, Phase.EXPORT, {})
        await publish_progress(state.task_id, phase=Phase.EXPORT, status="running", message="进入导出")
        return {"current_phase": Phase.EXPORT, "gate_status": GateStatus.SKIPPED}

    if not state.quality_results:
        items: list[LiteratureItem] = []
        for lit in state.literature:
            try:
                items.append(LiteratureItem(**lit))
            except Exception as exc:
                logger.warning("Skipping malformed literature item: %s", exc)
                continue

        # Step 1: extract cited keys and show which papers were actually cited
        cited_keys = extract_cite_keys("\n\n".join(state.sections.values()))
        pool_keys = {bibtex_key(it) for it in items}
        cited_count = len(cited_keys & pool_keys)
        await publish_progress(
            state.task_id, phase=Phase.VERIFICATION, status="running",
            message=f"已提取引用标记 {len(cited_keys)} 个，匹配文献库 {cited_count} 篇，开始核验...",
        )

        # Step 2: verify; revise flagged sentences (applied and re-verified only in full_auto)
        outcome = await verify_and_revise(
            items, state.sections, state.outline, state.language, state.topic,
            auto_apply=Phase.VERIFICATION not in state.gate_phases,
        )
        final = outcome.final
        review = None
        if settings.review_draft:
            await publish_progress(state.task_id, phase=Phase.VERIFICATION, status="running", message="模拟审稿中…")
            review = await _simulated_review(outcome.sections, state.outline, state.topic, state.language)

        quality_results = check_quality({
            "paper_type": state.paper_type,
            "literature": state.literature,
            "sections": outcome.sections,
            "outline": state.outline,
            "angle": state.angle,
            "prisma_flow": state.prisma_flow,
            "ablation_design": state.ablation_design,
            "verified_citations": [item.model_dump(exclude={"raw"}) for item in final.verified],
        })
        ver_payload = {
            "sections": outcome.sections,
            "verified_citations": [item.model_dump(exclude={"raw"}) for item in final.verified],
            "citation_issues": [issue.model_dump() for issue in final.issues],
            "uncited_claims": [claim.as_dict() for claim in final.uncited],
            "revisions": [revision.as_dict() for revision in outcome.revisions],
            "review": review,
            # machine-flavoured prose on the final text: suggestions only, nothing rewritten
            "style_findings": [f.as_dict() for f in check_style(outcome.sections)],
            "smart_pause": final.summary.smart_pause_triggered,
            "quality_results": quality_results,
        }
        await _save_phase_result(state.task_id, Phase.VERIFICATION, ver_payload)
        await publish_progress(state.task_id, phase=Phase.VERIFICATION, status="completed", message="引文核验完成")
    else:
        ver_payload = {
            "verified_citations": state.verified_citations,
            "citation_issues": state.citation_issues,
            "uncited_claims": state.uncited_claims,
            "revisions": state.revisions,
            "review": state.review,
            "style_findings": state.style_findings,
            "quality_results": state.quality_results,
        }

    if Phase.VERIFICATION in state.gate_phases:
        return {"current_phase": Phase.VERIFICATION, "gate_status": GateStatus.PENDING, **ver_payload}

    return {"current_phase": Phase.EXPORT, "gate_status": GateStatus.SKIPPED, **ver_payload}


async def _simulated_review(sections: dict[str, str], outline: list[dict], topic: str, language: str) -> dict:
    llm, retry = reviewer_llm(), reviewer_llm("low")
    reviewer = ReviewPanel(llm, retry_llm=retry) if settings.review_panel else ReviewAgent(llm=llm, retry_llm=retry)
    return await reviewer.review(sections, outline, topic, language)


async def node_export(state: PaperState) -> dict:
    if _already_done(state, Phase.EXPORT):
        return {"gate_status": GateStatus.SKIPPED}

    if state.markdown_content and state.resume_from_phase == Phase.EXPORT:
        return {"current_phase": Phase.EXPORT, "gate_status": GateStatus.APPROVED}

    if state.failed_sections:
        raise RuntimeError(
            f"以下章节写作失败，请重试后再导出：{', '.join(state.failed_sections)}"
        )

    await publish_progress(state.task_id, phase=Phase.EXPORT, status="running", message="生成导出文件中")

    export_state = {
        "topic": state.topic,
        "language": state.language,
        "synthesis": state.synthesis,
        "outline": state.outline,
        "sections": state.sections,
        "literature": state.literature,
        "verified_citations": state.verified_citations,
        "paper_type": state.paper_type,
        "prisma_flow": state.prisma_flow,
        "ablation_design": state.ablation_design,
        "angle": state.angle,
    }

    latex_content = LatexExporter().export(export_state)
    markdown_content = MarkdownExporter().export(export_state)
    await publish_progress(state.task_id, phase=Phase.EXPORT, status="completed", message="导出文件生成完成")

    if Phase.EXPORT in state.gate_phases:
        return {
            "current_phase": Phase.EXPORT,
            "gate_status": GateStatus.PENDING,
            "latex_content": latex_content,
            "markdown_content": markdown_content,
        }

    return {
        "current_phase": Phase.EXPORT,
        "gate_status": GateStatus.APPROVED,
        "latex_content": latex_content,
        "markdown_content": markdown_content,
    }


async def node_wait_gate(state: PaperState) -> dict:
    return {}


def build_graph() -> StateGraph:
    g = StateGraph(PaperState)

    g.add_node("scoping", node_scoping)
    g.add_node("literature", node_literature)
    g.add_node("cleaning", node_cleaning)
    g.add_node("prisma", node_prisma)
    g.add_node("trends", node_trends)
    g.add_node("angle", node_angle)
    g.add_node("outline", node_outline)
    g.add_node("ablation", node_ablation)
    g.add_node("writing", node_writing)
    g.add_node("verification", node_verification)
    g.add_node("export", node_export)
    g.add_node("wait_gate", node_wait_gate)

    g.set_entry_point("scoping")

    phase_sequence = [
        ("scoping", "literature"),
        ("literature", "cleaning"),
        ("cleaning", "prisma"),
        ("prisma", "trends"),
        ("trends", "angle"),
        ("angle", "outline"),
        ("outline", "ablation"),
        ("ablation", "writing"),
        ("writing", "verification"),
        ("verification", "export"),
    ]

    for src, dst in phase_sequence:
        g.add_conditional_edges(
            src,
            _should_gate,
            {"wait_gate": "wait_gate", "continue": dst},
        )

    g.add_edge("wait_gate", END)
    g.add_edge("export", END)

    return g.compile()


paper_graph = build_graph()
