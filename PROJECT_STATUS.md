# 知微高数项目状态

更新时间：2026-11-25（Asia/Shanghai）

## 当前事实

| 项目 | 当前状态 |
| --- | --- |
| 服务版本 | `0.6.11` |
| 固定公网地址 | `https://cfyyy.pythonanywhere.com` |
| 无需登录演示页 | `https://cfyyy.pythonanywhere.com/demo` |
| 公网演示页前端 | 已发布问答模式与教学模式双模式版 |
| `MATH_API_KEY` | 当前未启用 |
| OCR 主链路 | 阿里云百炼视觉模型 |
| 视觉模型 | `dashscope` / `qwen3-vl-plus` |
| 普通问答模型 | `dashscope` / `qwen-plus`，复用视觉密钥 |
| 百炼免费额度（普通问答） | `qwen-plus` 剩余 `949,950 / 1,000,000`（`95%`），到期 `2026-12-24` |
| 百炼免费额度（视觉） | `qwen3-vl-plus` 剩余 `879,921 / 1,000,000`（`88%`），到期 `2026-12-24` |
| 百炼账户余额 | 截图核对约 `¥10`；实际可用余额与计费口径以费用中心账单为准 |
| 免费额度耗尽策略 | `qwen-plus` 与 `qwen3-vl-plus` 均已启用“免费额度用尽即停” |
| 百炼公开限流（普通问答） | 华北 2（北京）`qwen-plus`：`30,000 RPM / 5,000,000 TPM` |
| 百炼公开限流（视觉） | 华北 2（北京）`qwen3-vl-plus`：`3,000 RPM / 5,000,000 TPM` |
| OCR 备用链路 | 扣子 OCR，当前已配置 |
| Windows 离线 OCR | 公网未启用，仅作为未配置任何上游时的本地降级；调用时优先 PowerShell 7，必要时回退 Windows PowerShell 5.1 |
| 持久化日志 | 公网当前未启用 |
| 服务端会话 | 进程内存，30 分钟过期，最多 500 个 |
| OCR 结果缓存 | 进程内存，10 分钟过期 |
| 浏览器语音 | Web Speech API，中文识别加回答朗读 |
| 本地启动方式 | `scripts/start-demo.cmd` 使用 PowerShell 7；优先 Uvicorn，不可用时自动降级到 Flask WSGI |
| 扣子知识库 | ID `7687143690564796426`，13 个同济大学教材文件、496 个分段 |
| 扣子工作流 | 五条计算工作流均已发布，已移除旧 `X-API-Key` 请求头 |
| 最近完整测试 | `312` 项，`312` 项通过，结果为 `OK` |
| 版本入库状态 | `0.6.11` 已加入中文数学归一化、同济教材知识库、安全图片 URL 视觉 OCR、统一 solution gate 和 PythonAnywhere 动态加载修复；本轮源码整理随本次提交入库，并由同提交的 GitHub Actions 复核 |

## 2026-11-25 P0 核心修复

- 统一 solution gate 已集中到 `app/solution_gate.py`：只有 `status=ok`、合法求解
  `intent`、`verified=true`、`verification.passed=true`、全部验算检查通过、计算明细
  存在且独立复算通过时，结果才可进入主回答、教学步骤、知识点和错题本。
- 主回答、教学模式、知识点推荐与错题本现在共享同一份经门禁验证的 solution；求解
  失败时不再继续生成教学步骤、知识点卡片或最终答案。
- 数学输入规范化已覆盖 `cos(2t)` / `cos(2*t)`、中文正负无穷与 `∞`、中文乘法、根号、
  分数和上下标等常见写法；规范化只在明确的数学上下文中转换，不强行拆分函数名。
- 普通章节回答已移除泛化占位文本，改为展示实际输入、实际结果和方法说明；新增自然
  语言显式曲线切线识别，仍由 SymPy 求解和统一门禁验证，不硬编码最终答案。
- 修复水平切线对应法线的确定性求解与独立验算错误：`y=x^2` 在 `x=0` 处的正确法线
  为 `x=0`，不再是错误的 `y=0`。
- 新增参数方程切线与法线正向测试、六类缺少必要条件负面测试、五次重复提交稳定性
  测试，以及手动输入与“OCR 识别结果确认后”求解路径一致性测试。
- 网页输入区新增可折叠“输入提示”和五个可直接填入的规范示例，覆盖定积分、极限、
  偏导数、微分方程和无穷级数；示例只填入输入框，不自动发送。
- 修复自然语言词序识别：`x平方在0到1上的定积分` 可识别为定积分，
  `sin(x)/x 在 x趋于0 时的极限` 可识别为极限；页面同时明确说明自然语言可识别。
- 最新真实本地 HTTP 验收通过 `190/190`，记录位于
  `work/p0-http-acceptance.json` 和 `work/p0-http-acceptance.md`。
- 聚焦回归通过 `239/239`，最新完整单元测试通过 `312/312`，结果均为 `OK`。
- 真实主页脚本连续运行 `3` 次均通过，覆盖重复简单题、复杂极限、定积分、口语积分、
  求导、极限、连续追问、教学首步保护、OCR 编辑确认和移动端布局。
