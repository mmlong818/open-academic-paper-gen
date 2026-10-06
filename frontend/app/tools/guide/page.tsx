"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { guideStart, guideReply, GuideMessage, GuideResultData, SSEEvent } from "@/lib/tools-api";

const TYPE_HREF: Record<string, string> = {
  review: "/?type=review",
  empirical: "/?type=empirical",
  experimental: "/?type=experimental",
  systematic: "/?type=systematic",
  computational: "/?type=computational",
};

export default function GuideToolPage() {
  const [field, setField] = useState("");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [started, setStarted] = useState(false);
  const [messages, setMessages] = useState<GuideMessage[]>([]);
  const [userInput, setUserInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [recommendedType, setRecommendedType] = useState<string | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => { cleanupRef.current?.(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  function handleStart() {
    if (!field.trim()) return;
    setStarted(true);
    setLoading(true);

    cleanupRef.current = guideStart(
      field.trim(),
      language,
      (event: SSEEvent) => {
        if (event.type === "result") {
          const data = event.data as GuideResultData;
          setMessages([{ role: "assistant", content: data.message }]);
          setLoading(false);
        }
        if (event.type === "error") setLoading(false);
        if (event.type === "done") setLoading(false);
      }
    );
  }

  function handleReply() {
    if (!userInput.trim() || loading) return;
    const answer = userInput.trim();
    setUserInput("");
    const newHistory: GuideMessage[] = [...messages, { role: "user", content: answer }];
    setMessages(newHistory);
    setLoading(true);

    cleanupRef.current = guideReply(
      { field, language, history: messages, user_answer: answer },
      (event: SSEEvent) => {
        if (event.type === "result") {
          const data = event.data as GuideResultData;
          setMessages([...newHistory, { role: "assistant", content: data.message }]);
          if (data.done) {
            setDone(true);
            if (data.recommended_type) setRecommendedType(data.recommended_type);
          }
          setLoading(false);
        }
        if (event.type === "error") setLoading(false);
        if (event.type === "done") setLoading(false);
      }
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-10">
        <div className="mb-6">
          <Link href="/tools" className="text-sm text-gray-500 hover:text-gray-700">← 工具箱</Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">选题引导</h1>
        <p className="text-sm text-gray-500 mb-6">通过3轮对话确定最适合你的论文类型</p>

        {!started ? (
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <div>
              <label htmlFor="field" className="block text-sm font-medium text-gray-700 mb-1">
                研究领域 <span className="text-red-500">*</span>
              </label>
              <input
                id="field"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                placeholder="例：教育学、计算机科学、公共卫生…"
                value={field}
                onChange={(e) => setField(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="lang" className="block text-sm font-medium text-gray-700 mb-1">引导语言</label>
              <select id="lang" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={language} onChange={(e) => setLanguage(e.target.value as "zh" | "en")}>
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </div>
            <button
              className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              onClick={handleStart}
              disabled={!field.trim()}
            >
              开始引导
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4 min-h-[200px] max-h-[60vh] overflow-y-auto">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-xl px-4 py-3 text-sm whitespace-pre-wrap ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 text-gray-800"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-xl px-4 py-3 text-sm text-gray-400">思考中…</div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {!done ? (
              <div className="flex gap-2">
                <input
                  className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                  placeholder="输入 A、B 或 C，或用文字回答"
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleReply()}
                  disabled={loading}
                />
                <button
                  className="bg-blue-600 text-white px-4 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                  onClick={handleReply}
                  disabled={loading || !userInput.trim()}
                >
                  发送
                </button>
              </div>
            ) : recommendedType ? (
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-center">
                <p className="text-sm text-blue-700 mb-3">引导完成！使用推荐类型创建完整论文：</p>
                <Link
                  href={TYPE_HREF[recommendedType] ?? "/"}
                  className="inline-block bg-blue-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
                >
                  去创建论文 →
                </Link>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
