import json
import unittest
from unittest.mock import patch

from deploy import demo_chat


class DemoChatRegressionTest(unittest.TestCase):
    def test_spoken_chinese_math_is_normalized_before_solving(self):
        cases = (
            ("求 x的平方 的导数", "verify", "x**2", "2*x"),
            ("根号下x 的积分", "integrate", "sqrt(x)", "2*x**(3/2)/3"),
            ("0 到 1 x平方 的定积分", "integrate", "x**2", "1/3"),
            ("求极限 x→0 sinx除以x", "limit", "sin(x)/x", "1"),
        )
        for message, intent, expression, result in cases:
            with self.subTest(message=message):
                payload = demo_chat.build_chat_response(message)

                self.assertEqual("ok", payload["status"])
                self.assertEqual(intent, payload["intent"])
                self.assertEqual(
                    expression,
                    payload["calculation"]["expression"],
                )
                result_key = {
                    "verify": "derivative",
                    "integrate": "integral",
                    "limit": "limit",
                }[intent]
                self.assertEqual(result, payload["calculation"][result_key])

    def test_spoken_expression_only_is_normalized_without_calculation(self):
        cases = (
            ("x分之一", "1/x"),
            ("x的立方", "x**3"),
        )
        for message, normalized in cases:
            with self.subTest(message=message):
                payload = demo_chat.build_chat_response(message)

                self.assertEqual("ok", payload["status"])
                self.assertEqual("normalize", payload["intent"])
                self.assertEqual(normalized, payload["formula_text"])

    def test_math_concept_question_uses_tongji_knowledge(self):
        payload = demo_chat.build_chat_response("积分的定义")

        self.assertEqual("ok", payload["status"])
        self.assertEqual("knowledge", payload["intent"])
        self.assertNotIn("这次没算出来", payload["reply"])

    def test_compact_definite_integral(self):
        payload = demo_chat.build_chat_response("计算定积分 ∫0^1 x^2 dx")

        self.assertEqual("ok", payload["status"])
        self.assertEqual("integrate", payload["intent"])
        self.assertEqual("x**2", payload["calculation"]["expression"])
        self.assertEqual("1/3", payload["calculation"]["integral"])

    def test_parametric_tangent_normal_solution_is_repeatable(self):
        question = (
            "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
            "处的切线方程和法线方程。"
        )
        payloads = [
            demo_chat.build_chat_response(question)
            for _ in range(3)
        ]

        for payload in payloads:
            self.assertEqual("ok", payload["status"])
            self.assertEqual("solve", payload["intent"])
            calculation = payload["calculation"]
            self.assertEqual("derivatives", calculation["chapter"])
            self.assertEqual(
                "parametric_tangent_normal",
                calculation["topic"],
            )
            self.assertIn("(sqrt(2)/2, 0)", calculation["result"])
            self.assertIn(
                "y = -2*sqrt(2)*x + 2",
                calculation["result"],
            )
            self.assertIn(
                "y = sqrt(2)*x/4 - 1/4",
                calculation["result"],
            )
            self.assertEqual(
                [
                    "参数方程求导",
                    "切线斜率与切线方程",
                    "法线斜率与法线方程",
                    "切点坐标与直线方程",
                ],
                [item["title"] for item in payload["knowledge_points"]],
            )
            self.assertIn("**题目理解**", payload["reply"])
            self.assertIn("dx", payload["reply"])
            self.assertIn("dy", payload["reply"])
            self.assertIn("切线斜率", payload["reply"])
            self.assertIn("法线斜率", payload["reply"])
            self.assertIn("切点", payload["reply"])
            self.assertIn("**最终答案**", payload["reply"])
            self.assertEqual(1, payload["reply"].count("切点为"))

        self.assertEqual(
            [payload["calculation"] for payload in payloads],
            [payloads[0]["calculation"]] * 3,
        )
        self.assertEqual(
            [payload["reply"] for payload in payloads],
            [payloads[0]["reply"]] * 3,
        )

    def test_natural_explicit_curve_tangent_uses_verified_solver(self):
        cases = (
            ("求曲线 y=x^2 在 x=1 处的切线方程", "Eq(y, 2*x - 1)"),
            ("求曲线 y=x^2 在点 x=1 处的切线", "Eq(y, 2*x - 1)"),
            ("求 y=x^2 在 x=-1 处的切线方程", "Eq(y, -2*x - 1)"),
        )
        for question, expected in cases:
            with self.subTest(question=question):
                payload = demo_chat.build_chat_response(question)
                calculation = payload["calculation"]

                self.assertEqual("ok", payload["status"])
                self.assertEqual("solve", payload["intent"])
                self.assertEqual("tangent", calculation["topic"])
                self.assertEqual(expected, calculation["result"])
                self.assertIs(True, payload["verified"])
                self.assertIn("一阶导数", payload["reply"])
                self.assertIn("切线斜率", payload["reply"])
                self.assertIn(calculation["latex"], payload["reply"])

    def test_explicit_tangent_and_normal_request_is_not_partially_solved(self):
        payload = demo_chat.build_chat_response(
            "求曲线 y=x^2 在 x=1 处的切线方程和法线方程"
        )

        self.assertNotEqual("ok", payload["status"])
        self.assertIsNone(payload["calculation"])
        self.assertIsNot(True, payload.get("verified"))
        self.assertNotIn("**最终答案**", payload["reply"])

    def test_generic_chapter_reply_uses_actual_conditions_and_verified_result(
        self,
    ):
        cases = (
            (
                "求梯度 x^2+y^2",
                "x^{2} + y^{2}",
                "2 x",
            ),
            (
                "求微分方程 y' - y = 0",
                "y' - y = 0",
                "C_{1} e^{x}",
            ),
        )
        headings = ("题目理解", "解题思路", "详细计算步骤", "最终答案")
        obsolete_phrases = (
            "本题属于“",
            "标准公式完成计算",
            "最终结果见下方公式与答案",
        )

        for question, condition_text, result_text in cases:
            with self.subTest(question=question):
                payload = demo_chat.build_chat_response(question)
                reply = payload["reply"]

                self.assertEqual("ok", payload["status"])
                self.assertEqual("solve", payload["intent"])
                self.assertIs(
                    True,
                    payload["calculation"]["verification"]["passed"],
                )
                positions = [reply.index(heading) for heading in headings]
                self.assertEqual(sorted(positions), positions)
                self.assertIn(condition_text, reply)
                self.assertIn(payload["calculation"]["latex"], reply)
                self.assertIn(result_text, reply)
                for phrase in obsolete_phrases:
                    self.assertNotIn(phrase, reply)

    def test_natural_language_limit_before_expression(self):
        payload = demo_chat.build_chat_response(
            "求极限 x→0 sin(3x)/x"
        )

        self.assertEqual("ok", payload["status"])
        self.assertEqual("limit", payload["intent"])
        self.assertEqual("sin(3*x)/x", payload["calculation"]["expression"])
        self.assertEqual("3", payload["calculation"]["limit"])

    def test_natural_language_one_sided_limit(self):
        payload = demo_chat.build_chat_response("求极限 x→0+ 1/x")

        self.assertEqual("limit", payload["intent"])
        self.assertEqual("1/x", payload["calculation"]["expression"])
        self.assertEqual("+", payload["calculation"]["direction"])
        self.assertEqual("oo", payload["calculation"]["limit"])

    def test_spoken_limit_forms_use_the_same_deterministic_solver(self):
        cases = (
            ("当x趋近0时sinx除以x的极限", "sin(x)/x", "0", None, "1"),
            ("求极限x→0+1/x", "1/x", "0", "+", "oo"),
            ("limx→0+1/x", "1/x", "0", "+", "oo"),
            (
                "当x趋近0时 (1+x)^(1/x) 的极限",
                "(x + 1)**(1/x)",
                "0",
                None,
                "E",
            ),
            (
                "求极限 x趋于无穷 (1+1/x)^x",
                "(1 + 1/x)**x",
                "oo",
                None,
                "E",
            ),
            (
                "求极限 x趋近于正无穷 (1+1/x)^x",
                "(1 + 1/x)**x",
                "oo",
                None,
                "E",
            ),
            (
                "求极限 x趋于正无穷时 1/x",
                "1/x",
                "oo",
                None,
                "0",
            ),
            (
                "求极限 x趋于∞时 1/x",
                "1/x",
                "oo",
                None,
                "0",
            ),
            (
                "求极限 x趋于无穷大时 1/x",
                "1/x",
                "oo",
                None,
                "0",
            ),
            ("求极限 x趋于0负 1/x", "1/x", "0", "-", "-oo"),
            ("求极限 x趋于负无穷 1/x", "1/x", "-oo", None, "0"),
        )
        for message, expression, point, direction, result in cases:
            with self.subTest(message=message):
                payload = demo_chat.build_chat_response(message)

                self.assertEqual("ok", payload["status"])
                self.assertEqual("limit", payload["intent"])
                self.assertEqual(
                    expression,
                    payload["calculation"]["expression"],
                )
                self.assertEqual(point, payload["calculation"]["point"])
                self.assertEqual(
                    direction,
                    payload["calculation"]["direction"],
                )
                self.assertEqual(result, payload["calculation"]["limit"])

    def test_two_sided_limit_reports_nonexistence(self):
        cases = (
            ("求极限 x→0 1/x", ("-oo", "oo")),
            ("当x趋近0时1/x的极限", ("-oo", "oo")),
            ("求极限 x→0 sin(1/x)", None),
        )
        for message, one_sided in cases:
            with self.subTest(message=message):
                payload = demo_chat.build_chat_response(message)
                calculation = payload["calculation"]

                self.assertEqual("ok", payload["status"])
                self.assertEqual("limit", payload["intent"])
                self.assertIs(False, calculation["exists"])
                self.assertEqual("不存在", calculation["limit"])
                if one_sided is None:
                    self.assertIn("振荡", calculation["explanation"])
                else:
                    self.assertEqual(
                        one_sided[0],
                        calculation["left_limit"],
                    )
                    self.assertEqual(
                        one_sided[1],
                        calculation["right_limit"],
                    )
                self.assertIn("最终答案", payload["reply"])
                self.assertIn("不存在", payload["reply"])

    def test_deterministic_math_replies_use_four_sections(self):
        cases = (
            "求导 x^2",
            "积分 x^2",
            "求极限 x→0 sin(x)/x",
        )
        headings = ("题目理解", "解题思路", "详细计算步骤", "最终答案")
        for message in cases:
            with self.subTest(message=message):
                reply = demo_chat.build_chat_response(message)["reply"]

                positions = [reply.index(heading) for heading in headings]
                self.assertEqual(sorted(positions), positions)

    def test_chat_mode_defaults_to_qa_and_preserves_deterministic_answers(self):
        for message in ("求导 x^2", "积分 x^2", "求极限 x→0 sin(x)/x"):
            with self.subTest(message=message):
                qa = demo_chat.build_chat_response(message)
                teach = demo_chat.build_chat_response(message, mode="teach")

                self.assertEqual("qa", qa["mode"])
                self.assertEqual("teach", teach["mode"])
                self.assertEqual(qa["reply"], teach["reply"])
                self.assertEqual(qa["calculation"], teach["calculation"])

    def test_teaching_mode_uses_a_distinct_general_prompt(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "先看已知条件。你觉得下一步该设什么变量？"
                                },
                                "finish_reason": "stop",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ).encode("utf-8")

        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(
                demo_chat,
                "urlopen",
                return_value=FakeResponse(),
            ) as urlopen_mock,
        ):
            payload = demo_chat.build_chat_response(
                "帮我制定一份复习计划",
                mode="teach",
            )

        self.assertEqual("teach", payload["mode"])
        request_payload = json.loads(
            urlopen_mock.call_args.args[0].data.decode("utf-8")
        )
        self.assertEqual(
            demo_chat.TEACHING_CHAT_SYSTEM_PROMPT,
            request_payload["messages"][0]["content"],
        )

    def test_vector_dot_product_alias(self):
        payload = demo_chat.build_chat_response(
            "求向量 a=(1,2,3) 和 b=(4,5,6) 的点积"
        )

        self.assertEqual("solve", payload["intent"])
        self.assertEqual("vectors", payload["calculation"]["chapter"])
        self.assertEqual("dot", payload["calculation"]["topic"])
        self.assertEqual("32", payload["calculation"]["result"])

    def test_higher_derivative_forms(self):
        cases = (
            ("求二阶导 x^3", "x**3", "6*x", 2),
            ("求 x^3 的二阶导数", "x**3", "6*x", 2),
            ("求二阶导数 x^4", "x**4", "12*x**2", 2),
            ("求三阶导数 x^4", "x**4", "24*x", 3),
            ("求 x^4 的三阶导数", "x**4", "24*x", 3),
        )
        for message, expression, derivative, order in cases:
            with self.subTest(message=message):
                payload = demo_chat.build_chat_response(message)

                self.assertEqual("verify", payload["intent"])
                self.assertEqual(
                    expression,
                    payload["calculation"]["expression"],
                )
                self.assertEqual(
                    derivative,
                    payload["calculation"]["derivative"],
                )
                self.assertEqual(order, payload["calculation"]["order"])

    def test_derivative_value_at_point_forms(self):
        cases = (
            ("f(x)=x^2，求f'(2)", "x**2", "4"),
            ("求 f(x)=x^3 在 x=2 的导数值", "x**3", "12"),
        )
        for message, expression, value in cases:
            with self.subTest(message=message):
                payload = demo_chat.build_chat_response(message)

                self.assertEqual("verify", payload["intent"])
                self.assertEqual(
                    expression,
                    payload["calculation"]["expression"],
                )
                self.assertEqual(value, payload["calculation"]["derivative"])
                self.assertEqual("2", payload["calculation"]["point"])

    def test_derivative_differential_and_explicit_variable_forms(self):
        for message in (
            "计算 d/dx x^2",
            "对 x^2 求关于 x 的导数",
        ):
            with self.subTest(message=message):
                payload = demo_chat.build_chat_response(message)

                self.assertEqual("verify", payload["intent"])
                self.assertEqual("x**2", payload["calculation"]["expression"])
                self.assertEqual("2*x", payload["calculation"]["derivative"])
                self.assertEqual("x", payload["calculation"]["variable"])

    def test_gradient_infers_variables(self):
        payload = demo_chat.build_chat_response("求梯度 x^2+y^2")

        self.assertEqual("solve", payload["intent"])
        self.assertEqual(
            "multivariable_calculus",
            payload["calculation"]["chapter"],
        )
        self.assertEqual("gradient", payload["calculation"]["topic"])
        self.assertIn("2*x", payload["calculation"]["result"])
        self.assertIn("2*y", payload["calculation"]["result"])

    def test_equation_and_matrix_determinant(self):
        equation = demo_chat.build_chat_response("解方程 x^2-1=0")
        determinant = demo_chat.build_chat_response(
            "求矩阵 [[1,2],[3,4]] 的行列式"
        )

        self.assertEqual("solve", equation["intent"])
        self.assertEqual(["-1", "1"], equation["calculation"]["solutions"])
        self.assertEqual("solve", determinant["intent"])
        self.assertEqual("-2", determinant["calculation"]["result"])

    def test_confirmed_ocr_path_matches_text_for_core_math(self):
        cases = (
            (
                "求极限 x→0 sin(3x)/x",
                "limit",
                "limit",
                "3",
            ),
            (
                "求导 x^3",
                "verify",
                "derivative",
                "3*x**2",
            ),
            (
                "计算不定积分 ∫ x^2 dx",
                "integrate",
                "integral",
                "x**3/3",
            ),
        )
        headings = ("题目理解", "解题思路", "详细计算步骤", "最终答案")
        for question, intent, result_key, result in cases:
            with self.subTest(question=question):
                text_response = demo_chat.build_chat_response(question)
                confirmed_response = demo_chat._solve_confirmed_question(
                    question
                )

                self.assertEqual(intent, text_response["intent"])
                self.assertEqual(intent, confirmed_response["intent"])
                self.assertEqual(
                    text_response["calculation"]["expression"],
                    confirmed_response["calculation"]["expression"],
                )
                self.assertEqual(
                    result,
                    text_response["calculation"][result_key],
                )
                self.assertEqual(
                    result,
                    confirmed_response["calculation"][result_key],
                )
                self.assertEqual(
                    text_response["reply"],
                    confirmed_response["reply"],
                )
                positions = [
                    confirmed_response["reply"].index(heading)
                    for heading in headings
                ]
                self.assertEqual(sorted(positions), positions)

    def test_confirmed_model_solution_rejects_incomplete_or_tool_claiming_reply(
        self,
    ):
        valid = (
            "**题目理解**\n求函数的导数。\n\n"
            "**解题思路**\n使用幂函数求导公式。\n\n"
            "**详细计算步骤**\n根据公式逐项求导。\n\n"
            "**最终答案**\n导数为 2x。"
        )
        self.assertIsNone(
            demo_chat._confirmed_solve_reply_invalid_reason(valid)
        )
        self.assertEqual(
            "内容过短",
            demo_chat._confirmed_solve_reply_invalid_reason(
                "题目理解：求导。最终答案：2x。"
            ),
        )
        self.assertEqual(
            "缺少统一的四段结构",
            demo_chat._confirmed_solve_reply_invalid_reason(
                "题目理解：这是函数求导题。"
                "解题思路：使用幂函数公式逐项求导。"
                "计算：根据公式计算得到结果。"
                "最终答案：2x。"
            ),
        )
        self.assertEqual(
            "包含未经核验的工具调用声明",
            demo_chat._confirmed_solve_reply_invalid_reason(
                valid.replace("使用幂函数求导公式", "我调用了数学工具完成计算")
            ),
        )

    def test_confirmed_model_solution_is_unverified_for_downstream_gates(
        self,
    ):
        reply = (
            "**题目理解**\n求函数的导数。\n\n"
            "**解题思路**\n使用幂函数求导公式。\n\n"
            "**详细计算步骤**\n根据公式逐项求导。\n\n"
            "**最终答案**\n导数为 2x。"
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {"content": reply},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ).encode("utf-8")

        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(
                demo_chat,
                "urlopen",
                return_value=FakeResponse(),
            ) as urlopen_mock,
        ):
            payload = demo_chat._build_general_chat_response(
                "待解题目：求导 x^2",
                None,
                demo_chat.CONFIRMED_SOLVE_SYSTEM_PROMPT,
            )

        self.assertEqual("unverified", payload["status"])
        self.assertEqual("general", payload["intent"])
        self.assertIs(False, payload["verified"])
        self.assertIsNone(payload["calculation"])
        self.assertIs(False, payload["verification"]["passed"])
        self.assertIn("未经独立验算", payload["reply"])
        self.assertIn("**最终答案**", payload["reply"])

        from deploy import wsgi_app

        teaching = wsgi_app._start_teaching_response(
            "unverified-model-solution-test",
            "待解题目：求导 x^2",
            payload,
        )
        self.assertEqual("error", teaching["status"])
        self.assertIsNone(teaching.get("teaching"))
        self.assertFalse(teaching.get("knowledge_points") or [])

        request_payload = json.loads(
            urlopen_mock.call_args.args[0].data.decode("utf-8")
        )
        self.assertEqual(0.15, request_payload["temperature"])
        self.assertEqual(
            demo_chat.CONFIRMED_SOLVE_MAX_TOKENS,
            request_payload["max_tokens"],
        )

    def test_general_chat_mode_keeps_success_status(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "复习计划可以从每周复盘开始。",
                                },
                                "finish_reason": "stop",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ).encode("utf-8")

        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(
                demo_chat,
                "urlopen",
                return_value=FakeResponse(),
            ),
        ):
            payload = demo_chat._build_general_chat_response(
                "帮我制定复习计划",
                None,
                demo_chat.GENERAL_CHAT_SYSTEM_PROMPT,
            )

        self.assertEqual("ok", payload["status"])
        self.assertEqual("general", payload["intent"])
        self.assertIsNone(payload["calculation"])
        self.assertNotIn("verified", payload)

    def test_confirmed_model_solution_rejects_truncated_output(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {"content": "**题目理解**\n求导。"},
                                "finish_reason": "length",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ).encode("utf-8")

        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(
                demo_chat,
                "urlopen",
                return_value=FakeResponse(),
            ),
        ):
            payload = demo_chat._build_general_chat_response(
                "待解题目：求导 x^2",
                None,
                demo_chat.CONFIRMED_SOLVE_SYSTEM_PROMPT,
            )

        self.assertEqual("error", payload["status"])
        self.assertIn("截断", payload["reply"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