- 本地服务与公网 `/health` 均返回 `0.6.11`。用户提供的两张 GitHub 截图对应
  同一个 `Public regression` 失败事件及其 QQ 邮件通知，不是两个独立故障。
- 旧提交 `348f430` 的失败根因是工作流仍断言 `0.6.7`；远端提交 `6651932`
  的后续失败已另行定位到部署验收第 `11/11` 项：脚本使用 `example.com`
  作为非图片探测地址，PythonAnywhere 访问该第三方站点失败并返回预期的
  `502`，而脚本只接受 `400`。这不是 OCR、求解或版本断言故障。
- 部署验收的非图片探测地址已改为仓库内稳定文本文件，并在
  `.github/workflows/public-regression.yml` 中绑定当前 `github.sha`，避免
  第三方站点不可达、`main` 缓存和提交漂移影响结果。远程 OCR 图片地址同样
  绑定当前提交。
- 公网回归验收期间额外观测到一次 `/demo` 页面 20 秒瞬态超时，立即复测时页面
  耗时 `6.51` 秒且返回 HTTP `200`。GitHub Actions 的部署验收请求上限已调整为
  `60` 秒，既覆盖 PythonAnywhere 偶发慢响应，也保持在单作业 10 分钟上限内。
- 修复后实际公网验收 `11/11` 通过，包含真实视觉 OCR 识别；公网极限回归
  `6/6`、章节求解回归 `9/9`、固定种子随机回归全部通过。
- 旧失败运行会保留失败历史，最终以本次提交触发的 `Test suite`、
  `Public health check` 和 `Public regression` 新运行结果为准。
- 桌面与手机视口的浅色/深色四场景 Playwright 检查通过：提示展开与收起、示例填入、
  模式切换正常，无重叠、横向溢出、脚本错误或示例自动提交；记录位于
  `work/visual-check-20261125/report.json`。
- 本轮已在真实公网服务上完成远程图片 OCR 与 SSRF 防护验收，但未修改公网应用
  代码、未重新部署 PythonAnywhere，也未开展 PPT 或 P1 全章节大规模修复。

## 2026-11-24 扣子后端整改

- 新增中文口语数学归一化：平方、立方、任意次方、根号、除法、乘法、加减法、分数和 Unicode 上下标会在后端解析前统一转换。
- 扣子智能体只抽取学生原话作为参数，不得先把“x的平方”“根号下x”“sinx除以x”等片段改写成猜测公式。
- `COZE_WORKFLOWS.md` 已统一 `math_verify`、`math_integrate`、`math_limit`、`math_solve`、`math_plot`、`knowledge_lookup` 和 `ocr_question` 的字段、接口与测试契约。
- 知识库检索只读取 `knowledge/` 下同济大学《高等数学》第 1—12 章；目录文件 `00_教材目录与编写规则.md` 只用于上传说明，不参与检索。
- “定义/概念/含义”类问题增加标题命中加权，“定积分的定义”优先返回 `knowledge/05_定积分.md` 的“三、定积分的概念”。
- 本地完整回归为 `214` 项、`210` 项通过、`4` 项可选测试跳过，结果为 `OK`。
- `2026-11-24 19:21:29 +08:00` 已发布公网 `app/math_text.py`，文件大小 `10890` 字节，SHA256 `6B1339E27887F40D21EB6B3784E390BADBEFD757C597DDB89E61E204B6796019`；远端回读一致，Reload 返回 HTTP `200`。
- 扣子知识库已整体替换为同济大学《高等数学》教材：知识库 ID `7687143690564796426`，共 13 个教材文件、496 个分段。
- 扣子提示词已更新到后端 `v0.6.11` 并发布；五条工作流均已完成发布：
  `math_verify v0.0.10`、`math_integrate v0.0.7`、`math_limit v0.0.5`、
  `math_solve v0.0.4`、`math_plot v0.0.7`。
- 五条工作流已清理旧请求头 `X-API-Key` 和 `bypass-tunnel-reminder`，保留
  `Accept` 与必要的 `Content-Type`；发布后用扣子 UI 逐条试运行，平方、积分、
  根号、极限、级数收敛和函数绘图均返回预期结果。
- 公网健康检查返回 `version=0.6.10`；部署验收 `10/10`、极限回归 `6/6`、
  章节求解回归 `9/9` 和固定种子随机回归全部通过。
- 公网 `/demo` 曾因 PythonAnywhere WSGI 启动器未把动态加载模块登记到
  `sys.modules` 而返回 HTTP `500`，错误为 `TemplateNotFound: demo.html`。现已把
  Flask 模板和静态目录固定为基于 `deploy/wsgi_app.py` 的绝对路径，并新增动态加载
  回归测试。
- `2026-11-24 20:20:53 +08:00` 已发布修复后的 `deploy/wsgi_app.py`，文件大小
  `37570` 字节，SHA256 `624D84747A8B35B75D550918E62E2E89743C06988912C8ADFA740CF8F8AE696B`。
  远端回读一致，Reload 返回 HTTP `200`，公网 `/demo` 返回 HTTP `200`，页面
  `313465` 字节且验收标记完整。
