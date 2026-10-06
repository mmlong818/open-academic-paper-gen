"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import {
  searchLiterature,
  LiteratureResult,
  SSEEvent,
} from "@/lib/tools-api";

export default function LiteratureToolPage() {
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [count, setCount] = useState<20 | 40 | 80>(20);
  const [yearFrom, setYearFrom] = useState("");

  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [results, setResults] = useState<LiteratureResult[]>([]);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      cleanupRef.current?.();
    };
  }, []);

  function handleStart() {
    if (!topic.trim()) return;
    setStatus("loading");
    setStatusMsg("正在检索…");
    setResults([]);

    cleanupRef.current = searchLiterature(
      {
        topic: topic.trim(),
        language,
        count,
        year_from: yearFrom ? parseInt(yearFrom) : undefined,
      },
      (event: SSEEvent) => {
        if (event.type === "status") setStatusMsg(event.message);
        if (event.type === "result") {
          const data = event.data;
          if (Array.isArray(data)) {
            setResults(data as LiteratureResult[]);
          }
          setStatus("done");
        }
        if (event.type === "error") {
          setStatusMsg(event.message);
          setStatus("error");
        }
        if (event.type === "done") setStatus("done");
      }
    );
  }

  function handleStop() {
    cleanupRef.current?.();
    setStatus("idle");
  }

  function handleCopy() {
    const text = results
      .map(
        (r, i) =>
          `${i + 1}. ${r.title} (${r.year ?? "n.d."}) — ${r.authors.slice(0, 3).join(", ")}${r.doi ? ` DOI: ${r.doi}` : ""}`
      )
      .join("\n");
    navigator.clipboard.writeText(text);
  }

  function handleDownload() {
    const lines = results.map(
      (r, i) =>
        `## ${i + 1}. ${r.title}\n\n**作者：** ${r.authors.join(", ")}  \n**年份：** ${r.year ?? "n.d."}  \n**来源：** ${r.source}  \n${r.doi ? `**DOI：** ${r.doi}  \n` : ""}${r.url ? `**链接：** ${r.url}  \n` : ""}\n**摘要：** ${r.abstract}\n`
    );
    const blob = new Blob([lines.join("\n---\n\n")], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `literature-${Date.now()}.md`;
    a.click();
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-10">
        <div className="mb-6">
          <Link href="/tools" className="text-sm text-gray-500 hover:text-gray-700">
            ← 工具箱
          </Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">文献检索</h1>

        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              研究主题 <span className="text-red-500">*</span>
            </label>
            <input
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="例：transformer architecture in NLP"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">语言</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                value={language}
                onChange={(e) => setLanguage(e.target.value as "zh" | "en")}
              >
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">数量</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                value={count}
                onChange={(e) => setCount(parseInt(e.target.value) as 20 | 40 | 80)}
              >
                <option value={20}>20篇</option>
                <option value={40}>40篇</option>
                <option value={80}>80篇</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">发表年份≥</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="例：2020"
                value={yearFrom}
                onChange={(e) => setYearFrom(e.target.value)}
              />
            </div>
          </div>

          <div className="flex gap-3">
            <button
              className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              onClick={handleStart}
              disabled={status === "loading" || !topic.trim()}
            >
              {status === "loading" ? "检索中…" : "开始检索"}
            </button>
            {status === "loading" && (
              <button
                className="px-4 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
                onClick={handleStop}
              >
                停止
              </button>
            )}
          </div>

          {(status === "loading" || status === "error") && (
            <p className={`text-sm ${status === "error" ? "text-red-500" : "text-gray-500"}`}>
              {statusMsg}
            </p>
          )}
        </div>

        {results.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-gray-800">
                检索结果（{results.length} 篇）
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={handleCopy}
                  className="text-xs px-3 py-1 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  复制列表
                </button>
                <button
                  onClick={handleDownload}
                  className="text-xs px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  下载 .md
                </button>
              </div>
            </div>

            <div className="space-y-4">
              {results.map((r, i) => (
                <div key={i} className="border-b border-gray-100 pb-4 last:border-0 last:pb-0">
                  <p className="text-sm font-medium text-gray-900">
                    {i + 1}. {r.title}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {r.authors.slice(0, 3).join(", ")}
                    {r.authors.length > 3 ? " 等" : ""} · {r.year ?? "n.d."} · {r.source}
                  </p>
                  {r.abstract && (
                    <p className="text-xs text-gray-400 mt-1 line-clamp-2">{r.abstract}</p>
                  )}
                  {r.doi && (
                    <p className="text-xs text-blue-400 mt-0.5">DOI: {r.doi}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
