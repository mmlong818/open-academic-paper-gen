export type WritingLanguage = "zh" | "en";
export type SourceMix = "zh_major" | "balanced" | "en_major";

export const SOURCE_MIX_LABELS: Record<SourceMix, string> = {
  zh_major: "中文为主",
  balanced: "中英均衡",
  en_major: "英文为主",
};

const CJK = /[一-鿿]/;

export function hasChinese(text: string): boolean {
  return CJK.test(text);
}

// 写作语言：主题写了中文就用中文，写了英文就用英文；还没写时看浏览器语言
export function inferLanguage(topic: string, browserLanguage: string | undefined): WritingLanguage {
  if (hasChinese(topic)) return "zh";
  if (topic.trim()) return "en";
  return (browserLanguage ?? "").toLowerCase().startsWith("zh") ? "zh" : "en";
}

// 中文论文通常要中外文献兼顾；英文论文以英文文献为主
export function defaultSourceMix(language: WritingLanguage): SourceMix {
  return language === "zh" ? "balanced" : "en_major";
}
