# 简历优化 Agent

一个可运行的简历优化 Agent 应用：用户可以上传或粘贴简历，输入目标 JD，系统先分析简历与 JD 的匹配度，在用户确认后生成优化后的简历，并支持导出 Markdown / Word / PDF。

## 1. 功能说明

- 支持上传简历文件：`pdf`、`docx`、`md`、`txt`
- 支持直接粘贴简历文本
- 支持输入目标职位 JD
- Agent 分析输出：
  - 匹配分数
  - 匹配亮点
  - 主要缺口
  - 具体优化建议
  - 风险提醒，避免简历内容失真
- 用户确认后生成优化后的简历正文
- 支持导出：`md`、`docx`、`pdf`
- LLM API Key 通过环境变量配置，不写死在代码中
- 支持 Docker 一键构建和启动

## 2. Agent 架构设计

本项目采用“分析 Agent + 改写 Agent”的双阶段 Harness 设计：

```text
用户输入简历/JD
   ↓
Resume Parser：解析 PDF / Word / Markdown / Text
   ↓
Context Builder：裁剪、清洗、组织简历与 JD 上下文
   ↓
Analysis Agent：输出匹配亮点、缺口、建议、风险提醒
   ↓
Memory：以 session 形式保存原始简历、JD、分析结果
   ↓ 用户确认
Optimization Agent：基于原始事实和分析结果生成优化简历
   ↓
Export Tool：导出 md / docx / pdf
```

### 关键设计点

1. **忠于事实**  
   Prompt 中明确约束模型只能基于原始简历事实改写，不允许编造学历、公司、项目、指标、技术栈。

2. **用户确认机制**  
   系统不会直接生成优化简历，而是先展示分析结果。只有用户点击“确认并生成优化简历”后才进入改写阶段。

3. **Memory 管理**  
   当前版本使用内存字典保存 session：`resume_text`、`jd_text`、`analysis`、`optimized_resume`。生产环境可替换为 Redis / PostgreSQL。

4. **Context Engineering**  
   后端会对输入文本进行清洗和长度控制，避免过长上下文影响模型稳定性。

5. **工具化能力**  
   文件解析、简历分析、简历生成、格式导出均封装为独立函数，便于后续扩展为 LangGraph / CrewAI 等 Agent 框架。

## 3. 技术栈

- Backend：FastAPI
- Frontend：原生 HTML/CSS/JavaScript
- LLM：DeepSeek OpenAI-Compatible API
- 文件解析：pypdf、python-docx
- 文件导出：python-docx、reportlab
- 部署：Docker / docker-compose

## 4. 环境变量配置

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

> 注意：不要把真实 API Key 提交到 GitHub。请确保 `.env` 已被 `.gitignore` 忽略。

## 5. Docker 启动方式

### 方式一：使用 docker compose

```bash
docker compose up --build
```

启动成功后访问：

```text
http://localhost:8000
```

### 方式二：使用 Dockerfile

构建镜像：

```bash
docker build -t resume-agent .
```

启动容器：

```bash
docker run --rm -p 8000:8000 \
  -e DEEPSEEK_API_KEY=你的 DeepSeek API Key \
  -e DEEPSEEK_BASE_URL=https://api.deepseek.com \
  -e DEEPSEEK_MODEL=deepseek-chat \
  resume-agent
```

访问：

```text
http://localhost:8000
```

## 6. 本地开发启动

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 7. 使用流程

1. 打开 `http://localhost:8000`
2. 上传简历文件，或直接粘贴简历文本
3. 粘贴目标岗位 JD
4. 点击“分析匹配度”
5. 查看匹配亮点、主要缺口、优化建议和风险提醒
6. 确认后点击“确认并生成优化简历”
7. 查看生成结果
8. 按需导出 Markdown / Word / PDF

## 8. API 简要说明

### 解析简历文件

```http
POST /api/parse-resume
Content-Type: multipart/form-data
```

### 分析简历与 JD

```http
POST /api/analyze
Content-Type: application/json

{
  "resume_text": "简历文本",
  "jd_text": "目标 JD"
}
```

### 确认并生成优化简历

```http
POST /api/optimize
Content-Type: application/json

{
  "session_id": "分析接口返回的 session_id",
  "user_confirmed": true,
  "extra_instruction": "可选补充要求"
}
```

### 导出优化简历

```http
GET /api/export/{session_id}.md
GET /api/export/{session_id}.docx
GET /api/export/{session_id}.pdf
```

## 9. 基本验收建议

面试官可按以下方式验收：

1. `cp .env.example .env` 并填写 API Key
2. 执行 `docker compose up --build`
3. 浏览器访问 `http://localhost:8000`
4. 粘贴一份简历和题目中的 AI Agent 开发工程师 JD
5. 点击分析，检查是否输出匹配亮点、主要缺口和优化建议
6. 点击确认生成，检查改写后的简历是否忠于原始事实
7. 分别导出 `md`、`docx`、`pdf`，检查文件是否能正常打开

## 10. 后续可扩展方向

- 使用 Redis / PostgreSQL 持久化 session 和历史版本
- 增加用户可编辑的“事实确认表”，让用户确认可使用事实后再生成简历
- 接入向量数据库，支持多版本简历和多岗位 JD 匹配
- 引入 LangGraph，将 Parser、Analyzer、Reviewer、Writer、Exporter 拆成显式节点
- 增加 Review Agent，对优化后简历进行“事实一致性检查”和“JD 关键词覆盖检查”
