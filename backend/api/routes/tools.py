import asyncio
import json
import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.core.llm import fast_llm
from backend.literature.crew import LiteratureCrew
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.writing.angle import AngleAgent
from backend.writing.outline import OutlineAgent
from backend.writing.synthesis import SynthesisAgent

logger = logging.getLogger(__name__)
router = APIRouter()

# IP 速率限制：每IP每分钟最多10次
_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 10
_RATE_WINDOW = 60.0


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    calls = [t for t in _rate_store[ip] if now - t < _RATE_WINDOW]
    if calls:
        _rate_store[ip] = calls
    else:
        _rate_store.pop(ip, None)
    if len(calls) >= _RATE_LIMIT:
        return False
    _rate_store[ip] = calls + [now]
    return True


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_ip(request: Request) -> str:
    # X-Forwarded-For is trusted; deploy behind a reverse proxy that controls this header
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── 文献检索 ──────────────────────────────────────────────────

class LiteratureToolRequest(BaseModel):
    topic: str
    language: str = "zh"
    count: int = 20
    year_from: int | None = None


async def _stream_literature(body: LiteratureToolRequest):
    yield _sse({"type": "status", "message": "正在检索文献…"})
    query = SearchQuery(
        keywords=[body.topic],
        language=body.language,  # type: ignore[arg-type]
        max_results=body.count,
    )
    crew = LiteratureCrew()
    try:
        items = await asyncio.wait_for(crew.run(query), timeout=55.0)
    except asyncio.TimeoutError:
        yield _sse({"type": "error", "message": "检索超时，请稍后重试"})
        return
    except Exception as e:
        yield _sse({"type": "error", "message": f"检索失败: {e}"})
        return

    # year_from 过滤
    if body.year_from:
        items = [i for i in items if i.year and i.year >= body.year_from]
    items = items[: body.count]

    results = [
        {
            "title": item.title or "",
            "authors": item.authors or [],
            "year": item.year,
            "abstract": item.abstract or "",
            "source": item.source or "",
            "url": item.url,
            "doi": item.doi,
        }
        for item in items
    ]
    yield _sse({"type": "status", "message": f"找到 {len(results)} 篇文献"})
    yield _sse({"type": "result", "data": results})
    yield _sse({"type": "done"})


