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
| 函数图像 JSON/SVG | `https://cfyyy.pythonanywhere.com/plot-query` |
| 浏览器直接显示图像 | `https://cfyyy.pythonanywhere.com/plot.svg` |

独立对话页及其 `/demo/api/*` 接口始终允许浏览器直接访问，不需要登录，并继续受频率限制保护。聊天历史只保存在访问者自己的浏览器 `localStorage` 中；刷新页面后仍可看到自己的记录，但不同用户不会看到彼此的对话，也不会读取扣子中的会话历史。页面使用的 KaTeX 公式资源随项目一起部署，不依赖外部 CDN。当前公网部署未启用 `MATH_API_KEY`；如果后续启用，扣子的 5 个计算工作流 HTTP 节点必须增加 `X-API-Key` 请求头，并与 PythonAnywhere 环境变量保持一致。`/demo`、`/demo/api/*`、`/health` 和浏览器显示图片用的 `/plot.svg` 始终不需要 API Key。

普通问答默认关闭。需要在独立对话页回答非数学问题时，在 PythonAnywhere 的环境变量中配置 `GENERAL_CHAT_API_URL`、`GENERAL_CHAT_API_KEY` 和 `GENERAL_CHAT_MODEL`，然后重新加载 Web 应用。配置后，非数学问题内容会发送给该模型服务；数学题仍由本项目的 SymPy 接口计算。

图片识别优先使用 OpenAI 兼容的视觉模型。线上公网当前启用 `VISION_API_BASE`（或 `VISION_API_URL`）、`VISION_API_KEY` 和 `VISION_MODEL`，扣子 OCR 作为备用链路。可选的 Windows 离线 OCR 仅在未配置任何上游服务时尝试，不会掩盖视觉服务和扣子的故障。相关变量可参考根目录的 `.env.example`。

## 扣子节点

已将修改过的工作流地址从 LocalTunnel 替换为 PythonAnywhere：

| 工作流 | 公网接口 |
| --- | --- |
| `math_verify` | `https://cfyyy.pythonanywhere.com/verify-query` |
| `math_integrate` | `https://cfyyy.pythonanywhere.com/integrate-query` |
| `math_limit` | `https://cfyyy.pythonanywhere.com/limit-query` |
| `math_solve` | `https://cfyyy.pythonanywhere.com/solve-query` |
| `math_plot` | `https://cfyyy.pythonanywhere.com/plot-query`、`https://cfyyy.pythonanywhere.com/plot.svg` |

启用 `MATH_API_KEY` 后，除 `/plot.svg` 只用于浏览器显示图片外，其余计算接口都要带 `X-API-Key` 请求头。`math_plot` 调用 `/plot-query` 时同样要带请求头；当前未启用时不需要该请求头。

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

Reload 会重启 Web 进程，因此内存中的演示会话状态和 OCR 结果缓存会被清空。浏览器 `localStorage` 中的聊天记录仍保留；用户在 Reload 后再次上传图片即可重新建立会话。

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

## 浏览器原生语音 0.6.7 上线

本轮把演示页升级为浏览器原生语音输入和回答朗读，不新增语音云服务、密钥或 WebSocket。服务端只负责返回版本 `0.6.7`；语音识别和朗读均由访问者浏览器完成。

待上传文件：

```text
app/main.py
deploy/templates/demo.html
```

发布包：

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| `app/main.py` | 28024 | `2CC2C31026B557BF809E765218CB3745F5632A7E83B0AD5216727F88C5A345E8` |
| `deploy/templates/demo.html` | 277202 | `73C8321CD73BB97DC60879F49F6F8BAA8114A2B1D14F1D4BFA7F6009B9B4084B` |

本地交付包为 `gaoshu-voice-0.6.7-20260928.zip`，大小 `60260` 字节，SHA256 为 `8DA69BBD1FFEE79E97585EDB9CD0DDD18142E91655AA064D058637897BC23D04`。上传前应先核验压缩包哈希，并确认包内只有上表两个文件。

