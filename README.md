# PDF-Textualization

**前排提示:项目是vibe的,代码质量可能会比较烂喵**

将扫描版 PDF 转换为 Markdown 的工具，使用智谱 GLM-OCR API 进行文字识别，并可选择性地通过 LLM 对识别结果进行清洗优化。

## 功能特性

- **OCR 识别**：调用智谱 GLM-OCR API，支持扫描版 PDF 的版面解析
- **LLM 清洗**：可选的 LLM 后处理，去除页眉页脚、修复断行、保留段落结构
- **图片处理**：自动下载或裁剪 PDF 中的图片并本地化引用
- **进度输出**：后端以 JSON 格式向 stdout 实时输出进度，便于集成
- **双端支持**：提供 CLI 命令行工具和跨平台桌面 GUI 两种使用方式

## 项目结构

```
PDF-Textualization/
├── backend/                   # Python CLI 后端
│   ├── main.py                # 入口点
│   ├── config.py              # 配置管理（优先级：CLI > 环境变量 > config.yaml > 默认值）
│   ├── config.example.yaml    # 配置模板
│   ├── requirements.txt       # Python 依赖
│   ├── pipeline.py            # 主异步编排器，输出 JSON 进度
│   ├── pdf_processor.py       # PDF 分批提取
│   ├── ocr_client.py          # GLM-OCR API 调用与重试
│   ├── llm_client.py          # OpenAI 兼容 LLM 调用与重试
│   ├── md_generator.py        # Markdown 文件组装
│   └── image_downloader.py    # 图片下载与本地化
│
└── frontend/                  # C# / .NET 9 Avalonia 桌面 GUI
    ├── PDFTextualization.sln
    └── PDFTextualization/
        ├── ViewModels/
        │   └── MainWindowViewModel.cs  # 全部 UI 逻辑、进程管理、进度解析
        └── Views/
            └── MainWindow.axaml        # 主窗口 XAML 布局
```

## 处理流程

```
输入 PDF
  → pdf_processor   （按批次提取页面）
  → ocr_client      （GLM-OCR API，429/5xx 自动重试）
  → pipeline        （滑动窗口并发，最多 3 路 LLM 调用）
  → llm_client      （OpenAI 兼容，限速自动重试）
  → image_downloader（下载图片或从 PDF 裁剪）
  → md_generator    （组装为 .md 文件）
```

## 准备工作

### 获取 API Key

1. 前往 [智谱开放平台](https://open.bigmodel.cn/) 注册账号并创建 API Key，用于 OCR 识别
2. （可选）如需 LLM 清洗，可使用同一 Key 调用 GLM 模型，或配置其他 OpenAI 兼容服务

### 配置文件

复制配置模板并填写 API Key：

```bash
cp backend/config.example.yaml backend/config.yaml
```

编辑 `backend/config.yaml`：

**这里推荐使用的是4.5-air,质量不会下降的情况下并行数量提升了**

```yaml
ocr_api:
  key: "your-glm-api-key"

llm_api:
  key: "your-llm-api-key"
  provider: "glm"           # "glm" 或 "openai"

llm:
  enabled: true
  model: "glm-4.6"
  max_concurrent: 3

output:
  heading_format: "# Page {n}"
```

也可以通过环境变量传入（无需配置文件）：

```bash
export OCR_API_KEY="your-glm-api-key"
export LLM_API_KEY="your-llm-api-key"
```

## 使用方法

### 方式一：命令行（CLI）

**安装依赖：**

```bash
cd backend
pip install -r requirements.txt
```

**基本用法（使用 config.yaml）：**

```bash
python main.py input.pdf
```

**指定输出文件：**

```bash
python main.py input.pdf -o output.md
```

**完整参数示例：**

```bash
python main.py input.pdf \
  -o output.md \
  --ocr-api-key "your-glm-key" \
  --llm-api-key "your-llm-key" \
  --llm-provider glm \
  --llm-model glm-4.6 \
  --pages 1-50
```

**跳过 LLM 清洗：**

```bash
python main.py input.pdf --no-llm
```

**参数优先级：** CLI 参数 > 环境变量 > config.yaml > 默认值

### 方式二：桌面 GUI

**环境要求：** .NET 9 SDK

**构建并运行：**

```bash
cd frontend
dotnet restore PDFTextualization.sln
dotnet build PDFTextualization.sln -c Debug
dotnet run --project PDFTextualization/ -c Debug
```

GUI 启动后，在界面中选择 PDF 文件、填写 API Key，点击开始即可。进度条和日志实时更新。

**打包发布：**

```bash
# Windows
dotnet publish PDFTextualization/ -c Release -r win-x64

# macOS (Apple Silicon)
dotnet publish PDFTextualization/ -c Release -r osx-arm64

# Linux
dotnet publish PDFTextualization/ -c Release -r linux-x64
```

## 依赖

### 后端（Python）

| 包 | 用途 |
|----|------|
| `pymupdf >= 1.24.0` | PDF 页面提取与图片裁剪 |
| `openai >= 1.0.0` | LLM 调用（兼容 GLM 和 OpenAI） |
| `httpx >= 0.27.0` | 异步 HTTP 客户端（OCR 调用） |
| `pyyaml >= 6.0` | 配置文件解析 |
| `rich >= 13.0` | 控制台日志输出 |

### 前端（C#）

| 包 | 用途 |
|----|------|
| .NET 9.0 | 运行时 |
| Avalonia 11.3.12 | 跨平台 UI 框架 |
| CommunityToolkit.Mvvm 8.2.1 | MVVM 框架 |

## 重试策略

- **OCR**：遇到 429 / 5xx 错误时，按 0s → 2s → 5s → 15s 间隔自动重试
- **LLM**：遇到限速时，按 0s → 20s → 40s → 60s 间隔自动重试

## 许可证

见 [LICENSE](LICENSE) 文件。
