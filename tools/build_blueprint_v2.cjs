const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  Document,
  LevelFormat,
  Packer,
  Paragraph,
  TextRun,
} = require("docx");

const OUTPUT = path.resolve(
  process.cwd(),
  "docs",
  "product",
  "02_论文科研数据异常筛查Agent建设蓝图_V2.3.docx",
);

const FONT_CN = "宋体";
const FONT_EN = "Calibri";
const BLACK = "000000";

function text(value, options = {}) {
  return new TextRun({
    text: String(value),
    font: { ascii: FONT_EN, hAnsi: FONT_EN, eastAsia: FONT_CN, cs: FONT_EN },
    size: options.size || 21,
    bold: options.bold || undefined,
    color: BLACK,
  });
}

function paragraph(value = "", options = {}) {
  return new Paragraph({
    children: Array.isArray(value) ? value : [text(value, options)],
    alignment: options.alignment || AlignmentType.JUSTIFIED,
    spacing: options.spacing || { after: 0, line: 240 },
    numbering: options.numbering,
    indent: options.indent,
    keepNext: options.keepNext,
  });
}

function title(value) {
  return paragraph([text(value, { size: 36, bold: true })], {
    alignment: AlignmentType.CENTER,
    spacing: { after: 0, line: 240 },
    keepNext: true,
  });
}

function section(value) {
  return paragraph([text(value, { size: 28, bold: true })], {
    alignment: AlignmentType.LEFT,
    spacing: { before: 120, after: 0, line: 240 },
    keepNext: true,
  });
}

function sub(value) {
  return paragraph([text(value, { bold: true })], {
    alignment: AlignmentType.LEFT,
    spacing: { before: 80, after: 0, line: 240 },
    keepNext: true,
  });
}

function item(value, reference = "decimal") {
  return paragraph(value, { numbering: { reference, level: 0 } });
}

function label(name, value) {
  return paragraph([text(name, { bold: true }), text(value)]);
}

