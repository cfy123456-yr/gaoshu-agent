# 知微高等数学学伴

面向大学理工科学生的高等数学教育智能体项目。知识库按照同济大学《高等数学》体系覆盖上册第 1—7 章和下册第 8—12 章。

项目采用“大模型负责教学表达，SymPy 负责确定性计算，知识库负责概念和教材依据”的架构。

## 当前功能

- 通过扣子智能体提供“知微老师”中文对话。
- 提供无需登录的独立对话演示页，支持在浏览器中连续输入求导、积分、极限和函数图像题目。
- 演示页聊天记录只保存在当前浏览器的 `localStorage`，不读取或展示其他用户的扣子会话记录。
- 使用 `math_verify` 工作流计算导数并判断学生答案。
- 使用 `math_integrate` 工作流计算不定积分、定积分并判断学生答案。
- 使用数学服务计算双侧极限、左极限和右极限并判断学生答案。
- 使用统一求解接口 `/solve` 覆盖极限、导数应用、积分、微分方程、向量、多元函数微分、重积分、曲线曲面积分和无穷级数等章节题型。
- 提供纯 SVG 函数图像接口，可生成 `sin(x)`、`x^2` 等显函数的坐标图和曲线。
- 扣子侧可使用一个 `math_solve` 工作流按 `chapter` 和 `topic` 路由到对应确定性求解器。
- 扣子侧可使用 `math_plot` 工作流生成函数图像，并在对话中通过 Markdown 图片链接显示。
- 使用 `knowledge_lookup` 工作流检索导数、微分和积分知识。
- FastAPI 数学服务同时提供 JSON 和查询参数两种调用方式。
- 数学表达式支持 `x^2`、`x**2`、`3x` 和 `3*x` 等常见写法。

## 项目结构

```text
gaoshu-agent/
├─ app/
│  ├─ main.py
│  ├─ plotting.py
│  └─ chapter_solvers.py
├─ knowledge/
│  ├─ 01_导数与微分基础.md
│  └─ 02_积分基础.md
├─ knowledge_tongji/
│  ├─ 00_教材目录与编写规则.md
│  ├─ 01_函数与极限.md
│  ├─ 03_微分中值定理与导数的应用.md
│  ├─ 05_反常积分补充.md
│  ├─ 06_定积分的应用.md
│  └─ 07—12 章各知识文件
├─ deploy/
│  ├─ wsgi_app.py
│  ├─ demo_chat.py
│  ├─ templates/demo.html
│  ├─ static/katex/
│  └─ pythonanywhere_wsgi.py
├─ scripts/
│  ├─ start-demo.cmd
│  ├─ start-demo.ps1
│  ├─ test-api.cmd
│  ├─ stop-demo.cmd
│  ├─ stop-demo.ps1
│  ├─ verify-deployment.cmd
│  ├─ verify-limit-regression.cmd
│  ├─ verify_limit_regression.py
│  ├─ verify-solve-regression.cmd
│  ├─ verify_solve_regression.py
│  └─ verify_deployment.py
├─ tests/
│  ├─ test_math_api.py
│  ├─ test_security_api.py
│  ├─ test_demo_page.py
│  ├─ test_plotting.py
│  ├─ test_service_components.py
│  └─ test_chapter_solvers.py
├─ .dockerignore
├─ .env.example
├─ .gitignore
├─ DEPLOYMENT.md
├─ Dockerfile
├─ README.md
├─ render.yaml
└─ requirements.txt
```

`.venv/`、缓存文件和 `.env` 不进入 Git 仓库。

## 环境要求

- Python 3.13
- pip
- Git

## 安装依赖

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果 PowerShell 禁止执行激活脚本，可以不激活虚拟环境，直接使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

部署后可运行多章节接口回归：

```powershell
.\scripts\verify-solve-regression.cmd --base-url https://cfyyy.pythonanywhere.com
```

极限接口回归：

```powershell
.\scripts\verify-limit-regression.cmd --base-url https://cfyyy.pythonanywhere.com
```

## 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

演示时可以直接双击 `scripts\start-demo.cmd`，脚本会自动完成：

