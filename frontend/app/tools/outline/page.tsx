"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { generateOutline, OutlineSection, SSEEvent } from "@/lib/tools-api";

const PAPER_TYPES = [
  { value: "general", label: "通用" },
  { value: "review", label: "文献综述" },
  { value: "empirical", label: "实证研究" },
  { value: "experimental", label: "实验研究" },
  { value: "systematic", label: "系统综述/Meta" },
  { value: "computational", label: "计算/AI论文" },
];

export default function OutlineToolPage() {
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [paperType, setPaperType] = useState("general");

  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [sections, setSections] = useState<OutlineSection[]>([]);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      cleanupRef.current?.();
    };
  }, []);

  function handleStart() {
    if (!topic.trim()) return;
    setStatus("loading");
    setStatusMsg("正在生成提纲…");
    setSections([]);

    cleanupRef.current = generateOutline(
      { topic: topic.trim(), language, paper_type: paperType },
      (event: SSEEvent) => {
        if (event.type === "status") setStatusMsg(event.message);
        if (event.type === "result") {
          const data = event.data;
          if (Array.isArray(data)) {
            setSections(data as OutlineSection[]);
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
    const text = sections
      .map((s, i) => `${i + 1}. ${s.title}${s.summary ? `\n   ${s.summary}` : ""}`)
      .join("\n");
    navigator.clipboard.writeText(text);
  }

  function handleDownload() {
    const lines = sections.map(
      (s, i) => `## ${i + 1}. ${s.title}\n\n${s.summary ?? ""}`
    );
    const blob = new Blob([lines.join("\n\n")], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `outline-${Date.now()}.md`;
    a.click();
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-10">
        <div className="mb-6">
          <Link href="/tools" className="text-sm text-gray-500 hover:text-gray-700">
            ← 工具箱
          </Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">提纲生成</h1>

        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              研究主题 <span className="text-red-500">*</span>
            </label>
            <input
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="例：社交媒体使用对青少年心理健康的影响"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
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
              <label className="block text-sm font-medium text-gray-700 mb-1">论文类型</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                value={paperType}
                onChange={(e) => setPaperType(e.target.value)}
              >
                {PAPER_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              onClick={handleStart}
              disabled={status === "loading" || !topic.trim()}
            >
              {status === "loading" ? "生成中…" : "生成提纲"}
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

        {sections.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-gray-800">
                论文提纲（{sections.length} 节）
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={handleCopy}
                  className="text-xs px-3 py-1 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  复制
                </button>
                <button
                  onClick={handleDownload}
                  className="text-xs px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  下载 .md
                </button>
              </div>
            </div>

            <div className="space-y-3">
              {sections.map((s, i) => (
                <div key={i} className="flex gap-3">
                  <span className="text-sm font-bold text-blue-600 w-6 shrink-0">
                    {i + 1}.
                  </span>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{s.title}</p>
                    {s.summary && (
                      <p className="text-xs text-gray-500 mt-0.5">{s.summary}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
