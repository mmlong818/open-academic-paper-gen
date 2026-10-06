"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { writeAbstract, SSEEvent } from "@/lib/tools-api";

const PAPER_TYPES = [
  { value: "general", label: "通用" },
  { value: "review", label: "文献综述" },
  { value: "empirical", label: "实证研究" },
  { value: "experimental", label: "实验研究" },
  { value: "systematic", label: "系统综述" },
  { value: "computational", label: "计算/AI" },
];

export default function AbstractToolPage() {
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [paperType, setPaperType] = useState("general");
  const [keyArgument, setKeyArgument] = useState("");
  const [method, setMethod] = useState("");
  const [findings, setFindings] = useState("");

  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [abstractText, setAbstractText] = useState("");
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => () => { cleanupRef.current?.(); }, []);

  function handleStart() {
    if (!topic.trim() || !keyArgument.trim()) return;
    setStatus("loading");
    setStatusMsg("正在生成摘要…");
    setAbstractText("");

    cleanupRef.current = writeAbstract(
      { topic: topic.trim(), language, paper_type: paperType, key_argument: keyArgument.trim(), method, findings },
      (event: SSEEvent) => {
        if (event.type === "status") setStatusMsg(event.message);
        if (event.type === "result") {
          const data = event.data;
          if (data && typeof data === "object" && !Array.isArray(data)) {
            setAbstractText((data as { abstract: string }).abstract ?? "");
          }
          setStatus("done");
        }
        if (event.type === "error") { setStatusMsg(event.message); setStatus("error"); }
        if (event.type === "done") setStatus("done");
      }
    );
  }

  function handleDownload() {
    const blob = new Blob([abstractText], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `abstract-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-10">
        <div className="mb-6">
          <Link href="/tools" className="text-sm text-gray-500 hover:text-gray-700">← 工具箱</Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">摘要写作</h1>

        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="topic" className="block text-sm font-medium text-gray-700 mb-1">
                论文主题 <span className="text-red-500">*</span>
              </label>
              <input
                id="topic"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                placeholder="论文主题"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="lang" className="block text-sm font-medium text-gray-700 mb-1">语言</label>
              <select id="lang" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={language} onChange={(e) => setLanguage(e.target.value as "zh" | "en")}>
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="ptype" className="block text-sm font-medium text-gray-700 mb-1">论文类型</label>
            <select id="ptype" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={paperType} onChange={(e) => setPaperType(e.target.value)}>
              {PAPER_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>

          <div>
            <label htmlFor="arg" className="block text-sm font-medium text-gray-700 mb-1">
              核心论点 <span className="text-red-500">*</span>
            </label>
            <textarea id="arg" rows={2} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none" placeholder="本文的核心主张或结论是什么？" value={keyArgument} onChange={(e) => setKeyArgument(e.target.value)} />
          </div>

          <div>
            <label htmlFor="method" className="block text-sm font-medium text-gray-700 mb-1">研究方法（可选）</label>
            <input id="method" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" placeholder="例：问卷调查、回归分析、系统综述…" value={method} onChange={(e) => setMethod(e.target.value)} />
          </div>

          <div>
            <label htmlFor="findings" className="block text-sm font-medium text-gray-700 mb-1">主要发现（可选）</label>
            <textarea id="findings" rows={2} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none" placeholder="主要结果或发现" value={findings} onChange={(e) => setFindings(e.target.value)} />
          </div>

          <button
            className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            onClick={handleStart}
            disabled={status === "loading" || !topic.trim() || !keyArgument.trim()}
          >
            {status === "loading" ? "生成中…" : "生成摘要"}
          </button>

          {(status === "loading" || status === "error") && (
            <p className={`text-sm ${status === "error" ? "text-red-500" : "text-gray-500"}`}>{statusMsg}</p>
          )}
        </div>

        {abstractText && (
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-gray-800">生成摘要</h2>
              <div className="flex gap-2">
                <button onClick={() => navigator.clipboard.writeText(abstractText).catch(() => {})} className="text-xs px-3 py-1 border border-gray-300 rounded-lg hover:bg-gray-50">复制</button>
                <button onClick={handleDownload} className="text-xs px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700">下载</button>
              </div>
            </div>
            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{abstractText}</p>
            <p className="text-xs text-gray-400 mt-3">{abstractText.length} 字符</p>
          </div>
        )}
      </div>
    </div>
  );
}
