# 知微高数项目状态

更新时间：2026-09-29 21:08（Asia/Shanghai）

## 当前事实

| 项目 | 当前状态 |
| --- | --- |
| 服务版本 | `0.6.7` |
| 固定公网地址 | `https://cfyyy.pythonanywhere.com` |
| 无需登录演示页 | `https://cfyyy.pythonanywhere.com/demo` |
| 公网演示页前端 | 已发布移动端加固与慢请求进度提示版 |
| `MATH_API_KEY` | 当前未启用 |
| OCR 主链路 | 阿里云百炼视觉模型 |
| OCR 备用链路 | 扣子 OCR，当前已配置 |
| Windows 离线 OCR | 公网未启用，仅作为未配置任何上游时的本地降级 |
| 持久化日志 | 公网当前未启用 |
| 服务端会话 | 进程内存，30 分钟过期，最多 500 个 |
| OCR 结果缓存 | 进程内存，10 分钟过期 |
| 浏览器语音 | Web Speech API，中文识别加回答朗读 |
| 版本入库状态 | `0.6.7` 与 Gitee OCR 编号整合已提交；本地 `main` 同时包含 GitHub 与 Gitee 远端历史 |

## 2026-09-29 核查与推进

启动本地后端后复跑完整回归，合并 Gitee 新增题号测试并补入移动端加固、慢请求反馈和
部署标记测试后的结果：

```text
Ran 160 tests in 6.642s
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

当前 `.venv` 中 `a2wsgi` 文件被 Windows 拒绝读取，`uvicorn` 因此无法导入；本轮改用与
PythonAnywhere 部署相同的 Flask WSGI 入口启动本地服务，未修改项目代码或运行环境。
首次未启动服务时出现的 9 项接口失败属于连接拒绝，服务启动后同一套测试全部通过。

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
- 已新增 `scripts/export-submission-material.ps1`：使用 PowerShell 7 将参赛手册、
  AI 使用记录和项目状态合并为打印版 HTML，并调用本机 Microsoft Edge 生成 A4
  PDF。实际导出与文件头校验成功；Edge 实渲染截图确认中文字体、表格与长标题
  无溢出。

持久化 JSONL 日志在演示阶段继续关闭。当前公网使用 PythonAnywhere 自带的访问与错误
日志，配合 GitHub Actions 健康检查和四组公网回归已覆盖稳定性观察；开启额外日志会
引入重复记录和长期磁盘占用，收益不足。正式发布前如需审计请求耗时和错误类型，再在
PythonAnywhere 环境中设置 `LOG_ENABLED=true`，确认日志轮转和 `/health` 状态后启用。

提交前审计结论：

- 工作区改动集中在 `0.6.7`、OCR 第四轮修复、学习空间和语音、随机回归及部署文档。
- 未在高置信度密钥模式下发现待提交跟踪文件包含 Token、API Key 或私钥。
- `.gitignore` 已补充忽略 `.test-*`、`.tmp-*` 和 `work/`，避免测试安装器、临时输出、发布产物和浏览器会话探测目录进入版本库。
- GitHub `main` 已整合到 `23c483f1ee8d06601747dd4997860528cdb7adcb`，Gitee `origin/main` 已整合到 `a5d408258d98f061b7f807cc52ae264803048f84`。
- 两个远端都是本地 `main` 的祖先；Gitee OCR 编号整合提交为 `ed361a5`，题号识别支持无标点、混合标点和重复题号。

下一步进入浏览器真机语音验收和 OCR 稳定性复跑，并以双远端 SHA 核验作为本轮仓库收尾条件。

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

## 本轮验证

验证时间：2026-09-28 21:22 至 21:25（Asia/Shanghai）。

### 本地完整测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：运行 `142` 项，`138` 项通过，`4` 项跳过，`OK (skipped=4)`。

跳过项是旧版显式曲线/曲面积分用例，当前属于可选项，不影响现有公网部署。

浏览器语音定向测试共 `94` 项，全部通过，其中 `4` 项沿用上述可选跳过；已确认语音识别、回答朗读、能力降级和页面切换清理逻辑均包含在演示页回归中。

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
- [x] 已本地修复 `10. 2 + 2` 被并入为 `10.2 + 2` 的提示词问题，两处 OCR 提示词均包含题号间距约束，定向测试与完整 `141` 项回归通过。
- [x] 已将题号间距修复上传 PythonAnywhere 并 Reload；`probe-short-2plus2.png` 生产复测返回 `10. 2 + 2`，不再被并入为 `10.2 + 2`。
- [x] 已上传第四轮的 `demo_vision.py`、`demo_coze_ocr.py` 和 `wsgi_app.py` 并 Reload；缓存旁路生产复测确认空题号图返回 `2 + 2`，真实题号图保留 `10. 2 + 2`，该展示层问题已关闭。
- [ ] 通过云平台控制台确认视觉模型与普通问答模型的限流、额度和余额；仅凭 `/health` 无法判断。
- [x] 持久日志决策：演示阶段继续关闭，依赖 PythonAnywhere 平台日志、GitHub Actions
  健康检查和公网回归；正式发布前再启用 JSONL 日志并验证轮转。
- [x] 已把 PythonAnywhere 的备份、上传、Reload、短算式验真和回滚整理为固定发布清单，见 `DEPLOYMENT.md`。

### P2

- [x] 扣子 OCR 备用链路决策：暂时保留，待短算式修复上线并稳定运行后再评估下线；阿里云视觉模型仍为主链路。
- [x] 已同步扣子“知微老师”提示词的服务范围：`COZE_AGENT_PROMPT.md` 原先只声明“大学高等数学”，与已修复的 OCR 范围冲突；现改为高等数学加基础算术、代数、几何等一切可计算数学题，并明确“题目简单不构成拒绝理由”。该文件仍需手工粘贴回扣子平台后生效。
- [ ] 收集移动端真实使用反馈，继续优化长题干、键盘弹出和慢网络反馈。
- [x] 已整理作品说明、五至八分钟演示脚本、答辩问答与提交前检查，见
  `docs/SUBMISSION_GUIDE.md`。
- [x] 已整理开发阶段 AI 工具用途、运行阶段模型边界、数据密钥规则和提交声明模板，
  见 `docs/AI_USAGE_LOG.md`；演示视频仍待录制。
- [x] 已把单题和多题演示图片整理到 `docs/demo-assets/`，并通过公网 OCR 验证；
  单题进入确认状态，多题正确拆分为 3 项选择题号。
- [x] 已保存 OCR 固定矩阵报告；固定种子随机回归已由单元测试和公网脚本覆盖。
- [x] 已由 GitHub Actions 提供外部健康监控：定时检查公网版本和状态，相关文件
  `push` 时立即检查，并通过 GitHub Actions 失败通知告警；短信、电话等独立告警
  渠道不在当前演示范围。

## 主要文档

- `README.md`：安装、启动、接口和配置说明。
- `DEPLOYMENT.md`：PythonAnywhere 部署、验收和 Reload 行为。
- `COZE_WORKFLOWS.md`：扣子工作流接入说明。
- `COZE_AGENT_PROMPT.md`：扣子智能体提示词说明。
- `docs/SUBMISSION_GUIDE.md`：作品说明、演示视频脚本、答辩问答和提交清单。
- `docs/AI_USAGE_LOG.md`：开发与运行阶段的 AI 工具边界、复核记录和声明模板。
- `scripts/export-submission-material.ps1`：生成可打印的参赛材料 HTML 与 A4 PDF。
- `deploy/PYTHONANYWHERE.md`：PythonAnywhere 初始部署步骤。
