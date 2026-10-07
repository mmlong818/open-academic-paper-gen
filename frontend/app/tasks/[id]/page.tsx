"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, Task, LiteratureItem, Revision, OutlineSection, AngleData, PHASE_LABELS, STATUS_LABELS, COLLAB_MODE_LABELS, CITATION_STYLE_LABELS, CitationStyle } from "@/lib/api";
import AngleApprovalPanel from "./AngleApprovalPanel";
import LiteratureMix from "./LiteratureMix";
import EvidenceTable from "./EvidenceTable";
import NoveltyPanel from "./NoveltyPanel";
import { ClaimCoverageBadge, ClaimCoverageSummary } from "./ClaimCoverage";
import type { SourceMix } from "@/lib/language";

function downloadFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

interface ProgressMessage {
  phase: number;
  status: string;
  message: string;
  ts: number;
}

const WS_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080")
  .replace(/^http/, "ws");

const STYLE_RULE_LABELS: Record<string, string> = {
  colloquial: "口语化开头", jargon: "黑话", signpost: "套话反复出现", pivot: "翻案句偏多",
  significant: "「显著」无统计依据", conjunctions: "连接词过密", rhythm: "句长单调",
};

const STAGE_LABELS: Record<string, string> = { writing: "写作", retrieval: "检索" };
const REVIEWER_LABELS: Record<string, string> = { evidence: "证据审稿人", coverage: "覆盖审稿人", reasoning: "论证审稿人" };
const REVISION_STATUS: Record<string, string> = {
  proposed: "待采纳", applied: "已自动应用", accepted: "已采纳", rejected: "未通过检查",
};

type PanelState = "completed" | "running" | "pending";

const APPROVAL_HINTS: Record<number, Record<string, string>> = {
  1: { general: "确认研究问题和关键词准确覆盖选题范围后继续。" },
  2: { general: "确认检索结果文献量充足、来源多样后继续。", review: "综述通常需要60-100篇文献。", systematic: "系统综述需要100-200篇文献。" },
  3: { general: "确认清洗后核心文献均已保留，重复和无关条目已移除。" },
  4: { general: "确认趋势分析准确识别了研究空白，可作为写作角度的依据。" },
  5: { general: "确认写作角度明确、贡献创新后继续。" },
  6: { general: "确认提纲结构合理、层次清晰后继续。" },
  7: { general: "确认各章节内容完整、逻辑连贯后继续。" },
  8: { general: "确认引文核验结果无误后继续导出。" },
  9: { general: "确认导出文件格式正确后完成。" },
};

const PHASE_PALETTE: Record<number, { border: string; bg: string; badge: string; text: string }> = {
  1: { border: "border-violet-200",  bg: "bg-violet-50",  badge: "bg-violet-100 text-violet-700",  text: "text-violet-700"  },
  2: { border: "border-blue-200",    bg: "bg-blue-50",    badge: "bg-blue-100 text-blue-700",      text: "text-blue-700"    },
  3: { border: "border-red-200",      bg: "bg-red-50",     badge: "bg-red-100 text-red-700",        text: "text-red-700"     },
  4: { border: "border-teal-200",    bg: "bg-teal-50",    badge: "bg-teal-100 text-teal-700",      text: "text-teal-700"    },
  5: { border: "border-emerald-200", bg: "bg-emerald-50", badge: "bg-emerald-100 text-emerald-700",text: "text-emerald-700" },
  6: { border: "border-amber-200",   bg: "bg-amber-50",   badge: "bg-amber-100 text-amber-700",    text: "text-amber-700"   },
  7: { border: "border-orange-200",  bg: "bg-orange-50",  badge: "bg-orange-100 text-orange-700",  text: "text-orange-700"  },
  8: { border: "border-rose-200",    bg: "bg-rose-50",    badge: "bg-rose-100 text-rose-700",      text: "text-rose-700"    },
  9: { border: "border-purple-200",  bg: "bg-purple-50",  badge: "bg-purple-100 text-purple-700",  text: "text-purple-700"  },
};

function PhasePanel({
  phase,
  label,
  state,
  canEdit,
  onEdit,
  onRedoFrom,
  approvalNode,
  children,
}: {
  phase: number;
  label: string;
  state: PanelState;
  canEdit?: boolean;
  onEdit?: () => void;
  onRedoFrom?: () => void;
  approvalNode?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const [confirmRedo, setConfirmRedo] = useState(false);
  const palette = PHASE_PALETTE[phase] ?? { border: "border-gray-200", bg: "bg-gray-50", badge: "bg-gray-100 text-gray-700", text: "text-gray-700" };

  if (state === "pending") {
    return (
      <div id={`phase-${phase}`} className="border border-gray-100 rounded-lg overflow-hidden opacity-40">
        <div className="flex items-center gap-2 px-4 py-3 bg-gray-50 text-sm text-gray-400">
          <span className="w-5 h-5 rounded-full bg-gray-200 flex items-center justify-center text-xs">{phase}</span>
          {label}
        </div>
      </div>
    );
  }

  if (state === "running") {
    const hasContent = children != null;
    return (
      <div id={`phase-${phase}`} className={`border ${palette.border} rounded-lg overflow-hidden`}>
        <button
          onClick={() => hasContent && setOpen((v) => !v)}
          className={`w-full flex items-center gap-2 px-4 py-3 ${palette.bg} text-sm font-medium ${palette.text} ${hasContent ? "cursor-pointer" : "cursor-default"}`}
        >
          <span className={`w-5 h-5 rounded-full ${palette.badge} flex items-center justify-center text-xs font-bold`}>{phase}</span>
          {label}
          <svg className="ml-1 w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          <span className="text-xs font-normal ml-auto opacity-70">进行中…</span>
          {hasContent && <span className="text-gray-400 text-xs ml-1">{open ? "▲" : "▼"}</span>}
        </button>
        {hasContent && open && (
          <div className="bg-white px-4 py-4">{children}</div>
        )}
      </div>
    );
  }

  const isWaiting = !!approvalNode;

  return (
    <div id={`phase-${phase}`} className={`border rounded-lg overflow-hidden ${isWaiting ? "border-yellow-300" : palette.border}`}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-left transition-colors ${isWaiting ? "bg-yellow-50 hover:bg-yellow-100" : `${palette.bg} hover:brightness-95`}`}
      >
        <span className="flex items-center gap-2">
          <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${isWaiting ? "bg-yellow-200 text-yellow-800" : palette.badge}`}>{phase}</span>
          <span className={isWaiting ? "text-yellow-800" : palette.text}>{label}</span>
          {isWaiting && <span className="text-xs font-normal text-yellow-600 ml-1">等待审批</span>}
        </span>
        <span className="flex items-center gap-2">
          {canEdit && onEdit && open && (
            <span
              role="button"
              onClick={(e) => { e.stopPropagation(); onEdit(); }}
              className="text-xs text-blue-600 hover:underline px-1"
            >
              ✏ 编辑
            </span>
          )}
          {onRedoFrom && !isWaiting && (
            <span
              role="button"
              onClick={(e) => { e.stopPropagation(); setConfirmRedo(true); }}
              className="text-xs text-gray-500 hover:text-gray-700 hover:underline px-1"
            >
              ↺ 从此步重做
            </span>
          )}
          <span className="text-gray-400 text-xs">{open ? "▲ 收起" : "▼ 展开"}</span>
        </span>
      </button>
      {confirmRedo && onRedoFrom && (
        <div className="flex flex-wrap items-center gap-2 px-4 py-3 bg-red-50 border-t border-red-100 text-sm text-red-700">
          <span>将清空第 {phase} 阶段及之后的全部结果，并从这里重新执行。</span>
          <button onClick={() => { setConfirmRedo(false); onRedoFrom(); }}
            className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-xs font-medium">确认重做</button>
          <button onClick={() => setConfirmRedo(false)}
            className="text-red-600 hover:bg-red-100 px-3 py-1 rounded text-xs">取消</button>
        </div>
      )}
      {open && (
        <div className="bg-white">
          <div className="px-4 py-4">{children}</div>
          {approvalNode && (
            <div className="px-4 pb-4 pt-0">{approvalNode}</div>
          )}
        </div>
      )}
    </div>
  );
}

