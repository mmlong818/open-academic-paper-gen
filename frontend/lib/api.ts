import type { SourceMix } from "./language";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export interface CitationIssue {
  title: string;
  doi: string | null;
  layer: string;
  reason: string;
  action: string;
  /** Pipeline stage the problem most likely came from: "writing", "retrieval", or both joined by "+". */
  stage?: string;
}

export interface UncitedClaim {
  section: string;
  sentence: string;
  reason: string;
}

export interface Revision {
  id: number;
  section: string;
  /** the paragraph as written, and the constrained rewrite of its flagged sentences */
  before: string;
  after: string;
  problems: Array<{ sentence: string; kind: "unsupported" | "uncited"; reason: string }>;
  /** proposed -> applied (full_auto) or accepted (user); rejected when a check failed */
  status: "proposed" | "applied" | "accepted" | "rejected";
  note: string;
  /** after re-verification in full_auto: did the flagged problems go away? */
  resolved: boolean | null;
}

// 写作风格检查（去 AI 味）：suggest = 建议修改，judge = 需人工判断；只给建议，不改写
// 写作角度的创新点诊断：四层新颖性、伪创新、文献池中最接近的工作
export interface NoveltyDiagnosis {
  levels: Record<string, { verdict: string; reason: string }>;
  pseudo: { pattern: string; reason: string }[];
  closest: { key: string; title: string; year: number | null; overlap: string }[];
  dropped_keys: number;
  objection: string;
}

// 证据表一行：空字符串表示原文未报告
export interface EvidenceRow {
  key: string;
  title: string;
  year: number | null;
  task: string;
  method: string;
  data: string;
  metric: string;
  finding: string;
  limitation: string;
}

export interface StyleFinding {
  section: string;
  rule: string;
  severity: "suggest" | "judge";
  detail: string;
}

export interface ReviewComment {
  section: string;
  /** verbatim text of the draft the comment is about */
  quote: string;
  issue: string;
  severity: "major" | "minor";
  suggestion: string;
  /** three-reviewer panel only: which reviewers raised it */
  reviewers?: string[];
}

/** Simulated peer review of the final draft: suggestions only, never applied to the text. */
export interface Review {
  comments: ReviewComment[];
  limitations: string[];
  dropped_unquoted: number;
  panel?: boolean;
}

export interface LiteratureItem {
  title: string;
  authors: string[];
  year: number | null;
  abstract: string;
  source: string;
  url: string | null;
  doi: string | null;
}

export interface OutlineSection {
  title: string;
  summary?: string;
}

export interface Task {
  id: string;
  topic: string;
  language: string;
  collab_mode: string;
  paper_type: string;
  source_mix?: SourceMix;
  status: string;
  phase: number;
  error_message: string | null;
  citation_issues: CitationIssue[] | null;
  /** Factual statements that carry no citation (T1.1); separate from citation_issues. */
  uncited_claims?: UncitedClaim[] | null;
  revisions?: Revision[] | null;
  review?: Review | null;
  style_findings?: StyleFinding[] | null;
  created_at: string;
  updated_at: string;
  is_starred: boolean;
  is_deleted: boolean;
  // 各阶段输出（仅详情接口返回）
  research_questions: string[] | null;
  keywords: string[] | null;
  literature: LiteratureItem[] | null;
  synthesis: string | null;
  evidence_table?: EvidenceRow[] | null;
  cleaning_report?: {
    total_before: number;
    total_after: number;
    removed_dup: number;
    excluded_by_llm?: number;
    chained_candidates?: number;
    chained_included?: number;
  } | null;
  angle: {
    writing_angle: string;
    contribution: string;
    gap: string;
    hypotheses: string[];
    approach: string;
  } | null;
  novelty?: NoveltyDiagnosis | null;
  outline: OutlineSection[] | null;
  sections: Record<string, string> | null;
  quality_results?: Array<{
    item: string;
    passed: boolean | null;
    note: string;
  }> | null;
  failed_sections?: string[] | null;
  verified_count?: number | null;
}

export type AngleData = NonNullable<Task["angle"]>;

