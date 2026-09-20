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

独立对话页及其 `/demo/api/*` 接口始终允许浏览器直接访问，不需要登录，并继续受频率限制保护。聊天历史只保存在访问者自己的浏览器 `localStorage` 中；刷新页面后仍可看到自己的记录，但不同用户不会看到彼此的对话，也不会读取扣子中的会话历史。页面使用的 KaTeX 公式资源随项目一起部署，不依赖外部 CDN。当前部署未启用 `MATH_API_KEY`，扣子请求不需要 API Key 请求头。若以后启用，
扣子 HTTP 节点必须增加 `X-API-Key` 请求头，并与环境变量保持一致。

## 扣子节点

已将修改过的工作流地址从 LocalTunnel 替换为 PythonAnywhere：

| 工作流 | 公网接口 |
| --- | --- |
| `math_verify` | `https://cfyyy.pythonanywhere.com/verify-query` |
| `math_integrate` | `https://cfyyy.pythonanywhere.com/integrate-query` |
| `math_limit` | `https://cfyyy.pythonanywhere.com/limit-query` |
| `math_solve` | `https://cfyyy.pythonanywhere.com/solve-query` |

后端接口已经全部提供；扣子账号中是否已经绑定，以工作流列表实际状态为准。建议把所有章节题型都路由到 `math_solve`，避免为每个章节重复维护 HTTP 节点。

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

部署后执行多章节回归，覆盖级数、重积分、高阶导数、微分方程、梯度、方向导数、曲线积分和曲面积分：

```powershell
.\scripts\verify-solve-regression.cmd --base-url https://cfyyy.pythonanywhere.com
```

以上接口已经验证返回 `is_correct: true`。

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

外部监控与告警、函数图像和语音仍属于后续功能。
