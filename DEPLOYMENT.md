# 固定公网部署说明

当前项目使用 PythonAnywhere 提供长期公网服务，不需要保持本机、FastAPI
进程或 LocalTunnel 隧道运行。

固定公网地址：

```text
https://cfyyy.pythonanywhere.com
```

## 服务信息

| 项目 | 配置 |
| --- | --- |
| PythonAnywhere 用户名 | `cfyyy` |
| 服务端项目目录 | `/home/cfyyy/gaoshu-agent` |
| Python 版本 | 3.13 |
| 虚拟环境 | `/home/cfyyy/gaoshu-agent/.venv` |
| WSGI 文件 | `/var/www/cfyyy_pythonanywhere_com_wsgi.py` |
| Web 框架 | Flask 同步 WSGI |

不要将 `.env`、令牌、API 密钥或学生个人数据提交到 Git 仓库。

## 图片识别（公网）

公网识图使用扣子智能体中的 `OCR / Image2text` 插件。PythonAnywhere
等 Linux 服务器不能使用 Windows 本机 OCR，因此生产环境必须在 Web
应用的环境变量中配置：

```text
COZE_API_TOKEN=<扣子访问令牌>
COZE_BOT_ID=<已发布并启用 OCR / Image2text 的机器人 ID>
COZE_API_BASE=https://api.coze.cn
COZE_TIMEOUT_SECONDS=60
COZE_POLL_INTERVAL_SECONDS=0.8
WINDOWS_OCR_FALLBACK=false
```

配置完成后重新加载 Web 应用，并上传一张正常清晰的题目图片验证
`/demo/api/ocr`。接口成功时应返回 `provider: "coze"` 和识别出的文字；
`GET /demo/api/health` 的 `ocr.configured` 应为 `true`。
如果提示 `COZE_API_TOKEN` 或 `COZE_BOT_ID` 未配置，说明服务器环境变量
尚未生效。不要把令牌写入仓库或页面代码。

使用 `render.yaml` 创建 Render Blueprint 时，`COZE_API_TOKEN` 会在部署
阶段要求填写；机器人 ID、接口地址和超时参数已经写入清单。也可以在
Render 控制台的 Environment 页面手动覆盖这些值。

Windows OCR 只用于本机 Windows 开发时的降级，识别上下标、分式、根号、
积分和导数符号的能力有限，公网服务不能依赖它。

## 公网接口

| 接口 | 地址 |
| --- | --- |
| 独立对话演示 | `https://cfyyy.pythonanywhere.com/demo` |
| 对话接口 | `https://cfyyy.pythonanywhere.com/demo/api/chat` |
| 演示页健康检查 | `https://cfyyy.pythonanywhere.com/demo/api/health` |
| 健康检查 | `https://cfyyy.pythonanywhere.com/health` |
| 求导与导数判题 | `https://cfyyy.pythonanywhere.com/verify-query` |
| 积分与积分判题 | `https://cfyyy.pythonanywhere.com/integrate-query` |
| 极限与极限判题 | `https://cfyyy.pythonanywhere.com/limit-query` |
| 章节统一求解 | `https://cfyyy.pythonanywhere.com/solve-query` |
| 函数图像 JSON/SVG | `https://cfyyy.pythonanywhere.com/plot-query` |
| 浏览器直接显示图像 | `https://cfyyy.pythonanywhere.com/plot.svg` |

独立对话页及其 `/demo/api/*` 接口始终允许浏览器直接访问，不需要登录，并继续受频率限制保护。聊天历史只保存在访问者自己的浏览器 `localStorage` 中；刷新页面后仍可看到自己的记录，但不同用户不会看到彼此的对话，也不会读取扣子中的会话历史。页面使用的 KaTeX 公式资源随项目一起部署，不依赖外部 CDN。当前公网部署已启用 `MATH_API_KEY`；扣子的 5 个计算工作流 HTTP 节点必须增加 `X-API-Key` 请求头，并与 PythonAnywhere 环境变量保持一致。`/demo`、`/demo/api/*`、`/health` 和浏览器显示图片用的 `/plot.svg` 不需要 API Key。

普通问答默认关闭。需要在独立对话页回答非数学问题时，在 PythonAnywhere 的环境变量中配置 `GENERAL_CHAT_API_URL`、`GENERAL_CHAT_API_KEY` 和 `GENERAL_CHAT_MODEL`，然后重新加载 Web 应用。配置后，非数学问题内容会发送给该模型服务；数学题仍由本项目的 SymPy 接口计算。

## 扣子节点

已将修改过的工作流地址从 LocalTunnel 替换为 PythonAnywhere：

| 工作流 | 公网接口 |
| --- | --- |
| `math_verify` | `https://cfyyy.pythonanywhere.com/verify-query` |
| `math_integrate` | `https://cfyyy.pythonanywhere.com/integrate-query` |
| `math_limit` | `https://cfyyy.pythonanywhere.com/limit-query` |
| `math_solve` | `https://cfyyy.pythonanywhere.com/solve-query` |
| `math_plot` | `https://cfyyy.pythonanywhere.com/plot-query`、`https://cfyyy.pythonanywhere.com/plot.svg` |

除 `/plot.svg` 只用于浏览器显示图片外，其余计算接口都要带 `X-API-Key` 请求头。`math_plot` 调用 `/plot-query` 时同样要带请求头。

