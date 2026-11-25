# 扣子工作流配置

本文件定义扣子“知微老师”的完整工作流接入契约，目标后端版本为 `v0.6.11`。提示词见 `COZE_AGENT_PROMPT.md`。

## 前置条件

先更新 PythonAnywhere 服务并 Reload，确认 `/health` 返回 `0.6.11`。

固定服务地址：

```text
https://cfyyy.pythonanywhere.com
```

所有计算工作流必须使用以下字段约定：

1. `expression`、`candidate`、`lower`、`upper`、`point` 等数学字段接受学生原始口语，不需要智能体先转换成标准公式。
2. 智能体可以从整句题目中抽取参数，但不得把“x的平方、根号下x、x的立方、sinx除以x”等片段改写成猜测的公式。
3. 后端 `v0.6.11` 会在解析前统一归一化口语、Unicode 上下标、LaTeX 分式和根号。
4. 例如 `0到1 x平方的定积分` 应传为 `expression=x平方&lower=0&upper=1`；`sinx除以x 当x趋近0求极限` 应传为 `expression=sinx除以x&point=0`。
5. 后端 JSON 布尔值可能是原生 `true`、`false`，也可能是 `null`。工作流结束节点应保留该值；如果后续代码节点要求字符串，则统一转换为 `"true"`、`"false"` 或空字符串。

如果 PythonAnywhere 环境启用了 `MATH_API_KEY`，所有计算工作流 HTTP 节点都要增加请求头：

```text
X-API-Key: 与 PythonAnywhere 的 MATH_API_KEY 相同
```

另外保留 `Accept: application/json`。`/plot.svg` 只用于图片显示，不需要 API Key。

## 工作流清单

| 工作流 | 用途 | 后端接口 |
| --- | --- | --- |
| `math_verify` | 求导、导数值、切线斜率、导数答案判断 | `POST /verify-query` |
| `math_integrate` | 不定积分、定积分、反常积分、积分答案判断 | `POST /integrate-query` |
| `math_limit` | 双侧极限、单侧极限、数列极限、极限答案判断 | `POST /limit-query` |
| `math_solve` | 其他章节和扩展题型统一求解 | `POST /solve-query` |
| `math_plot` | 显函数图像 | `POST /plot-query` |
| `knowledge_lookup` | 检索同济大学《高等数学》本科教材知识库 | `POST /demo/api/knowledge` |
| `ocr_question` | 识别学生上传的数学题图片 | 扣子图像理解节点；可选 `POST /demo/api/ocr` |

## math_verify

用途：显函数 `y=f(x)` 的求导、某点导数值、切线斜率、变化率以及导数答案判断。

### 开始节点

| 变量名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| expression | String | 是 | 无 | 学生原始数学片段，如 `x的平方` |
| variable | String | 否 | x | 自变量 |
| candidate | String | 否 | 空 | 学生原话中的候选导数 |

### HTTP 请求节点

请求方式：

```text
POST
```

请求地址：

```text
https://cfyyy.pythonanywhere.com/verify-query
```

查询参数：

| 参数名 | 参数值 |
| --- | --- |
| expression | {{expression}} |
| variable | {{variable}} |
| candidate | {{candidate}} |

请求体留空。请求头设置为 `Accept: application/json` 和上述可选 `X-API-Key`。

### 结束节点

| 输出名 | 来源 |
| --- | --- |
| expression | HTTP 返回的 expression |
| variable | HTTP 返回的 variable |
| derivative | HTTP 返回的 derivative |
| derivative_latex | HTTP 返回的 derivative_latex |
| candidate | HTTP 返回的 candidate |
| is_correct | HTTP 返回的 is_correct |

### 测试

口语表达式：

```json
{
  "expression": "x的平方",
  "variable": "x",
  "candidate": ""
}
```

预期：`derivative = 2*x`，`is_correct = null`。

正确候选：