@router.post("/literature")
async def tool_literature(body: LiteratureToolRequest, request: Request):
    ip = _get_ip(request)
    if not _check_rate_limit(ip):
        async def _rl():
            yield _sse({"type": "error", "message": "请求过于频繁"})
        return StreamingResponse(_rl(), media_type="text/event-stream")
    return StreamingResponse(
        _stream_literature(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 提纲生成 ──────────────────────────────────────────────────

class OutlineToolRequest(BaseModel):
    topic: str
    language: str = "zh"
    paper_type: str = "general"


async def _stream_outline(body: OutlineToolRequest):
    yield _sse({"type": "status", "message": "正在生成提纲…"})
    type_hint = {
        "review": "（文献综述结构：引言→主题分区综述→研究议程→结论）",
        "empirical": "（实证研究结构：引言→文献与假设→数据与方法→结果→讨论→结论）",
        "experimental": "（实验研究结构：引言→实验1→实验2→总体讨论→结论）",
        "systematic": "（系统综述结构：引言→方法→PRISMA筛选→结果→讨论→结论）",
        "computational": "（计算/AI论文结构：引言→相关工作→方法→实验→分析→结论）",
    }.get(body.paper_type, "")
    enhanced_topic = f"{body.topic} {type_hint}".strip()
    llm = fast_llm(max_tokens=2048)
    agent = OutlineAgent(llm=llm)
    try:
        sections = await asyncio.wait_for(
            agent.run(
                topic=enhanced_topic,
                synthesis="",
                research_questions=[],
                language=body.language,
            ),
            timeout=55.0,
        )
    except asyncio.TimeoutError:
        yield _sse({"type": "error", "message": "生成超时，请稍后重试"})
        return
    except Exception as e:
        yield _sse({"type": "error", "message": f"生成失败: {e}"})
        return
    yield _sse({"type": "status", "message": "提纲生成完成"})
    yield _sse({"type": "result", "data": sections})
    yield _sse({"type": "done"})


@router.post("/outline")
async def tool_outline(body: OutlineToolRequest, request: Request):
    ip = _get_ip(request)
    if not _check_rate_limit(ip):
        async def _rl():
            yield _sse({"type": "error", "message": "请求过于频繁"})
        return StreamingResponse(_rl(), media_type="text/event-stream")
    return StreamingResponse(
        _stream_outline(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 研究角度分析 ──────────────────────────────────────────────

class AngleToolRequest(BaseModel):
    topic: str
    language: str = "zh"
    synthesis: str = ""
    research_questions: list[str] = []


async def _stream_angle(body: AngleToolRequest):
    yield _sse({"type": "status", "message": "正在分析研究角度…"})
    llm = fast_llm(max_tokens=2048)
    agent = AngleAgent(llm=llm)
    try:
        result = await asyncio.wait_for(
            agent.run(
                topic=body.topic,
                synthesis=body.synthesis,
                research_questions=body.research_questions,
                language=body.language,
            ),
            timeout=55.0,
        )
    except asyncio.TimeoutError:
        yield _sse({"type": "error", "message": "分析超时，请稍后重试"})
        return
    except Exception as e:
        yield _sse({"type": "error", "message": f"分析失败: {e}"})
        return
    yield _sse({"type": "status", "message": "角度分析完成"})
    yield _sse({"type": "result", "data": result})
    yield _sse({"type": "done"})


@router.post("/angle")
async def tool_angle(body: AngleToolRequest, request: Request):
    ip = _get_ip(request)
    if not _check_rate_limit(ip):
        async def _rl():
            yield _sse({"type": "error", "message": "请求过于频繁"})
        return StreamingResponse(_rl(), media_type="text/event-stream")
    return StreamingResponse(
        _stream_angle(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 摘要写作 ─────────────────────────────────────────────────

class AbstractToolRequest(BaseModel):
    topic: str
    language: str = "zh"
    paper_type: str = "general"
    key_argument: str
    method: str = ""
    findings: str = ""


async def _stream_abstract(body: AbstractToolRequest):
    yield _sse({"type": "status", "message": "正在生成摘要…"})

    if body.language == "zh":
        structured_prompt = (
            f"请为以下学术论文生成一篇结构化摘要（200-250字），按「背景—目的—方法—结果—结论」结构组织。\n\n"
            f"论文主题：{body.topic}\n"
            f"论文类型：{body.paper_type}\n"
            f"核心论点：{body.key_argument}\n"
            f"研究方法：{body.method or '未指定'}\n"
            f"主要发现：{body.findings or '未指定'}\n\n"
            f"直接输出摘要正文，不加标题或注释。"
        )
    else:
        structured_prompt = (
            f"Write a structured abstract (200-250 words) for the following academic paper, "
            f"organized as: Background — Purpose — Methods — Results — Conclusion.\n\n"
            f"Topic: {body.topic}\n"
            f"Paper type: {body.paper_type}\n"
            f"Key argument: {body.key_argument}\n"
            f"Methods: {body.method or 'Not specified'}\n"
            f"Main findings: {body.findings or 'Not specified'}\n\n"
            f"Output only the abstract text, no headings or annotations."
        )

    llm = fast_llm(max_tokens=600)
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(structured_prompt),
            timeout=55.0,
        )
        abstract_text = response.content.strip()
    except asyncio.TimeoutError:
        yield _sse({"type": "error", "message": "生成超时，请稍后重试"})
        return
    except Exception as e:
        yield _sse({"type": "error", "message": f"生成失败: {e}"})
        return

    yield _sse({"type": "status", "message": "摘要生成完成"})
    yield _sse({"type": "result", "data": {"abstract": abstract_text}})
    yield _sse({"type": "done"})


@router.post("/abstract")
async def tool_abstract(body: AbstractToolRequest, request: Request):
    ip = _get_ip(request)
    if not _check_rate_limit(ip):
        async def _rl():
            yield _sse({"type": "error", "message": "请求过于频繁"})
        return StreamingResponse(_rl(), media_type="text/event-stream")
    return StreamingResponse(
        _stream_abstract(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 文献综述段落 ──────────────────────────────────────────────

class SynthesisToolRequest(BaseModel):
    topic: str
    language: str = "zh"
    literature_json: str


async def _stream_synthesis(body: SynthesisToolRequest):
    yield _sse({"type": "status", "message": "正在生成文献综述段落…"})

    try:
        lit_raw: list[dict] = json.loads(body.literature_json)
    except Exception:
        yield _sse({"type": "error", "message": "文献 JSON 格式错误，请检查输入"})
        return

    items = [
        LiteratureItem(
            title=r.get("title", ""),
            authors=r.get("authors", []),
            year=r.get("year"),
            abstract=r.get("abstract", ""),
            source=r.get("source", "upload"),
            url=r.get("url", ""),
            doi=r.get("doi"),
        )
        for r in lit_raw[:50]
    ]

    llm = fast_llm(max_tokens=3000)
    agent = SynthesisAgent(llm=llm)
    try:
        result = await asyncio.wait_for(
            agent.run(topic=body.topic, literature=items, language=body.language),
            timeout=55.0,
        )
    except asyncio.TimeoutError:
        yield _sse({"type": "error", "message": "生成超时，请稍后重试"})
        return
    except Exception as e:
        yield _sse({"type": "error", "message": f"生成失败: {e}"})
        return

    yield _sse({"type": "status", "message": "综述段落生成完成"})
    yield _sse({"type": "result", "data": {"synthesis": result}})
    yield _sse({"type": "done"})


@router.post("/synthesis")
async def tool_synthesis(body: SynthesisToolRequest, request: Request):
    ip = _get_ip(request)
    if not _check_rate_limit(ip):
        async def _rl():
            yield _sse({"type": "error", "message": "请求过于频繁"})
        return StreamingResponse(_rl(), media_type="text/event-stream")
    return StreamingResponse(
        _stream_synthesis(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 选题引导对话 ──────────────────────────────────────────────

class GuideStartRequest(BaseModel):
    field: str
    language: str = "zh"


class GuideReplyRequest(BaseModel):
    field: str
    language: str = "zh"
    history: list[dict]
    user_answer: str


_GUIDE_QUESTIONS_ZH = [
    "你的研究是否涉及收集或分析数据？\nA. 是，我会收集/分析数据\nB. 否，主要整合已有文献",
    "数据来源是？\nA. 实验操控（我设计了实验条件）\nB. 调查问卷（我发放了问卷）\nC. 观测/档案数据（已有数据集）",
    "是否需要系统性地整合多项已有研究（含统计合并）？\nA. 是（系统综述或 Meta 分析）\nB. 否（叙述性整合）",
]

_GUIDE_QUESTIONS_EN = [
    "Does your research involve collecting or analyzing data?\nA. Yes, I will collect/analyze data\nB. No, mainly synthesizing existing literature",
    "What is your data source?\nA. Experimental manipulation (I designed conditions)\nB. Survey/questionnaire (I distributed surveys)\nC. Observational/archival data (existing datasets)",
    "Do you need to systematically integrate multiple existing studies (including statistical pooling)?\nA. Yes (systematic review or meta-analysis)\nB. No (narrative synthesis)",
]

_TYPE_LABELS_ZH = {
    "review": "文献综述（Narrative Review）",
    "empirical": "实证研究（Empirical Research）",
    "experimental": "实验研究（Experimental Research）",
    "systematic": "系统综述 / Meta 分析（Systematic Review / Meta-Analysis）",
    "computational": "计算 / AI 研究（Computational Research）",
}

_TYPE_LABELS_EN = {
    "review": "Literature Review (Narrative Review)",
    "empirical": "Empirical Research",
    "experimental": "Experimental Research",
    "systematic": "Systematic Review / Meta-Analysis",
    "computational": "Computational / AI Research",
}


def _infer_type_from_answers(answers: list[str], field: str) -> str:
    field_lower = field.lower()
    if any(kw in field_lower for kw in ["machine learning", "deep learning", "nlp", "ai", "计算", "人工智能", "机器学习", "深度学习"]):
        return "computational"
    if not answers:
        return "general"
    a0 = answers[0].upper().strip()
    if a0.startswith("B"):
        if len(answers) >= 2:
            a2 = answers[1].upper().strip()
            return "systematic" if a2.startswith("A") else "review"
        return "review"
    if len(answers) >= 2:
        a1 = answers[1].upper().strip()
        if a1.startswith("A"):
            return "experimental"
        if a1.startswith("B"):
            return "empirical"
        return "empirical"
    return "empirical"


async def _stream_guide_start(body: GuideStartRequest):
    questions = _GUIDE_QUESTIONS_ZH if body.language == "zh" else _GUIDE_QUESTIONS_EN
    first_q = questions[0]
    if body.language == "zh":
        intro = f"好的，我来帮你确定最合适的论文类型。先问几个问题。\n\n**问题 1/3：**\n\n{first_q}"
    else:
        intro = f"Sure, let me help you identify the right paper type. A few quick questions.\n\n**Question 1/3:**\n\n{first_q}"
    yield _sse({"type": "result", "data": {"message": intro, "step": 1, "done": False}})
    yield _sse({"type": "done"})


async def _stream_guide_reply(body: GuideReplyRequest):
    questions = _GUIDE_QUESTIONS_ZH if body.language == "zh" else _GUIDE_QUESTIONS_EN
    type_labels = _TYPE_LABELS_ZH if body.language == "zh" else _TYPE_LABELS_EN

    answers: list[str] = []
    for msg in body.history:
        if msg.get("role") == "user":
            answers.append(msg["content"])
    answers.append(body.user_answer)

    step = len(answers)
    skip_q2 = answers[0].upper().strip().startswith("B") if answers else False

    if step == 1 and not skip_q2:
        next_q = questions[1]
        msg = f"明白。**问题 2/3：**\n\n{next_q}" if body.language == "zh" else f"Got it. **Question 2/3:**\n\n{next_q}"
        yield _sse({"type": "result", "data": {"message": msg, "step": 2, "done": False}})
    elif step == 1 and skip_q2:
        next_q = questions[2]
        msg = f"明白。**问题 2/3（最后一题）：**\n\n{next_q}" if body.language == "zh" else f"Got it. **Question 2/3 (last one):**\n\n{next_q}"
        yield _sse({"type": "result", "data": {"message": msg, "step": 2, "done": False, "_skip_q2": True}})
    else:
        paper_type = _infer_type_from_answers(answers, body.field)
        label = type_labels.get(paper_type, paper_type)
        if body.language == "zh":
            conclusion = (
                f"根据你的回答，推荐论文类型：\n\n"
                f"**{label}**\n\n"
                f"这种类型最适合你的研究方向。\n"
                f"你可以回到主页选择该类型，开始生成完整论文，\n"
                f"或使用「提纲生成」工具先看一下这种类型的章节结构。"
            )
        else:
            conclusion = (
                f"Based on your answers, the recommended paper type is:\n\n"
                f"**{label}**\n\n"
                f"This type best fits your research direction.\n"
                f"You can go back to the main page and select this type to generate a full paper,\n"
                f"or use the Outline tool to preview the section structure."
            )
        yield _sse({"type": "result", "data": {
            "message": conclusion,
            "step": 3,
            "done": True,
            "recommended_type": paper_type,
        }})

    yield _sse({"type": "done"})


@router.post("/guide/start")
async def tool_guide_start(body: GuideStartRequest, request: Request):
    ip = _get_ip(request)
    if not _check_rate_limit(ip):
        async def _rl():
            yield _sse({"type": "error", "message": "请求过于频繁"})
        return StreamingResponse(_rl(), media_type="text/event-stream")
    return StreamingResponse(
        _stream_guide_start(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/guide/reply")
async def tool_guide_reply(body: GuideReplyRequest, request: Request):
    ip = _get_ip(request)
    if not _check_rate_limit(ip):
        async def _rl():
            yield _sse({"type": "error", "message": "请求过于频繁"})
        return StreamingResponse(_rl(), media_type="text/event-stream")
    return StreamingResponse(
        _stream_guide_reply(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
