# 知微高等数学学伴

面向大学理工科学生的高等数学教育智能体项目。知识库按照同济大学《高等数学》体系覆盖上册第 1—7 章和下册第 8—12 章。

项目采用“大模型负责教学表达，SymPy 负责确定性计算，知识库负责概念和教材依据”的架构。

## 当前功能

- 通过扣子智能体提供“知微老师”中文对话。
- 提供无需登录的独立对话演示页，支持在浏览器中连续输入求导、积分、极限和函数图像题目。
- 演示页支持浏览器原生中文语音输入；转写内容只写入输入框，核对后再由用户手动发送。
- 助手回答支持浏览器原生中文朗读，可逐条开始或停止。
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
│  ├─ check_health.py
│  ├─ publish-pythonanywhere-file.ps1
│  ├─ stop-demo.cmd
│  ├─ stop-demo.ps1
│  ├─ verify-deployment.cmd
│  ├─ verify-limit-regression.cmd
│  ├─ verify_limit_regression.py
│  ├─ verify-solve-regression.cmd
│  ├─ verify_solve_regression.py
│  ├─ verify_random_regression.py
│  └─ verify_deployment.py
├─ tests/
│  ├─ test_health_check.py
│  ├─ test_math_api.py
│  ├─ test_security_api.py
│  ├─ test_demo_page.py
│  ├─ test_launchers.py
│  ├─ test_plotting.py
│  ├─ test_service_components.py
│  ├─ test_chapter_solvers.py
│  ├─ test_random_regression.py
│  └─ test_verify_deployment.py
├─ .dockerignore
├─ .env.example
├─ .gitignore
├─ DEPLOYMENT.md
├─ Dockerfile
├─ PROJECT_STATUS.md
├─ README.md
├─ render.yaml
└─ requirements.txt
```

`.venv/`、缓存文件和 `.env` 不进入 Git 仓库。

## 环境要求

- Python 3.13
- pip
- Git
- 本地演示启动脚本使用 PowerShell 7（`pwsh`）

可选的 Windows 离线 OCR 会先尝试 PowerShell 7；当前系统只有在 PowerShell 7
无法加载 WinRT OCR 类型时，才回退到 Windows PowerShell 5.1。

## 安装依赖

PowerShell 7（推荐）：

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

固定随机种子的公网随机回归：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_random_regression.py --base-url https://cfyyy.pythonanywhere.com
```

公网健康检查默认会等待 PythonAnywhere 冷启动或短暂重启，最多重试 `5` 次：

```powershell
.\.venv\Scripts\python.exe .\scripts\check_health.py
```

可通过 `--attempts`、`--delay` 和 `--timeout`，或对应的
`HEALTH_CHECK_ATTEMPTS`、`HEALTH_CHECK_DELAY`、`HEALTH_CHECK_TIMEOUT`
环境变量调整监控等待时间。

## 启动服务

本地演示推荐直接运行与 PythonAnywhere 相同的 Flask WSGI 入口：

```powershell
.\.venv\Scripts\python.exe -c "from deploy.wsgi_app import application; application.run(host='127.0.0.1', port=8000, use_reloader=False, threaded=True)"
```

演示时可以直接双击 `scripts\start-demo.cmd`，脚本会自动完成：

1. 优先使用 Uvicorn；本机 `a2wsgi` 或 `uvicorn` 不可用时自动降级到 Flask WSGI。
2. 核对本地 `/health` 版本，发现旧进程时先重启。
3. 输出本地演示页、固定公网演示页、健康检查和智能体地址。

演示结束后双击 `scripts\stop-demo.cmd` 即可停止本地数学服务。公网服务固定运行在
PythonAnywhere，不依赖本机隧道。更完整的部署与验收说明见 `DEPLOYMENT.md`。

数学服务启动后，可以双击 `scripts\test-api.cmd` 运行自动回归测试。测试覆盖健康检查、导数判题、不定积分、定积分、双侧与左右极限、统一章节求解、函数图像、非法表达式拦截、API Key、限流、计算超时、日志隐私、日志轮转配置、独立对话演示页和本地启动脚本。

也可以直接使用 Python 命令运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

如果测试服务不在默认地址，可先设置 `TEST_BASE_URL`。

需要 FastAPI OpenAPI 文档或自动重载时，可以使用 Uvicorn：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

