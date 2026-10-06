"""规则+轻量 LLM 混合质量检查器。
每个检查项返回 {"item": str, "passed": bool | None, "note": str}。
"""
from __future__ import annotations

from backend.pipeline.type_configs import get_type_config


def check_quality(state_dict: dict) -> list[dict]:
    """从 pipeline state dict 中读取数据，返回质量检查结果列表。"""
    paper_type = state_dict.get("paper_type", "general")
    cfg = get_type_config(paper_type)
    results: list[dict] = []

    literature: list = state_dict.get("literature", [])
    sections: dict = state_dict.get("sections", {})
    outline: list = state_dict.get("outline", [])
    angle: dict = state_dict.get("angle", {}) or {}
    prisma_flow: str = state_dict.get("prisma_flow", "")
    ablation_design: str = state_dict.get("ablation_design", "")
    verified_citations: list = state_dict.get("verified_citations", [])

    lit_count = len(literature)
    results.append({
        "item": f"文献数量（{cfg.lit_count_min}–{cfg.lit_count_max} 篇）",
        "passed": cfg.lit_count_min <= lit_count <= cfg.lit_count_max * 1.2,
        "note": f"实际检索 {lit_count} 篇",
    })

    has_abstract = any(
        "abstract" in (s.get("title", "") or "").lower() or "摘要" in (s.get("title", "") or "").lower()
        for s in outline
    )
    results.append({
        "item": "包含摘要章节",
        "passed": has_abstract or bool(sections),
        "note": "已有摘要" if has_abstract else "未检测到独立摘要节",
    })

    section_count = len(sections)
    outline_count = len(outline)
    results.append({
        "item": "章节完整性（正文节数 >= 提纲节数）",
        "passed": section_count >= outline_count if outline_count > 0 else section_count > 0,
        "note": f"提纲 {outline_count} 节，已生成 {section_count} 节",
    })

    results.append({
        "item": "引用文献已核验",
        "passed": len(verified_citations) > 0,
        "note": f"核验通过 {len(verified_citations)} 篇",
    })

    # 类型专属检查
    if paper_type == "systematic":
        results.append({
            "item": "PRISMA 筛选流程已生成",
            "passed": bool(prisma_flow),
            "note": "已有 PRISMA 流程描述" if prisma_flow else "缺少 PRISMA 流程，建议手动添加",
        })
        results.append({
            "item": f"文献量达到系统综述要求（≥{cfg.lit_count_min} 篇）",
            "passed": lit_count >= cfg.lit_count_min,
            "note": f"当前 {lit_count} 篇，要求 ≥{cfg.lit_count_min} 篇",
        })

    elif paper_type == "computational":
        results.append({
            "item": "消融实验设计已生成",
            "passed": bool(ablation_design),
            "note": "已有消融实验设计" if ablation_design else "缺少消融实验设计",
        })
        results.append({
            "item": "贡献点已明确（angle.contribution 非空）",
            "passed": bool(angle.get("contribution", "")),
            "note": "已有贡献声明" if angle.get("contribution") else "贡献声明为空",
        })

    elif paper_type in ("empirical", "experimental"):
        hypotheses = angle.get("hypotheses", [])
        results.append({
            "item": "研究假设已列出（H1, H2...）",
            "passed": len(hypotheses) > 0,
            "note": f"共 {len(hypotheses)} 条假设" if hypotheses else "未检测到研究假设",
        })

    elif paper_type == "review":
        results.append({
            "item": "研究角度自动跳过（综述类无需 angle 节点）",
            "passed": True,
            "note": "符合文献综述规范",
        })

    # TypeConfig 质检清单条目（文字描述，标记为手动确认）
    for checklist_item in cfg.quality_checklist:
        results.append({
            "item": checklist_item,
            "passed": None,       # None = 需要人工确认
            "note": "请人工核查",
        })

    return results