function InlineApprovalBar({
  phase,
  paperType,
  onApprove,
  approving,
  onRedo,
  redoing,
  pendingRevisions = 0,
}: {
  phase: number;
  paperType: string;
  onApprove: () => void;
  approving: boolean;
  onRedo: () => void;
  redoing: boolean;
  pendingRevisions?: number;
}) {
  const hint = APPROVAL_HINTS[phase]?.[paperType] ?? APPROVAL_HINTS[phase]?.general ?? "";
  const busy = approving || redoing;
  const [confirming, setConfirming] = useState(false);
  return (
    <div className="border-t border-yellow-200 pt-3">
      {hint && (
        <p className="text-xs text-yellow-700 bg-yellow-50 rounded-md px-3 py-2 mb-3 leading-relaxed">{hint}</p>
      )}
      {confirming && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-red-700 bg-red-50 rounded-md px-3 py-2 mb-3">
          <span>还有 {pendingRevisions} 条修订待采纳，直接继续会把原句带进导出稿。</span>
          <a href="#revisions" className="text-red-700 underline text-xs">查看修订</a>
          <button onClick={() => { setConfirming(false); onApprove(); }}
            className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-xs font-medium">仍然继续</button>
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => (pendingRevisions > 0 && !confirming ? setConfirming(true) : onApprove())}
          disabled={busy}
          className="bg-yellow-500 hover:bg-yellow-600 text-white px-5 py-2 rounded-md text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {approving ? "提交中…" : "✓ 批准，继续执行"}
        </button>
        <button
          onClick={onRedo}
          disabled={busy}
          className="bg-gray-100 hover:bg-gray-200 text-gray-600 px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {redoing ? "重做中…" : "↺ 重做此步"}
        </button>
      </div>
    </div>
  );
}

