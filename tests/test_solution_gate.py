import copy
import unittest
from unittest.mock import patch

from app.chapter_solvers import MissingInputError, solve_chapter
from app.math_text import normalize_math_text
from app.solution_gate import is_verified_solution
from deploy import demo_chat


PARAMETRIC_QUESTION = (
    "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
    "处的切线方程和法线方程。"
)
PARAMETRIC_INPUTS = {
    "x_expression": "sin(t)",
    "y_expression": "cos(2*t)",
    "parameter": "t",
    "parameter_value": "pi/4",
}
INCOMPLETE_MATH_QUESTIONS = (
    "求参数方程 x=sin(t), y=cos(2t) 的切线方程和法线方程",
    "求函数的极值",
    "求函数的最大值",
    "求积分",
    "求微分方程的通解",
    "求极限",
)
CURVE_ANALYSIS_QUESTION = (
    "求函数 y = x^3 - 12x + 10 的单调区间,极值点,凹凸区间,拐点。"
)
INFINITESIMAL_COMPARISON_QUESTION = (
    "2. 当 x -> 0 时,下列函数哪一个 是其他三个的高阶无穷小( )\n"
    "A. x^2\n"
    "B. 1 - cos(x)\n"
    "C. x - tan(x)\n"
    "D. ln(1+x^2)"
)


