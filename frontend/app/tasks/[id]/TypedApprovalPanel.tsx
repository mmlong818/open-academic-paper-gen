"use client";

import { Task } from "@/lib/api";
import AngleApprovalPanel from "./AngleApprovalPanel";

interface Props {
  task: Task;
  onTaskUpdate: (t: Task) => void;
  onApprove: () => void;
  approving: boolean;
  error: string | null;
}

const TYPE_PHASE_LABELS: Record<string, Record<number, string>> = {
  review: {
    1: "主题定界",
    2: "文献检索",
    3: "文献数据清洗",
    4: "研究趋势/空白发现",
    6: "提纲（综述结构）",
    7: "章节写作",
    8: "引用验证",
    9: "导出",
  },
  systematic: {
    1: "主题定界",
    2: "文献检索",
    3: "PRISMA 文献筛选",
    4: "证据综合",
    5: "写作角度",
    6: "提纲（PRISMA 结构）",
    7: "章节写作",
    8: "引用验证",
    9: "导出",
  },
  computational: {
    1: "主题定界",
    2: "相关工作检索",
    3: "文献数据清洗",
    4: "研究趋势/空白发现",
    5: "研究角度与贡献",
    6: "提纲（方法+实验结构）",
    7: "章节写作",
    8: "引用验证",
    9: "导出",
  },
  empirical: {
    1: "主题定界",
    2: "文献检索",
    3: "文献数据清洗",
    4: "研究趋势/空白发现",
    5: "假设与研究角度",
    6: "提纲（IMRaD 结构）",
    7: "章节写作",
    8: "引用验证",
    9: "导出",
  },
  experimental: {
    1: "主题定界",
    2: "文献检索",
    3: "文献数据清洗",
    4: "研究趋势/空白发现",
    5: "研究假设",
    6: "提纲（多实验结构）",
    7: "章节写作",
    8: "引用验证",
    9: "导出",
  },
};

const TYPE_APPROVAL_HINTS: Record<string, Record<number, string>> = {
  review: {
    2: "文献综述通常需要60-100篇文献。确认检索结果覆盖面足够后继续。",
    3: "请确认清洗后文献去除了明显重复和低相关条目，核心文献均已保留。",
    6: "综述提纲应按主题分区组织，而非按论文逐一排列。请确认章节结构合理。",
  },
  systematic: {
    2: "系统综述需要100-200篇文献，并遵循 PRISMA 2020 筛选流程。请确认文献量充足。",
    3: "PRISMA 筛选结果请确认纳入/排除标准已被正确执行。",
    6: "系统综述提纲应包含：引言→方法→结果→讨论→结论，符合 PRISMA 报告规范。",
  },
  computational: {
    3: "请确认保留的文献均与研究方法/模型直接相关。",
    5: "计算/AI 论文需要明确列出3-5条贡献点，确认角度分析包含清晰的贡献声明。",
    6: "计算论文提纲应包含：引言→相关工作→方法→实验→消融分析→结论。",
  },
  empirical: {
    3: "请确认保留文献覆盖核心理论基础和同类实证研究。",
    5: "实证研究需要明确的假设（H1, H2…），请确认假设具体且可检验。",
    6: "实证论文提纲应遵循 IMRaD 结构，假设在文献综述后提出。",
  },
  experimental: {
    3: "请确认保留文献覆盖实验设计方法和相关变量研究。",
    5: "实验研究需要包含操控变量和控制条件的假设，请确认假设清晰。",
    6: "实验论文提纲通常包含多个实验（研究1→研究2→总体讨论）。",
  },
};

export default function TypedApprovalPanel({ task, onTaskUpdate, onApprove, approving, error }: Props) {
  const paperType = task.paper_type ?? "general";
  const phase = task.phase;

  if (phase === 5) {
    return <AngleApprovalPanel task={task} onTaskUpdate={onTaskUpdate} />;
  }

  const hint = TYPE_APPROVAL_HINTS[paperType]?.[phase];
  const phaseLabels = TYPE_PHASE_LABELS[paperType] ?? {};
  const phaseLabel = phaseLabels[phase] ?? `阶段 ${phase}`;

  return (
    <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-5">
      <h3 className="font-medium text-yellow-800 mb-1">
        等待审批 — {phaseLabel}
      </h3>

      {hint && (
        <div className="bg-yellow-100 border border-yellow-200 rounded-md p-3 mb-3">
          <p className="text-xs text-yellow-800 leading-relaxed">
            <span className="font-semibold">
              {paperType === "general" ? "提示" : `${paperType.toUpperCase()} 类型提示`}：
            </span>{" "}
            {hint}
          </p>
        </div>
      )}

      <p className="text-sm text-yellow-700 mb-4">
        流水线已在当前阶段暂停，请确认后继续执行。
      </p>

      {error && <p className="text-sm text-red-600 mb-2">{error}</p>}

      <button
        onClick={onApprove}
        disabled={approving}
        className="bg-yellow-500 hover:bg-yellow-600 text-white px-5 py-2 rounded-md text-sm font-medium disabled:opacity-50"
      >
        {approving ? "提交中…" : "✓ 批准，继续执行"}
      </button>
    </div>
  );
}