- `2026-11-24 23:22 +08:00` 已补齐公网双模式依赖并 Reload：`app/main.py`、
  `app/chapter_solvers.py`、`deploy/demo_chat.py`、`deploy/demo_coze_ocr.py` 和
  `deploy/demo_remote_image.py` 均完成远端回读，随后公网 `/demo` 恢复 HTTP `200`。
- 公网双模式浏览器验收通过：问答默认选中、教学模式逐步作答、错答提示、获取提示、
  跳过、完成、重新开始、切回问答均已验证；桌面和移动端无横向溢出，控制台、页面脚本
  与 HTTP 响应无新增错误。报告保存在 `work/public-teaching-check/report.json`。

## 2026-09-29 核查与推进

启动本地后端后复跑完整回归，合并 Gitee 新增题号测试并补入移动端加固、慢请求反馈和
部署标记测试后的结果：

```text
Ran 166 tests in 6.717s
OK (skipped=4)
```

本轮完成移动端与图片识别稳定性加固：

- 演示页声明 `interactive-widget=resizes-content`，并在小屏下监听
  `visualViewport`，让应用高度跟随软键盘和可视视口变化。
- 应用外壳补充左右安全区，图片预览区限制为相对视口的最大高度，避免横屏刘海遮挡
  和键盘弹出后底部操作区被覆盖。
- 图片 OCR 增加 `90` 秒客户端超时，超时后显示明确恢复提示；正常完成、手动取消和
  超时三条路径都会清理计时器。
- 新增 `test_demo_page_handles_mobile_viewport_and_ocr_timeout` 固定上述行为。
- Edge 实渲染检查通过：桌面 `1440 px` 与小屏断点均完整显示输入区和发送按钮；
  页面内联脚本通过 Node 语法解析。
- 公网健康检查从约 `45` 秒的短重试改为可配置的长重试：默认最多 `5` 次、每次
  超时 `20` 秒、失败间隔 `10` 秒；健康检查工作流、检查脚本或部署代码变更时会
  立即触发，不再只依赖最长达数小时的稀疏定时任务。新增两项单元测试覆盖恢复和
  最终失败路径。
- 双远端同步 `908b51a` 后，`push` 触发的第 `55` 次 `Public health check`
  于 `2026-09-29T11:28:41Z` 启动、`11:28:47Z` 成功，运行地址为
  `https://github.com/cfy123456-yr/gaoshu-agent/actions/runs/36561980402`。
- 新增 GitHub Actions `Test suite`：推送 `main` 或提交拉取请求时，在干净的
  Python 3.13 环境启动 Flask WSGI 服务并复跑完整单元测试。
- 第 `1` 次 `Test suite` 基于 `4970cb0d5b9041b559687b453246a4a8e995acd4`
  于 `2026-09-29T11:30:15Z` 启动、`11:30:49Z` 成功，运行地址为
  `https://github.com/cfy123456-yr/gaoshu-agent/actions/runs/36562144014`。
- 新增 `scripts/publish-pythonanywhere-file.ps1`，把单文件发布固定为备份、上传、
  远端回读、Reload 和公网标记验证五步；本地 `-ValidateOnly` 与 `-WhatIf` 预演
  均通过。
- 本地启动与停止脚本改为统一调用 PowerShell 7：`start-demo.cmd` 和
  `stop-demo.cmd` 不再通过 Windows PowerShell 5.1 启动；`work` 目录固定在当前
  仓库下，不再误写到仓库的父目录。
- `start-demo.ps1` 移除已废弃的 LocalTunnel/npx 逻辑，优先使用 Uvicorn，发现
  `a2wsgi` 或 Uvicorn 不可用时自动改用与 PythonAnywhere 相同的 Flask WSGI
  入口；`stop-demo.ps1` 只停止本地 `127.0.0.1:8000` 数学服务。
- 新增 `tests/test_launchers.py`，固定 PowerShell 7、仓库内 `work` 目录、Flask
  降级入口和停止脚本边界；完整测试因此从 `160` 项增加到 `164` 项。
- Windows 离线 OCR 改为优先调用 PowerShell 7；只有 PowerShell 7 无法加载 WinRT
  `Windows.Media.Ocr.OcrEngine` 并返回失败时，才回退 Windows PowerShell 5.1。
  新增两项单元测试，固定候选顺序、仅在 7 失败后回退，以及 7 成功时不启动 5.1；
  完整测试因此从 `164` 项增加到 `166` 项。
- `2026-09-29 19:38:38` 完成移动端加固前端发布：远端文件与本地 `310730` 字节、
  SHA256 `7C106596B33FE5F7E8743AC683383507B5A8A2658DA8B2C8846D9359A03FB0DF`
  完全一致，Reload 返回 HTTP `200`，公网 `/demo` 返回 HTTP `200`，并确认包含
  `interactive-widget=resizes-content`、`window.visualViewport` 和
  `OCR_REQUEST_TIMEOUT_MS = 90000`。发布旧文件已备份到
  `work/pythonanywhere-backup-20260929-193745/`。