class SolutionGateContractTest(unittest.TestCase):
    def test_chapter_solution_has_verified_gate_contract(self):
        payload = solve_chapter(
            "derivatives",
            "parametric_tangent_normal",
            PARAMETRIC_INPUTS,
        )

        self.assertEqual("ok", payload["status"])
        self.assertIs(True, payload["verified"])
        self.assertEqual(
            "parametric_tangent_normal",
            payload["verification"]["kind"],
        )
        self.assertIs(True, payload["verification"]["passed"])
        self.assertTrue(payload["verification"]["checks"])
        self.assertTrue(
            all(check["passed"] for check in payload["verification"]["checks"])
        )

    def test_parametric_tangent_normal_positive_case(self):
        payload = solve_chapter(
            "derivatives",
            "parametric_tangent_normal",
            PARAMETRIC_INPUTS,
        )

        self.assertIn("(sqrt(2)/2, 0)", payload["result"])
        self.assertIn("y = -2*sqrt(2)*x + 2", payload["result"])
        self.assertIn("y = sqrt(2)*x/4 - 1/4", payload["result"])
        self.assertIs(
            True,
            payload["verification"]["passed"],
        )
        self.assertIn(
            "tangent_point",
            {
                check["name"]
                for check in payload["verification"]["checks"]
            },
        )
        self.assertIn(
            "normal_slope_relation",
            {
                check["name"]
                for check in payload["verification"]["checks"]
            },
        )

    def test_parametric_tangent_normal_requires_parameter_value(self):
        with self.assertRaises(MissingInputError) as raised:
            solve_chapter(
                "derivatives",
                "parametric_tangent_normal",
                {
                    "x_expression": "sin(t)",
                    "y_expression": "cos(2*t)",
                    "parameter": "t",
                },
            )

        self.assertEqual("parameter_value", raised.exception.field)
        self.assertIn("参数点", raised.exception.detail)

    def test_known_function_arguments_are_canonicalized(self):
        equivalent_cases = (
            ("cos(2t)", "cos(2 t)", "cos(2*t)"),
            ("sqrt(4t)", "sqrt(4 t)", "sqrt(4*t)"),
        )

        for variants in equivalent_cases:
            with self.subTest(variants=variants):
                normalized = {
                    normalize_math_text(value)
                    for value in variants
                }
                self.assertEqual(1, len(normalized))

        self.assertEqual(
            "sin(cos(2*t))",
            normalize_math_text("sin(cos(2t))"),
        )
        self.assertEqual(
            "cos(2*cos(t))",
            normalize_math_text("cos(2cos(t))"),
        )
        self.assertEqual("sin(t)", normalize_math_text("sin(t)"))

    def test_chinese_infinity_terms_are_normalized_safely(self):
        self.assertEqual("x趋于oo", normalize_math_text("x趋于正无穷"))
        self.assertEqual("x趋于-oo", normalize_math_text("x趋于负无穷大"))
        self.assertEqual("x趋于oo", normalize_math_text("x趋于无穷"))
        self.assertEqual("x趋于oo", normalize_math_text("x趋于∞"))
        self.assertEqual("无穷级数", normalize_math_text("无穷级数"))
        self.assertEqual("无穷小", normalize_math_text("无穷小"))
        self.assertEqual("无穷大量", normalize_math_text("无穷大量"))
        self.assertEqual("无穷远", normalize_math_text("无穷远"))
        self.assertEqual("无穷多", normalize_math_text("无穷多"))

    def test_adjacent_spoken_roots_are_normalized_independently(self):
        cases = (
            ("根号下x加根号下y", "sqrt(x)+sqrt(y)"),
            ("根号下x减根号下y", "sqrt(x)-sqrt(y)"),
        )

        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(expected, normalize_math_text(source))

    def test_spoofed_ok_without_complete_gate_is_rejected(self):
        spoofed_payloads = (
            {
                "status": "ok",
                "intent": "verify",
                "calculation": None,
            },
            {
                "status": "ok",
                "intent": "verify",
                "calculation": {"derivative": "2*x"},
                "verified": False,
                "verification": {
                    "passed": False,
                    "checks": [{"name": "rule", "passed": False}],
                },
            },
            {
                "status": "ok",
                "intent": "verify",
                "calculation": {"derivative": "2*x"},
                "verified": True,
                "verification": {
                    "passed": True,
                    "checks": [],
                },
            },
        )

        for payload in spoofed_payloads:
            with self.subTest(payload=payload):
                self.assertFalse(is_verified_solution(payload))

    def test_bare_result_cannot_pass_solution_gate(self):
        payload = {
            "status": "ok",
            "intent": "solve",
            "verified": True,
            "verification": {
                "passed": True,
                "kind": "generic_solve",
                "checks": [{"name": "result_available", "passed": True}],
            },
            "calculation": {"result": "2*x"},
        }

        self.assertFalse(is_verified_solution(payload))

    def test_arithmetic_requires_original_expression(self):
        payload = {
            "status": "ok",
            "intent": "arithmetic",
            "verified": True,
            "verification": {
                "passed": True,
                "kind": "arithmetic",
                "checks": [{"name": "result_available", "passed": True}],
            },
            "calculation": {"result": "9"},
        }

        self.assertFalse(is_verified_solution(payload))

    def test_stale_checks_cannot_validate_modified_result(self):
        payload = demo_chat.build_chat_response("求导 x^2")
        tampered = copy.deepcopy(payload)
        tampered["calculation"]["derivative"] = "3*x"
        tampered["calculation"]["derivative_function"] = "3*x"

        self.assertIs(True, payload["verified"])
        self.assertFalse(is_verified_solution(tampered))

    def test_tampered_chapter_context_is_rejected(self):
        payload = solve_chapter(
            "derivatives",
            "parametric_tangent_normal",
            PARAMETRIC_INPUTS,
        )
        tampered = copy.deepcopy(payload)
        tampered["verification_context"]["inputs"]["parameter_value"] = "pi/3"

        self.assertFalse(is_verified_solution(tampered))

    def test_chapter_solution_without_context_is_rejected(self):
        payload = demo_chat.build_chat_response(PARAMETRIC_QUESTION)
        tampered = copy.deepcopy(payload)
        tampered.pop("verification_context", None)
        tampered["calculation"].pop("verification_context", None)

        self.assertFalse(is_verified_solution(tampered))

    def test_unregistered_chapter_verifier_cannot_pass(self):
        payload = {
            "status": "ok",
            "intent": "solve",
            "verified": True,
            "verification": {
                "passed": True,
                "kind": "not_registered",
                "checks": [{"name": "looks_ok", "passed": True}],
            },
            "verification_context": {
                "chapter": "unknown",
                "topic": "not_registered",
                "inputs": {},
            },
            "calculation": {
                "chapter": "unknown",
                "topic": "not_registered",
                "result": "42",
            },
        }

        self.assertFalse(is_verified_solution(payload))

    def test_valid_supported_solution_shapes_still_pass(self):
        questions = (
            "求导 x^2",
            "解方程 x^2-1=0",
            "求矩阵 [[1,2],[3,4]] 的行列式",
            "求函数 f(x)=x^2-4x+3 在 [0,5] 上的最大值",
        )

        for question in questions:
            with self.subTest(question=question):
                payload = demo_chat.build_chat_response(question)

                self.assertEqual("ok", payload["status"])
                self.assertIs(True, payload["verified"])
                self.assertTrue(is_verified_solution(payload))

    def test_nonexistent_limit_requires_matching_side_evidence(self):
        payload = demo_chat.build_chat_response("求极限 x→0 1/x")
        tampered = copy.deepcopy(payload)
        tampered["calculation"]["left_limit"] = "0"

        self.assertIs(True, payload["verified"])
        self.assertFalse(is_verified_solution(tampered))