没有 PythonAnywhere API Token 时，在 **Files** 页面进入 `/home/cfyyy/gaoshu-agent/`：

1. 先下载线上 `app/main.py` 和 `deploy/templates/demo.html` 作为回滚备份。
2. 上传本机验证过的同名文件，覆盖线上版本。
3. 进入 **Web** 页面，点击 `cfyyy.pythonanywhere.com` 对应的 **Reload**。
4. 访问 `/health`，确认返回 `version=0.6.7`。
5. 打开 `/demo`，在 Chrome、Edge 或 Safari 中验证麦克风授权、实时转写、公式核对、手动发送、回答朗读和停止朗读。

语音识别使用浏览器的 Web Speech API，识别服务是否可用、是否需要联网以及音频由谁处理取决于浏览器厂商，并不等同于完全离线识别。Firefox 或旧浏览器不提供语音 API 时，页面会隐藏麦克风按钮；文字输入、图片 OCR 和数学求解仍保持可用。回答朗读使用 `speechSynthesis`，可用音色取决于操作系统和浏览器。

验收重点：

```text
支持语音时：麦克风可见，授权后能实时转写，发送前必须人工核对。
不支持语音时：麦克风隐藏，输入区布局回到三段，文字流程正常。
回答朗读：每条已完成回答有“朗读”，播放中变为“停止”。
切换会话、清空对话、新建会话和离开页面时，语音识别与朗读停止。
```

如果回滚，重新上传备份的 `app/main.py` 和 `deploy/templates/demo.html`，再执行一次 **Reload**。

## 知微老师 UI 去模板化改版（2026-09-28 已上线）

本轮只更新演示页，保留原有三栏结构、错题集、历史对话、本地存储、图片识别、语音输入和回答朗读功能。

发布范围：

```text
deploy/templates/demo.html
```

发布结果：

| 项目 | 结果 |
| --- | --- |
| 发布时间 | `2026-09-28 22:16 +08:00` |
| 本地与线上字节数 | `292455` |
| SHA256 | `eb64e977cbfe811373dc2af44c888af349c978de4cb729c05fd1353601161ab8` |
| 上传后回读校验 | 字节数与 SHA256 一致 |
| PythonAnywhere Reload | HTTP `200`，`{"status":"OK"}` |
| 公网健康检查 | `status=ok`、`version=0.6.7`、OCR 已配置 |

发布前线上旧页面备份：

```text
C:\Users\24557\Documents\Codex\gaoshu-agent-v2\gaoshu-agent\work\pythonanywhere-backup-20260928-221556\demo.html
```

旧页面字节数为 `277202`，SHA256 为 `73C8321CD73BB97DC60879F49F6F8BAA8114A2B1D14F1D4BFA7F6009B9B4084B`。回滚时重新上传该备份并再次 Reload。

公网浏览器审计结果：

- 桌面 `1440x1000` 与手机 `390x844` 均无文档级横向溢出。
- 深色主题正常。
- “拍照识题”“批改作业”“复习错题”三个快捷入口动作正常。
- “求导 x^2”返回结构化答案，依次显示“最终结果”“解题思路”“知识点巩固”，结果为 `2*x`。
- 公网截图保存在 `C:\Users\24557\Documents\Codex\2026-09-28\ni-ha\work\ui-public-audit`。

## 暖色统一与对话语气优化（2026-09-28 已上线）

本轮统一演示页右侧聊天区与左侧两栏的暖灰纸色，弱化普通助手消息的气泡装饰，并将开场欢迎语调整为更自然的教师式语气。发布范围仍只有演示页：

```text
deploy/templates/demo.html
```

发布结果：