- `2026-09-29 20:51:37` 完成慢请求进度提示前端发布：远端文件与本地 `311840` 字节、
  SHA256 `4D6CA7FAAB283EEA8C66ACBE9BA245140C56EA9CE588C71F9895E8D4271B8EFD`
  完全一致，Reload 返回 HTTP `200`，公网 `/demo` 返回 HTTP `200` 且包含五项必需
  标记。发布前旧版已备份到
  `work/pythonanywhere-backup-20260929-205027/demo.html`；公网响应归一化后为
  `302077` 字节，SHA256
  `3B529BFD43E05251B70EE8F28FD33780855C13DA93CC4748972659530A6BDC05`。
- 使用 Edge 真实渲染检查长题干、无空格长串和长输入内容，覆盖 `390x844`、
  `360x640` 与 `1440x900`；页面、消息气泡、文本节点和输入区均无横向溢出。

`2026-09-29` 继续推进模型链路验收：

- 用户已在真实手机上完成语音人工验收，浏览器中文语音输入、转写核对、手动发送和
  回答朗读均可用。
- 公网普通问答实测正常但响应偏慢：“帮我制定一份复习计划”返回 `intent=general`、
  `status=ok`，耗时约 `10.784s`；询问底层模型时返回 `status=ok`，模型自述为
  `Qwen3`，耗时约 `5.232s`。
- `/demo/api/health` 已扩展非敏感模型元数据：视觉链路返回提供商、模型名和备用链路
  状态，普通问答返回是否启用、提供商、模型名、密钥来源和超时；`key_source` 区分
  `dedicated`、`vision_fallback` 和 `missing`，不会返回密钥内容。
- 部署验收脚本已加入模型健康断言，后续发布会在普通接口回归前直接确认视觉模型和
  普通问答模型均已配置，且模型名、提供商和密钥来源合法。
- 模型健康与部署断言改动完成后，本地完整回归为 `172` 项、`168` 项通过、
  `4` 项可选测试跳过。
- `2026-09-29 21:30` 前后已逐文件发布 `deploy/demo_chat.py`、`deploy/demo_vision.py`
  和 `deploy/wsgi_app.py`：三次远端回读均与本地 SHA256 完全一致，最后一个文件
  Reload 返回 HTTP `200`，公网健康页立即包含 `general_chat`、`vision_model` 和
  `key_source` 标记。
- 公网健康接口现在确认视觉链路为 `dashscope/qwen3-vl-plus`，普通问答为
  `dashscope/qwen-plus`，`key_source=vision_fallback`，超时 `30s`；扣子 OCR
  备用链路仍为已配置状态。
- 新版部署验收 `10/10` 通过，其中模型健康断言已实际执行；普通问答复测
  “帮我制定一份复习计划”耗时约 `7.839s`，“你底层使用的是什么模型？只回答模型名称”
  耗时约 `4.756s`，两项均返回 `intent=general`、`status=ok`。
- 模型发布后的公网回归继续全部通过：极限固定回归 `6/6`、章节统一求解固定回归
  `9/9`、固定种子随机回归全部通过。
- 模型健康改动提交 `35bd3d7` 已同步到 Gitee 与 GitHub，两个远端 `main` SHA
  完全一致；GitHub Actions 三个推送工作流全部成功：
  `Test suite` 运行 `36575895778`、`Public regression` 运行 `36575895754`、
  `Public health check` 运行 `36575895815`。

### 百炼控制台与限流核对（2026-09-29 21:47）

- 普通问答模型 `qwen-plus` 的免费额度显示剩余 `95%`，即
  `949,950 / 1,000,000`，到期时间为 `2026-12-24`。
- 视觉模型 `qwen3-vl-plus` 的免费额度显示剩余 `88%`，即
  `879,921 / 1,000,000`，到期时间为 `2026-12-24`。
- 用户已确认两个模型的“免费额度用尽即停”开关均已打开。免费额度耗尽后将按该策略停止，
  不再继续消耗账户余额；上线期间仍需关注模型告警和状态，避免额度耗尽造成服务中断。
- 账户余额截图显示约 `¥10`，金额较小。以上额度与余额均为控制台展示值，实际计费、
  抵扣和可用余额应以费用中心账单为准。
- 模型监控选择“最近 6 小时、实时推理、全部 API Key”：共 `2` 个模型、`8` 次调用、
  `0` 次失败，平均调用时长 `2.4s`；`qwen-plus` 为 `6` 次、`2.67s`，
  `qwen3-vl-plus` 为 `2` 次、`1.42s`。该窗口样本较小且监控页明确说明数据仅供参考，
  不能替代完整计费账单或长期稳定性结论。
- 三张截图未提供 `QPS`、`TPM` 或其他具体限流值；现已从官方《限流》文档确认华北 2
  （北京）公开额度：`qwen-plus` 为 `30,000 RPM / 5,000,000 TPM`，
  `qwen3-vl-plus` 为 `3,000 RPM / 5,000,000 TPM`。
- 官方说明限流条件按每分钟显示，服务也可能按 `RPS = RPM / 60` 和
  `TPS = TPM / 60` 执行。因此上述数字应作为每分钟约束及潜在秒级上限理解，不能视为
  永久固定且不会变化的实际 QPS 承诺。