class UnifiedDisplayGateTest(unittest.TestCase):
    def test_six_missing_condition_cases_fail_without_downstream_content(self):
        for question in INCOMPLETE_MATH_QUESTIONS:
            with self.subTest(question=question):
                with patch.object(
                    demo_chat,
                    "_build_general_chat_response",
                    return_value=None,
                ):
                    payload = demo_chat.build_chat_response(question)

                self.assertNotEqual("ok", payload["status"])
                self.assertIsNot(True, payload.get("verified"))
                self.assertIsNone(payload.get("calculation"))
                self.assertFalse(payload.get("knowledge_points") or [])
                self.assertNotIn("**最终答案**", payload.get("reply", ""))

    def test_missing_parameter_point_returns_explicit_needs_input(self):
        with patch.object(
            demo_chat,
            "_build_general_chat_response",
            return_value=None,
        ):
            payload = demo_chat.build_chat_response(
                "求参数方程 x=sin(t), y=cos(2t) 的切线方程和法线方程"
            )

        self.assertEqual("needs_input", payload["status"])
        self.assertEqual("solve", payload["intent"])
        self.assertIsNone(payload["calculation"])
        self.assertEqual(["parameter_value"], payload["missing_fields"])
        self.assertIsNot(True, payload.get("verified"))
        self.assertFalse(payload.get("knowledge_points") or [])

    def test_missing_differential_equation_returns_explicit_needs_input(self):
        with patch.object(
            demo_chat,
            "_build_general_chat_response",
            return_value=None,
        ):
            payload = demo_chat.build_chat_response("求微分方程的通解")

        self.assertEqual("needs_input", payload["status"])
        self.assertEqual("solve", payload["intent"])
        self.assertIsNone(payload["calculation"])
        self.assertEqual(["equation"], payload["missing_fields"])
        self.assertIsNot(True, payload.get("verified"))
        self.assertFalse(payload.get("knowledge_points") or [])

    def test_ocr_confirmation_reply_avoids_duplicate_punctuation(self):
        question = "求极限 x→0 sin(x)/x。"
        reply = demo_chat.build_ocr_confirmation_reply(question)

        self.assertIn(f"题目已识别，请核对：{question}", reply)
        self.assertNotIn("。。", reply)
        self.assertIn("确认无误回复“确认”，我将开始计算。", reply)

    def test_incomplete_extrema_requests_never_fall_through_to_general_chat(self):
        general_success = {
            "status": "ok",
            "intent": "general",
            "reply": "这是一个不应出现的通用模型成功回答。",
            "formula_latex": "",
            "formula_text": "",
            "calculation": None,
        }

        for question in ("求函数的极值", "求函数的最大值", "求函数的最小值"):
            with self.subTest(question=question):
                with patch.object(
                    demo_chat,
                    "_build_general_chat_response",
                    return_value=general_success,
                ) as general_chat:
                    payload = demo_chat.build_chat_response(question)

                self.assertEqual("needs_input", payload["status"])
                self.assertEqual("solve", payload["intent"])
                self.assertIsNone(payload["calculation"])
                self.assertFalse(payload.get("knowledge_points") or [])
                self.assertIn("具体函数表达式", payload["reply"])
                general_chat.assert_not_called()

    def test_extrema_concept_questions_still_use_concept_answer_path(self):
        concept_response = {
            "status": "ok",
            "intent": "general",
            "reply": "极值描述的是局部范围，最值描述的是整个定义域或指定区间。",
            "formula_latex": "",
            "formula_text": "",
            "calculation": None,
        }

        for question in ("极值的定义", "最大值的概念"):
            with self.subTest(question=question):
                with (
                    patch.object(
                        demo_chat,
                        "_build_knowledge_response",
                        return_value=None,
                    ),
                    patch.object(
                        demo_chat,
                        "_build_general_chat_response",
                        return_value=concept_response,
                    ) as general_chat,
                ):
                    payload = demo_chat.build_chat_response(question)

                self.assertEqual("general", payload["intent"])
                general_chat.assert_called_once()

    def test_failed_math_request_cannot_start_teaching(self):
        from deploy import wsgi_app

        failed = demo_chat.build_chat_response("求积分")
        response = wsgi_app._start_teaching_response(
            "solution-gate-test",
            "求积分",
            failed,
        )

        self.assertEqual("error", response["status"])
        self.assertIsNone(response.get("calculation"))
        self.assertIsNone(response.get("teaching"))
        self.assertFalse(response.get("knowledge_points") or [])

    def test_incomplete_success_claim_cannot_start_teaching(self):
        from deploy import wsgi_app

        spoofed = {
            "status": "ok",
            "intent": "verify",
            "reply": "看起来已经完成。",
            "calculation": {"derivative": "2*x"},
            "verified": True,
            "verification": {
                "passed": True,
                "checks": [],
            },
        }
        response = wsgi_app._start_teaching_response(
            "spoofed-solution-gate-test",
            "求导 x^2",
            spoofed,
        )

        self.assertEqual("error", response["status"])
        self.assertEqual("teaching_failed", response["intent"])
        self.assertIsNone(response.get("calculation"))
        self.assertIsNone(response.get("teaching"))
        self.assertFalse(response.get("knowledge_points") or [])

    def test_manual_and_confirmed_ocr_paths_match(self):
        manual = demo_chat.build_chat_response(PARAMETRIC_QUESTION)
        confirmed = demo_chat._solve_confirmed_question(PARAMETRIC_QUESTION)

        self.assertEqual("ok", manual["status"])
        self.assertEqual(manual["calculation"], confirmed["calculation"])
        self.assertEqual(manual["reply"], confirmed["reply"])
        self.assertEqual(
            manual.get("knowledge_points"),
            confirmed.get("knowledge_points"),
        )
        self.assertIs(True, manual.get("verified"))
        self.assertIs(True, confirmed.get("verified"))

    def test_curve_analysis_manual_and_confirmed_paths_are_complete(self):
        manual = demo_chat.build_chat_response(CURVE_ANALYSIS_QUESTION)
        confirmed = demo_chat._solve_confirmed_question(
            CURVE_ANALYSIS_QUESTION
        )

        for payload in (manual, confirmed):
            self.assertEqual("ok", payload["status"])
            self.assertEqual("solve", payload["intent"])
            self.assertIs(True, payload["verified"])
            self.assertEqual(
                "curve_analysis",
                payload["calculation"]["topic"],
            )
            self.assertIn("单调递增区间", payload["reply"])
            self.assertIn("极大值", payload["reply"])
            self.assertIn("拐点", payload["reply"])
            self.assertIn(
                "一阶导数与单调区间的判定",
                payload["knowledge_points"],
            )
            for heading in (
                "**题目理解**",
                "**解题思路**",
                "**详细计算步骤**",
                "**最终答案**",
            ):
                self.assertIn(heading, payload["reply"])

        self.assertEqual(manual["calculation"], confirmed["calculation"])
        self.assertEqual(manual["reply"], confirmed["reply"])
        self.assertEqual(
            manual["knowledge_points"],
            confirmed["knowledge_points"],
        )

    def test_infinitesimal_comparison_manual_and_confirmed_paths_are_complete(
        self,
    ):
        manual = demo_chat.build_chat_response(
            INFINITESIMAL_COMPARISON_QUESTION
        )
        confirmed = demo_chat._solve_confirmed_question(
            INFINITESIMAL_COMPARISON_QUESTION
        )

        for payload in (manual, confirmed):
            self.assertEqual("ok", payload["status"])
            self.assertEqual("solve", payload["intent"])
            self.assertIs(True, payload["verified"])
            self.assertEqual("C", payload["calculation"]["result"])
            self.assertEqual(
                {"A": 2, "B": 2, "C": 3, "D": 2},
                payload["calculation"]["details"]["orders"],
            )
            self.assertIn("选项 C", payload["reply"])
            self.assertIn(
                "无穷小阶数的定义",
                payload["knowledge_points"],
            )

        self.assertEqual(manual["calculation"], confirmed["calculation"])
        self.assertEqual(manual["reply"], confirmed["reply"])
        self.assertEqual(
            manual["knowledge_points"],
            confirmed["knowledge_points"],
        )

    def test_natural_language_core_requests_are_verified_and_repeatable(self):
        cases = (
            (
                "当 x 从 0 到 pi 时 sin(x) 的定积分",
                "integrate",
                "integral",
                "2",
            ),
            (
                "y的导数减y等于0",
                "solve",
                "result",
                "C1*exp(x)",
            ),
            (
                "一般项 1/n^2 是否收敛",
                "solve",
                "result",
                "收敛",
            ),
            (
                "求 z=x^2*y 在点 (1,2) 处对 x 的偏导数",
                "solve",
                "result",
                "4",
            ),
        )

        for question, intent, result_key, expected_result in cases:
            with self.subTest(question=question):
                payloads = [
                    demo_chat.build_chat_response(question)
                    for _ in range(3)
                ]
                baseline = payloads[0]

                self.assertEqual("ok", baseline["status"])
                self.assertEqual(intent, baseline["intent"])
                self.assertIs(True, baseline.get("verified"))
                self.assertIn(
                    expected_result,
                    baseline["calculation"][result_key],
                )
                for payload in payloads[1:]:
                    self.assertEqual(
                        baseline["calculation"],
                        payload["calculation"],
                    )
                    self.assertEqual(baseline["reply"], payload["reply"])
                    self.assertEqual(
                        baseline["verification"],
                        payload["verification"],
                    )

    def test_natural_language_word_order_variants_are_supported(self):
        cases = (
            (
                "x平方在0到1上的定积分",
                "integrate",
                "integral",
                "1/3",
            ),
            (
                "sin(x)/x 在 x趋于0 时的极限",
                "limit",
                "limit",
                "1",
            ),
        )

        for question, intent, result_key, expected_result in cases:
            with self.subTest(question=question):
                payload = demo_chat.build_chat_response(question)

                self.assertEqual("ok", payload["status"])
                self.assertEqual(intent, payload["intent"])
                self.assertIs(True, payload.get("verified"))
                self.assertIn(
                    expected_result,
                    payload["calculation"][result_key],
                )

    def test_natural_language_core_requests_match_confirmed_ocr_path(self):
        questions = (
            "当 x 从 0 到 pi 时 sin(x) 的定积分",
            "y的导数减y等于0",
            "一般项 1/n^2 是否收敛",
            "求 z=x^2*y 在点 (1,2) 处对 x 的偏导数",
        )

        for question in questions:
            with self.subTest(question=question):
                manual = demo_chat.build_chat_response(question)
                confirmed = demo_chat._solve_confirmed_question(question)

                self.assertEqual("ok", manual["status"])
                self.assertEqual("ok", confirmed["status"])
                self.assertEqual(manual["calculation"], confirmed["calculation"])
                self.assertEqual(manual["reply"], confirmed["reply"])
                self.assertEqual(
                    manual.get("knowledge_points"),
                    confirmed.get("knowledge_points"),
                )
                self.assertIs(True, confirmed.get("verified"))

    def test_partial_derivative_with_incomplete_point_fails_closed(self):
        with patch.object(
            demo_chat,
            "_build_general_chat_response",
            return_value=None,
        ):
            payload = demo_chat.build_chat_response(
                "求 z=x^2*y 在点 (1) 处对 x 的偏导数"
            )

        self.assertNotEqual("ok", payload["status"])
        self.assertIsNot(True, payload.get("verified"))
        self.assertIsNone(payload.get("calculation"))
        self.assertFalse(payload.get("knowledge_points") or [])
        self.assertNotIn("**最终答案**", payload.get("reply", ""))

    def test_new_topics_reject_missing_required_conditions(self):
        cases = (
            (
                "求函数的单调区间、极值点、凹凸区间和拐点",
                "expression",
            ),
            (
                "当 x 趋于 时，下列哪个是其他三个的高阶无穷小 "
                "A. x^2 B. 1-cos(x) C. x-tan(x) D. ln(1+x^2)",
                "point",
            ),
            (
                "当 x -> 0 时，下列哪个是其他三个的高阶无穷小 "
                "A. x^2 B. 1-cos(x) C. x-tan(x)",
                "options",
            ),
        )

        for question, missing_field in cases:
            with self.subTest(question=question):
                with patch.object(
                    demo_chat,
                    "_build_general_chat_response",
                    return_value=None,
                ):
                    payload = demo_chat.build_chat_response(question)

                self.assertEqual("needs_input", payload["status"])
                self.assertEqual("solve", payload["intent"])
                self.assertIsNone(payload.get("calculation"))
                self.assertIsNot(True, payload.get("verified"))
                self.assertFalse(payload.get("knowledge_points") or [])
                self.assertEqual(
                    [missing_field],
                    payload.get("missing_fields"),
                )
                self.assertNotIn("**最终答案**", payload.get("reply", ""))

    def test_confirmed_failure_text_has_no_unrelated_topic_requirements(self):
        unknown = demo_chat._needs_input(
            "我还没识别出具体要计算的内容。",
            intent="unknown",
        )
        with (
            patch.object(
                demo_chat,
                "_math_response",
                return_value=unknown,
            ),
            patch.object(
                demo_chat,
                "_build_general_chat_response",
                return_value=None,
            ),
        ):
            payload = demo_chat._solve_confirmed_question(
                "这是一道暂时无法归类的题目"
            )

        self.assertEqual("error", payload["status"])
        self.assertNotIn("参数方程", payload["reply"])
        self.assertIn("没有识别出可验证的题型", payload["reply"])

    def test_new_topic_tampering_cannot_pass_solution_gate(self):
        curve = demo_chat.build_chat_response(CURVE_ANALYSIS_QUESTION)
        tampered_curve = copy.deepcopy(curve)
        tampered_curve["calculation"]["details"]["local_maxima"][0]["y"] = "25"
        self.assertFalse(is_verified_solution(tampered_curve))

        infinitesimal = demo_chat.build_chat_response(
            INFINITESIMAL_COMPARISON_QUESTION
        )
        tampered_infinitesimal = copy.deepcopy(infinitesimal)
        tampered_infinitesimal["calculation"]["details"]["orders"]["C"] = 2
        self.assertFalse(is_verified_solution(tampered_infinitesimal))

    def test_new_topics_are_stable_across_repeated_submissions(self):
        for question in (
            CURVE_ANALYSIS_QUESTION,
            INFINITESIMAL_COMPARISON_QUESTION,
        ):
            with self.subTest(question=question):
                payloads = [
                    demo_chat.build_chat_response(question)
                    for _ in range(3)
                ]
                baseline = payloads[0]
                self.assertEqual("ok", baseline["status"])
                self.assertIs(True, baseline["verified"])

                for payload in payloads[1:]:
                    self.assertEqual(
                        baseline["calculation"],
                        payload["calculation"],
                    )
                    self.assertEqual(baseline["reply"], payload["reply"])
                    self.assertEqual(
                        baseline["verification"],
                        payload["verification"],
                    )
                    self.assertEqual(
                        baseline["knowledge_points"],
                        payload["knowledge_points"],
                    )

    def test_repeated_submission_is_stable(self):
        payloads = [
            demo_chat.build_chat_response(PARAMETRIC_QUESTION)
            for _ in range(5)
        ]

        baseline = payloads[0]
        self.assertEqual("ok", baseline["status"])
        self.assertIs(True, baseline["verified"])
        for payload in payloads[1:]:
            self.assertEqual(baseline["calculation"], payload["calculation"])
            self.assertEqual(baseline["reply"], payload["reply"])
            self.assertEqual(
                baseline["verification"],
                payload["verification"],
            )
            self.assertEqual(
                baseline["knowledge_points"],
                payload["knowledge_points"],
            )


if __name__ == "__main__":
    unittest.main()
