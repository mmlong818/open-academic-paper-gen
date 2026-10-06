"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { writeSynthesis, SSEEvent } from "@/lib/tools-api";

const PLACEHOLDER_JSON = `[
  {
    "title": "Deep learning in medical imaging",
    "authors": ["Zhang, L.", "Wang, M."],
    "year": 2023,
    "abstract": "This paper reviews...",
    "source": "Nature Medicine",
    "doi": "10.1038/xxx"
  }
]`;

export default function SynthesisToolPage() {
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [litJson, setLitJson] = useState("");

  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [synthesis, setSynthesis] = useState("");
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => () => { cleanupRef.current?.(); }, []);

  function handleStart() {
    if (!topic.trim() || !litJson.trim()) return;
    setStatus("loading");
    setStatusMsg("正在生成综述段落…");
    setSynthesis("");

    cleanupRef.current = writeSynthesis(
      { topic: topic.trim(), language, literature_json: litJson.trim() },
      (event: SSEEvent) => {
        if (event.type === "status") setStatusMsg(event.message);
        if (event.type === "result") {
          const data = event.data;
          if (data && typeof data === "object" && !Array.isArray(data)) {
            setSynthesis((data as { synthesis: string }).synthesis ?? "");
          }
          setStatus("done");
        }
        if (event.type === "error") { setStatusMsg(event.message); setStatus("error"); }
        if (event.type === "done") setStatus("done");
      }
    );
  }

  function handleDownload() {
    const blob = new Blob([synthesis], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `synthesis-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-10">
        <div className="mb-6">
          <Link href="/tools" className="text-sm text-gray-500 hover:text-gray-700">← 工具箱</Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">文献综述段落</h1>

        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="topic" className="block text-sm font-medium text-gray-700 mb-1">
                聚焦主题 <span className="text-red-500">*</span>
              </label>
              <input
                id="topic"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                placeholder="例：深度学习在医学影像中的应用"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="lang" className="block text-sm font-medium text-gray-700 mb-1">输出语言</label>
              <select id="lang" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={language} onChange={(e) => setLanguage(e.target.value as "zh" | "en")}>
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="lit" className="block text-sm font-medium text-gray-700 mb-1">
              文献列表 JSON <span className="text-red-500">*</span>
            </label>
            <p className="text-xs text-gray-400 mb-1">格式：JSON 数组，每项包含 title、authors、year、abstract 等字段</p>
            <textarea
              id="lit"
              rows={8}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
              placeholder={PLACEHOLDER_JSON}
              value={litJson}
              onChange={(e) => setLitJson(e.target.value)}
            />
          </div>

          <button
            className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            onClick={handleStart}
            disabled={status === "loading" || !topic.trim() || !litJson.trim()}
          >
            {status === "loading" ? "生成中…" : "生成综述段落"}
          </button>

          {(status === "loading" || status === "error") && (
            <p className={`text-sm ${status === "error" ? "text-red-500" : "text-gray-500"}`}>{statusMsg}</p>
          )}
        </div>

        {synthesis && (
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-gray-800">综述段落</h2>
              <div className="flex gap-2">
                <button onClick={() => navigator.clipboard.writeText(synthesis).catch(() => {})} className="text-xs px-3 py-1 border border-gray-300 rounded-lg hover:bg-gray-50">复制</button>
                <button onClick={handleDownload} className="text-xs px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700">下载 .md</button>
              </div>
            </div>
            <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{synthesis}</div>
          </div>
        )}
      </div>
    </div>
  );
}
