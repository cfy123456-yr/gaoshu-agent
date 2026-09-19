# 知微高等数学学伴

面向大学理工科学生的高等数学教育智能体项目。第一阶段覆盖导数与微分、不定积分和定积分。

项目采用“大模型负责教学表达，SymPy 负责确定性计算，知识库负责概念和教材依据”的架构。

## 当前功能

- 通过扣子智能体提供“知微老师”中文对话。
- 使用 `math_verify` 工作流计算导数并判断学生答案。
- 使用 `math_integrate` 工作流计算不定积分、定积分并判断学生答案。
- 使用 `knowledge_lookup` 工作流检索导数、微分和积分知识。
- FastAPI 数学服务同时提供 JSON 和查询参数两种调用方式。
- 数学表达式支持 `x^2`、`x**2`、`3x` 和 `3*x` 等常见写法。

## 项目结构

```text
gaoshu-agent/
├─ app/
│  └─ main.py
├─ knowledge/
│  ├─ 01_导数与微分基础.md
│  └─ 02_积分基础.md
├─ tools/
│  └─ cloudflared.exe
├─ .gitignore
├─ README.md
└─ requirements.txt
```

`tools/`、`.venv/`、缓存文件和 `.env` 不进入 Git 仓库。

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

## 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

开发时可增加自动重载：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

服务启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`

## 接口说明

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

## 扣子工作流

| 工作流 | 用途 | 后端接口 |
| --- | --- | --- |
| `math_verify` | 求导、导数答案判断 | `/verify-query` |
| `math_integrate` | 不定积分、定积分、积分答案判断 | `/integrate-query` |
| `knowledge_lookup` | 检索高数知识库 | 扣子知识库 |

## 知识库

- `01_导数与微分基础.md`：导数定义、求导公式、求导法则、微分和常见错误。
- `02_积分基础.md`：原函数、不定积分、定积分、换元法、分部积分法和常见错误。

## 安全说明

当前接口主要用于本地开发和作品演示，公开发布前还需要增加：

- API 鉴权。
- 请求频率限制。
- 表达式长度限制。
- 计算超时。
- 日志、监控和密钥管理。

不要将 `.env`、令牌、API 密钥或个人学生数据提交到 Git 仓库。

## 当前状态

已实现文字对话、导数与积分计算、答案判断、知识库检索和多轮上下文测试。OCR、语音、稳定公网部署、独立前端和参赛材料仍在后续开发中。