| 项目 | 结果 |
| --- | --- |
| 发布时间 | `2026-09-28 22:58 +08:00` |
| 本地与线上字节数 | `305575` |
| SHA256 | `81D89D7A78DF3F5764D13A1A33DCC9E71C18ACB242FEB05697CD7DDFBD469879` |
| 上传后回读校验 | 字节数与 SHA256 一致 |
| PythonAnywhere Reload | HTTP `200`，`{"status":"OK"}` |
| 公网页面 | 已确认暖色变量、新版欢迎语和旧欢迎语迁移逻辑均已生效 |
| 公网健康检查 | `status=ok`、`version=0.6.7`、OCR 已配置 |

发布前线上旧页面备份：

```text
C:\Users\24557\Documents\Codex\gaoshu-agent-v2\gaoshu-agent\work\pythonanywhere-backup-20260928-225719\demo.html
```

该备份为字节数 `302343`、SHA256 `2088154C1195CA42D69E0BDD3AFEAB1F19256E4BE0C655EC7148A19EEDA7C407` 的上一版页面。回滚时重新上传该备份并再次 Reload。固定发布脚本保存在 `work\publish-demo-ui-v7.ps1`。

## OCR 短算式与题号修复上线与回滚

本轮用于发布视觉提示词和服务端题号复核修复。待上传文件为：

```text
deploy/demo_vision.py
deploy/demo_coze_ocr.py
deploy/wsgi_app.py
```

没有 API Token 时，可以走浏览器手工路径，效果与下面的脚本流程一致：

1. 登录 PythonAnywhere，进入 **Files** 页面，打开 `/home/cfyyy/gaoshu-agent/deploy/`。
2. 先把线上 `demo_vision.py`、`demo_coze_ocr.py` 和 `wsgi_app.py` 下载到本地作为回滚备份。
3. 再上传仓库内验证过的同名文件，覆盖线上版本。请使用当前工作树中的文件，不要使用早于本轮题号间距修复的旧压缩包。
4. 切到 **Web** 页面，点击 `cfyyy.pythonanywhere.com` 对应的 **Reload** 按钮。
5. 执行下面第 4 步的短算式验证，三项都必须返回 HTTP `200`。

有 Token 时优先走下面的脚本流程，因为备份文件、上传结果和发布记录都会留在本地，便于回滚和复查。

### 2026-09-28 第二轮：题号间距修复（已发布）

本轮在短算式识别范围修复之上，继续解决 `10. 2 + 2` 被识别成 `10.2 + 2` 的问题。发布范围仍只有：

```text
deploy/demo_vision.py
deploy/demo_coze_ocr.py
```

已发布的第二轮版本：

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| `deploy/demo_vision.py` | 11275 | `8A9147D227091E0AE25D3667C1993471F7AF4F7E565C413E7470F84CF0481930` |
| `deploy/demo_coze_ocr.py` | 20247 | `9DD51AFD69946EA2E609610E4DBBC3F90FC4B62C4A944B49BC423C2D45C7FB5C` |

上线后公网复测结果（`2026-09-28T12:48Z` 前后 Reload，`/health` 为 `version=0.6.6`）：

- `probe-short-2plus2.png`（内容 `10. 2 + 2`）：HTTP `200`，`state=awaiting_ocr_confirmation`，识别文本 `10. 2 + 2`，原问题已关闭。
- `probe-clean-2plus2.png`（内容只有 `2 + 2`）：HTTP `200`，但识别文本为 `1. 2 + 2`，模型仍会补出图中不存在的题号。

两次复测都改用“同一像素、改写一个角像素后重新编码”的副本，返回 `cache_hit=false`，确保读到的是线上模型的真实输出而不是缓存。

### 2026-09-28 第四轮：视觉复核题号（已上线验收）

第三轮虽然加入了“禁止补出题号”的提示词，但提示词中把 `1. 2 + 2` 作为反例原文写出，模型会把该反例直接复现到干净图片的输出中，因此第三轮没有上传生产环境。第四轮同时做两项修复：