```json
{
  "expression": "x的立方减2x",
  "variable": "x",
  "candidate": "3x平方减2"
}
```

预期：`derivative = 3*x**2 - 2`，`is_correct = true`。

错误候选：

```json
{
  "expression": "x的立方",
  "variable": "x",
  "candidate": "2x平方"
}
```

预期：`is_correct = false`。

## math_integrate

用途：不定积分、定积分、反常积分以及积分答案判断。

### 开始节点

| 变量名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| expression | String | 是 | 无 | 学生原始数学片段，如 `根号下x` |
| variable | String | 否 | x | 积分变量 |
| lower | String | 否 | 空 | 定积分下限；不定积分留空 |
| upper | String | 否 | 空 | 定积分上限；不定积分留空 |
| candidate | String | 否 | 空 | 学生原话中的候选积分结果 |

### HTTP 请求节点

请求方式：

```text
POST
```

请求地址：

```text
https://cfyyy.pythonanywhere.com/integrate-query
```

查询参数：

| 参数名 | 参数值 |
| --- | --- |
| expression | {{expression}} |
| variable | {{variable}} |
| lower | {{lower}} |
| upper | {{upper}} |
| candidate | {{candidate}} |

请求体留空。请求头设置为 `Accept: application/json` 和上述可选 `X-API-Key`。

### 结束节点

| 输出名 | 来源 |
| --- | --- |
| expression | HTTP 返回的 expression |
| variable | HTTP 返回的 variable |
| integral | HTTP 返回的 integral |
| integral_latex | HTTP 返回的 integral_latex |
| candidate | HTTP 返回的 candidate |
| is_correct | HTTP 返回的 is_correct |

### 测试

不定积分：

```json
{
  "expression": "根号下x",
  "variable": "x",
  "candidate": ""
}
```

预期：`integral = 2*x**(3/2)/3`，`is_correct = null`。

定积分：

```json
{
  "expression": "x平方",
  "variable": "x",
  "lower": "0",
  "upper": "1",
  "candidate": "1/3"
}
```

预期：`integral = 1/3`，`is_correct = true`。

错误候选：

```json
{
  "expression": "x平方",
  "variable": "x",
  "lower": "0",
  "upper": "1",
  "candidate": "1/2"
}
```

预期：`is_correct = false`。

## math_limit

用途：双侧极限、左极限、右极限、极限答案判断。

### 开始节点

| 变量名 | 类型 | 必填 | 默认值 |
| --- | --- | --- | --- |
| expression | String | 是 | 无 |
| variable | String | 否 | x |
| point | String | 否 | 0 |
| direction | String | 否 | 空 |
| candidate | String | 否 | 空 |

### HTTP 请求节点

请求方式：

```text
POST
```

请求地址：

```text
https://cfyyy.pythonanywhere.com/limit-query
```

查询参数：

| 参数名 | 参数值 |
| --- | --- |
| expression | {{expression}} |
| variable | {{variable}} |
| point | {{point}} |
| direction | {{direction}} |
| candidate | {{candidate}} |

请求体留空。请求头设置为 `Accept: application/json` 和上述 `X-API-Key`。

### 结束节点

输出以下字段：

| 输出名 | 来源 |
| --- | --- |
| limit | HTTP 返回的 limit |
| limit_latex | HTTP 返回的 limit_latex |
| candidate | HTTP 返回的 candidate |
| is_correct | 代码节点输出的字符串 is_correct（`"true"`、`"false"` 或空字符串） |

### 测试

测试输入：

```json
{
  "expression": "sin(x)/x",
  "variable": "x",
  "point": "0",
  "candidate": "1"
}
```

预期结果：

```text
limit = 1
is_correct = true
```

右极限测试：

```json
{
  "expression": "1/x",
  "variable": "x",
  "point": "0",
  "direction": "+",
  "candidate": "oo"
}
```

## math_solve

用途：除基础求导、积分、极限之外，统一处理全章节确定性求解。

