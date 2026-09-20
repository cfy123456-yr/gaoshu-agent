# 扣子工作流配置

本文只负责新增工作流。智能体提示词最后统一整体更新。

## 前置条件

先更新 PythonAnywhere 服务并 Reload，确认 `/health` 返回 `0.5.0`。

公网已启用 API Key。所有计算工作流 HTTP 节点都要增加请求头：

```text
X-API-Key: 与 PythonAnywhere 的 MATH_API_KEY 相同
```

另外保留 `Accept: application/json`。`/plot.svg` 只用于图片显示，不需要 API Key。

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
| multiple_integrals | double, double_polar, triple |
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

## 当前状态

- `math_limit`：试运行通过，已加入智能体。
- `math_solve`：试运行通过，已加入智能体。
- `math_plot`：试运行通过，已加入智能体，并可在对话中显示函数图像。
- 统一提示词已替换到扣子并发布。
- 已完成空候选答案、正确候选答案、错误候选答案、级数求解和不定积分补 `C` 话术的回归测试。
