"use client";

import { useState } from "react";
import { api, AngleData, Task } from "@/lib/api";

interface Props {
  task: Task;
  onTaskUpdate: (t: Task) => void;
}

const EMPTY_ANGLE: AngleData = {
  writing_angle: "",
  contribution: "",
  gap: "",
  hypotheses: [""],
  approach: "",
};

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-yellow-800 uppercase mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}

export default function AngleApprovalPanel({ task, onTaskUpdate }: Props) {
  const [draft, setDraft] = useState<AngleData>(
    () => (task.angle?.writing_angle ? task.angle : EMPTY_ANGLE)
  );
  const [regenerating, setRegenerating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [redoing, setRedoing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateField(key: keyof Omit<AngleData, "hypotheses">, value: string) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function updateHypothesis(index: number, value: string) {
    setDraft((d) => ({
      ...d,
      hypotheses: d.hypotheses.map((h, i) => (i === index ? value : h)),
    }));
  }

  function addHypothesis() {
    setDraft((d) => ({ ...d, hypotheses: [...d.hypotheses, ""] }));
  }

  function removeHypothesis(index: number) {
    setDraft((d) => ({
      ...d,
      hypotheses: d.hypotheses.filter((_, i) => i !== index),
    }));
  }

  async function handleRegenerate() {
    setRegenerating(true);
    setError(null);
    try {
      const updated = await api.generateAngle(task.id);
      onTaskUpdate(updated);
      setDraft(updated.angle?.writing_angle ? updated.angle : EMPTY_ANGLE);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "重新生成失败");
    } finally {
      setRegenerating(false);
    }
  }

  async function handleApproveWithAngle() {
    setApproving(true);
    setError(null);
    try {
      await api.saveAngle(task.id, draft);
      await api.approveTask(task.id);
      // 乐观更新为 running，审批面板立刻消失，WebSocket / 轮询负责后续真实状态刷新
      onTaskUpdate({ ...task, status: "running", angle: draft });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setApproving(false);
    }
  }

  async function handleRedo() {
    setRedoing(true);
    setError(null);
    try {
      await api.redoPhase(task.id, 5);
      onTaskUpdate({ ...task, status: "running" });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "重做失败");
    } finally {
      setRedoing(false);
    }
  }

  const busy = regenerating || approving || redoing;

  return (
    <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-yellow-800">等待审批 — 写作角度</h3>
          <p className="text-sm text-yellow-700 mt-0.5">
            确认或编辑写作角度后，点击「生成大纲」继续。
          </p>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={busy}
          className="text-xs px-3 py-1.5 border border-yellow-400 text-yellow-700 rounded-md hover:bg-yellow-100 disabled:opacity-50 shrink-0"
        >
          {regenerating ? "生成中…" : "↺ 重新生成"}
        </button>
      </div>

      <div className="space-y-3">
        <Field label="独特写作角度">
          <textarea
            rows={2}
            value={draft.writing_angle}
            onChange={(e) => updateField("writing_angle", e.target.value)}
            className="w-full border border-yellow-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-yellow-400 resize-none"
          />
        </Field>

        <Field label="研究空白">
          <textarea
            rows={2}
            value={draft.gap}
            onChange={(e) => updateField("gap", e.target.value)}
            className="w-full border border-yellow-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-yellow-400 resize-none"
          />
        </Field>

        <Field label="学术贡献">
          <textarea
            rows={2}
            value={draft.contribution}
            onChange={(e) => updateField("contribution", e.target.value)}
            className="w-full border border-yellow-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-yellow-400 resize-none"
          />
        </Field>

        <Field label="可验证假设">
          <div className="space-y-2">
            {draft.hypotheses.map((h, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input
                  type="text"
                  value={h}
                  onChange={(e) => updateHypothesis(i, e.target.value)}
                  placeholder={`假设 ${i + 1}`}
                  className="flex-1 border border-yellow-300 rounded-md px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-yellow-400"
                />
                <button
                  type="button"
                  onClick={() => removeHypothesis(i)}
                  disabled={draft.hypotheses.length <= 1}
                  className="w-6 h-6 flex items-center justify-center text-yellow-500 hover:text-red-400 disabled:opacity-30 text-lg leading-none"
                  title="删除"
                >
                  ×
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={addHypothesis}
              className="text-xs text-yellow-700 hover:text-yellow-900 underline"
            >
              + 添加假设
            </button>
          </div>
        </Field>

        <Field label="推荐研究方法">
          <textarea
            rows={2}
            value={draft.approach}
            onChange={(e) => updateField("approach", e.target.value)}
            className="w-full border border-yellow-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-yellow-400 resize-none"
          />
        </Field>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={handleApproveWithAngle}
          disabled={busy || !draft.writing_angle.trim()}
          className="flex-1 bg-yellow-500 hover:bg-yellow-600 text-white py-2.5 rounded-md text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {approving ? "提交中…" : "✓ 以此角度生成大纲"}
        </button>
        <button
          onClick={handleRedo}
          disabled={busy}
          className="px-4 py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-md text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {redoing ? "重做中…" : "↺ 重做此步"}
        </button>
      </div>
    </div>
  );
}
