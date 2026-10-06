from dataclasses import dataclass

__all__ = ["TypeConfig", "TYPE_CONFIGS", "get_type_config"]


@dataclass(frozen=True)
class TypeConfig:
    lit_count_min: int
    lit_count_max: int
    skip_phases: tuple[int, ...] = ()
    extra_nodes: tuple[str, ...] = ()
    section_template: str = "general"
    quality_checklist: tuple[str, ...] = ()


TYPE_CONFIGS: dict[str, TypeConfig] = {
    "general": TypeConfig(
        lit_count_min=20,
        lit_count_max=40,
        quality_checklist=("结构完整", "引用格式正确"),
    ),
    "review": TypeConfig(
        lit_count_min=60,
        lit_count_max=100,
        section_template="review",
        quality_checklist=(
            "Torraco整合综述标准",
            "明确检索策略",
            "主题分区综述（非逐篇摘要）",
            "含研究议程",
        ),
    ),
    "empirical": TypeConfig(
        lit_count_min=40,
        lit_count_max=60,
        section_template="empirical",
        quality_checklist=(
            "假设明确且可检验",
            "识别策略说明（因果推断）",
            "描述性统计表",
            "多重稳健性检验",
            "APA/JARS报告规范",
        ),
    ),
    "experimental": TypeConfig(
        lit_count_min=30,
        lit_count_max=50,
        section_template="experimental",
        quality_checklist=(
            "随机分配说明",
            "操控检验",
            "样本量功效分析",
            "效应量（Cohen's d / η²）",
            "OSF预注册项",
        ),
    ),
    "systematic": TypeConfig(
        lit_count_min=100,
        lit_count_max=200,
        extra_nodes=("prisma",),
        section_template="systematic",
        quality_checklist=(
            "PRISMA 2020合规",
            "PROSPERO注册",
            "双盲筛选（κ系数）",
            "偏倚风险评估（RoB 2）",
            "GRADE证据确定性",
            "发表偏倚检验（漏斗图）",
        ),
    ),
    "computational": TypeConfig(
        lit_count_min=40,
        lit_count_max=80,
        extra_nodes=("ablation",),
        section_template="computational",
        quality_checklist=(
            "贡献点列表（3-5条）",
            "消融实验覆盖每个组件",
            "多随机种子统计显著性",
            "基线包含SOTA+简单基线",
            "可复现性清单（代码/配置/种子）",
        ),
    ),
}


def get_type_config(paper_type: str) -> TypeConfig:
    """Return TypeConfig for the given paper type, falling back to 'general'."""
    return TYPE_CONFIGS.get(paper_type, TYPE_CONFIGS["general"])