### 开始节点

| 变量名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| chapter | String | 是 | 章节英文名 |
| topic | String | 是 | 题型英文名 |
| inputs | Object | 是 | 题型参数对象 |
| candidate | String | 否 | 学生答案，没有则为空 |

### HTTP 请求节点

请求方式：

```text
POST
```

请求地址：

```text
https://cfyyy.pythonanywhere.com/solve-query
```

查询参数：

| 参数名 | 参数值 |
| --- | --- |
| chapter | {{chapter}} |
| topic | {{topic}} |
| inputs | {{inputs}} |
| candidate | {{candidate}} |

请求体留空。请求头设置为 `Accept: application/json` 和上述 `X-API-Key`。

`inputs` 必须是 JSON 字符串，例如：

```json
{"expression":"1/n^2","variable":"n"}
```

### 结束节点

输出以下字段：

| 输出名 | 来源 |
| --- | --- |
| method | HTTP 返回的 method |
| result | HTTP 返回的 result |
| latex | HTTP 返回的 latex |
| candidate | 代码节点输出的 candidate |
| is_correct_text | 代码节点输出的字符串 is_correct_text（`"true"`、`"false"` 或空字符串） |
| notes | HTTP 返回的 notes |

### 测试一：级数收敛

```json
{
  "chapter": "series",
  "topic": "convergence",
  "inputs": {
    "expression": "1/n^2",
    "variable": "n"
  },
  "candidate": null
}
```

预期：

```text
result = 收敛
```

### 测试二：二重积分

```json
{
  "chapter": "multiple_integrals",
  "topic": "double",
  "inputs": {
    "expression": "x*y",
    "variables": ["x", "y"],
    "lower_x": "0",
    "upper_x": "1",
    "lower_y": "0",
    "upper_y": "1"
  },
  "candidate": null
}
```

预期：

```text
result = 1/4
```

### 测试三：二阶导数

```json
{
  "chapter": "derivatives",
  "topic": "higher_derivative",
  "inputs": {
    "expression": "x^3",
    "variable": "x",
    "order": 2
  },
  "candidate": "6x"
}
```

预期：

```text
result = 6*x
is_correct_text = "true"
```

### 测试四：微分方程

```json
{
  "chapter": "differential_equations",
  "topic": "dsolve",
  "inputs": {
    "equation": "y' - y",
    "variable": "x",
    "function": "y"
  },
  "candidate": null
}
```

预期结果包含：

```text
C1*exp(x)
```

### 测试五：梯度

```json
{
  "chapter": "multivariable_calculus",
  "topic": "gradient",
  "inputs": {
    "expression": "x^2*y",
    "variables": ["x", "y"]
  },
  "candidate": null
}
```

预期结果包含：

```text
2*x*y
x**2
```

### 测试六：多约束条件极值

```json
{
  "chapter": "multivariable_calculus",
  "topic": "conditional_extrema",
  "inputs": {
    "expression": "x^2+y^2+z^2",
    "variables": ["x", "y", "z"],
    "constraints": ["x=0", "y=0"]
  },
  "candidate": null
}
```

预期结果包含：

```text
point: x=0, y=0, z=0
kind: 极小值
```

## 章节与题型

支持的 `chapter`：

```text
limits
derivatives
integrals
differential_equations
vectors
multivariable_calculus
multiple_integrals
line_surface_integrals
series
```

支持的 `topic`：

| chapter | topic |
| --- | --- |
| limits | limit, sequence_limit |
| derivatives | derivative, higher_derivative, differential, tangent, normal, mean_value, critical_points, monotonicity, extrema, taylor, curvature, parametric_derivative |
| integrals | indefinite, definite, improper |
| differential_equations | dsolve |
| vectors | dot, cross, norm, angle, distance, projection |
| multivariable_calculus | partial, mixed_partial, gradient, hessian, directional_derivative, implicit_derivative, system_implicit_derivative, multivariable_extrema, conditional_extrema |
| multiple_integrals | double, double_polar, triple, triple_cylindrical, triple_spherical |
| line_surface_integrals | line_scalar, line_vector, surface_scalar, flux |
| series | sum, convergence, power_radius |