后端接口已经全部提供；`math_verify`、`math_integrate`、`math_limit`、`math_solve`、`math_plot` 和 `knowledge_lookup` 已加入智能体。所有扩展章节题型统一路由到 `math_solve`，函数图像由 `math_plot` 处理。提示词和调用路由规则已完成统一更新并通过扣子回归测试。

`math_plot` 建议使用 `samples=80`、`width=640`、`height=360`，减少 SVG 体积并加快响应。智能体通过 `/plot.svg` 的 Markdown 图片链接显示图像。

`math_solve` 使用查询参数请求，`inputs` 传入 JSON 字符串：

```text
chapter=series
topic=sum
inputs={"expression":"1/n^2","variable":"n","lower":1,"upper":"oo"}
candidate=
```

可用的 `chapter`：`limits`、`derivatives`、`integrals`、`differential_equations`、`vectors`、`multivariable_calculus`、`multiple_integrals`、`line_surface_integrals`、`series`。

`inputs` 按题型传入，例如：导数用 `expression`、`variable`、`order`；切线用 `expression`、`point`；微分方程用 `equation`、`variable`、`function`；向量题用 `left`、`right` 或 `vector` 数组；二重积分用 `expression`、`variables`、`lower_x`、`upper_x`、`lower_y`、`upper_y`。完整题型列表可从 `/health` 的 `solve_topics` 读取。

固定公网地址不需要请求头 `bypass-tunnel-reminder`。

## 更新服务端代码

每次本地代码推送到 GitHub 后，在 PythonAnywhere 的 Bash console 执行：

```bash
cd ~/gaoshu-agent
source .venv/bin/activate
git pull
python -m pip install -r requirements.txt
cp deploy/pythonanywhere_wsgi.py /var/www/cfyyy_pythonanywhere_com_wsgi.py
```

回到 PythonAnywhere 的 **Web** 页面，点击 **Reload**。

## 部署验收

健康检查：

```bash
curl -i --max-time 25 https://cfyyy.pythonanywhere.com/health
```

应返回 `HTTP/1.1 200 OK`，响应中包含 `"status": "ok"`。

求导接口：

```bash
curl -sS -X POST --get 'https://cfyyy.pythonanywhere.com/verify-query' --data-urlencode 'expression=x^2' --data-urlencode 'variable=x' --data-urlencode 'candidate=2x'
```

积分接口：

```bash
curl -sS -X POST --get 'https://cfyyy.pythonanywhere.com/integrate-query' --data-urlencode 'expression=x^2' --data-urlencode 'variable=x' --data-urlencode 'candidate=x^3/3'
```

极限接口：

```bash
curl -sS -X POST --get 'https://cfyyy.pythonanywhere.com/limit-query' --data-urlencode 'expression=sin(x)/x' --data-urlencode 'variable=x' --data-urlencode 'point=0' --data-urlencode 'candidate=1'
```

章节统一求解接口：

```bash
curl -sS -X POST --get 'https://cfyyy.pythonanywhere.com/solve-query' \
  --data-urlencode 'chapter=series' \
  --data-urlencode 'topic=convergence' \
  --data-urlencode 'inputs={"expression":"1/n^2","variable":"n"}'
```

函数图像接口：

```bash
curl -sS -X POST --get 'https://cfyyy.pythonanywhere.com/plot-query' \
  --data-urlencode 'expression=sin(x)' \
  --data-urlencode 'x_min=-3' \
  --data-urlencode 'x_max=3'

curl -sS --get 'https://cfyyy.pythonanywhere.com/plot.svg' \
  --data-urlencode 'expression=x^2' \
  --data-urlencode 'x_min=-5' \
  --data-urlencode 'x_max=5'
```

部署后执行多章节回归，覆盖级数、重积分、高阶导数、微分方程、梯度、方向导数、曲线积分和曲面积分：

```powershell
.\scripts\verify-solve-regression.cmd --base-url https://cfyyy.pythonanywhere.com
```

以上接口已经验证返回 `is_correct: true`。

极限接口回归，覆盖普通极限、无穷极限、左右极限和候选答案判断：

```powershell
.\scripts\verify-limit-regression.cmd --base-url https://cfyyy.pythonanywhere.com
```

对话接口：

```bash
curl -sS -X POST 'https://cfyyy.pythonanywhere.com/demo/api/chat' \
  -H 'Content-Type: application/json' \
  -d '{"message":"积分 0 到 1 x^2"}'
```

应返回 `"status": "ok"`，并包含 `"intent": "integrate"` 和 `"integral": "1/3"`。

演示页验收：

```text
https://cfyyy.pythonanywhere.com/demo
https://cfyyy.pythonanywhere.com/demo/api/health
```

页面应能直接打开，不要求登录或 API Key。依次发送“求导 x^2”“积分 x^2”“积分 0 到 1 x^2”和“lim x→0 sin(x)/x”，应看到知微老师的对话回复、可正常渲染的数学公式和计算结果。发送几条消息后刷新页面，当前浏览器仍应保留自己的记录；点击“清空对话”后记录应被删除。

## 长期运行注意事项

1. 每月登录一次 PythonAnywhere。
2. 在 Web 页面点击 **Run until 1 month from today**。
3. 修改工作流后，需要分别发布工作流，再重新发布扣子智能体。
4. 定期访问 `/health`，确认服务仍返回 `"status": "ok"`。

外部监控与告警和语音仍属于后续功能。