1. 检查并启动本地数学服务。
2. 核对本地 `/health` 版本，发现旧进程时先重启。
3. 检查公网隧道健康状态，隧道失效时自动重建。
4. 输出智能体页面以及求导、积分、极限、统一求解和函数图像接口地址。

演示结束后双击 `scripts\stop-demo.cmd` 即可停止本脚本启动的隧道和数学服务。更完整的部署与验收说明见 `DEPLOYMENT.md`。

数学服务启动后，可以双击 `scripts\test-api.cmd` 运行自动回归测试。测试覆盖健康检查、导数判题、不定积分、定积分、双侧与左右极限、统一章节求解、函数图像、非法表达式拦截、API Key、限流、计算超时、日志隐私、日志轮转配置和独立对话演示页。

也可以直接使用 Python 命令运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

如果测试服务不在默认地址，可先设置 `TEST_BASE_URL`。

开发时可增加自动重载：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

服务启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`
- 独立对话演示：`http://127.0.0.1:5000/demo`

## 接口说明

### 独立对话演示

```http
POST /demo/api/chat
Content-Type: application/json

{"message":"积分 0 到 1 x^2"}
```

该接口把自然语言中的求导、积分或极限请求转换为确定性数学计算，返回适合对话页展示的意图、公式和计算结果。它是无需登录的公开演示接口，不使用或返回扣子的会话记录。

普通问题默认不处理。配置 `GENERAL_CHAT_API_URL`、`GENERAL_CHAT_API_KEY` 和 `GENERAL_CHAT_MODEL` 后，非数学问题会交给所配置的模型回答；普通问题内容会发送给该模型服务。数学计算始终使用本项目的 SymPy 工具，不交给通用模型猜测。

### 健康检查

```http
GET /health
```

### 导数计算与判题

```http
POST /verify-query?expression=x^2&variable=x&candidate=2x
```

返回字段包括：

- `derivative`：SymPy 计算得到的导数。
- `derivative_latex`：可供 LaTeX 渲染的导数。
- `is_correct`：学生答案是否正确；没有提供答案时为 `null`。

### 积分计算与判题

不定积分：

```http
POST /integrate-query?expression=x^2&variable=x&candidate=x^3/3
```

定积分：

```http
POST /integrate-query?expression=x^2&variable=x&lower=0&upper=1&candidate=1/3
```

返回字段包括：

- `integral`：积分结果。
- `integral_latex`：可供 LaTeX 渲染的积分结果。
- `is_correct`：学生答案是否正确；没有提供答案时为 `null`。

### 极限计算与判题

双侧极限：

```http
POST /limit-query?expression=sin(x)/x&variable=x&point=0&candidate=1
```

左极限和右极限：

```http
POST /limit-query?expression=1/x&variable=x&point=0&direction=+
POST /limit-query?expression=1/x&variable=x&point=0&direction=-
```

返回字段包括：

- `limit`：极限结果。
- `limit_latex`：可供 LaTeX 渲染的极限结果。
- `direction`：`+` 表示右极限，`-` 表示左极限，空值表示双侧极限。
- `is_correct`：学生答案是否正确；没有提供答案时为 `null`。

### 章节统一求解

```http
POST /solve
Content-Type: application/json

{
  "chapter": "differential_equations",
  "topic": "dsolve",
  "inputs": {
    "equation": "y' - y",
    "variable": "x",
    "function": "y"
  }
}
```

该接口返回 `method`、`result`、`latex`、`notes` 等字段；提供 `candidate` 时，能确定性比较的题型会返回 `is_correct`。支持的章节包括 `limits`、`derivatives`、`integrals`、`differential_equations`、`vectors`、`multivariable_calculus`、`multiple_integrals`、`line_surface_integrals` 和 `series`。

参数方程求导示例：

```http
POST /solve
Content-Type: application/json

{
  "chapter": "derivatives",
  "topic": "parametric_derivative",
  "inputs": {
    "x_expression": "t^2",
    "y_expression": "t^3",
    "parameter": "t"
  }
}
```

方程组确定函数求偏导示例：

```http
POST /solve
Content-Type: application/json

{
  "chapter": "multivariable_calculus",
  "topic": "system_implicit_derivative",
  "inputs": {
    "equations": ["u+v=x", "u-v=y"],
    "dependents": ["u", "v"],
    "variable": "x",
    "dependent": "u"
  }
}
```

