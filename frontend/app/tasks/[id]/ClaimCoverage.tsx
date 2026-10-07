"use client";

import type { CitationIssue } from "@/lib/api";

const EVIDENCE_LABELS: Record<string, string> = {
  full_text: "全文", body: "正文节选", abstract: "摘要", none: "无文本",
};

// 论断覆盖：每处引用按什么判定、有多少没能判定。旧任务没有这些字段，不显示。
export function ClaimCoverageSummary({ issues }: { issues: CitationIssue[] }) {
  const rows = issues.filter(i => i.claims);
  if (rows.length === 0) return null;
  const sum = (pick: (i: CitationIssue) => number) => rows.reduce((n, i) => n + pick(i), 0);
  const judged = (kind: string) => sum(i => (i.evidence === kind ? i.claims!.judged : 0));
  const total = sum(i => i.claims!.total);
  const unclear = sum(i => i.claims!.unclear);
  const unjudged = sum(i => i.claims!.unjudged);

  return (
    <p className="text-xs text-gray-500 mb-3">
      论断 <strong>{total}</strong> 处：全文判定 {judged("full_text")} · 节选判定 {judged("body")} · 摘要判定 {judged("abstract")}
      {" · "}无法判断 {unclear}
      {" · "}<span className={unjudged ? "text-red-500 font-medium" : ""}>未判定 {unjudged}</span>
    </p>
  );
}

export function ClaimCoverageBadge({ issue }: { issue: CitationIssue }) {
  if (!issue.claims) return null;
  const { total, unclear, unjudged } = issue.claims;
  const parts = [`${total} 处论断`, EVIDENCE_LABELS[issue.evidence ?? ""] ?? issue.evidence];
  if (unclear) parts.push(`无法判断 ${unclear}`);
  if (unjudged) parts.push(`未判定 ${unjudged}`);
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${unjudged ? "bg-red-50 text-red-600" : "bg-gray-100 text-gray-500"}`}>
      {parts.join(" · ")}
    </span>
  );
}