## math_plot

用途：根据显函数表达式生成函数图像。

### 开始节点

| 变量名 | 类型 | 必填 | 默认值 |
| --- | --- | --- | --- |
| expression | String | 是 | 无 |
| variable | String | 否 | x |
| x_min | String | 否 | -10 |
| x_max | String | 否 | 10 |

### HTTP 请求节点

请求方式：

```text
POST
```

请求地址：

```text
https://cfyyy.pythonanywhere.com/plot-query
```

查询参数：

| 参数名 | 参数值 |
| --- | --- |
| expression | {{expression}} |
| variable | {{variable}} |
| x_min | {{x_min}} |
| x_max | {{x_max}} |
| samples | 80 |
| width | 640 |
| height | 360 |

请求体留空。请求头设置为 `Accept: application/json` 和上述 `X-API-Key`。`samples=80` 可以显著减小返回的 SVG 内容，加快智能体响应。

### 图像显示格式

智能体应将题目参数代入以下 Markdown 图片链接并原样输出：

```text
![函数图像](https://cfyyy.pythonanywhere.com/plot.svg?expression={{expression}}&variable={{variable}}&x_min={{x_min}}&x_max={{x_max}})
```

### 测试

测试输入：

```text
expression = sin(x)
variable = x
x_min = -3
x_max = 3
```

预期结果：`/plot-query` 返回 `svg` 字段，智能体对话中显示正弦函数图像。

## knowledge_lookup

用途：只检索同济大学《高等数学》本科教材知识库，覆盖第一章至第十二章。该工作流不得接其他知识库，也不得把模型记忆或网络搜索结果混入教材检索。

### 开始节点

| 变量名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| query | String | 是 | 无 | 学生的概念或方法问题 |
| limit | Integer | 否 | 3 | 最多返回 3 条教材片段，后端上限为 5 |

### HTTP 请求节点

请求方式：

```text
POST
```

请求地址：

```text
https://cfyyy.pythonanywhere.com/demo/api/knowledge
```

请求头：

```text
Accept: application/json
```

请求查询参数：

```text
query={{query}}&limit={{limit}}
```

该接口属于公开演示接口，不需要 `X-API-Key`。

请求体：留空（`bodyType=EMPTY`）。扣子 HTTP 节点不会替换 JSON 字符串内的
`{{query}}`、`{{limit}}` 占位符；查询参数方式由后端直接读取，并由扣子完成变量插值。

### 结束节点

| 输出名 | 来源 |
| --- | --- |
| query | HTTP 返回的 query |
| count | HTTP 返回的 count |
| engine | HTTP 返回的 engine |
| results | HTTP 返回的 results |

每条 `results` 包含：

| 字段 | 含义 |
| --- | --- |
| id | 教材片段标识 |
| title | 小节标题 |
| chapter | 同济教材章节 |
| source | 知识文件来源，必须位于 `knowledge/` |
| heading_path | 标题路径 |
| excerpt | 教材摘录 |
| score | 检索相关度 |

### 测试

教材概念：

```text
POST /demo/api/knowledge?query=定积分的定义&limit=3
```

预期：`count >= 1`，第一条结果的 `source` 为 `knowledge/05_定积分.md`，标题为“三、定积分的概念”，`chapter` 包含“定积分”。

章节召回：

```text
POST /demo/api/knowledge?query=第九章 多元函数微分法&limit=3
```

预期：返回 `knowledge/09_多元函数微分法及其应用.md` 的教材片段。

无结果时：明确说明同济教材知识库未检索到内容，不得改用其他教材或编造出处。

## ocr_question

