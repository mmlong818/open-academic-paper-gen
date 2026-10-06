"use client";

import { useState } from "react";
import type { EvidenceRow } from "@/lib/api";

const FIELDS: [keyof EvidenceRow, string][] = [
  ["task", "任务"], ["method", "方法"], ["data", "数据"],
  ["metric", "指标"], ["finding", "主要发现"], ["limitation", "局限"],
];

// 证据表：每篇有摘要或正文的文献一行，只抽原文写明的内容；空格即「未报告」
export default function EvidenceTable({ rows, poolSize, onExport, exporting }: {
  rows: EvidenceRow[];
  poolSize: number;
  onExport: (fmt: "csv" | "markdown") => void;
  exporting: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4 border-t border-gray-100 pt-3">
      <div className="flex items-center gap-3 text-xs">
        <button type="button" onClick={() => setOpen(o => !o)} className="text-blue-600 hover:underline">
          {open ? "收起" : "展开"}证据表
        </button>
        <span className="text-gray-500">
          {rows.length} / {poolSize} 篇（仅抽取有摘要或正文的文献；空格表示原文未报告）
        </span>
        <button type="button" disabled={exporting} onClick={() => onExport("csv")}
          className="ml-auto text-gray-600 hover:text-gray-900 disabled:opacity-50">CSV</button>
        <button type="button" disabled={exporting} onClick={() => onExport("markdown")}
          className="text-gray-600 hover:text-gray-900 disabled:opacity-50">Markdown</button>
      </div>
      {open && (
        <div className="mt-2 max-h-96 overflow-auto">
          <table className="text-xs border-collapse w-full">
            <thead className="sticky top-0 bg-gray-50">
              <tr>
                <th className="border border-gray-200 px-2 py-1 text-left">文献</th>
                {FIELDS.map(([, label]) => (
                  <th key={label} className="border border-gray-200 px-2 py-1 text-left">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.key} className="align-top">
                  <td className="border border-gray-200 px-2 py-1 min-w-40">{row.title}{row.year ? ` (${row.year})` : ""}</td>
                  {FIELDS.map(([field]) => (
                    <td key={field} className="border border-gray-200 px-2 py-1 min-w-32">
                      {row[field] || <span className="text-gray-300">未报告</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