如果该命令提示无法导入 `a2wsgi`，说明本地虚拟环境损坏；删除 `.venv` 后按本文的
安装依赖步骤重建即可。日常演示不需要 Uvicorn。

服务启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- 独立对话演示：`http://127.0.0.1:8000/demo`
- OpenAPI 文档（仅使用 Uvicorn 启动时）：`http://127.0.0.1:8000/docs`

## 接口说明

### 独立对话演示

```http
POST /demo/api/chat
Content-Type: application/json

{"message":"积分 0 到 1 x^2"}
```

该接口把自然语言中的求导、积分或极限请求转换为确定性数学计算，返回适合对话页展示的意图、公式和计算结果。它是无需登录的公开演示接口，不使用或返回扣子的会话记录。

普通问答默认使用阿里云百炼的 OpenAI 兼容接口和 `qwen-plus`；未单独配置 `GENERAL_CHAT_API_KEY` 时，会复用 `VISION_API_KEY`。也可以用 `GENERAL_CHAT_API_URL`、`GENERAL_CHAT_API_KEY` 和 `GENERAL_CHAT_MODEL` 显式覆盖。普通问题内容会发送给该模型服务；数学计算始终使用本项目的 SymPy 工具，不交给通用模型猜测。

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

多变量、多约束条件极值：

```http
POST /solve
Content-Type: application/json

{
  "chapter": "multivariable_calculus",
  "topic": "conditional_extrema",
  "inputs": {
    "expression": "x^2+y^2+z^2",
    "variables": ["x", "y", "z"],
    "constraints": ["x=0", "y=0"]
  }
}
```

`constraints` 也可写成 `"x=0; y=0"`。等式约束数量必须少于变量数量；单约束仍可用原有的 `constraint` 字段。

极坐标二重积分示例：

```http
POST /solve
Content-Type: application/json

{
  "chapter": "multiple_integrals",
  "topic": "double_polar",
  "inputs": {
    "expression": "x^2+y^2",
    "lower_r": "0",
    "upper_r": "1",
    "lower_theta": "0",
    "upper_theta": "2*pi"
  }
}
```

柱面坐标三重积分示例：

```http
POST /solve
Content-Type: application/json

{
  "chapter": "multiple_integrals",
  "topic": "triple_cylindrical",
  "inputs": {
    "expression": "x^2+y^2",
    "lower_r": "0",
    "upper_r": "1",
    "lower_theta": "0",
    "upper_theta": "2*pi",
    "lower_z": "0",
    "upper_z": "1"
  }
}
```

球面坐标三重积分示例：

