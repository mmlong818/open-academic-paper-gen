"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, Task, CreateTaskInput, PHASE_LABELS, STATUS_LABELS } from "@/lib/api";
import {
  SOURCE_MIX_LABELS, SourceMix, WritingLanguage, defaultSourceMix, inferLanguage,
} from "@/lib/language";

type Tab = "all" | "starred";

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "completed"
      ? "bg-green-100 text-green-700"
      : status === "failed"
      ? "bg-red-100 text-red-700"
      : status === "waiting"
      ? "bg-yellow-100 text-yellow-700"
      : "bg-blue-100 text-blue-700";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${cls}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [tab, setTab] = useState<Tab>("all");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<CreateTaskInput>({
    topic: "",
    language: "zh",
    collab_mode: "key_gates",
    source_mix: "balanced",
  });
  // 用户手动改过的项不再被自动推断覆盖
  const [touched, setTouched] = useState({ language: false, mix: false });

  function withInferred(next: CreateTaskInput, t = touched): CreateTaskInput {
    const browser = typeof navigator === "undefined" ? undefined : navigator.language;
    const language: WritingLanguage = t.language ? next.language : inferLanguage(next.topic, browser);
    const source_mix = t.mix ? next.source_mix : defaultSourceMix(language);
    return { ...next, language, source_mix };
  }

  useEffect(() => {
    setForm((f) => withInferred(f));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [paperType, setPaperType] = useState("general");
  const [error, setError] = useState<string | null>(null);

  async function loadTasks(activeTab = tab) {
    try {
      const data = await api.listTasks(activeTab === "starred");
      setTasks(data);
    } catch {
      setError("无法加载任务列表");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    loadTasks(tab);
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.topic.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const task = await api.createTask({ ...form, paper_type: paperType as CreateTaskInput["paper_type"] });
      await api.startTask(task.id);
      router.push(`/tasks/${task.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setCreating(false);
    }
  }

  async function handleStar(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    setError(null);
    try {
      const updated = await api.starTask(id);
      setTasks((prev) =>
        tab === "starred"
          ? prev.filter((t) => t.id !== id)
          : prev.map((t) => (t.id === id ? updated : t))
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "收藏操作失败");
    }
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    setError(null);
    if (!window.confirm("确认删除该任务？")) return;
    try {
      await api.deleteTask(id);
      setTasks((prev) => prev.filter((t) => t.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  return (
    <div className="space-y-8">
      {/* 新建表单 */}
      <section className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium">新建论文生成任务</h2>
          <Link href="/tools" className="text-sm text-blue-600 hover:underline">
            工具箱 →
          </Link>
        </div>
        <form onSubmit={handleCreate} className="space-y-4">
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              论文类型
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { value: "general", label: "通用" },
                { value: "review", label: "文献综述" },
                { value: "empirical", label: "实证研究" },
                { value: "experimental", label: "实验研究" },
                { value: "systematic", label: "系统综述" },
                { value: "computational", label: "计算/AI" },
              ].map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setPaperType(t.value)}
                  className={`py-2 px-3 rounded-lg text-xs border transition-all ${
                    paperType === t.value
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white text-gray-600 border-gray-300 hover:border-blue-400"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-1">
              不确定？选"通用"即可
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              研究主题
            </label>
            <input
              type="text"
              value={form.topic}
              onChange={(e) => setForm(withInferred({ ...form, topic: e.target.value }))}
              placeholder="例如：深度学习在医学影像诊断中的应用"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>
          <div className="flex gap-4">
            <div className="flex-1">
              <label htmlFor="writing-language" className="block text-sm font-medium text-gray-700 mb-1">
                写作语言
              </label>
              <select
                id="writing-language"
                value={form.language}
                onChange={(e) => {
                  const t = { ...touched, language: true };
                  setTouched(t);
                  setForm(withInferred({ ...form, language: e.target.value as WritingLanguage }, t));
                }}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none"
              >
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </div>
            <div className="flex-1">
              <label htmlFor="source-mix" className="block text-sm font-medium text-gray-700 mb-1">
                文献侧重
              </label>
              <select
                id="source-mix"
                value={form.source_mix}
                onChange={(e) => {
                  setTouched({ ...touched, mix: true });
                  setForm({ ...form, source_mix: e.target.value as SourceMix });
                }}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none"
              >
                {(Object.keys(SOURCE_MIX_LABELS) as SourceMix[]).map((m) => (
                  <option key={m} value={m}>{SOURCE_MIX_LABELS[m]}</option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                协作模式
              </label>
              <select
                value={form.collab_mode}
                onChange={(e) =>
                  setForm({
                    ...form,
                    collab_mode: e.target.value as CreateTaskInput["collab_mode"],
                  })
                }
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none"
              >
                <option value="full_auto">全自动</option>
                <option value="key_gates">关键节点审批</option>
              </select>
            </div>
          </div>
          <p className="text-xs text-gray-400 -mt-2">
            写作语言与文献侧重按主题自动选择，可以修改；检索完成后还能按新侧重重新检索。
          </p>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={creating}
            className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {creating ? "生成中…" : "开始生成"}
          </button>
        </form>
      </section>

      {/* 任务列表 */}
      <section>
        {error && (
          <p className="text-sm text-red-600 mb-3 px-1">{error}</p>
        )}

        {/* Tabs */}
        <div className="flex items-center gap-1 mb-4 border-b border-gray-200">
          {(["all", "starred"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t === "all" ? "全部任务" : "⭐ 收藏夹"}
            </button>
          ))}
        </div>

        {loading ? (
          <p className="text-sm text-gray-500">加载中…</p>
        ) : tasks.length === 0 ? (
          <p className="text-sm text-gray-500">
            {tab === "starred" ? "收藏夹为空" : "暂无任务"}
          </p>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => (
              <div key={task.id} className="relative group">
                <Link
                  href={`/tasks/${task.id}`}
                  className="block bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors pr-20"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{task.topic}</span>
                    <div className="flex items-center gap-1.5">
                      <StatusBadge status={task.status} />
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    阶段：{PHASE_LABELS[task.phase] ?? task.phase} ·{" "}
                    {new Date(task.created_at).toLocaleString("zh-CN")}
                  </div>
                </Link>

                {/* 操作按钮浮层 */}
                <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => handleStar(e, task.id)}
                    title={task.is_starred ? "取消收藏" : "加入收藏"}
                    className={`w-7 h-7 flex items-center justify-center rounded hover:bg-yellow-50 transition-colors text-base ${
                      task.is_starred ? "text-yellow-400" : "text-gray-300 hover:text-yellow-400"
                    }`}
                  >
                    ★
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, task.id)}
                    title="删除任务"
                    className="w-7 h-7 flex items-center justify-center rounded hover:bg-red-50 text-gray-300 hover:text-red-400 transition-colors text-base"
                  >
                    🗑
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
