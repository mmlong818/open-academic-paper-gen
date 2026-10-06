"use client";

import { useState } from "react";
import type { LiteratureItem } from "@/lib/api";
import { SOURCE_MIX_LABELS, SourceMix, hasChinese } from "@/lib/language";

const ZH_TARGET: Record<SourceMix, number> = { zh_major: 70, balanced: 50, en_major: 20 };

const SOURCE_NAMES: Record<string, string> = {
  semantic_scholar: "Semantic Scholar", openalex: "OpenAlex", crossref: "CrossRef", arxiv: "arXiv",
};

function percent(part: number, whole: number): number {
  return whole ? Math.round((part / whole) * 100) : 0;
}

// 某一语种低于目标占比的一半时说明原因：开放数据源的中文文献常常少、偏题、缺摘要
function shortfall(literature: LiteratureItem[], sourceMix: SourceMix): string | null {
  const target = ZH_TARGET[sourceMix];
  const zh = literature.filter((lit) => hasChinese(lit.title ?? ""));
  const share = percent(zh.length, literature.length);
  const [side, papers, want] = share < target / 2
    ? ["中文", zh, target]
    : 100 - share < (100 - target) / 2
      ? ["英文", literature.filter((lit) => !hasChinese(lit.title ?? "")), 100 - target]
      : [null, [], 0];
  if (!side) return null;
  const bare = papers.filter((lit) => !(lit.abstract ?? "").trim()).length;
  const other = side === "中文" ? "英文为主" : "中文为主";
  return `可用的${side}文献不足：清洗后 ${papers.length} 篇（${percent(papers.length, literature.length)}%，目标约 ${want}%）`
    + (bare ? `，其中 ${bare} 篇无摘要` : "")
    + `。正文会尽量引用这些文献；也可以在第 2 步「从此步重做」补充检索词，或改用「${other}」。`;
}

// 文献构成：中英文各多少、来自哪些来源；检索闸门上可以换一种侧重重新检索
export default function LiteratureMix({
  literature,
  sourceMix,
  onResearch,
  busy = false,
  warnShortfall = false,
}: {
  literature: LiteratureItem[];
  sourceMix: SourceMix;
  onResearch?: (mix: SourceMix) => void;
  busy?: boolean;
  warnShortfall?: boolean;
}) {
  const warning = warnShortfall ? shortfall(literature, sourceMix) : null;
  const [nextMix, setNextMix] = useState<SourceMix>(sourceMix);
  const zh = literature.filter((lit) => hasChinese(lit.title ?? "")).length;
  const en = literature.length - zh;
  const sources = Object.entries(
    literature.reduce<Record<string, number>>((acc, lit) => {
      acc[lit.source] = (acc[lit.source] ?? 0) + 1;
      return acc;
    }, {}),
  ).sort((a, b) => b[1] - a[1]);

  return (
    <div className="text-xs mb-3 p-3 bg-gray-50 rounded-lg space-y-2">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span className="text-gray-700">
          文献构成：中文 <strong>{zh}</strong> 篇（{percent(zh, literature.length)}%）· 英文 <strong>{en}</strong> 篇（{percent(en, literature.length)}%）
        </span>
        <span className="text-gray-500">
          侧重：{SOURCE_MIX_LABELS[sourceMix]}（中文目标约 {ZH_TARGET[sourceMix]}%）
        </span>
      </div>
      {warning && (
        <p className="text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 leading-relaxed">{warning}</p>
      )}
      <div className="text-gray-500">
        来源：{sources.map(([source, n]) => `${SOURCE_NAMES[source] ?? source} ${n}`).join(" · ")}
      </div>
      {onResearch && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <label htmlFor="mix-adjust" className="text-gray-600">换一种侧重：</label>
          <select
            id="mix-adjust"
            value={nextMix}
            onChange={(e) => setNextMix(e.target.value as SourceMix)}
            className="border border-gray-300 rounded px-2 py-1 text-xs"
          >
            {(Object.keys(SOURCE_MIX_LABELS) as SourceMix[]).map((m) => (
              <option key={m} value={m}>{SOURCE_MIX_LABELS[m]}</option>
            ))}
          </select>
          <button
            onClick={() => onResearch(nextMix)}
            disabled={busy || nextMix === sourceMix}
            className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-xs font-medium disabled:opacity-40"
          >
            {busy ? "重新检索中…" : "按新侧重重新检索"}
          </button>
          <span className="text-gray-400">将替换本次检索结果</span>
        </div>
      )}
    </div>
  );
}