1. 删除提示词中可被模型照抄的 `1. 2 + 2` 反例，只保留抽象的“从图中实际可见的第一个字符开始输出”。
2. 当视觉模型对单行简单算式返回以 `1.` 开头的结果时，额外调用一次视觉复核；只有复核确认图中真实存在题号时才保留。

发布范围：

```text
deploy/demo_vision.py
deploy/demo_coze_ocr.py
deploy/wsgi_app.py
```

已上线版本：

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| `deploy/demo_vision.py` | 16329 | `826D2B57BF3C138330FF84B5C441A42F518B54A9118EA8946DF6188F8E0DA109` |
| `deploy/demo_coze_ocr.py` | 20518 | `3AB89496D114A51B9D6DB2E62F94CCEE52DE97C28A27120A8524C407DC91DF1F` |
| `deploy/wsgi_app.py` | 35018 | `830CED1AE834317CF21E34C944056569FDBBA414D762A7AC7DEAC246F988077A` |

测试文件 `tests/test_demo_page.py` 同步更新为 `85181` 字节、SHA256 `0226777C163CCB6F18CB1A654CD56F2EF759989972D7BD653078B20A8090B479`，但不上传服务器。

交付包按上述三个服务端文件生成；上线时已确认 PythonAnywhere 的文件大小与表中的字节数一致。

本地已通过提示词断言、服务端复核测试和完整回归：`141` 项测试，`137` 项通过，`4` 项跳过。第四轮已上传并 Reload，使用以下夹具完成公网验证：

```text
C:\Users\24557\Documents\Codex\2026-09-28\ni-ha\work\ocr-fixtures\probe-short-2plus2.png
```

缓存旁路夹具与验收结果：

| 夹具 | 图中内容 | 生产结果 |
| --- | --- | --- |
| `probe-short-2plus2-v4-cachebust.png` | `10. 2 + 2` | HTTP `200`、`cache_hit=false`、`awaiting_ocr_confirmation`，文本保留 `10. 2 + 2` |
| `probe-clean-2plus2-v4-cachebust.png` | `2 + 2` | HTTP `200`、`cache_hit=false`、`awaiting_ocr_confirmation`，文本为 `2 + 2`，未补出 `1.` |

模型输出可能有轻微格式差异，但题号与算式之间必须保留分隔，且不得凭空补出题号。

OCR 结果缓存以“MIME 类型 + 图片字节”的 SHA256 为键，与会话无关，所以同一张图在 10 分钟内重复上传一定返回 `cache_hit=true` 和上一轮结果。要验证提示词是否真的生效，必须让图片字节发生变化，例如改动一个角像素后重新编码，再确认响应里 `cache_hit=false`；直接重复上传同一文件无法反映最新提示词。

发布前必须在当前终端设置 PythonAnywhere API Token。Token 只放在环境变量中，不写入命令历史、文档或仓库：

```powershell
$env:PYTHONANYWHERE_API_TOKEN = "<在 PythonAnywhere 账户页面生成>"
$username = "cfyyy"
$targetRoot = "/home/cfyyy/gaoshu-agent"
$backupRoot = Join-Path $PWD "work\pythonanywhere-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
```

1. 先下载线上原文件作为回滚点。任何一项备份失败都应停止发布：

```powershell
curl.exe -fsS -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -o (Join-Path $backupRoot "demo_vision.py") `
  "https://www.pythonanywhere.com/api/v0/user/$username/files/path$targetRoot/deploy/demo_vision.py"

curl.exe -fsS -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -o (Join-Path $backupRoot "demo_coze_ocr.py") `
  "https://www.pythonanywhere.com/api/v0/user/$username/files/path$targetRoot/deploy/demo_coze_ocr.py"

curl.exe -fsS -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -o (Join-Path $backupRoot "wsgi_app.py") `
  "https://www.pythonanywhere.com/api/v0/user/$username/files/path$targetRoot/deploy/wsgi_app.py"