const children = [
  title("论文科研数据筛查系统建设蓝图"),
  paragraph("V2.3｜本地完整验证版｜2026 年 10 月", { alignment: AlignmentType.CENTER }),
  paragraph(""),

  section("一、项目定位"),
  label("建设目标：", "检查论文公开或已授权的科研数据，标出需要核对的位置，并提供原始数据明细。"),
  label("主要用户：", "研究人员、课题组负责人、科研管理人员、期刊编辑和数据审查人员。"),
  label("处理材料：", "CSV、TSV、XLSX、XLS、XLSM、XLSB、文字版 PDF 和 DOCX；扫描图片暂不支持。"),
  label("核心原则：", "只说明数据、位置和关系，不判断作者意图，不直接作违规认定。"),
  paragraph(""),

  section("二、需求依据"),
  item("任务书要求发现跨组重复、固定加减、固定比例、线性关系、尾数规律、统计量不自洽和跨载体矛盾等问题。", "requirements"),
  item("PaperConan 推文强调由程序完成确定性计算，由 Agent 理解字段与研究语义，并由人工完成最终裁定。", "requirements"),
  item("共享对照、重新绘图、单位换算、归一化、公式派生、检测下限和固定分母均可能产生良性信号，必须主动排查。", "requirements"),
  item("扫描结果必须说明已解析范围、规则覆盖和未覆盖原因；“没有报告”不能解释为“论文没有问题”。", "requirements"),
  paragraph(""),

  section("三、核心业务流程"),
  item("提交材料：上传同一论文的多份材料、输入 DOI/公开链接，或载入内置合成样例。", "flow"),
  item("开始检查：系统校验文件格式、大小和检查范围。", "flow"),
  item("查看结果：先查看材料读取情况，再按文件、数据表、行列核对原始数值；跨文件结果并列展示。", "flow"),
  item("回原表核对：用户确认单位、公式、图注和原始记录；可选择逐条 AI 解释，先报价再确认。", "flow"),
  item("保存结果：用户记录复核意见，下载初筛 JSON/HTML 或冻结的 Word、PDF、Excel、HTML 报告。", "flow"),
  paragraph(""),

  section("四、产品页面"),
  sub("1. 开始筛查"),
  paragraph("主页面包含材料上传、检查范围、处理状态、待核对内容和原始数据；只使用研究人员日常用语。"),
  item("材料区：多选或拖拽追加，逐份移除、清空；最多 20 份，每份 20 MB，合计 100 MB，重名拒绝。", "scan-page"),
  item("范围区：快速、标准和全面三个选项，并用括号说明适用范围。", "scan-page"),
  item("状态区：显示等待中、检查中、已完成或未完成。", "scan-page"),
  item("结果区：显示文件、数据表、数值和待核对数量，并说明每份材料的读取情况及未完成范围。", "scan-page"),
  item("明细区：按关键词和优先级筛选，点击后查看位置、数据关系和原始数值。", "scan-page"),
  item("报告区：查看、下载中文报告与 JSON，并可查看 PaperConan 原始记录；逐条解释绑定线索。", "scan-page"),
  sub("2. 筛查记录"),
  paragraph("本机保存材料、范围、状态、时间和复核意见；重启后可重新打开结果；中断记录说明原因。"),
  sub("3. 使用说明"),
  paragraph("只保留操作步骤、支持范围和结果边界，不展示模型话术或重复解释。"),
  paragraph(""),

  section("五、检测规则与输出"),
  item("完全相同：跨列、跨表或跨文件出现相同数据或连续片段。", "rules"),
  item("固定平移：两组数据逐项保持同一差值，例如 B = A + 0.300。", "rules"),
  item("固定比例：两组数据逐项保持恒定倍数，需排查单位换算和归一化。", "rules"),
  item("精确线性：数据满足固定斜率和截距关系，需核对是否为公式派生列。", "rules"),
  item("重复向量与机械序列：多行结构、差分或时间轨迹过度一致。", "rules"),
  item("数字与统计信号：尾数分布、舍入聚集及检测器支持的统计一致性线索。", "rules"),
  label("每项结果至少输出：", "优先级、问题类型、文件、数据表、行号、相关列、数量和原始数据。内部编号不对用户显示。"),
  paragraph(""),

  section("六、系统实现"),
  label("前端：", "三入口单页工作台；用户界面用中文白话，不显示内部编号、英文状态或运行日志。"),
  label("服务端：", "Python 本地服务将同批材料放入同一目录联合检查，负责校验、状态查询、结果与报告。"),
  label("检测引擎：", "PaperConan 0.8.5，作为数值事实来源；界面不得修改或伪造检测结果。"),
  label("任务机制：", "双工作线程执行；SQLite 保存记录，输入和结果留在本地；重启时恢复历史并标记中断任务。"),
  label("模型职责：", "DeepSeek V4.1 Flash（API 标识 deepseek-flash）只解释已发现的线索；每次最多发送单条线索的少量证据，模型不能代替数值检测或人工决定。"),
  label("费用与安全：", "环境变量或本机加密配置读取密钥；逐条报价、确认后调用；超时或失败仍保留确定性结果；原文件不发送给模型。"),
  label("运行产物：", "SQLite、上传材料和报告留在本地 runtime；冻结报告生成 Word、PDF、Excel、HTML。"),
  label("接口：", "健康检查、任务扫描、材料发现、复核报告、逐条解释报价/执行及 JSON/原始记录下载。"),
  paragraph(""),

  section("七、当前交付边界"),
  item("本版范围：本地上传、真实数值扫描、覆盖说明、人工复核、逐条 AI 解释与四格式报告。", "scope"),
  item("后续由平台方完成：佰茵云登录、账号权限、对象存储、任务调度、部署配置和联调；本版不冒充平台已接入。", "scope"),
  item("PDF、Word 的实际可解析程度由源文件结构和 PaperConan 解析器决定；解析失败必须明确报告。", "scope"),
  item("公开材料入口只获取可直连的公开文件，不绕过登录或付费；无 OCR、图像鉴伪和多用户隔离。", "scope"),
  item("异常是待复核统计信号，不能据此认定科研不端或作者意图；未读取范围不得宣称无异常。", "scope"),
  paragraph(""),

  section("八、验收标准"),
  item("页面显示筛查服务正常，不出现内部组件名称和版本。", "acceptance"),
  item("用户可以追加、移除多份材料，开始联合检查；输入边界和重名文件均有明确提示。", "acceptance"),
  item("检查完成后显示固定差值及跨文件结果，能定位左右来源和原始值，不虚构对应关系。", "acceptance"),
  item("筛选有效；重启独立进程后可以重新打开历史，中断记录不会显示为检查成功。", "acceptance"),
  item("逐条解释先显示最高费用并确认，模型失败时仍可看扫描和人工证据；解释与线索及证据版本绑定。", "acceptance"),
  item("查看报告和下载报告均来自本次真实检查结果，JSON 与原始 PaperConan 记录可核对。", "acceptance"),
  item("部分或全部材料读取失败时，页面和报告明确说明；结果用于辅助核对，不作违规认定。", "acceptance"),
  item("后端自动测试、真实 HTTP 扫描和浏览器交互测试全部通过后，才能进入人工验收。", "acceptance"),
];

const doc = new Document({
  creator: "Codex",
  title: "论文科研数据筛查系统建设蓝图 V2.3",
  subject: "精简交付版建设蓝图",
  description: "版式对齐《利德云建设蓝图》：宋体、黑色、标题 18 磅、正文 10.5 磅。",
  styles: {
    default: {
      document: {
        run: { font: { ascii: FONT_EN, hAnsi: FONT_EN, eastAsia: FONT_CN, cs: FONT_EN }, size: 21, color: BLACK },
        paragraph: { alignment: AlignmentType.JUSTIFIED, spacing: { after: 0, line: 240 } },
      },
    },
  },
  numbering: {
    config: [
      ...["decimal", "requirements", "flow", "scan-page", "rules", "scope", "acceptance"].map((reference) => ({
        reference,
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 420, hanging: 360 } } } }],
      })),
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1800, bottom: 1440, left: 1800, header: 851, footer: 992 } } },
    children,
  }],
});

fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(OUTPUT, buffer);
  console.log(`Generated: ${OUTPUT} (${buffer.length} bytes)`);
});