```http
POST /solve
Content-Type: application/json

{
  "chapter": "multiple_integrals",
  "topic": "triple_spherical",
  "inputs": {
    "expression": "1",
    "lower_rho": "0",
    "upper_rho": "1",
    "lower_phi": "0",
    "upper_phi": "pi",
    "lower_theta": "0",
    "upper_theta": "2*pi"
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

当前公网服务未启用 `MATH_API_KEY`，公开演示接口可以直接调用。若正式启用密钥，扣子的 `math_verify`、`math_integrate`、`math_limit`、`math_solve`、`math_plot` HTTP 节点必须增加请求头 `X-API-Key`，其值与 PythonAnywhere 的 `MATH_API_KEY` 一致。`/demo`、`/demo/api/*`、`/health` 和浏览器显示图片用的 `/plot.svg` 始终不需要 API Key。

普通问答模型可以显式使用百炼配置，密钥不会返回给浏览器：

```powershell
$env:GENERAL_CHAT_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
$env:GENERAL_CHAT_API_KEY = "替换为你的模型密钥"
$env:GENERAL_CHAT_MODEL = "qwen-plus"
```

图片识别优先使用 OpenAI 兼容的视觉模型接口；未完整配置时才尝试扣子备用链路。线上公网当前使用视觉模型主链路，扣子工作流作为备用：

```powershell
$env:VISION_API_BASE = "https://your-vision-endpoint.example/v1"
$env:VISION_API_KEY = "替换为你的视觉模型密钥"
$env:VISION_MODEL = "qwen3-vl-plus"
$env:VISION_TIMEOUT_SECONDS = "30"

$env:COZE_API_TOKEN = ""
$env:COZE_OCR_WORKFLOW_ID = ""
```

如果同时配置视觉模型和扣子 OCR，服务按 `vision`、`coze` 的顺序尝试；两套上游都失败时不会用质量不可控的本地 OCR 掩盖故障。只有完全未配置上游服务时，才会尝试可选的 Windows 本地 OCR。

`GET /health` 会返回服务版本、启动时间、运行时长、计算超时、工作线程数、限流、API 密钥开关、日志状态和输入限制，但不会返回 API 密钥。`GET /demo/api/health` 额外返回视觉模型和普通问答模型的提供商、模型名、密钥来源和超时配置，同样不会返回密钥内容。`logs/` 已加入 `.gitignore`。

公网服务已部署到 PythonAnywhere，固定地址为 `https://cfyyy.pythonanywhere.com`。无需登录的对话演示页位于 `https://cfyyy.pythonanywhere.com/demo`，可连续体验求导、积分和极限计算。KaTeX 公式资源随项目一起部署，不依赖外部 CDN；聊天历史只保存在访问者自己的浏览器中。`.github/workflows/health-check.yml` 每 15 分钟检查一次公网健康状态和版本号，健康检查工作流、检查脚本或部署代码变更时也会立即检查，失败时 GitHub Actions 会发送失败通知。不要将 `.env`、令牌、API 密钥或个人学生数据提交到 Git 仓库。部署和更新步骤见 `DEPLOYMENT.md`。

## 当前状态

已完成从知识库到教学对话的核心闭环：

- 智能体已发布：<https://www.coze.cn/store/agent/7687155979821481999?bot_id=true>
- 知识库已绑定：12 个文档、464 个分段。
- 已绑定并测试 `math_verify`、`math_integrate`、`math_limit`、`math_solve`、`math_plot`、`knowledge_lookup`。
- 已验证不定积分 `∫x^2 dx = x^3/3` 和定积分 `∫_0^1 x^2 dx = 1/3` 的答案判断。
- 已验证求导 `f(x)=x^2 sin x` 的结果和候选答案判断。
- 本地完整测试共 166 项，162 项通过、4 项可选旧版显式曲线/曲面积分测试跳过；
  GitHub Actions 会在推送 `main` 和提交拉取请求时自动复跑整套测试；公网极限固定
  回归 6/6、统一求解固定回归 9/9、部署验收 10/10、固定种子随机回归全部通过。
  本地启动脚本也已纳入回归，覆盖 PowerShell 7 调用、工作目录和 Flask 降级路径。
- 已加入计算超时保护、JSONL 轮转日志和增强健康检查。
- 同济版高等数学第 1—12 章知识文件已经整理完成。
- 已提供无需登录的独立对话演示页 `/demo`，支持连续输入求导、积分、极限、函数图像和候选答案判断。
- 演示页已接入函数图像：输入“画函数 y=sin(x)，x 从 -3 到 3”会直接在对话气泡中显示曲线。
- 演示页公式资源已改为项目内自托管，聊天记录只保存在当前浏览器，不与其他用户共享。
- 已部署到 PythonAnywhere，固定公网地址为 `https://cfyyy.pythonanywhere.com`，不再依赖本机 LocalTunnel。
- 已通过扣子实测求导 `f(x)=x^2` 和不定积分 `∫x^2 dx` 两条完整链路。
- 已加入章节统一求解器，覆盖 45 个题型；级数收敛、重积分、微分方程、梯度等题型已通过扣子工作流实测。
- 已加入纯 SVG 函数图像接口，本地绘图单元测试通过。
- 已通过 `math_plot` 在智能体对话中显示函数图像。
- 已统一更新并发布扣子提示词，完成求导、积分、极限和级数的空答案、正确/错误候选答案及不定积分补 `C` 话术回归。
- 扣子提示词已允许普通问答；独立演示页也支持通过环境变量接入通用模型，同时保留高数题强制走确定性计算工具的规则。

公网图片识别主链路已切换为视觉模型 OCR，扣子工作流保留为可选备用，本地 Windows OCR 仅作为未配置上游时的降级方案。图片题采用严格两阶段流程：第一轮只转写并等待用户确认，确认后的下一轮才调用确定性计算；识别残缺或上游失败时要求重新上传，不猜测公式。服务端会话和 OCR 缓存均为进程内存，PythonAnywhere Web 应用 Reload 后会清空。浏览器原生语音输入和回答朗读已接入演示页；语音识别通常依赖浏览器厂商的在线服务，并非完全离线。当前不支持语音 API 的浏览器会隐藏麦克风，文字输入、图片识别和数学求解不受影响。