```

2. 上传本地验证过的三个文件：

```powershell
curl.exe -fsS -X POST -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -F "content=@deploy/demo_vision.py" `
  "https://www.pythonanywhere.com/api/v0/user/$username/files/path$targetRoot/deploy/demo_vision.py"

curl.exe -fsS -X POST -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -F "content=@deploy/demo_coze_ocr.py" `
  "https://www.pythonanywhere.com/api/v0/user/$username/files/path$targetRoot/deploy/demo_coze_ocr.py"

curl.exe -fsS -X POST -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -F "content=@deploy/wsgi_app.py" `
  "https://www.pythonanywhere.com/api/v0/user/$username/files/path$targetRoot/deploy/wsgi_app.py"
```

3. Reload Web 应用：

```powershell
curl.exe -fsS -X POST `
  -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -H "Content-Type: application/json" `
  --data "{}" `
  "https://www.pythonanywhere.com/api/v0/user/$username/webapps/cfyyy.pythonanywhere.com/reload/"
```

4. 验证健康和短算式图片。以下请求应返回 HTTP `200`、`state=awaiting_ocr_confirmation` 和 `requires_confirmation=true`；任何一项仍返回 `422` 都不能视为发布成功：

```powershell
.\.venv\Scripts\python.exe .\scripts\check_health.py