- 百炼控制台的“运维管理 > 模型监控”用于查看实际调用量、失败数和耗时，不展示模型
  公开限流表；限流表查看地址为
  `https://help.aliyun.com/zh/model-studio/rate-limit`。

### 模型异常提示细化（2026-09-29 已上线）

- 普通问答与图片识别现已分别处理 `401`、`403` 和 `429`：鉴权失败、免费额度耗尽或
  服务暂停、请求过于频繁都会返回可区分的用户提示；普通问答额外覆盖上游 `5xx`
  和网络、超时等连接异常。
- `403` 提示会明确指向百炼控制台的额度与“免费额度用尽即停”策略，便于线上服务因
  额度耗尽暂停时快速定位，不再与临时限流混为同一种错误。
- 新增 `2` 项模型异常分支测试，完整回归为 `174` 项、`170` 项通过、`4` 项可选测试
  跳过，结果为 `OK`。
- `2026-09-29 21:54` 至 `21:55` 已逐文件发布：`demo_chat.py` 为 `99908` 字节、
  SHA256 `B218F14BD1AFF73F91F24FEE99C248ED1D990C59486F46B4603A78AFD93A0E2F`，
  `demo_vision.py` 为 `16920` 字节、
  SHA256 `127462EAF7C95363AD03EF97173918D963A2C3C16833E29D9C7A2A508F5D9253`；
  两次远端回读均与本地一致，最后一次 Reload 返回 HTTP `200`。
- 发布前旧版本已分别备份到
  `work/pythonanywhere-backup-20260929-215434/demo_chat.py`（`98696` 字节）和
  `work/pythonanywhere-backup-20260929-215448/demo_vision.py`（`16719` 字节）。
- 公网复测通过：`/health` 返回 `version=0.6.7`；`/demo/api/health` 确认视觉模型为
  `dashscope/qwen3-vl-plus`、普通问答为 `dashscope/qwen-plus`、密钥来源为
  `vision_fallback`；公网部署验收 `10/10`，演示页返回 HTTP `200` 且必需前端标记完整。

当前 `.venv` 中 `a2wsgi` 文件仍被 Windows 旧 ACL 拒绝读取，`uvicorn` 因此无法导入。
本地启动脚本现已自动检测并改用与 PythonAnywhere 部署相同的 Flask WSGI 入口，不再
阻塞日常演示和测试；若需要恢复 Uvicorn，应重建 `.venv` 后重新安装依赖。

公网固定回归全部通过：

- 部署验收 `10/10` 通过，API Key 鉴权因当前未启用而跳过。
- 极限固定回归 `6/6` 通过。
- 章节统一求解固定回归 `9/9` 通过。
- 固定种子随机回归通过：随机多项式、区间最值、有理算术和章节主题均正常。

2026-09-29 本轮再次复跑上述四组公网回归，结果保持不变：

- 部署验收 `10/10` 通过，仍跳过尚未启用的 API Key 鉴权。
- 极限固定回归 `6/6` 通过。
- 章节统一求解固定回归 `9/9` 通过。
- 固定种子随机回归全部通过。

新前端发布后再次复跑四组公网回归，结果仍全部通过：部署验收 `10/10`、极限固定回归
`6/6`、章节统一求解固定回归 `9/9`、固定种子随机回归全部通过。公网 `/demo`
响应为 `302077` 字节，服务器端模板换行归一化后的页面 SHA256 为
`3B529BFD43E05251B70EE8F28FD33780855C13DA93CC4748972659530A6BDC05`。
- `3d181da` 已同步到 Gitee 和 GitHub；GitHub Actions 第 `10` 次 `Test suite` 与
  第 `4` 次 `Public regression` 均基于该提交完成并成功。
- `5f1bbc3` 的提交材料已同步到 Gitee 和 GitHub；GitHub Actions `Test suite`
  于 `2026-09-29T13:02:35Z` 基于 `9edc23d` 启动并成功，地址为
  `https://github.com/cfy123456-yr/gaoshu-agent/actions/runs/36572249733`。
持久化 JSONL 日志在演示阶段继续关闭。当前公网使用 PythonAnywhere 自带的访问与错误
日志，配合 GitHub Actions 健康检查和四组公网回归已覆盖稳定性观察；开启额外日志会
引入重复记录和长期磁盘占用，收益不足。正式发布前如需审计请求耗时和错误类型，再在
PythonAnywhere 环境中设置 `LOG_ENABLED=true`，确认日志轮转和 `/health` 状态后启用。

提交前审计结论：

- 本轮提交内容集中在 Windows 离线 OCR 的 PowerShell 7 优先调用、测试以及当前
  状态和部署基线说明。
- 未在高置信度密钥模式下发现待提交跟踪文件包含 Token、API Key 或私钥。
- `.gitignore` 已补充忽略 `.test-*`、`.tmp-*` 和 `work/`，避免测试安装器、临时输出、发布产物和浏览器会话探测目录进入版本库。
- 推送前已确认两个远端都包含此前整合历史；本轮提交后再同步 GitHub 与 Gitee，
  并以远端 `main` SHA 和 GitHub Actions 结果作为仓库收尾条件。

