import Link from "next/link";

const TOOLS = [
  {
    id: "literature",
    name: "文献检索",
    desc: "输入研究主题，自动检索多数据源学术文献，可按数量和年份筛选",
    time: "约30–60秒",
    href: "/tools/literature",
    icon: "📚",
  },
  {
    id: "outline",
    name: "提纲生成",
    desc: "输入主题和论文类型，生成符合该类型规范的章节结构",
    time: "约15–30秒",
    href: "/tools/outline",
    icon: "📋",
  },
  {
    id: "angle",
    name: "研究角度分析",
    desc: "输入主题，识别研究空白和切入角度，输出写作角度与学术贡献框架",
    time: "约20–40秒",
    href: "/tools/angle",
    icon: "🔍",
  },
  {
    id: "abstract",
    name: "摘要写作",
    desc: "输入核心论点、方法和发现，生成结构化学术摘要（200-250字）",
    time: "约10–20秒",
    href: "/tools/abstract",
    icon: "✍️",
  },
  {
    id: "synthesis",
    name: "文献综述段落",
    desc: "粘贴文献列表，自动生成主题综述叙述段落",
    time: "约20–40秒",
    href: "/tools/synthesis",
    icon: "📖",
  },
  {
    id: "guide",
    name: "选题引导",
    desc: "通过3轮对话帮你确定最合适的论文类型和研究方向",
    time: "约2分钟",
    href: "/tools/guide",
    icon: "🧭",
  },
];

export default function ToolsPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="mb-8">
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">
            ← 返回主页
          </Link>
        </div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">学术工具箱</h1>
        <p className="text-gray-500 mb-10">
          独立工具，无需创建任务，即开即用，结果可直接复制或下载
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {TOOLS.map((tool) => (
            <Link
              key={tool.id}
              href={tool.href}
              className="block bg-white rounded-xl border border-gray-200 p-6 hover:border-blue-400 hover:shadow-md transition-all"
            >
              <div className="text-3xl mb-3">{tool.icon}</div>
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                {tool.name}
              </h2>
              <p className="text-sm text-gray-500 mb-3">{tool.desc}</p>
              <span className="text-xs text-gray-400">{tool.time}</span>
            </Link>
          ))}
        </div>

        <p className="mt-12 text-center text-sm text-gray-400">
          需要生成完整论文？
          <Link href="/" className="text-blue-500 hover:underline ml-1">
            创建完整任务
          </Link>
        </p>
      </div>
    </div>
  );
}