foreach ($case in @(
  @{ name = "1plus1"; image = "probe-short-context.png" },
  @{ name = "2plus2"; image = "probe-short-2plus2.png" },
  @{ name = "8divide2"; image = "probe-short-divide.png" }
)) {
  curl.exe -sS -X POST `
    -H "X-Demo-Session: release-$($case.name)-$(Get-Date -Format 'yyyyMMddHHmmss')" `
    -F "image=@C:\Users\24557\Documents\Codex\2026-09-28\ni-ha\work\ocr-fixtures\$($case.image)" `
    "https://cfyyy.pythonanywhere.com/demo/api/ocr"
  ""
}
```

5. 如果需要回滚，重新上传备份文件并再次 Reload：

```powershell
curl.exe -fsS -X POST -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -F "content=@$(Join-Path $backupRoot 'demo_vision.py')" `
  "https://www.pythonanywhere.com/api/v0/user/$username/files/path$targetRoot/deploy/demo_vision.py"

curl.exe -fsS -X POST -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -F "content=@$(Join-Path $backupRoot 'demo_coze_ocr.py')" `
  "https://www.pythonanywhere.com/api/v0/user/$username/files/path$targetRoot/deploy/demo_coze_ocr.py"

curl.exe -fsS -X POST `
  -H "Authorization: Token $env:PYTHONANYWHERE_API_TOKEN" `
  -H "Content-Type: application/json" `
  --data "{}" `
  "https://www.pythonanywhere.com/api/v0/user/$username/webapps/cfyyy.pythonanywhere.com/reload/"
```

发布记录至少保留：发布时间、源文件 SHA256、备份目录、健康检查结果、三张短算式图片的 HTTP 状态和 OCR 文本。Reload 会清空内存会话和 OCR 缓存，这是预期行为。

## 长期运行注意事项

1. 每月登录一次 PythonAnywhere。
2. 在 Web 页面点击 **Run until 1 month from today**。
3. 修改工作流后，需要分别发布工作流，再重新发布扣子智能体。
4. 定期访问 `/health`，确认服务仍返回 `"status": "ok"`。
5. 独立对话页的会话状态保存在进程内，默认 30 分钟过期、最多 500 个；OCR 结果缓存默认保留 10 分钟，Reload 后两者都会清空。

浏览器原生语音输入和回答朗读随 `0.6.7` 发布。语音识别使用 Web Speech API，通常依赖 Chrome、Edge、Safari 等浏览器厂商的在线服务，并非完全离线；不支持语音 API 的浏览器会隐藏麦克风按钮，文字与图片功能保持可用。外部监控与告警仍属于后续功能。

## 学习空间 UI 精修上线（2026-09-28 22:36 +08:00）

本轮继续收敛主聊天区的模板感，并把解答区改成高数专用学习卡片。只发布前端模板：

```text
deploy/templates/demo.html
```

发布结果：

| 项目 | 结果 |
| --- | --- |
| 本地与远端文件字节数 | `304636` |
| SHA256 | `BFF5CE7D4624BFB99E3CC63C24690E9A4AD346DE2EBF4F45087BAB541FBED34F` |
| 上传后远端回读 | 字节数与 SHA256 一致 |
| PythonAnywhere Reload | HTTP `200`，`{"status":"OK"}` |
| 公网健康检查 | `status=ok`、`version=0.6.7`、OCR 已配置 |

发布前线上旧页面备份：

```text
C:\Users\24557\Documents\Codex\gaoshu-agent-v2\gaoshu-agent\work\pythonanywhere-backup-20260928-223609\demo.html
```

备份字节数为 `292455`，SHA256 为 `EB64E977CBFE811373DC2AF44C888AF349C978DE4CB729C05FD1353601161AB8`。如需回滚，重新上传该备份并 Reload。

本轮公网页面已包含：

- 主区域“今天的草稿纸”和纸张底色 `#FAFAF8`。
- 欢迎语“嗨，我是知微 👋 今天遇到什么难啃的高数题了？发文字或拍照都行，我先帮你顺顺思路！”
- 带图标的“拍照识题”“批改作业”“复习错题”快捷入口。
- “最终结果 / 解题思路 / 知识点巩固”结构化解答卡、分步卡片和 KaTeX 公式。
- “这步没看懂”“我懂了，加入错题本”“朗读答案”操作。

公网浏览器验收结果：

- 桌面 `1440x1000` 与手机 `390x844` 均无文档级横向溢出。
- 三个快捷入口动作正常。
- “求导 x^2”返回 `2*x`，结构化分段、分步卡片、加入错题本和朗读按钮均正常。
- 截图保存在 `C:\Users\24557\Documents\Codex\2026-09-28\ni-ha\work\ui-public-audit-v5`。

发布后的完整回归为 `143` 项，`139` 项通过，`4` 项跳过。Impeccable 检测只报告整页壳层与原生对话框的 padding 误报，以及用户明确指定的纸张底色提示，不构成本轮缺陷。

## 移除服务状态胶囊上线（2026-09-28 22:42 +08:00）

本轮移除页面右上角的“服务在线 / 服务离线 / 连接中”状态胶囊，以及只服务于该胶囊的 CSS 和前端健康轮询。后端 `/demo/api/health` 保留，部署、监控和外部健康检查不受影响。

发布范围：

```text
deploy/templates/demo.html
```

发布结果：

| 项目 | 结果 |
| --- | --- |
| 发布时间 | `2026-09-28 22:42:46 +08:00` |
| 本地文件 | `302343` 字节 |
| SHA256 | `2088154C1195CA42D69E0BDD3AFEAB1F19256E4BE0C655EC7148A19EEDA7C407` |
| 上传后远端回读 | 字节数和 SHA256 均一致 |
| PythonAnywhere Reload | HTTP `200`，`{"status":"OK"}` |
| 公网首页 | HTTP `200`，不再包含 `serviceStatus`、`status-chip`、`服务在线` 或 `checkService` |
| 公网健康接口 | HTTP `200`，`status=ok`，`version=0.6.7` |

发布前线上旧页面备份：

```text
C:\Users\24557\Documents\Codex\gaoshu-agent-v2\gaoshu-agent\work\pythonanywhere-backup-20260928-224153\demo.html
```

备份文件为 `304636` 字节，SHA256 为 `BFF5CE7D4624BFB99E3CC63C24690E9A4AD346DE2EBF4F45087BAB541FBED34F`。

发布后的完整回归为 `143` 项，`139` 项通过，`4` 项按既有条件跳过。Impeccable 对 `1440x900` 和 `390x844` 公网页面复检，未新增与本次改动相关的发现。