下一步持续收集移动端使用反馈；正式发布前再启用 `MATH_API_KEY` 和持久化日志，并
同步检查扣子工作流请求头。扣子提示词回填、云平台额度、停止策略、公开限流和本次
模型异常提示部署均已完成；代码、启动、测试和部署说明继续以仓库自动化结果为准。

## 已完成能力

- 求导、积分、极限和候选答案判断。
- 函数图像 JSON 与 SVG 输出。
- 章节统一求解，覆盖极限、导数、积分、微分方程、向量、多元函数微分、重积分、曲线曲面积分和级数等题型。
- 基础四则运算、区间最值、分数与小数输入。
- 无需登录的独立演示页，支持数学求解、普通问答、函数图像和浏览器本地聊天记录。
- 演示页支持浏览器原生中文语音输入，转写只进入输入框，核对后手动发送。
- 已完成助手回答朗读，可逐条开始或停止，不支持语音 API 的浏览器会自动隐藏麦克风。
- 两阶段 OCR：先识别并等待确认，确认后才使用确定性求解器计算。
- 多题图片识别、题目选择、失败清理、重复图片缓存和坏图后恢复。
- PythonAnywhere 固定公网部署，健康检查和版本校验脚本。
- 公网视觉 OCR，扣子 OCR 备用，Windows OCR 仅作最后降级。

## 历史验证快照（2026-09-28）

验证时间：2026-09-28 21:22 至 21:25（Asia/Shanghai）。

### 本地完整测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：运行 `142` 项，`138` 项通过，`4` 项跳过，`OK (skipped=4)`。

跳过项是旧版显式曲线/曲面积分用例，当前属于可选项，不影响现有公网部署。

本次快照中的浏览器语音定向测试共 `94` 项，全部通过，其中 `4` 项沿用上述可选跳过；
已确认语音识别、回答朗读、能力降级和页面切换清理逻辑均包含在演示页回归中。

使用本地部署入口进行浏览器冒烟检查：桌面 `1440 px`、小屏 `640 px` 和等效 `390 px` CSS 视口均正常渲染，麦克风与“朗读”入口可见，输入区和操作按钮没有横向溢出。该检查不包含真实麦克风授权、实际语音转写和系统音色播放，仍需在 Chrome、Edge 或 Safari 中人工验收。

### 公网固定回归

```powershell
.\scripts\verify-deployment.cmd --base-url https://cfyyy.pythonanywhere.com
.\scripts\verify-limit-regression.cmd --base-url https://cfyyy.pythonanywhere.com
.\scripts\verify-solve-regression.cmd --base-url https://cfyyy.pythonanywhere.com
.\.venv\Scripts\python.exe .\scripts\verify_random_regression.py --base-url https://cfyyy.pythonanywhere.com
```

结果：

- 部署验收 `10/10` 通过，其中 API Key 鉴权因当前未启用而跳过。
- 极限固定回归 `6/6` 通过。
- 章节统一求解固定回归 `9/9` 通过。
- 固定种子随机回归通过：4 组随机多项式、4 组区间最值、4 组有理算术、3 个随机章节题。

### 公网 OCR 与普通问答

使用清晰单题、模糊单题、多题整页和损坏 PNG 进行实测：

- 清晰极限图：视觉识别正确，首次请求 `1637 ms`，重复请求命中缓存。
- 模糊定积分图：视觉识别正确。
- 多题整页：正确识别 3 道独立题目，返回 `awaiting_question_selection`。
- 损坏 PNG：返回 `422`，未包含旧识别结果。
- 失败后重传好图：恢复到 `awaiting_ocr_confirmation`，识别文本一致。
- 普通问答：`/demo/api/chat` 返回 `intent=general`，模型回答正常。

随后执行 12 类 OCR 固定矩阵，结果为 9 项接受、3 项拒绝：

- 接受：清晰、模糊、多题、低对比度、旋转 8°、复杂公式、手写风格、分数算术、偏置图。
- 拒绝：旋转 18°、遮挡图、短算式 `10. 1 + 1`。
- 旋转 8° 虽然接受，但题号 `5.` 被误识别为 `24、`，仍需提示模型提高题号稳定性。

短算式 `422` 的根因已经定位：后端 `is_valid_ocr_question("1+1")` 和单元测试均通过，原先的视觉提示词却把识别范围限定为“高等数学题目”，导致基础算术被模型主动拒绝。`deploy/demo_vision.py` 与 `deploy/demo_coze_ocr.py` 已在本地源码中改为接受基础算术、代数、几何等所有可计算数学题，并新增提示词断言测试；定向测试和完整回归均通过。

该修复已于 2026-09-28 20:40 前后手工上传到 PythonAnywhere 的 `/home/cfyyy/gaoshu-agent/deploy/` 并 Reload，线上两个文件的字节数与本地修复版一致（`demo_vision.py` 11109 字节、`demo_coze_ocr.py` 20078 字节）。修复前这两段提示词只接受“高等数学题目”，公网对短算式一律返回 `422`；上线后同样的图片全部改为 `200`。

生产端上线后复测（`2026-09-28T12:41Z` 起，服务版本 `0.6.6`）：

