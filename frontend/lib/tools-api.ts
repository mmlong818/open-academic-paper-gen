const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export type SSEEvent =
  | { type: "status"; message: string }
  | { type: "result"; data: unknown }
  | { type: "error"; message: string }
  | { type: "done" };

export type SSEHandler = (event: SSEEvent) => void;

/**
 * POST to a tools SSE endpoint and call onEvent for each parsed event.
 * Returns a cleanup function that aborts the request.
 */
export function streamTool(
  endpoint: string,
  body: Record<string, unknown>,
  onEvent: SSEHandler
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/tools/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        onEvent({ type: "error", message: `请求失败 (${res.status})` });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6)) as SSEEvent;
              onEvent(event);
            } catch {
              // ignore malformed lines
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onEvent({ type: "error", message: "连接中断" });
      }
    }
  })();

  return () => controller.abort();
}

// ── Literature search ─────────────────────────────────────────

export interface LiteratureToolParams {
  topic: string;
  language: "zh" | "en";
  count: 20 | 40 | 80;
  year_from?: number;
}

export interface LiteratureResult {
  title: string;
  authors: string[];
  year: number | null;
  abstract: string;
  source: string;
  url: string | null;
  doi: string | null;
}

export function searchLiterature(
  params: LiteratureToolParams,
  onEvent: SSEHandler
): () => void {
  return streamTool("literature", params as unknown as Record<string, unknown>, onEvent);
}

// ── Outline generation ────────────────────────────────────────

export interface OutlineToolParams {
  topic: string;
  language: "zh" | "en";
  paper_type: string;
  target_words?: number;
}

export interface OutlineSection {
  title: string;
  summary?: string;
}

export function generateOutline(
  params: OutlineToolParams,
  onEvent: SSEHandler
): () => void {
  return streamTool("outline", params as unknown as Record<string, unknown>, onEvent);
}

// ── Angle analysis ────────────────────────────────────────────

export interface AngleToolParams {
  topic: string;
  language: "zh" | "en";
  synthesis?: string;
  research_questions?: string[];
}

export interface AngleResult {
  writing_angle: string;
  contribution: string;
  gap: string;
  hypotheses: string[];
  approach: string;
}

export function analyzeAngle(
  params: AngleToolParams,
  onEvent: SSEHandler
): () => void {
  return streamTool("angle", {
    topic: params.topic,
    language: params.language,
    synthesis: params.synthesis ?? "",
    research_questions: params.research_questions ?? [],
  }, onEvent);
}

// ── Abstract writing ──────────────────────────────────────────

export interface AbstractToolParams {
  topic: string;
  language: "zh" | "en";
  paper_type?: string;
  key_argument: string;
  method?: string;
  findings?: string;
}

export function writeAbstract(
  params: AbstractToolParams,
  onEvent: SSEHandler
): () => void {
  return streamTool("abstract", {
    topic: params.topic,
    language: params.language,
    paper_type: params.paper_type ?? "general",
    key_argument: params.key_argument,
    method: params.method ?? "",
    findings: params.findings ?? "",
  }, onEvent);
}

// ── Synthesis writing ─────────────────────────────────────────

export interface SynthesisToolParams {
  topic: string;
  language: "zh" | "en";
  literature_json: string;
}

export function writeSynthesis(
  params: SynthesisToolParams,
  onEvent: SSEHandler
): () => void {
  return streamTool("synthesis", {
    topic: params.topic,
    language: params.language,
    literature_json: params.literature_json,
  }, onEvent);
}

// ── Guide dialog ──────────────────────────────────────────────

export interface GuideMessage {
  role: "assistant" | "user";
  content: string;
}

export interface GuideResultData {
  message: string;
  step: number;
  done: boolean;
  recommended_type?: string;
}

export function guideStart(
  field: string,
  language: "zh" | "en",
  onEvent: SSEHandler
): () => void {
  return streamTool("guide/start", { field, language }, onEvent);
}

export function guideReply(
  params: {
    field: string;
    language: "zh" | "en";
    history: GuideMessage[];
    user_answer: string;
  },
  onEvent: SSEHandler
): () => void {
  return streamTool("guide/reply", params as Record<string, unknown>, onEvent);
}