// 参考文献格式：中文论文默认 GB/T 7714-2015，英文论文默认 APA 7
export type CitationStyle = "gbt7714" | "apa7" | "numeric";
export const CITATION_STYLE_LABELS: Record<CitationStyle, string> = {
  gbt7714: "GB/T 7714-2015",
  apa7: "APA 7",
  numeric: "简单编号",
};

export interface CreateTaskInput {
  topic: string;
  language: "zh" | "en";
  collab_mode: "full_auto" | "key_gates";
  paper_type?: "general" | "review" | "empirical" | "experimental" | "systematic" | "computational";
  source_mix?: SourceMix;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listTasks: (starred = false) =>
    request<Task[]>(`/api/tasks${starred ? "?starred=true" : ""}`),

  createTask: (input: CreateTaskInput) =>
    request<Task>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ ...input, paper_type: input.paper_type ?? "general" }),
    }),

  getTask: (id: string) => request<Task>(`/api/tasks/${id}`),

  startTask: (id: string) =>
    request<{ status: string }>(`/api/tasks/${id}/start`, { method: "POST" }),

  approveTask: (id: string) =>
    request<{ status: string }>(`/api/tasks/${id}/approve`, { method: "POST" }),

  starTask: (id: string) =>
    request<Task>(`/api/tasks/${id}/star`, { method: "POST" }),

  deleteTask: (id: string) =>
    request<void>(`/api/tasks/${id}`, { method: "DELETE" }),

  generateAngle: (id: string) =>
    request<Task>(`/api/tasks/${id}/angle`, { method: "POST" }),

  saveAngle: (id: string, angle: AngleData) =>
    request<Task>(`/api/tasks/${id}/angle`, {
      method: "PUT",
      body: JSON.stringify(angle),
    }),

  patchSnapshot: (id: string, data: Record<string, unknown>) =>
    request<Task>(`/api/tasks/${id}/snapshot`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  exportLatex: async (id: string, style?: CitationStyle): Promise<string> => {
    const res = await fetch(`${BASE_URL}/api/tasks/${id}/export/latex${style ? `?style=${style}` : ""}`);
    if (!res.ok) throw new Error(`${res.status}`);
    return res.text();
  },

  // 被引文献的 RIS / BibTeX，供 Zotero、EndNote 导入
  exportReferences: async (id: string, fmt: "ris" | "bibtex"): Promise<string> => {
    const res = await fetch(`${BASE_URL}/api/tasks/${id}/export/${fmt}`);
    if (!res.ok) throw new Error(`${res.status}`);
    return res.text();
  },

  exportEvidence: async (id: string, fmt: "csv" | "markdown"): Promise<string> => {
    const res = await fetch(`${BASE_URL}/api/tasks/${id}/export/evidence?fmt=${fmt}`);
    if (!res.ok) throw new Error(`${res.status}`);
    return res.text();
  },

  exportMarkdown: async (id: string, style?: CitationStyle): Promise<string> => {
    const res = await fetch(`${BASE_URL}/api/tasks/${id}/export/markdown${style ? `?style=${style}` : ""}`);
    if (!res.ok) throw new Error(`${res.status}`);
    return res.text();
  },

  redoPhase: (id: string, phase: number, sourceMix?: SourceMix) =>
    request<{ status: string }>(`/api/tasks/${id}/redo`, {
      method: "POST",
      body: JSON.stringify(sourceMix ? { phase, source_mix: sourceMix } : { phase }),
    }),

  retryTask: (id: string) =>
    request<{ status: string }>(`/api/tasks/${id}/retry`, { method: "POST" }),

  retrySection: (id: string, sectionTitle: string) =>
    request<Task>(`/api/tasks/${id}/retry-section`, {
      method: "POST",
      body: JSON.stringify({ section_title: sectionTitle }),
    }),
};

export const PHASE_LABELS: Record<number, string> = {
  1: "主题定界",
  2: "文献检索",
  3: "文献数据清洗",
  4: "研究趋势/空白",
  5: "写作角度",
  6: "大纲生成",
  7: "章节写作",
  8: "引文核验",
  9: "导出",
};

export const STATUS_LABELS: Record<string, string> = {
  pending: "待启动",
  running: "运行中",
  waiting: "等待审批",
  completed: "已完成",
  failed: "失败",
};

export const COLLAB_MODE_LABELS: Record<string, string> = {
  full_auto: "全自动",
  key_gates: "关键节点审批",
};