- `probe-short-2plus2.png`：HTTP `200`，`2057 ms`，`state=awaiting_ocr_confirmation`。
- `probe-short-divide.png`：HTTP `200`，`2677 ms`，`state=awaiting_ocr_confirmation`。
- `probe-short-context.png`：HTTP `200`，`5034 ms`，`state=awaiting_ocr_confirmation`。
- 另生成不含题号的干净图 `probe-clean-2plus2.png`：HTTP `200`，`9463 ms`（模型耗时 `7461 ms`），识别文本精确为 `2 + 2`。

同一轮冒烟：`/demo` 返回 `200`；`/verify` 对 `x^2` 返回 `derivative=2*x`、`derivative_latex=2 x`；`/demo/api/chat` 文本输入 `2+2` 返回 `intent=arithmetic`、`formula_text=2+2 = 4`，OCR 确认路径传入 `2 + 2` 返回 `formula_text=2 + 2 = 4`。识别、确认、计算三段均无回归。

题号间距修复已上传并完成公网验收（`2026-09-28T12:48Z` 前后的 Reload，`/health` 返回 `version=0.6.6`）：

- `probe-short-2plus2.png`（图中内容 `10. 2 + 2`）：HTTP `200`，`state=awaiting_ocr_confirmation`，识别文本为 `10. 2 + 2`，未出现 `10.2 + 2`。题号与算式被并入的原始问题已在生产关闭。
- `probe-clean-2plus2.png`（图中只有 `2 + 2`）：HTTP `200`，但识别文本为 `1. 2 + 2`，模型仍会补出图中不存在的题号 `1.`。

两轮请求都用“同一像素、不同字节”的副本（改动一个角像素后重新编码）做了缓存旁路，返回均为 `cache_hit=false`，因此结论来自线上模型的真实输出，而不是旧的缓存记录。OCR 结果缓存以“MIME 类型 + 图片字节”的 SHA256 为键，与会话无关，重复上传同一文件必然命中缓存，验真时必须换图或改图。

补题号的影响面已经确认：求解链路会先经过 `strip_question_number_prefix()`，单题文本开头的一个题号会被剥掉，所以 `1. 2 + 2` 与 `10. 2 + 2` 都能算出 `2 + 2`。因此题号与算式被并入（`10.2 + 2`）才是会算错结果的正确性缺陷，而多补一个 `1.` 只影响确认框里展示的识别原文。

PythonAnywhere 文件页截图已经确认：线上 `demo_vision.py` 为 `11275` 字节、修改时间 `2026-09-28 12:48`，`demo_coze_ocr.py` 为 `20247` 字节，仍是第二轮版本；第三轮从未上传。

第四轮本地修复同时处理两个问题：

- 删除提示词中可被模型照抄的 `1. 2 + 2` 反例，改为要求从图中实际可见的第一个字符开始输出。
- 当视觉模型对单行简单算式返回以 `1.` 开头的结果时，额外做一次视觉复核；确认图中没有题号后才剥离这个 `1.`，确认真实存在时原样保留。

第四轮已上线服务端指纹：

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| `deploy/demo_vision.py` | 16329 | `826D2B57BF3C138330FF84B5C441A42F518B54A9118EA8946DF6188F8E0DA109` |
| `deploy/demo_coze_ocr.py` | 20518 | `3AB89496D114A51B9D6DB2E62F94CCEE52DE97C28A27120A8524C407DC91DF1F` |
| `deploy/wsgi_app.py` | 35018 | `830CED1AE834317CF21E34C944056569FDBBA414D762A7AC7DEAC246F988077A` |

本地完整回归为 `141` 项、`137` 项通过、`4` 项跳过。2026-09-28 21:06 前后已在 PythonAnywhere 项目根目录解压第四轮 ZIP，确认三个线上文件大小分别为 `16329`、`20518`、`35018` 字节，并完成 Web Reload。

最终验收使用只改一个角像素的缓存旁路副本，两次请求均为 `cache_hit=false`、HTTP `200`、`state=awaiting_ocr_confirmation`：

- `probe-clean-2plus2-v4-cachebust.png`（图中只有 `2 + 2`）：返回识别文本 `2 + 2`，未再补出 `1.`。
- `probe-short-2plus2-v4-cachebust.png`（图中内容 `10. 2 + 2`）：返回识别文本 `10. 2 + 2`，真实题号仍保留。

第四轮补题号展示层问题已在生产关闭。

原始探测结果位于当前工作区的 `work/public-api-probe.json`、`work/ocr-matrix-report.json`，不属于仓库交付文件。

## 仍需完成

### P0

- [x] 已在设置 `PYTHONANYWHERE_API_TOKEN` 的 PowerShell 7 会话中运行
  `scripts/publish-pythonanywhere-file.ps1`，上传 `311840` 字节、SHA256
  `4D6CA7FAAB283EEA8C66ACBE9BA245140C56EA9CE588C71F9895E8D4271B8EFD`
  的 `deploy/templates/demo.html` 并完成 Reload 与五项公网标记验证。
