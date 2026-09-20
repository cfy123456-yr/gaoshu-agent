# 扣子工作流配置

本文只负责新增工作流。智能体提示词最后统一整体更新。

## 前置条件

先更新 PythonAnywhere 服务并 Reload，确认 `/health` 返回 `0.4.2`。

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

请求体留空。请求头保持 `Accept: application/json`。

### 结束节点

输出以下字段：

| 输出名 | 来源 |
| --- | --- |
| limit | HTTP 返回的 limit |
| limit_latex | HTTP 返回的 limit_latex |
| candidate | HTTP 返回的 candidate |
| is_correct | HTTP 返回的 is_correct |

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

请求体留空。

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
| candidate | HTTP 返回的 candidate |
| is_correct | HTTP 返回的 is_correct |
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
is_correct = true
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
| derivatives | derivative, higher_derivative, differential, tangent, normal, mean_value, critical_points, monotonicity, extrema, taylor, curvature |
| integrals | indefinite, definite, improper |
| differential_equations | dsolve |
| vectors | dot, cross, norm, angle, distance, projection |
| multivariable_calculus | partial, mixed_partial, gradient, hessian, directional_derivative, implicit_derivative, multivariable_extrema |
| multiple_integrals | double, triple |
| line_surface_integrals | line_scalar, line_vector, surface_scalar, flux |
| series | sum, convergence, power_radius |

## 发布顺序

1. 测试 `math_limit` 和 `math_solve` 均成功。
2. 分别发布两个工作流。
3. 回到智能体页面刷新工作流列表。
4. 将两个工作流加入智能体。
5. 发布智能体。

提示词暂时不改。两个工作流都能独立调用后，再统一重写提示词和路由规则。
