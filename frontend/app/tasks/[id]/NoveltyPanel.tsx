"use client";

import type { NoveltyDiagnosis } from "@/lib/api";

const LEVEL_LABELS: Record<string, string> = {
  problem: "研究问题", method: "方法", data: "数据/情境", perspective: "视角/理论",
};
const VERDICT_STYLE: Record<string, [string, string]> = {
  new: ["新", "bg-green-100 text-green-800"],
  incremental: ["增量", "bg-amber-100 text-amber-800"],
  existing: ["已有", "bg-red-100 text-red-700"],
  unclear: ["无法判断", "bg-gray-100 text-gray-600"],
};
const PSEUDO_LABELS: Record<string, string> = {
  a_plus_b: "A+B 简单拼接", old_method_new_domain: "旧方法换领域",
  dataset_swap: "只换数据集", rebranding: "旧概念换新名",
};

// 创新点诊断：只供审批时参考，不会改动写作角度；最接近的已有工作只取自文献池
export default function NoveltyPanel({ novelty }: { novelty: NoveltyDiagnosis }) {
  return (
    <div className="mt-4 border-t border-gray-100 pt-3 space-y-3">
      <p className="text-xs text-gray-500">
        创新点诊断（基于生成时的角度与文献池，仅供参考，不会修改角度）
      </p>
      <ul className="space-y-1">
        {Object.entries(novelty.levels).map(([level, { verdict, reason }]) => {
          const [label, style] = VERDICT_STYLE[verdict] ?? VERDICT_STYLE.unclear;
          return (
            <li key={level} className="text-xs flex gap-2 items-start">
              <span className="text-gray-500 w-16 shrink-0">{LEVEL_LABELS[level] ?? level}</span>
              <span className={`shrink-0 px-1.5 py-0.5 rounded ${style}`}>{label}</span>
              <span className="text-gray-700">{reason}</span>
            </li>
          );
        })}
      </ul>
      {novelty.pseudo.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-red-600 mb-1">疑似伪创新</p>
          <ul className="space-y-1">
            {novelty.pseudo.map((p, i) => (
              <li key={i} className="text-xs text-gray-700">
                <strong>{PSEUDO_LABELS[p.pattern] ?? p.pattern}</strong>：{p.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {novelty.closest.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-indigo-600 mb-1">压力测试：文献池中最接近的已有工作</p>
          <ul className="space-y-1">
            {novelty.closest.map(c => (
              <li key={c.key} className="text-xs text-gray-700">
                {c.title}{c.year ? ` (${c.year})` : ""} — {c.overlap}
              </li>
            ))}
          </ul>
        </div>
      )}
      {novelty.objection && (
        <p className="text-xs text-gray-700"><strong>审稿人最可能的反对意见：</strong>{novelty.objection}</p>
      )}
    </div>
  );
}