- [x] 已检查 GitHub Actions 的公开状态：工作流 `Public health check` 为 `active`，`main` 当前 SHA 为 `23c483f1ee8d06601747dd4997860528cdb7adcb`，修复已进入默认分支。
- [x] 已取得修复提交的运行结果：第 `50` 次运行基于 `23c483f1ee8d06601747dd4997860528cdb7adcb`，`2026-09-28T11:49:29Z` 由 `workflow_dispatch` 手工触发，`11:49:37Z` 完成，结论 `success`，其中 `Check public API` 步骤通过，地址为 `https://github.com/cfy123456-yr/gaoshu-agent/actions/runs/36417964912`。此前第 `49` 次仍是旧提交 `0d10854...` 的失败运行；历史定时运行间隔约 3 至 5 小时，因此改用手工触发，后续定时运行会使用同一份工作流文件。
- [x] 使用仓库内的 `scripts/check_health.py` 直接复跑公网检查，已通过：`version=0.6.7`。
- [x] 已复核定时检查的后续红色记录：公开 API 只能确认 `Check public API` 以退出码
  `1` 结束，无法读取失败日志正文；同一公网端点在本轮手动检查中返回 `version=0.6.7`。
  健康检查现已延长重试窗口，减少 PythonAnywhere 短暂重启造成的误报。
- [x] 已增加健康检查相关文件变更时的 `push` 触发，并确认第 `55` 次运行基于
  `908b51ae48f01f90db64fe30dd1ac5e3ca29fd98`，`event=push`，结论 `success`。
- [x] 已上传 `deploy/demo_vision.py` 和 `deploy/demo_coze_ocr.py` 到 PythonAnywhere 并 Reload；三张短算式图片复测全部返回 HTTP `200` 且 `state=awaiting_ocr_confirmation`，不含题号的干净图识别为 `2 + 2`。
- [x] `MATH_API_KEY` 决策：演示阶段继续关闭，保持扣子工作流和公开计算接口可直接验证；正式发布前再启用，并同步更新扣子的 5 个 HTTP 节点请求头。

### P1

- [x] 已将公网 OCR 扩展到 12 类固定矩阵，并保存接受/拒绝、耗时和状态结果。
- [x] 已补充手写风格、复杂公式、低对比度、旋转和遮挡验证；其中 18° 旋转和遮挡仍按预期拒绝。
- [x] 已本地修复 `10. 2 + 2` 被并入为 `10.2 + 2` 的提示词问题，两处 OCR 提示词均包含题号间距约束；当时定向测试与完整 `141` 项回归通过。
- [x] 已将题号间距修复上传 PythonAnywhere 并 Reload；`probe-short-2plus2.png` 生产复测返回 `10. 2 + 2`，不再被并入为 `10.2 + 2`。
- [x] 已上传第四轮的 `demo_vision.py`、`demo_coze_ocr.py` 和 `wsgi_app.py` 并 Reload；缓存旁路生产复测确认空题号图返回 `2 + 2`，真实题号图保留 `10. 2 + 2`，该展示层问题已关闭。
- [x] 已核对视觉模型与普通问答模型的限流、额度和余额：免费额度、余额、停止开关、
  最近 `6` 小时监控均已确认；华北 2（北京）公开限流为 `qwen-plus`
  `30,000 RPM / 5,000,000 TPM`、`qwen3-vl-plus`
  `3,000 RPM / 5,000,000 TPM`，来源为官方《限流》文档。
- [x] 持久日志决策：演示阶段继续关闭，依赖 PythonAnywhere 平台日志、GitHub Actions
  健康检查和公网回归；正式发布前再启用 JSONL 日志并验证轮转。
- [x] 已把 PythonAnywhere 的备份、上传、Reload、短算式验真和回滚整理为固定发布清单，见 `DEPLOYMENT.md`。

### P2

- [x] 扣子 OCR 备用链路决策：暂时保留，待短算式修复上线并稳定运行后再评估下线；阿里云视觉模型仍为主链路。
- [x] 已同步扣子“知微老师”提示词的服务范围：`COZE_AGENT_PROMPT.md` 原先只声明“大学高等数学”，与已修复的 OCR 范围冲突；现改为高等数学加基础算术、代数、几何等一切可计算数学题，并明确“题目简单不构成拒绝理由”。用户已于 `2026-09-29` 将该提示词手工粘贴到扣子平台并发布，本地代码侧等待同步事项已关闭。
- [x] 已完成真实手机语音人工验收：浏览器中文语音输入、转写核对、手动发送和回答朗读均可用。
- [ ] 收集移动端持续使用反馈，继续优化长题干、键盘弹出和慢网络反馈。
- [x] 已保存 OCR 固定矩阵报告；固定种子随机回归已由单元测试和公网脚本覆盖。
- [x] 已由 GitHub Actions 提供外部健康监控：定时检查公网版本和状态，相关文件
  `push` 时立即检查，并通过 GitHub Actions 失败通知告警；短信、电话等独立告警
  渠道不在当前演示范围。

## 主要文档

- `README.md`：安装、启动、接口和配置说明。
- `DEPLOYMENT.md`：PythonAnywhere 部署、验收和 Reload 行为。
- `COZE_WORKFLOWS.md`：扣子工作流接入说明。
- `COZE_AGENT_PROMPT.md`：扣子智能体提示词说明。
- `deploy/PYTHONANYWHERE.md`：PythonAnywhere 初始部署步骤。
