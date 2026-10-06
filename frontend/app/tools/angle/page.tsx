"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { analyzeAngle, AngleResult, SSEEvent } from "@/lib/tools-api";

export default function AngleToolPage() {
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [synthesis, setSynthesis] = useState("");

  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [result, setResult] = useState<AngleResult | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => () => { cleanupRef.current?.(); }, []);

  function handleStart() {
    if (!topic.trim()) return;
    setStatus("loading");
    setStatusMsg("正在分析…");
    setResult(null);

    cleanupRef.current = analyzeAngle(
      { topic: topic.trim(), language, synthesis },
      (event: SSEEvent) => {
        if (event.type === "status") setStatusMsg(event.message);
        if (event.type === "result") {
          const data = event.data;
          if (data && typeof data === "object" && !Array.isArray(data)) {
            setResult(data as AngleResult);
          }
          setStatus("done");
        }
        if (event.type === "error") { setStatusMsg(event.message); setStatus("error"); }
        if (event.type === "done") setStatus("done");
      }
    );
  }

  function handleCopy() {
    if (!result) return;
    const text = [
      `写作角度：${result.writing_angle}`,
      `研究空白：${result.gap}`,
      `学术贡献：${result.contribution}`,
      `研究方法：${result.approach}`,
      result.hypotheses?.length ? `假设/命题：\n${result.hypotheses.map((h, i) => `  H${i + 1}: ${h}`).join("\n")}` : "",
    ].filter(Boolean).join("\n\n");
    navigator.clipboard.writeText(text).catch(() => {});
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-10">
        <div className="mb-6">
          <Link href="/tools" className="text-sm text-gray-500 hover:text-gray-700">← 工具箱</Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">研究角度分析</h1>

        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6 space-y-4">
          <div>
            <label htmlFor="topic" className="block text-sm font-medium text-gray-700 mb-1">
              研究主题 <span className="text-red-500">*</span>
            </label>
            <input
              id="topic"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="例：人工智能在医疗诊断中的应用"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>

          <div>
            <label htmlFor="lang" className="block text-sm font-medium text-gray-700 mb-1">语言</label>
            <select
              id="lang"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              value={language}
              onChange={(e) => setLanguage(e.target.value as "zh" | "en")}
            >
              <option value="zh">中文</option>
              <option value="en">English</option>
            </select>
          </div>

          <div>
            <label htmlFor="synthesis" className="block text-sm font-medium text-gray-700 mb-1">
              已有文献综述（可选，粘贴可提高准确性）
            </label>
            <textarea
              id="synthesis"
              rows={4}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
              placeholder="粘贴已有的文献综述或摘要内容（可留空）"
              value={synthesis}
              onChange={(e) => setSynthesis(e.target.value)}
            />
          </div>

          <button
            className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            onClick={handleStart}
            disabled={status === "loading" || !topic.trim()}
          >
            {status === "loading" ? "分析中…" : "分析研究角度"}
          </button>

          {(status === "loading" || status === "error") && (
            <p className={`text-sm ${status === "error" ? "text-red-500" : "text-gray-500"}`}>{statusMsg}</p>
          )}
        </div>

        {result && (
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-semibold text-gray-800">分析结果</h2>
              <button onClick={handleCopy} className="text-xs px-3 py-1 border border-gray-300 rounded-lg hover:bg-gray-50">
                复制
              </button>
            </div>

            {[
              { label: "独特写作角度", value: result.writing_angle, color: "text-indigo-600" },
              { label: "研究空白", value: result.gap, color: "text-orange-600" },
              { label: "学术贡献", value: result.contribution, color: "text-green-600" },
              { label: "研究方法", value: result.approach, color: "text-blue-600" },
            ].map((item) => (
              <div key={item.label}>
                <p className={`text-xs font-semibold uppercase mb-1 ${item.color}`}>{item.label}</p>
                <p className="text-sm text-gray-700">{item.value}</p>
              </div>
            ))}

            {result.hypotheses && result.hypotheses.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase mb-1 text-purple-600">假设 / 命题</p>
                <ol className="space-y-1 list-none">
                  {result.hypotheses.map((h, i) => (
                    <li key={i} className="text-sm text-gray-700 flex gap-2">
                      <span className="text-purple-500 font-bold shrink-0">H{i + 1}.</span>
                      {h}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
