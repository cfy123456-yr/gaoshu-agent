"""Run textbook-style chapter cases through the live demo HTTP endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HEADINGS = ("题目理解", "解题思路", "详细计算步骤", "最终答案")

CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "01-01",
        "chapter": "01 函数与极限",
        "question": "求极限 x→0 sin(3x)/x",
        "intent": "limit",
        "expected": ["3"],
    },
    {
        "id": "01-02",
        "chapter": "01 函数与极限",
        "question": "求极限 x→0 (1-cos(x))/x^2",
        "intent": "limit",
        "expected": ["1/2"],
    },
    {
        "id": "01-03",
        "chapter": "01 函数与极限",
        "question": "求极限 x趋于无穷 (1+1/x)^x",
        "intent": "limit",
        "expected": ["E"],
    },
    {
        "id": "02-01",
        "chapter": "02 导数与微分",
        "question": "求导 x^3",
        "intent": "verify",
        "expected": ["3*x**2"],
    },
    {
        "id": "02-02",
        "chapter": "02 导数与微分",
        "question": "求导 sin(x)*exp(x)",
        "intent": "verify",
        "expected": ["sin(x)", "cos(x)", "exp(x)"],
    },
    {
        "id": "02-03",
        "chapter": "02 导数与微分",
        "question": "求二阶导数 x^4",
        "intent": "verify",
        "expected": ["12*x**2"],
    },
    {
        "id": "03-01",
        "chapter": "03 中值定理与导数应用",
        "question": "求切线 y=x^2 在 x=1 处",
        "intent": "solve",
        "expected": ["2*x - 1"],
    },
    {
        "id": "03-02",
        "chapter": "03 中值定理与导数应用",
        "question": "求极值 x^2-2x",
        "intent": "solve",
        "expected": ["极小值", "-1"],
    },
    {
        "id": "03-03",
        "chapter": "03 中值定理与导数应用",
        "question": "求单调区间 x^2-2x",
        "intent": "solve",
        "expected": ["2*x - 2", "1"],
    },
    {
        "id": "04-01",
        "chapter": "04 不定积分",
        "question": "积分 x^2",
        "intent": "integrate",
        "expected": ["x**3/3"],
    },
    {
        "id": "04-02",
        "chapter": "04 不定积分",
        "question": "积分 exp(x)",
        "intent": "integrate",
        "expected": ["exp(x)"],
    },
    {
        "id": "04-03",
        "chapter": "04 不定积分",
        "question": "积分 1/(1+x^2)",
        "intent": "integrate",
        "expected": ["atan(x)"],
    },
    {
        "id": "05-01",
        "chapter": "05 定积分",
        "question": "积分 0 到 1 x^2",
        "intent": "integrate",
        "expected": ["1/3"],
    },
    {
        "id": "05-02",
        "chapter": "05 定积分",
        "question": "积分 0 到 pi sin(x)",
        "intent": "integrate",
        "expected": ["2"],
    },
    {
        "id": "05-03",
        "chapter": "05 定积分",
        "question": "积分 1 到 E 1/x",
        "intent": "integrate",
        "expected": ["1"],
    },
    {
        "id": "06-01",
        "chapter": "06 定积分的应用",
        "question": "求曲线 y=x^2 与 x 轴在 0 到 1 之间围成的面积",
        "intent": "solve",
        "expected": ["1/3", "平面图形面积"],
    },
    {
        "id": "06-02",
        "chapter": "06 定积分的应用",
        "question": "求曲线 y=x 绕 x 轴旋转一周所得旋转体体积，x 从 0 到 1",
        "intent": "solve",
        "expected": ["pi/3", "旋转体体积"],
    },
    {
        "id": "06-03",
        "chapter": "06 定积分的应用",
        "question": "求曲线 y=(2/3)x^(3/2) 从 x=0 到 x=1 的弧长",
        "intent": "solve",
        "expected": ["sqrt(2)", "2/3", "平面曲线弧长"],
    },
    {
        "id": "07-01",
        "chapter": "07 微分方程",
        "question": "解微分方程 y'-y=0",
        "intent": "solve",
        "expected": ["C1", "exp(x)"],
    },
    {
        "id": "07-02",
        "chapter": "07 微分方程",
        "question": "解微分方程 y''+y=0",
        "intent": "solve",
        "expected": ["sin(x)", "cos(x)", "C1", "C2"],
    },
    {
        "id": "07-03",
        "chapter": "07 微分方程",
        "question": "解微分方程 y'+2*x*y=0",
        "intent": "solve",
        "expected": ["C1", "exp(-x**2)"],
    },
    {
        "id": "08-01",
        "chapter": "08 向量代数与空间解析几何",
        "question": "向量 (1,2,3) 点乘 (4,5,6)",
        "intent": "solve",
        "expected": ["32"],
    },
    {
        "id": "08-02",
        "chapter": "08 向量代数与空间解析几何",
        "question": "向量 (1,0,0) 叉乘 (0,1,0)",
        "intent": "solve",
        "expected": ["0", "0", "1"],
    },
    {
        "id": "08-03",
        "chapter": "08 向量代数与空间解析几何",
        "question": "向量 (3,4) 的模长",
        "intent": "solve",
        "expected": ["5"],
    },
    {
        "id": "09-01",
        "chapter": "09 多元函数微分法",
        "question": "求偏导 x^2*y 对 x",
        "intent": "solve",
        "expected": ["2*x*y"],
    },
    {
        "id": "09-02",
        "chapter": "09 多元函数微分法",
        "question": "梯度 x^2+y^2 变量 x,y",
        "intent": "solve",
        "expected": ["2*x", "2*y"],
    },
    {
        "id": "09-03",
        "chapter": "09 多元函数微分法",
        "question": "条件极值 x*y 约束 x+y=1 变量 x,y",
        "intent": "solve",
        "expected": ["1/2", "-1/2", "极大值"],
    },
    {
        "id": "10-01",
        "chapter": "10 重积分",
        "question": "积分 0 到 1 0 到 1 x+y",
        "intent": "solve",
        "expected": ["1"],
    },
    {
        "id": "10-02",
        "chapter": "10 重积分",
        "question": "极坐标二重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi",
        "intent": "solve",
        "expected": ["pi/2"],
    },
    {
        "id": "10-03",
        "chapter": "10 重积分",
        "question": "三重积分 x+y+z 变量 x,y,z",
        "intent": "solve",
        "expected": ["3/2"],
    },
    {
        "id": "11-01",
        "chapter": "11 曲线积分与曲面积分",
        "question": "第一类曲线积分 x+y 沿曲线 y=x，x 从 0 到 1",
        "intent": "solve",
        "expected": ["sqrt(2)"],
    },
    {
        "id": "11-02",
        "chapter": "11 曲线积分与曲面积分",
        "question": "第二类曲线积分 向量场(x,y) 沿曲线 y=x，x 从 0 到 1",
        "intent": "solve",
        "expected": ["1"],
    },
    {
        "id": "11-03",
        "chapter": "11 曲线积分与曲面积分",
        "question": "第二类曲面积分 向量场(0,0,1) 在曲面 z=x，x 从 0 到 1，y 从 0 到 1",
        "intent": "solve",
        "expected": ["1"],
    },
    {
        "id": "12-01",
        "chapter": "12 无穷级数",
        "question": "判断级数 1/n^2 收敛",
        "intent": "solve",
        "expected": ["收敛"],
    },
    {
        "id": "12-02",
        "chapter": "12 无穷级数",
        "question": "级数求和 1/n^2",
        "intent": "solve",
        "expected": ["pi**2/6"],
    },
    {
        "id": "12-03",
        "chapter": "12 无穷级数",
        "question": "幂级数 a_n=1/n 的收敛半径",
        "intent": "solve",
        "expected": ["1"],
    },
)


def _post_chat(
    base_url: str,
    case: dict[str, Any],
    repeat_index: int,
    timeout: float,
) -> tuple[int | None, dict[str, Any] | None, str]:
    payload = json.dumps(
        {
            "message": case["question"],
            "history": [],
            "mode": "qa",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/demo/api/chat",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Demo-Session": (
                f"chapter-audit-{case['id']}-{repeat_index}-{int(time.time())}"
            ),
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body), ""
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(body)
        except json.JSONDecodeError:
            error_payload = {"reply": body}
        return exc.code, error_payload, f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        return None, None, str(exc)


def _calculation_text(calculation: Any) -> str:
    if calculation is None:
        return ""
    return json.dumps(calculation, ensure_ascii=False, sort_keys=True)


def _extract_result(calculation: Any) -> str:
    if not isinstance(calculation, dict):
        return ""
    for key in ("result", "limit", "derivative", "integral", "solution"):
        value = calculation.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _response_signature(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    stable_payload = {
        "calculation": payload.get("calculation"),
        "formula_latex": payload.get("formula_latex"),
        "intent": payload.get("intent"),
        "mode": payload.get("mode"),
        "reply": payload.get("reply"),
        "status": payload.get("status"),
    }
    encoded = json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _classify(
    case: dict[str, Any],
    http_status: int | None,
    payload: dict[str, Any] | None,
    transport_error: str,
) -> tuple[str, list[str], str, float]:
    missing_headings = [
        heading
        for heading in HEADINGS
        if payload is None or heading not in str(payload.get("reply", ""))
    ]
    if http_status is None:
        return "network_error", missing_headings, "", 0.0
    if http_status != 200:
        return "http_error", missing_headings, "", 0.0
    if payload is None:
        return "invalid_json", missing_headings, "", 0.0
    if payload.get("status") != "ok":
        return "solve_error", missing_headings, "", 0.0

    calculation = payload.get("calculation")
    result = _extract_result(calculation)
    if calculation is None:
        return "non_deterministic_or_missing_calculation", missing_headings, result, 0.0
    if payload.get("intent") != case["intent"]:
        return "routing_error", missing_headings, result, 0.0
    if missing_headings:
        return "format_incomplete", missing_headings, result, 0.0

    searchable = "\n".join(
        (
            _calculation_text(calculation),
            str(payload.get("reply", "")),
            str(payload.get("formula_latex", "")),
        )
    )
    if not all(token in searchable for token in case["expected"]):
        return "answer_mismatch", missing_headings, result, 0.0
    return "pass", missing_headings, result, 0.0


def run_audit(
    base_url: str,
    *,
    repeat: int,
    delay: float,
    timeout: float,
) -> dict[str, Any]:
    started = datetime.now().astimezone()
    results: list[dict[str, Any]] = []
    for case in CASES:
        for repeat_index in range(1, repeat + 1):
            request_started = time.perf_counter()
            http_status, payload, transport_error = _post_chat(
                base_url,
                case,
                repeat_index,
                timeout,
            )
            elapsed_ms = round(
                (time.perf_counter() - request_started) * 1000,
                1,
            )
            failure, missing_headings, result, _ = _classify(
                case,
                http_status,
                payload,
                transport_error,
            )
            calculation = (
                payload.get("calculation")
                if isinstance(payload, dict)
                else None
            )
            method = (
                str(calculation.get("method", ""))
                if isinstance(calculation, dict)
                else ""
            )
            reply = str(payload.get("reply", "")) if payload else ""
            results.append(
                {
                    **case,
                    "repeat": repeat_index,
                    "http_status": http_status,
                    "response_status": (
                        payload.get("status") if payload else None
                    ),
                    "response_intent": (
                        payload.get("intent") if payload else None
                    ),
                    "mode": payload.get("mode") if payload else None,
                    "method": method,
                    "result": result,
                    "elapsed_ms": elapsed_ms,
                    "missing_headings": missing_headings,
                    "failure_category": failure,
                    "transport_error": transport_error,
                    "reply_excerpt": reply[:1000],
                    "response_signature": _response_signature(payload),
                }
            )
            if delay > 0:
                time.sleep(delay)

    failures = Counter(
        result["failure_category"]
        for result in results
        if result["failure_category"] != "pass"
    )
    chapters = sorted({result["chapter"] for result in results})
    rate_limited = sum(
        result["http_status"] == 429 for result in results
    )
    math_attempts = len(results) - rate_limited
    math_passed = sum(
        result["failure_category"] == "pass" for result in results
    )
    chapter_breakdown: dict[str, dict[str, int]] = {}
    for chapter in chapters:
        chapter_results = [
            result for result in results if result["chapter"] == chapter
        ]
        chapter_breakdown[chapter] = {
            "requests": len(chapter_results),
            "passed": sum(
                result["failure_category"] == "pass"
                for result in chapter_results
            ),
            "failed": sum(
                result["failure_category"] != "pass"
                for result in chapter_results
            ),
            "rate_limited": sum(
                result["http_status"] == 429 for result in chapter_results
            ),
        }
    consistency_rows: list[dict[str, Any]] = []
    for case in CASES:
        case_results = [
            result for result in results if result["id"] == case["id"]
        ]
        signatures = {
            result["response_signature"]
            for result in case_results
            if result["response_signature"]
        }
        consistency_rows.append(
            {
                "id": case["id"],
                "chapter": case["chapter"],
                "question": case["question"],
                "response_count": len(case_results),
                "distinct_responses": len(signatures),
                "consistent": len(signatures) == 1,
            }
        )
    consistent_cases = sum(
        row["consistent"] for row in consistency_rows
    )
    return {
        "generated_at": started.isoformat(timespec="seconds"),
        "base_url": base_url.rstrip("/"),
        "repeat": repeat,
        "case_count": len(CASES),
        "request_count": len(results),
        "chapter_count": len(chapters),
        "passed": sum(result["failure_category"] == "pass" for result in results),
        "failed": sum(result["failure_category"] != "pass" for result in results),
        "rate_limited": rate_limited,
        "math_attempts": math_attempts,
        "math_passed": math_passed,
        "math_failed": math_attempts - math_passed,
        "math_pass_rate": (
            round(math_passed / math_attempts, 4) if math_attempts else None
        ),
        "failure_breakdown": dict(sorted(failures.items())),
        "chapter_breakdown": chapter_breakdown,
        "consistency": {
            "case_count": len(consistency_rows),
            "consistent_cases": consistent_cases,
            "inconsistent_cases": len(consistency_rows) - consistent_cases,
            "rows": consistency_rows,
        },
        "results": results,
    }


def _escape_markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def write_reports(
    audit: dict[str, Any],
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# 同济高数 12 章真实 HTTP 审计",
        "",
        f"- 生成时间：{audit['generated_at']}",
        f"- 目标：`{audit['base_url']}`",
        f"- 题目数：{audit['case_count']}，章节数：{audit['chapter_count']}",
        f"- 请求数：{audit['request_count']}，通过：{audit['passed']}，失败：{audit['failed']}",
        f"- 限流请求（429）：{audit['rate_limited']}",
        (
            "- 排除限流后的数学通过率："
            f"{audit['math_passed']}/{audit['math_attempts']} "
            f"({(audit['math_pass_rate'] or 0) * 100:.2f}%)"
        ),
        (
            "- 同题三次响应一致性："
            f"{audit['consistency']['consistent_cases']}/"
            f"{audit['consistency']['case_count']} 题一致"
        ),
        f"- 每章题数：3",
        "",
        "## 失败分类",
        "",
    ]
    if audit["failure_breakdown"]:
        lines.extend(
            f"- `{category}`：{count}"
            for category, count in audit["failure_breakdown"].items()
        )
    else:
        lines.append("- 无失败项")
    lines.extend(
        (
            "",
            "## 分章统计",
            "",
            "| 章节 | 请求 | 通过 | 失败 | 429 |",
            "| --- | ---: | ---: | ---: | ---: |",
        )
    )
    for chapter, stats in audit["chapter_breakdown"].items():
        lines.append(
            f"| {_escape_markdown(chapter)} | {stats['requests']} | "
            f"{stats['passed']} | {stats['failed']} | {stats['rate_limited']} |"
        )
    lines.extend(
        (
            "",
            "## 重复一致性",
            "",
            "| 编号 | 题目 | 响应数 | 不同响应数 | 结论 |",
            "| --- | --- | ---: | ---: | --- |",
        )
    )
    for row in audit["consistency"]["rows"]:
        lines.append(
            f"| {row['id']} | {_escape_markdown(row['question'])} | "
            f"{row['response_count']} | {row['distinct_responses']} | "
            f"{'一致' if row['consistent'] else '不一致'} |"
        )
    lines.extend(
        (
            "",
            "## 逐题结果",
            "",
            "| 编号 | 章节 | 题目 | HTTP | 意图 | 方法 | 耗时(ms) | 结果 | 结论 |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
        )
    )
    for result in audit["results"]:
        if result["failure_category"] == "pass":
            verdict = "通过"
        elif result["missing_headings"]:
            verdict = (
                f"{result['failure_category']}；缺 "
                + "、".join(result["missing_headings"])
            )
        else:
            verdict = result["failure_category"]
        lines.append(
            "| {id}-{repeat} | {chapter} | {question} | {http} | "
            "{intent} | {method} | {elapsed} | {answer} | {verdict} |".format(
                id=_escape_markdown(result["id"]),
                repeat=result["repeat"],
                chapter=_escape_markdown(result["chapter"]),
                question=_escape_markdown(result["question"]),
                http=_escape_markdown(result["http_status"]),
                intent=_escape_markdown(result["response_intent"]),
                method=_escape_markdown(result["method"]),
                elapsed=_escape_markdown(result["elapsed_ms"]),
                answer=_escape_markdown(result["result"] or "-")[:240],
                verdict=_escape_markdown(verdict),
            )
        )
    lines.extend(
        (
            "",
            "## 判定规则",
            "",
            "只有 HTTP 200、状态 ok、确定性 calculation 存在、意图匹配、"
            "四段式标题完整且预期答案命中时才记为通过。"
            "只由通用模型给出看似正确的回答仍记为失败，因为无法保证重复稳定性。",
        )
    )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Running demo site base URL.",
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("work/chapter-audit-20261124.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("work/chapter-audit-20261124.md"),
    )
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    audit = run_audit(
        args.base_url,
        repeat=args.repeat,
        delay=args.delay,
        timeout=args.timeout,
    )
    write_reports(audit, args.json_output, args.markdown_output)
    print(
        json.dumps(
            {
                "passed": audit["passed"],
                "failed": audit["failed"],
                "requests": audit["request_count"],
                "rate_limited": audit["rate_limited"],
                "math_pass_rate": audit["math_pass_rate"],
                "consistent_cases": audit["consistency"]["consistent_cases"],
                "failures": audit["failure_breakdown"],
                "json": str(args.json_output),
                "markdown": str(args.markdown_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if audit["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
