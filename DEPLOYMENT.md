# 固定公网部署说明

当前演示环境使用 LocalTunnel，固定子域名为
`https://zhixi-gaoshu-2026.loca.lt`。这种方式需要本机、FastAPI 服务和
Node 隧道进程同时保持运行，只适合开发与临时演示。

固定公网部署推荐使用 Render 的免费 Web Service。仓库中的 `Dockerfile`、
`render.yaml` 和 `.env.example` 已经准备好，不需要再把密钥写入源码。

## 前置条件

- 一个 GitHub 账号。
- 一个 Render 账号，可使用 GitHub 登录。
- 已获授权的 GitHub 仓库，用于同步本项目源码。

Render 不能直接读取当前 Gitee 远端，因此必须先准备 GitHub 仓库。不要把
`.env`、真实 API Key、访问令牌或学生个人数据提交到任何仓库。

## 部署步骤

1. 在 GitHub 新建仓库，并将本项目推送到该仓库。
2. 登录 Render，选择 `New` -> `Blueprint`。
3. 选择 GitHub 仓库。Render 会读取根目录的 `render.yaml`。
4. 确认创建 `zhixi-gaoshu-math` Web Service。
5. Render 会自动生成 `MATH_API_KEY`，可在服务的 Environment 页面查看。
6. 等待部署完成，记录服务固定地址，例如：

```text
https://zhixi-gaoshu-math.onrender.com
```

免费实例闲置后可能休眠。正式演示前先访问 `/health` 唤醒服务。

## 部署验收

在项目根目录执行以下命令。将地址替换成 Render 实际生成的地址，并将密钥
放在命令行或 `MATH_API_KEY` 环境变量中，不要把密钥写进仓库文件。

```powershell
.\scripts\verify-deployment.cmd --base-url https://zhixi-gaoshu-math.onrender.com --api-key "你的 MATH_API_KEY"
```

检查脚本会验证：

- `/health` 服务状态、版本和配置。
- `/verify-query` 求导与候选答案判定。
- `/integrate-query` 不定积分、定积分与候选答案判定。
- `/limit-query` 极限与候选答案判定。
- 非法表达式拦截。
- 固定公网部署启用密钥后，无密钥请求返回 401。

全部显示通过后，固定地址即可用于扣子工作流。

## 扣子节点切换

将以下三个工作流的 HTTP 请求地址从 LocalTunnel 地址替换为 Render 地址：

| 工作流 | 固定接口 |
| --- | --- |
| `math_verify` | `https://你的域名/verify-query` |
| `math_integrate` | `https://你的域名/integrate-query` |
| 极限工作流 | `https://你的域名/limit-query` |

三个节点都需要增加请求头：

```text
X-API-Key: 与 MATH_API_KEY 一致
```

固定公网地址不需要再传 `bypass-tunnel-reminder`。

## 演示前检查

1. 访问固定域名 `/health`，确认返回 `status: ok`。
2. 运行 `scripts\verify-deployment.cmd` 完整验收。
3. 在扣子分别发送一道求导题、一道积分题、一道极限题。
4. 上传一道清晰的图片题，确认 OCR 识别结果需要学生确认后才计算。
5. 确认日志和回复中不出现 API Key、完整表达式或学生个人数据。

外部监控与告警、函数图像、语音和独立前端仍属于后续功能，不影响当前智能体
的文字题、图片题和三个计算工作流的在线演示。