条件极值示例：

```http
POST /solve
Content-Type: application/json

{
  "chapter": "multivariable_calculus",
  "topic": "conditional_extrema",
  "inputs": {
    "expression": "x*y",
    "variables": ["x", "y"],
    "constraint": "x+y=1"
  }
}
```

### 函数图像

生成 SVG 图像：

```http
POST /plot-query?expression=sin(x)&x_min=-3&x_max=3
```

直接在浏览器显示 SVG：

```http
GET /plot.svg?expression=x^2&x_min=-5&x_max=5
```

接口支持 `x_min`、`x_max`、`y_min`、`y_max`、`samples`、`width` 和 `height` 参数。图像由服务端纯 SVG 绘制，不依赖 Matplotlib 或外部 CDN。

## 扣子工作流

| 工作流 | 用途 | 后端接口 |
| --- | --- | --- |
| `math_verify` | 求导、导数答案判断 | `/verify-query` |
| `math_integrate` | 不定积分、定积分、积分答案判断 | `/integrate-query` |
| `math_limit` | 双侧极限、左极限、右极限与答案判断 | `/limit-query` |
| `math_solve` | 所有章节题型的统一求解与部分判断题 | `/solve` |
| `math_plot` | 生成显函数图像并返回 SVG | `/plot-query`、`/plot.svg` |
| `knowledge_lookup` | 检索高数知识库 | 扣子知识库 |

统一智能体提示词见 `COZE_AGENT_PROMPT.md`，可直接复制到扣子。

## 知识库

- `knowledge/01_导数与微分基础.md`：导数定义、求导公式、求导法则、微分和常见错误。
- `knowledge/02_积分基础.md`：原函数、不定积分、定积分、换元法、分部积分法和常见错误。
- `knowledge_tongji/`：函数与极限、微分中值定理、定积分应用、微分方程、向量代数、多元函数微分、重积分、曲线与曲面积分、无穷级数等章节文件。
- `knowledge_tongji/05_反常积分补充.md`：补齐定积分章节中的反常积分和审敛法。

第 1 章、第 3 章、第 5—12 章使用 `knowledge_tongji` 中的独立文件；第 2、4 章继续引用冻结文件，避免重复生成和版本冲突。

## 安全与配置

数学服务已加入基础安全防护：

- 可选 API 密钥校验：`MATH_API_KEY`。
- 内存请求频率限制：`RATE_LIMIT_PER_MINUTE`，默认每分钟 60 次。
- 表达式长度限制：`MAX_EXPRESSION_LENGTH`，默认 300 字符。
- 变量名长度限制：`MAX_SYMBOL_LENGTH`，默认 32 字符。
- 表达式字符检查和变量名白名单检查。
- SymPy 解析器使用受限的 `local_dict` 和空的 `global_dict`，不再直接解析不受信任内容。
- 计算超时：`CALCULATION_TIMEOUT_SECONDS`，默认 10 秒；超时返回 HTTP 504，并带 `X-Calculation-Timeout` 响应头。
- 计算线程池：`CALCULATION_WORKERS`，默认 4 个并发计算线程。
- JSONL 持久化日志：默认写入 `logs/math-service.jsonl`，日志按 5 MiB 轮转并保留 3 个备份。

日志只记录请求时间、接口、状态码、耗时、客户端哈希和错误类型，不记录数学表达式、API 密钥或学生个人数据。可通过以下变量调整：

```powershell
$env:LOG_ENABLED = "true"
$env:LOG_LEVEL = "INFO"
$env:LOG_FILE = "logs/math-service.jsonl"
$env:LOG_MAX_BYTES = "5242880"
$env:LOG_BACKUP_COUNT = "3"
```

可在启动服务前通过环境变量覆盖默认配置：