function EditBar({ onSave, onCancel, saving }: { onSave: () => void; onCancel: () => void; saving: boolean }) {
  return (
    <div className="flex gap-2 mt-3 pt-3 border-t border-gray-100">
      <button onClick={onSave} disabled={saving} className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
        {saving ? "保存中…" : "保存"}
      </button>
      <button onClick={onCancel} className="text-gray-500 px-4 py-1.5 rounded text-sm hover:bg-gray-100">取消</button>
    </div>
  );
}

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<"latex" | "markdown" | "ris" | "bibtex" | "evidence-csv" | "evidence-markdown" | null>(null);
  const [citationStyle, setCitationStyle] = useState<CitationStyle | null>(null);
  const [generatingAngle, setGeneratingAngle] = useState(false);
  const [approving, setApproving] = useState(false);
  const [redoing, setRedoing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<ProgressMessage[]>([]);
  const logBottomRef = useRef<HTMLDivElement>(null);

  const [editPhase, setEditPhase] = useState<number | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryingSection, setRetryingSection] = useState<string | null>(null);
  const [logExpanded, setLogExpanded] = useState(true);

  const loadTask = useCallback(async () => {
    try {
      const data = await api.getTask(id);
      setTask(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadTask();
    const timer = setInterval(async () => {
      const current = await api.getTask(id).catch(() => null);
      if (current) {
        setTask(current);
        if (current.status === "completed" || current.status === "failed") clearInterval(timer);
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [loadTask, id]);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/${id}`);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as { phase: number; status: string; message: string };
        setLog((prev) => [...prev, { ...msg, ts: Date.now() }]);
        api.getTask(id).then(setTask).catch(() => null);
      } catch { /* ignore */ }
    };
    ws.onerror = () => ws.close();
    return () => ws.close();
  }, [id]);


  // ── 编辑 ────────────────────────────────────────────────────────
  function isWaitingAt(phase: number) {
    return task?.status === "waiting" && task.phase === phase;
  }

  // 审批后不可编辑：仅在该阶段等待审批时才能编辑
  function canEdit(phase: number) {
    return isWaitingAt(phase) && editPhase !== phase;
  }

  function startEdit(phase: number) {
    if (!task) return;
    const d: Record<string, unknown> = {};
    if (phase === 1) { d.research_questions = [...(task.research_questions ?? [])]; d.keywords = [...(task.keywords ?? [])]; }
    if (phase === 2 || phase === 3) d.literature = JSON.parse(JSON.stringify(task.literature ?? []));
    if (phase === 4) d.synthesis = task.synthesis ?? "";
    if (phase === 6) d.outline = JSON.parse(JSON.stringify(task.outline ?? []));
    if (phase === 7) d.sections = { ...(task.sections ?? {}) };
    setDraft(d);
    setEditPhase(phase);
  }

  async function saveEdit() {
    if (!task || editPhase === null) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchSnapshot(task.id, draft);
      setTask(updated);
      setEditPhase(null);
      setDraft({});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  function cancelEdit() { setEditPhase(null); setDraft({}); }

  async function acceptRevision(rev: Revision) {
    if (!task?.sections || !task.revisions) return;
    const current = task.sections[rev.section] ?? "";
    if (!current.includes(rev.before)) {
      setError("该段落已被修改，无法自动采纳这条修订");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const sections = { ...task.sections, [rev.section]: current.replace(rev.before, rev.after) };
      const revisions = task.revisions.map(r => (r.id === rev.id ? { ...r, status: "accepted" as const } : r));
      setTask(await api.patchSnapshot(task.id, { sections, revisions }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "采纳失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleApprove() {
    if (!task) return;
    setApproving(true);
    setError(null);
    try {
      await api.approveTask(task.id);
      setTask({ ...task, status: "running" });
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "审批失败"); }
    finally { setApproving(false); }
  }

  async function handleRedo(phase: number, sourceMix?: SourceMix) {
    if (!task) return;
    setRedoing(true);
    setError(null);
    try {
      await api.redoPhase(task.id, phase, sourceMix);
      setTask({ ...task, status: "running", source_mix: sourceMix ?? task.source_mix });
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "重做失败"); }
    finally { setRedoing(false); }
  }

  async function handleGenerateAngle() {
    if (!task) return;
    setGeneratingAngle(true);
    setError(null);
    try { setTask(await api.generateAngle(task.id)); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "生成失败"); }
    finally { setGeneratingAngle(false); }
  }

  async function handleRetry() {
    if (!task) return;
    setRetrying(true);
    setError(null);
    try {
      await api.retryTask(task.id);
      setTask(await api.getTask(task.id));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "重试失败"); }
    finally { setRetrying(false); }
  }

  async function handleRetrySection(sectionTitle: string) {
    if (!task) return;
    setRetryingSection(sectionTitle);
    setError(null);
    try {
      setTask(await api.retrySection(task.id, sectionTitle));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "章节重试失败"); }
    finally { setRetryingSection(null); }
  }

  function styleFor(t: Task): CitationStyle {
    return citationStyle ?? (t.language === "zh" ? "gbt7714" : "apa7");
  }

  async function handleExportLatex() {
    if (!task) return;
    setExporting("latex");
    try { downloadFile(await api.exportLatex(task.id, styleFor(task)), `${task.topic}.tex`, "application/x-tex"); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "导出失败"); }
    finally { setExporting(null); }
  }

  async function handleExportReferences(fmt: "ris" | "bibtex") {
    if (!task) return;
    setExporting(fmt);
    try {
      const ext = fmt === "ris" ? "ris" : "bib";
      const mime = fmt === "ris" ? "application/x-research-info-systems" : "application/x-bibtex";
      downloadFile(await api.exportReferences(task.id, fmt), `${task.topic}.${ext}`, mime);
    }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "导出失败"); }
    finally { setExporting(null); }
  }

  async function handleExportEvidence(fmt: "csv" | "markdown") {
    if (!task) return;
    setExporting(`evidence-${fmt}`);
    try {
      const [ext, mime] = fmt === "csv" ? ["csv", "text/csv"] : ["md", "text/markdown"];
      downloadFile(await api.exportEvidence(task.id, fmt), `${task.topic}-证据表.${ext}`, mime);
    }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "导出失败"); }
    finally { setExporting(null); }
  }

  async function handleExportMarkdown() {
    if (!task) return;
    setExporting("markdown");
    try { downloadFile(await api.exportMarkdown(task.id, styleFor(task)), `${task.topic}.md`, "text/markdown"); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "导出失败"); }
    finally { setExporting(null); }
  }

  if (loading) return <p className="text-sm text-gray-500">加载中…</p>;
  if (!task) return <p className="text-sm text-red-600">{error ?? "任务不存在"}</p>;

  const phases = [1, 2, 3, 4, 5, 6, 7, 8, 9];
  const donePhase = task.status === "completed" ? 10 : task.phase;
  const t = task;

  function panelState(phase: number): PanelState {
    if (phase < donePhase) return "completed";
    if (phase === t.phase) {
      if (t.status === "waiting") return "completed";
      if (t.status === "running") return "running";
    }
    return "pending";
  }

  // 审批栏：仅当任务正在该阶段等待时显示（Phase 5 角度由 AngleApprovalPanel 接管）
  function approvalBar(phase: number): React.ReactNode | undefined {
    if (!isWaitingAt(phase) || phase === 5) return undefined;
    return (
      <InlineApprovalBar
        phase={phase}
        paperType={task.paper_type ?? "general"}
        onApprove={handleApprove}
        approving={approving}
        onRedo={() => handleRedo(phase)}
        redoing={redoing}
        pendingRevisions={phase === 8 ? (t.revisions ?? []).filter(r => r.status === "proposed").length : 0}
      />
    );
  }

  // 从已完成阶段重做：任务不在运行时可回到任意已完成阶段（等待中的阶段用审批栏里的"重做此步"）
  function redoFrom(phase: number): (() => void) | undefined {
    if (t.status === "running" || panelState(phase) !== "completed" || isWaitingAt(phase)) return undefined;
    return () => handleRedo(phase);
  }

  // ── 文献条目 ─────────────────────────────────────────────────────
  function LitItem({ lit, onRemove }: { lit: LiteratureItem; onRemove?: () => void }) {
    const [expanded, setExpanded] = useState(false);
    const openUrl = lit.url || (lit.doi ? `https://doi.org/${lit.doi}` : null);
    return (
      <div className="border border-gray-100 rounded p-2.5 group relative">
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800 leading-snug">
              {openUrl
                ? <a href={openUrl} target="_blank" rel="noreferrer" className="hover:text-blue-600 hover:underline">{lit.title}</a>
                : lit.title}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">
              {lit.authors?.slice(0, 3).join(", ")}{(lit.authors?.length ?? 0) > 3 ? " 等" : ""}
              {lit.year ? ` · ${lit.year}` : ""}
              {lit.source ? ` · ${lit.source}` : ""}
            </p>
            {lit.abstract && (
              <p className={`text-xs text-gray-600 mt-1 ${expanded ? "" : "line-clamp-2"}`}>{lit.abstract}</p>
            )}
            <div className="flex items-center gap-3 mt-1">
              {lit.abstract && (
                <button onClick={() => setExpanded(v => !v)} className="text-xs text-gray-400 hover:text-gray-600">
                  {expanded ? "收起摘要" : "展开摘要"}
                </button>
              )}
              {openUrl && <a href={openUrl} target="_blank" rel="noreferrer" className="text-xs text-blue-500 hover:underline">阅读原文 ↗</a>}
              {lit.doi && <span className="text-xs text-gray-400">DOI: {lit.doi}</span>}
            </div>
          </div>
          {onRemove && (
            <button onClick={onRemove} title="移除此文献"
              className="shrink-0 w-6 h-6 flex items-center justify-center rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors text-base opacity-0 group-hover:opacity-100">
              ×
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <button onClick={() => router.push("/")} className="text-sm text-blue-600 hover:underline">← 返回列表</button>

      {/* 任务信息卡 */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-semibold">{task.topic}</h2>
            <p className="text-sm text-gray-500 mt-1">
              {task.language === "zh" ? "中文" : "English"} · {COLLAB_MODE_LABELS[task.collab_mode] ?? task.collab_mode}
            </p>
          </div>
          <span className={`text-sm px-3 py-1 rounded-full ${
            task.status === "completed" ? "bg-green-100 text-green-700" :
            task.status === "failed" ? "bg-red-100 text-red-700" :
            task.status === "waiting" ? "bg-yellow-100 text-yellow-700" :
            "bg-blue-100 text-blue-700"
          }`}>
            {STATUS_LABELS[task.status] ?? task.status}
          </span>
        </div>
        <div className="mt-6">
          <div className="flex items-center gap-1">
            {phases.map((p) => (
              <div key={p} className="flex-1 flex flex-col items-center gap-1">
                <div className={`h-2 w-full rounded-full transition-all ${
                  p < donePhase ? "bg-green-400" :
                  p === task.phase ? task.status === "waiting" ? "bg-yellow-400" : "bg-blue-500" :
                  "bg-gray-200"
                }`} />
                <span className="text-gray-500 hidden sm:block" style={{ fontSize: "9px" }}>{PHASE_LABELS[p]}</span>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-600 mt-2">当前阶段：<strong>{PHASE_LABELS[task.phase] ?? task.phase}</strong></p>
        </div>
      </div>

      {/* 快速导航：紧贴内容区右侧（max-w-4xl = 56rem，px-6 = 1.5rem） */}
      <div
        className="fixed top-1/2 -translate-y-1/2 z-50 flex flex-col gap-1"
        style={{ right: "max(6px, calc(50vw - 28rem - 2.5rem))" }}
      >
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="w-8 h-8 flex items-center justify-center bg-white border border-gray-200 rounded shadow-sm text-gray-500 hover:text-gray-800 hover:border-gray-400 transition-colors text-xs"
          title="回到顶部"
        >
          ▲
        </button>
        <button
          onClick={() => {
            if (!task) return;
            document.getElementById(`phase-${task.phase}`)?.scrollIntoView({ behavior: "smooth", block: "end" });
          }}
          className="w-8 h-8 flex items-center justify-center bg-white border border-gray-200 rounded shadow-sm text-gray-500 hover:text-gray-800 hover:border-gray-400 transition-colors text-xs"
          title="跳到当前执行阶段"
        >
          ▼
        </button>
      </div>

      {/* 悬浮日志面板：固定在右下角 */}
      <div className="fixed bottom-4 right-4 z-50">
        {/* 日志面板（始终显示） */}
        <div className="w-80 bg-gray-900 rounded-lg shadow-xl overflow-hidden">
          <button
            onClick={() => setLogExpanded(v => !v)}
            className="w-full flex items-center justify-between px-3 py-1.5 text-xs text-gray-400 hover:bg-gray-800 transition-colors"
          >
            <span className="font-mono">执行日志 {log.length > 0 ? `(${log.length})` : ""}</span>
            <span>{logExpanded ? "▼" : "▲"}</span>
          </button>
          {logExpanded && (
            <div className="overflow-y-auto p-3 font-mono text-xs space-y-0.5" style={{ maxHeight: "calc(15 * (0.75rem * 1.5 + 0.125rem) + 1.5rem)" }}>
              {log.length === 0 ? (
                <p className="text-gray-600">暂无日志</p>
              ) : (
                log.map((entry, i) => (
                  <div key={i} className={entry.status === "failed" ? "text-red-400" : entry.status === "completed" || entry.status === "approved" ? "text-green-400" : "text-gray-300"}>
                    <span className="text-gray-500 mr-2">[{new Date(entry.ts).toLocaleTimeString("zh-CN")}]</span>
                    <span className="text-blue-400 mr-2">{PHASE_LABELS[entry.phase] ?? `P${entry.phase}`}</span>
                    {entry.message}
                  </div>
                ))
              )}
              <div ref={logBottomRef} />
            </div>
          )}
        </div>
      </div>

      {/* 全局操作错误（审批/重做等） */}
      {error && task.status !== "completed" && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* 失败原因 */}
      {task.status === "failed" && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-sm font-medium text-red-700 mb-1">任务失败</h3>
              {task.error_message && <p className="text-sm text-red-600">{task.error_message}</p>}
            </div>
            <button
              onClick={handleRetry}
              disabled={retrying}
              className="shrink-0 bg-red-600 hover:bg-red-700 text-white px-4 py-1.5 rounded-md text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {retrying ? "重试中…" : "↺ 重试"}
            </button>
          </div>
        </div>
      )}

      {/* ===== 各阶段输出 ===== */}
      <div className="space-y-3">

        {/* Phase 1: 主题定界 */}
        <PhasePanel phase={1} label="主题定界" state={panelState(1)} onRedoFrom={redoFrom(1)}
          canEdit={canEdit(1)} onEdit={() => startEdit(1)} approvalNode={approvalBar(1)}>
          {editPhase === 1 ? (
            <div className="space-y-4">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-2">研究问题</p>
                {(draft.research_questions as string[]).map((q, i) => (
                  <div key={i} className="flex gap-2 mb-1.5">
                    <input value={q} onChange={e => setDraft(d => ({ ...d, research_questions: (d.research_questions as string[]).map((v, j) => j === i ? e.target.value : v) }))}
                      className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
                    <button onClick={() => setDraft(d => ({ ...d, research_questions: (d.research_questions as string[]).filter((_, j) => j !== i) }))} className="text-red-400 hover:text-red-600 px-1">×</button>
                  </div>
                ))}
                <button onClick={() => setDraft(d => ({ ...d, research_questions: [...(d.research_questions as string[]), ""] }))} className="text-xs text-blue-600 hover:underline">+ 添加研究问题</button>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-2">关键词</p>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {(draft.keywords as string[]).map((kw, i) => (
                    <span key={i} className="flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">
                      <input value={kw} onChange={e => setDraft(d => ({ ...d, keywords: (d.keywords as string[]).map((v, j) => j === i ? e.target.value : v) }))}
                        className="bg-transparent border-none outline-none w-20 text-xs" />
                      <button onClick={() => setDraft(d => ({ ...d, keywords: (d.keywords as string[]).filter((_, j) => j !== i) }))} className="text-blue-400 hover:text-red-500">×</button>
                    </span>
                  ))}
                </div>
                <button onClick={() => setDraft(d => ({ ...d, keywords: [...(d.keywords as string[]), ""] }))} className="text-xs text-blue-600 hover:underline">+ 添加关键词</button>
              </div>
              <EditBar onSave={saveEdit} onCancel={cancelEdit} saving={saving} />
            </div>
          ) : (
            <>
              {task.research_questions && task.research_questions.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">研究问题</p>
                  <ol className="space-y-1 list-decimal list-inside">
                    {task.research_questions.map((q, i) => <li key={i} className="text-sm text-gray-700">{q}</li>)}
                  </ol>
                </div>
              )}
              {task.keywords && task.keywords.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">关键词</p>
                  <div className="flex flex-wrap gap-1.5">
                    {task.keywords.map((kw, i) => <span key={i} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">{kw}</span>)}
                  </div>
                </div>
              )}
            </>
          )}
        </PhasePanel>

        {/* Phase 2: 文献检索 */}
        <PhasePanel phase={2} label="文献检索" state={panelState(2)} onRedoFrom={redoFrom(2)}
          canEdit={canEdit(2)} onEdit={() => startEdit(2)} approvalNode={approvalBar(2)}>
          {editPhase === 2 ? (
            <div>
              <p className="text-xs text-gray-500 mb-2">共 {(draft.literature as LiteratureItem[]).length} 篇（悬停显示移除按钮）</p>
              <div className="space-y-2">
                {(draft.literature as LiteratureItem[]).map((lit, i) => (
                  <LitItem key={i} lit={lit} onRemove={() => setDraft(d => ({ ...d, literature: (d.literature as LiteratureItem[]).filter((_, j) => j !== i) }))} />
                ))}
              </div>
              <EditBar onSave={saveEdit} onCancel={cancelEdit} saving={saving} />
            </div>
          ) : (
            task.literature && task.literature.length > 0
              ? <div className="space-y-2">
                  {isWaitingAt(2) && (
                    <LiteratureMix literature={task.literature} sourceMix={task.source_mix ?? "balanced"}
                      onResearch={(mix) => handleRedo(2, mix)} busy={redoing} />
                  )}
                  <p className="text-xs text-gray-500 mb-2">共检索到 {task.literature.length} 篇文献</p>
                  {task.literature.map((lit, i) => <LitItem key={i} lit={lit} />)}
                </div>
              : <p className="text-sm text-gray-400">暂无文献数据</p>
          )}
        </PhasePanel>

        {/* Phase 3: 文献数据清洗 */}
        <PhasePanel phase={3} label="文献数据清洗" state={panelState(3)} onRedoFrom={redoFrom(3)}
          canEdit={canEdit(3)} onEdit={() => startEdit(3)} approvalNode={approvalBar(3)}>
          {editPhase === 3 ? (
            <div>
              <p className="text-xs text-gray-500 mb-2">保留 {(draft.literature as LiteratureItem[]).length} 篇（悬停显示移除按钮）</p>
              <div className="space-y-2">
                {(draft.literature as LiteratureItem[]).map((lit, i) => (
                  <LitItem key={i} lit={lit} onRemove={() => setDraft(d => ({ ...d, literature: (d.literature as LiteratureItem[]).filter((_, j) => j !== i) }))} />
                ))}
              </div>
              <EditBar onSave={saveEdit} onCancel={cancelEdit} saving={saving} />
            </div>
          ) : (
            <div>
              {task.cleaning_report && (
                <div className="flex flex-wrap gap-4 text-xs mb-3 p-3 bg-gray-50 rounded-lg">
                  <span className="text-gray-600">原始：<strong>{task.cleaning_report.total_before}</strong> 篇</span>
                  <span className="text-red-500">去重移除：<strong>{task.cleaning_report.removed_dup}</strong> 篇</span>
                  <span className="text-orange-500">相关性筛选排除：<strong>{task.cleaning_report.excluded_by_llm ?? 0}</strong> 篇</span>
                  {(task.cleaning_report.chained_candidates ?? 0) > 0 && (
                    <span className="text-blue-600">引用链补充：<strong>{task.cleaning_report.chained_included ?? 0}</strong> / {task.cleaning_report.chained_candidates} 篇</span>
                  )}
                  <span className="text-green-600">保留：<strong>{task.cleaning_report.total_after}</strong> 篇</span>
                </div>
              )}
              {task.cleaning_report && task.literature && task.literature.length > 0 && (
                <LiteratureMix literature={task.literature} sourceMix={task.source_mix ?? "balanced"} warnShortfall />
              )}
              {task.literature && task.literature.length > 0
                ? <div className="space-y-2">{task.literature.map((lit, i) => <LitItem key={i} lit={lit} />)}</div>
                : <p className="text-sm text-gray-400">暂无清洗后文献</p>}
            </div>
          )}
        </PhasePanel>

        {/* Phase 4: 研究趋势/空白发现 */}
        <PhasePanel phase={4} label="研究趋势/空白发现" state={panelState(4)} onRedoFrom={redoFrom(4)}
          canEdit={canEdit(4)} onEdit={() => startEdit(4)} approvalNode={approvalBar(4)}>
          {editPhase === 4 ? (
            <div>
              <textarea value={draft.synthesis as string}
                onChange={e => setDraft(d => ({ ...d, synthesis: e.target.value }))}
                rows={12}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
              <EditBar onSave={saveEdit} onCancel={cancelEdit} saving={saving} />
            </div>
          ) : (
            task.synthesis
              ? <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{task.synthesis}</div>
              : <p className="text-sm text-gray-400">暂无分析内容</p>
          )}
          {editPhase !== 4 && task.evidence_table && task.evidence_table.length > 0 && (
            <EvidenceTable rows={task.evidence_table} poolSize={task.literature?.length ?? 0}
              onExport={handleExportEvidence} exporting={exporting !== null} />
          )}
        </PhasePanel>

        {/* Phase 5: 写作角度（等待时用 AngleApprovalPanel，已完成显示结果） */}
        <PhasePanel phase={5} label="写作角度" state={panelState(5)} onRedoFrom={redoFrom(5)}
          approvalNode={isWaitingAt(5) ? <AngleApprovalPanel task={t} onTaskUpdate={setTask} /> : undefined}>
          {task.angle && task.angle.writing_angle ? (
            <div className="space-y-3">
              <div>
                <p className="text-xs font-semibold text-indigo-600 uppercase mb-1">独特写作角度</p>
                <p className="text-sm text-gray-800">{task.angle.writing_angle}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-indigo-600 uppercase mb-1">研究空白</p>
                <p className="text-sm text-gray-700">{task.angle.gap}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-indigo-600 uppercase mb-1">学术贡献</p>
                <p className="text-sm text-gray-700">{task.angle.contribution}</p>
              </div>
              {task.angle.hypotheses && task.angle.hypotheses.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-indigo-600 uppercase mb-1">可验证假设</p>
                  <ol className="space-y-1 list-decimal list-inside">
                    {task.angle.hypotheses.map((h, i) => <li key={i} className="text-sm text-gray-700">{h}</li>)}
                  </ol>
                </div>
              )}
              <div>
                <p className="text-xs font-semibold text-indigo-600 uppercase mb-1">推荐研究方法</p>
                <p className="text-sm text-gray-700">{task.angle.approach}</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400">暂无写作角度数据</p>
          )}
          {task.novelty && <NoveltyPanel novelty={task.novelty} />}
        </PhasePanel>

        {/* Phase 6: 大纲生成 */}
        <PhasePanel phase={6} label="大纲生成" state={panelState(6)} onRedoFrom={redoFrom(6)}
          canEdit={canEdit(6)} onEdit={() => startEdit(6)} approvalNode={approvalBar(6)}>
          {editPhase === 6 ? (
            <div className="space-y-2">
              {(draft.outline as OutlineSection[]).map((sec, i) => (
                <div key={i} className="flex gap-2 items-start border border-gray-100 rounded p-2">
                  <span className="text-xs font-bold text-gray-400 mt-1 w-4 shrink-0">{i + 1}.</span>
                  <div className="flex-1 space-y-1">
                    <input value={sec.title} onChange={e => setDraft(d => ({ ...d, outline: (d.outline as OutlineSection[]).map((s, j) => j === i ? { ...s, title: e.target.value } : s) }))}
                      placeholder="章节标题"
                      className="w-full border border-gray-200 rounded px-2 py-1 text-sm font-medium focus:outline-none focus:ring-1 focus:ring-blue-400" />
                    <input value={sec.summary ?? ""} onChange={e => setDraft(d => ({ ...d, outline: (d.outline as OutlineSection[]).map((s, j) => j === i ? { ...s, summary: e.target.value } : s) }))}
                      placeholder="章节摘要（可选）"
                      className="w-full border border-gray-200 rounded px-2 py-1 text-xs text-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-400" />
                  </div>
                  <button onClick={() => setDraft(d => ({ ...d, outline: (d.outline as OutlineSection[]).filter((_, j) => j !== i) }))} className="text-red-400 hover:text-red-600 px-1 mt-1">×</button>
                </div>
              ))}
              <button onClick={() => setDraft(d => ({ ...d, outline: [...(d.outline as OutlineSection[]), { title: "", summary: "" }] }))}
                className="text-xs text-blue-600 hover:underline">+ 添加章节</button>
              <EditBar onSave={saveEdit} onCancel={cancelEdit} saving={saving} />
            </div>
          ) : (
            task.outline && task.outline.length > 0
              ? <ol className="space-y-2">
                  {task.outline.map((sec, i) => (
                    <li key={i} className="flex gap-3">
                      <span className="text-xs font-bold text-gray-400 mt-0.5 w-4 shrink-0">{i + 1}.</span>
                      <div>
                        <p className="text-sm font-medium text-gray-800">{sec.title}</p>
                        {sec.summary && <p className="text-xs text-gray-500 mt-0.5">{sec.summary}</p>}
                      </div>
                    </li>
                  ))}
                </ol>
              : <p className="text-sm text-gray-400">暂无大纲数据</p>
          )}
        </PhasePanel>

        {/* Phase 7: 章节写作 */}
        {panelState(7) === "running" && task.sections && Object.keys(task.sections).length > 0 ? (
          <div id="phase-7" className="border border-blue-200 rounded-lg overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 bg-blue-50 text-sm font-medium text-blue-700">
              <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold">7</span>
              章节写作
              <svg className="ml-1 w-3.5 h-3.5 animate-spin text-blue-500" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              <span className="text-xs font-normal text-blue-500 ml-auto">已完成 {Object.keys(task.sections).length} / {task.outline?.length ?? "?"} 节</span>
            </div>
            <div className="px-4 py-4 bg-white space-y-4">
              {Object.entries(task.sections).map(([title, content]) => {
                const isFailed = content.startsWith("__SECTION_FAILED__");
                return (
                  <div key={title}>
                    <h4 className={`text-sm font-semibold mb-1 ${isFailed ? "text-red-600" : "text-gray-800"}`}>
                      {isFailed && "⚠ "}{title}
                    </h4>
                    {!isFailed && <div className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed border-l-2 border-gray-100 pl-3">{content}</div>}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <PhasePanel phase={7} label="章节写作" state={panelState(7)} onRedoFrom={redoFrom(7)}
            canEdit={canEdit(7)} onEdit={() => startEdit(7)} approvalNode={approvalBar(7)}>
            {editPhase === 7 ? (
              <div className="space-y-4">
                {Object.entries(draft.sections as Record<string, string>).map(([title, content]) => (
                  <div key={title}>
                    <h4 className="text-sm font-semibold text-gray-800 mb-1">{title}</h4>
                    <textarea value={content}
                      onChange={e => setDraft(d => ({ ...d, sections: { ...(d.sections as Record<string, string>), [title]: e.target.value } }))}
                      rows={8}
                      className="w-full border border-gray-200 rounded px-3 py-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
                  </div>
                ))}
                <EditBar onSave={saveEdit} onCancel={cancelEdit} saving={saving} />
              </div>
            ) : (
              task.sections && Object.keys(task.sections).length > 0
                ? <div className="space-y-4">
                    {Object.entries(task.sections).map(([title, content]) => {
                      const isFailed = content.startsWith("__SECTION_FAILED__");
                      return (
                        <div key={title} className={isFailed ? "border border-red-200 rounded-lg p-3 bg-red-50" : ""}>
                          <div className="flex items-center justify-between mb-1">
                            <h4 className={`text-sm font-semibold ${isFailed ? "text-red-700" : "text-gray-800"}`}>
                              {isFailed && <span className="mr-1">⚠</span>}{title}
                            </h4>
                            {isFailed && (
                              <button
                                onClick={() => handleRetrySection(title)}
                                disabled={retryingSection === title}
                                className="text-xs px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white rounded-md disabled:opacity-50 transition-colors"
                              >
                                {retryingSection === title ? "重试中…" : "↺ 重试此章节"}
                              </button>
                            )}
                          </div>
                          {isFailed
                            ? <p className="text-xs text-red-500">此章节生成失败，请点击重试按钮重新生成。</p>
                            : <div className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed border-l-2 border-gray-100 pl-3">{content}</div>
                          }
                        </div>
                      );
                    })}
                  </div>
                : <p className="text-sm text-gray-400">暂无章节内容</p>
            )}
          </PhasePanel>
        )}

        {/* Phase 8: 引文核验 */}
        <PhasePanel phase={8} label="引文核验" state={panelState(8)} onRedoFrom={redoFrom(8)} approvalNode={approvalBar(8)}>
          {task.citation_issues && task.citation_issues.length > 0 ? (
            <div>
              <p className="text-xs text-gray-500 mb-1">
                正文实际引用 <strong>{task.citation_issues.length}</strong> 条；
                文献库可用于导出 <strong>{task.verified_count ?? 0}</strong> 篇
              </p>
              <div className="flex gap-4 mb-3 text-xs">
                <span className="text-green-600 font-medium">✓ 通过核验 {task.citation_issues.filter(i => i.action === "kept").length}</span>
                <span className="text-yellow-600 font-medium">⚠ 警告 {task.citation_issues.filter(i => i.action === "warned").length}</span>
                <span className="text-red-500 font-medium">✗ 移除 {task.citation_issues.filter(i => i.action === "removed").length}</span>
                <span className="text-gray-500 font-medium">? 未核验 {task.citation_issues.filter(i => i.action === "unverified").length}</span>
              </div>
              <ClaimCoverageSummary issues={task.citation_issues} />
              <ul className="space-y-1.5">
                {task.citation_issues.map((issue, i) => (
                  <li key={i} className="text-sm text-yellow-700 flex gap-2">
                    <span className="text-xs font-medium bg-yellow-100 px-1.5 py-0.5 rounded shrink-0">{issue.action}</span>
                    {issue.stage && (
                      <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded shrink-0">
                        来源：{issue.stage.split("+").map(s => STAGE_LABELS[s] ?? s).join(" + ")}
                      </span>
                    )}
                    <ClaimCoverageBadge issue={issue} />
                    <span>{issue.title} — {issue.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : task.quality_results != null ? (
            task.quality_results.length > 0
              ? <div className="space-y-2">
                  {task.quality_results.map((r, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <span className={`mt-0.5 ${r.passed === true ? "text-green-500" : r.passed === false ? "text-red-500" : "text-yellow-500"}`}>
                        {r.passed === true ? "✓" : r.passed === false ? "✗" : "?"}
                      </span>
                      <div>
                        <p className="text-sm font-medium text-gray-700">{r.item}</p>
                        <p className="text-xs text-gray-400">{r.note}</p>
                      </div>
                    </div>
                  ))}
                </div>
              : <p className="text-sm text-green-600">引文核验通过，无问题</p>
          ) : (
            <p className="text-sm text-gray-400">核验尚未开始</p>
          )}
          {task.revisions && task.revisions.length > 0 && (
            <div id="revisions" className="mt-4">
              <p className="text-xs text-gray-500 mb-1">
                修订 <strong>{task.revisions.length}</strong> 条：
                已应用 {task.revisions.filter(r => r.status === "applied" || r.status === "accepted").length}，
                待采纳 {task.revisions.filter(r => r.status === "proposed").length}，
                未通过检查 {task.revisions.filter(r => r.status === "rejected").length}
              </p>
              <ul className="space-y-3">
                {task.revisions.map(rev => (
                  <li key={rev.id} className="text-sm border rounded p-2">
                    <div className="flex gap-2 items-center mb-1">
                      <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">{rev.section}</span>
                      <span className="text-xs font-medium">{REVISION_STATUS[rev.status] ?? rev.status}</span>
                      {rev.resolved === false && <span className="text-xs text-red-500">复核仍有问题</span>}
                      {rev.status === "proposed" && isWaitingAt(8) && (
                        <button
                          onClick={() => acceptRevision(rev)}
                          disabled={saving}
                          className="ml-auto text-xs px-2 py-0.5 rounded bg-green-600 text-white disabled:opacity-50"
                        >
                          采纳
                        </button>
                      )}
                    </div>
                    <ul className="text-xs text-yellow-700 mb-1">
                      {rev.problems.map((p, i) => <li key={i}>⚠ {p.reason}</li>)}
                    </ul>
                    {rev.status === "rejected" ? (
                      <p className="text-xs text-gray-400">{rev.note}</p>
                    ) : (
                      <>
                        <p className="text-xs text-gray-400 line-through whitespace-pre-wrap">{rev.before}</p>
                        <p className="text-xs text-green-700 whitespace-pre-wrap">{rev.after}</p>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {task.review && (task.review.comments.length > 0 || task.review.limitations.length > 0) && (
            <div className="mt-4">
              <p className="text-xs text-gray-500 mb-1">
                模拟审稿意见 <strong>{task.review.comments.length}</strong> 条（仅供参考，不会自动修改正文）
                {task.review.panel && "；三位审稿人互盲，多人提出的意见排在前面"}
              </p>
              <ul className="space-y-2">
                {task.review.comments.map((c, i) => (
                  <li key={i} className="text-sm border rounded p-2">
                    <div className="flex gap-2 items-center mb-1">
                      <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">{c.section}</span>
                      <span className={`text-xs font-medium ${c.severity === "major" ? "text-red-600" : "text-yellow-600"}`}>
                        {c.severity === "major" ? "重要" : "次要"}
                      </span>
                      {c.reviewers && (
                        <span className="text-xs text-gray-400">{c.reviewers.map(r => REVIEWER_LABELS[r] ?? r).join("、")}</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 italic mb-1">“{c.quote}”</p>
                    <p className="text-xs text-gray-800">{c.issue}</p>
                    {c.suggestion && <p className="text-xs text-green-700 mt-0.5">建议：{c.suggestion}</p>}
                  </li>
                ))}
              </ul>
              {task.review.limitations.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-gray-500 mb-1">建议补充的局限</p>
                  <ul className="list-disc pl-5 space-y-0.5">
                    {task.review.limitations.map((l, i) => <li key={i} className="text-xs text-gray-700">{l}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
          {task.style_findings && task.style_findings.length > 0 && (
            <div className="mt-4">
              <p className="text-xs text-gray-500 mb-1">
                写作风格提示 <strong>{task.style_findings.length}</strong> 条（机器腔检查，仅供参考，不会自动修改正文）
              </p>
              <ul className="space-y-1">
                {task.style_findings.map((f, i) => (
                  <li key={i} className="text-xs flex gap-2 items-start">
                    <span className={`shrink-0 px-1.5 py-0.5 rounded ${f.severity === "suggest" ? "bg-amber-100 text-amber-800" : "bg-gray-100 text-gray-600"}`}>
                      {f.severity === "suggest" ? "建议修改" : "需人工判断"}
                    </span>
                    <span className="text-gray-500 shrink-0">{f.section}</span>
                    <span className="text-gray-800">{STYLE_RULE_LABELS[f.rule] ?? f.rule}：{f.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {task.uncited_claims && task.uncited_claims.length > 0 && (
            <div className="mt-4">
              <p className="text-xs text-gray-500 mb-1">
                ⚠ 可能需要引用却未引用的陈述 <strong>{task.uncited_claims.length}</strong> 条
              </p>
              <ul className="space-y-1.5">
                {task.uncited_claims.map((claim, i) => (
                  <li key={i} className="text-sm text-yellow-700 flex gap-2">
                    <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded shrink-0">{claim.section}</span>
                    <span>{claim.sentence} — {claim.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </PhasePanel>

        {/* Phase 9: 导出 */}
        <PhasePanel phase={9} label="导出" state={panelState(9)} onRedoFrom={redoFrom(9)} approvalNode={approvalBar(9)}>
          <p className="text-sm text-gray-600">论文已生成完毕，可在下方下载 LaTeX 或 Markdown 格式。</p>
        </PhasePanel>
      </div>

      {/* 导出 */}
      {task.status === "completed" && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h3 className="font-medium mb-3">下载论文</h3>
          {error && <p className="text-sm text-red-600 mb-2">{error}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="citation-style" className="text-sm text-gray-600">参考文献格式</label>
            <select
              id="citation-style"
              value={styleFor(task)}
              onChange={(e) => setCitationStyle(e.target.value as CitationStyle)}
              className="border border-gray-300 rounded-md px-2 py-2 text-sm"
            >
              {(Object.keys(CITATION_STYLE_LABELS) as CitationStyle[]).map((s) => (
                <option key={s} value={s}>{CITATION_STYLE_LABELS[s]}</option>
              ))}
            </select>
            <button onClick={handleExportLatex} disabled={exporting !== null}
              className="bg-gray-800 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-900 disabled:opacity-50">
              {exporting === "latex" ? "导出中…" : "下载 LaTeX (.tex)"}
            </button>
            <button onClick={handleExportMarkdown} disabled={exporting !== null}
              className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
              {exporting === "markdown" ? "导出中…" : "下载 Markdown (.md)"}
            </button>
            <button onClick={() => handleExportReferences("bibtex")} disabled={exporting !== null}
              className="border border-gray-300 text-gray-700 px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-50 disabled:opacity-50">
              {exporting === "bibtex" ? "导出中…" : "BibTeX (.bib)"}
            </button>
            <button onClick={() => handleExportReferences("ris")} disabled={exporting !== null}
              title="导入 Zotero、EndNote 等文献管理软件"
              className="border border-gray-300 text-gray-700 px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-50 disabled:opacity-50">
              {exporting === "ris" ? "导出中…" : "RIS (.ris)"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