用途：识别学生上传的数学题图片。识别阶段只转写题目和请学生确认，不计算、不判题、不补充图片中没有的条件。

### 推荐实现

在扣子工作流中使用图像理解节点，输入学生本轮上传的图片。节点提示词必须覆盖：

1. 接受高等数学、基础算术、代数、几何等所有可计算数学题，题目简单不构成拒绝理由。
2. 只输出图中可见的题干，保留题号、正负号、系数、上下标、函数名、积分上下限和导数记号。
3. 多题按题号分行完整转写，不合并、不遗漏、不串题。
4. 看不清的符号标“疑似”，不得擅自改正；严重模糊或非数学题时要求重新上传。
5. 不计算、不判题、不解释，不输出 Markdown 代码块或额外说明。

### 开始节点

| 变量名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| image | File | 是 | 无 | 学生本轮上传的题目图片 |
| session_id | String | 否 | 空 | 若走后端接口，可传 8–80 位字母、数字、下划线或短横线 |

### 结束节点

| 输出名 | 类型 | 说明 |
| --- | --- | --- |
| formula_text | String | 识别出的题干，保留原始数学写法 |
| formula_latex | String | 可选；用于复述的 LaTeX，不参与后续计算参数 |
| question_count | Integer | 识别到的独立题目数量 |
| requires_confirmation | Boolean | 是否必须由学生先确认 |
| selection_required | Boolean | 是否因多题或疑似多题需要先选择 |
| warning | String | 疑似符号、多题或清晰度提示 |

结束节点默认输出 `requires_confirmation=true`。学生确认后，下一轮才允许进入计算工作流。

### 可选后端接口

如果扣子 HTTP 节点支持 `multipart/form-data`，也可以调用：

```text
POST https://cfyyy.pythonanywhere.com/demo/api/ocr
```

表单字段：

| 字段名 | 值 |
| --- | --- |
| image | 学生上传的 JPG、PNG、WebP 或 GIF 图片 |

可选请求头：

```text
X-Demo-Session: {{session_id}}
Accept: application/json
```

后端返回的主要字段：

| 字段 | 含义 |
| --- | --- |
| text | 完整识别文本 |
| provider | `vision`、`coze` 或 `windows` |
| warning | 识别提示 |
| question_blocks | 按题拆分的题目列表 |
| multiple_questions | 是否识别到多道题 |
| selection_required | 是否需要学生选择题目 |
| review_required | 是否建议重新确认或裁剪图片 |
| state | `awaiting_ocr_confirmation`、`awaiting_question_selection` 或 `awaiting_ocr_review` |
| requires_confirmation | 是否等待学生确认 |

### 测试

单题图片：返回一道完整题干，`requires_confirmation=true`，且不包含计算结果。

多题图片：返回多个 `question_blocks`，`selection_required=true`，先请学生选择一道。

模糊图片：返回重新上传提示，不猜测公式。

确认后测试：学生回复“确认”后，按题目类型调用 `math_verify`、`math_integrate`、`math_limit` 或 `math_solve`；数学片段仍按原始口语或 OCR 形式传入。

## 当前状态

- 本地后端 `v0.6.11` 已支持口语数学归一化和知识库查询参数请求，并由 `tests/test_coze_contracts.py` 锁定工作流字段契约。
- 本地知识库只索引 `knowledge/` 下 12 个同济大学《高等数学》正文章节文件；目录文件 `00_教材目录与编写规则.md` 用于上传说明，不参与检索。
- “定义/概念/含义”类问题优先命中标题中的对应概念小节，避免被后文章节中的高频复述挤到第二页。
- 扣子云端的提示词发布、工作流发布和知识库替换必须在扣子控制台完成。本文件是本地验收通过的接入规格，不等同于云端已经发布。
- 发布后必须逐项验证口语求导、口语积分、定积分上下限、概念计算混合题、知识库章节召回和多题图片确认流程。