```powershell
$env:MATH_API_KEY = "替换为你的密钥"
$env:RATE_LIMIT_PER_MINUTE = "60"
$env:MAX_EXPRESSION_LENGTH = "300"
$env:MAX_SYMBOL_LENGTH = "32"
$env:CALCULATION_TIMEOUT_SECONDS = "10"
$env:CALCULATION_WORKERS = "4"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

当前公网服务已启用 `MATH_API_KEY`。扣子的 `math_verify`、`math_integrate`、`math_limit`、`math_solve`、`math_plot` HTTP 节点必须增加请求头 `X-API-Key`，其值与 PythonAnywhere 的 `MATH_API_KEY` 一致。`/demo`、`/demo/api/*`、`/health` 和浏览器显示图片用的 `/plot.svg` 仍可直接访问。

普通问答模型使用独立配置，密钥不会返回给浏览器：

```powershell
$env:GENERAL_CHAT_API_URL = "https://api.deepseek.com/chat/completions"
$env:GENERAL_CHAT_API_KEY = "替换为你的模型密钥"
$env:GENERAL_CHAT_MODEL = "deepseek-chat"
```

`GET /health` 会返回服务版本、启动时间、运行时长、计算超时、工作线程数、限流、API 密钥开关、日志状态和输入限制，但不会返回 API 密钥。`logs/` 已加入 `.gitignore`。

公网服务已部署到 PythonAnywhere，固定地址为 `https://cfyyy.pythonanywhere.com`。无需登录的对话演示页位于 `https://cfyyy.pythonanywhere.com/demo`，可连续体验求导、积分和极限计算。KaTeX 公式资源随项目一起部署，不依赖外部 CDN；聊天历史只保存在访问者自己的浏览器中。`.github/workflows/health-check.yml` 每 15 分钟检查一次公网健康状态和版本号，失败时 GitHub Actions 会发送失败通知。不要将 `.env`、令牌、API 密钥或个人学生数据提交到 Git 仓库。部署和更新步骤见 `DEPLOYMENT.md`。

## 当前状态

已完成从知识库到教学对话的核心闭环：

- 智能体已发布：<https://www.coze.cn/store/agent/7687155979821481999?bot_id=true>
- 知识库已绑定：12 个文档、464 个分段。
- 已绑定并测试 `math_verify`、`math_integrate`、`math_limit`、`math_solve`、`math_plot`、`knowledge_lookup`。
- 已验证不定积分 `∫x^2 dx = x^3/3` 和定积分 `∫_0^1 x^2 dx = 1/3` 的答案判断。
- 已验证求导 `f(x)=x^2 sin x` 的结果和候选答案判断。
- 本地 55 项单元测试通过，公网极限回归 6/6、多章节回归 9/9 通过。
- 已加入计算超时保护、JSONL 轮转日志和增强健康检查。
- 同济版高等数学第 1—12 章知识文件已经整理完成。
- 已提供无需登录的独立对话演示页 `/demo`，支持连续输入求导、积分、极限、函数图像和候选答案判断。
- 演示页已接入函数图像：输入“画函数 y=sin(x)，x 从 -3 到 3”会直接在对话气泡中显示曲线。
- 演示页公式资源已改为项目内自托管，聊天记录只保存在当前浏览器，不与其他用户共享。
- 已部署到 PythonAnywhere，固定公网地址为 `https://cfyyy.pythonanywhere.com`，不再依赖本机 LocalTunnel。
- 已通过扣子实测求导 `f(x)=x^2` 和不定积分 `∫x^2 dx` 两条完整链路。
- 已加入章节统一求解器，覆盖约 40 个题型；级数收敛、重积分、微分方程、梯度等题型已通过扣子工作流实测。
- 已加入纯 SVG 函数图像接口，本地绘图单元测试通过。
- 已通过 `math_plot` 在智能体对话中显示函数图像。
- 已统一更新并发布扣子提示词，完成求导、积分、极限和级数的空答案、正确/错误候选答案及不定积分补 `C` 话术回归。
- 扣子提示词已允许普通问答；独立演示页也支持通过环境变量接入通用模型，同时保留高数题强制走确定性计算工具的规则。

图片识别已改用 `ocr_question` 插件，调用时只传入图片地址，返回题目文字和用 `$` 包裹的公式。图片题采用严格两阶段流程：第一轮只转写并等待用户确认，确认后的下一轮才调用计算工作流；识别残缺时要求重新拍照，不猜测公式。图片积分题的两阶段流程已经通过验证。语音和参赛材料仍在后续开发中。
