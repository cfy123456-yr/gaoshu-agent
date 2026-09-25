import io
import random
import unittest
from fractions import Fraction
from unittest.mock import patch

import sympy

from app.chapter_solvers import solve_chapter
from deploy import demo_chat, demo_interval_solver, wsgi_app


class RandomizedSolverRegressionTest(unittest.TestCase):
    def assert_equivalent(self, actual, expected, variables):
        locals_map = {str(variable): variable for variable in variables}
        parsed = sympy.sympify(str(actual), locals=locals_map)
        difference = sympy.simplify(parsed - expected)
        self.assertEqual(
            sympy.Integer(0),
            difference,
            f"expected {expected!r}, got {actual!r}",
        )

    def random_polynomial(self, rng):
        variable = sympy.symbols("x", real=True)
        degree = rng.randint(1, 5)
        coefficients = [rng.randint(-5, 5) for _ in range(degree)]
        leading = rng.choice((-1, 1)) * rng.randint(1, 5)
        coefficients.append(leading)
        expression = sum(
            coefficient * variable**power
            for power, coefficient in enumerate(coefficients)
            if coefficient
        )
        return variable, expression

    def test_seeded_random_polynomials_against_sympy(self):
        rng = random.Random(20260925)
        for case_index in range(24):
            with self.subTest(case=case_index):
                variable, expression = self.random_polynomial(rng)
                expression_text = str(expression)

                derivative = sympy.diff(expression, variable)
                derivative_payload = solve_chapter(
                    "derivatives",
                    "derivative",
                    {"expression": expression_text, "variable": "x"},
                    candidate=str(derivative),
                )
                self.assertIs(True, derivative_payload["is_correct"])
                self.assert_equivalent(
                    derivative_payload["result"],
                    derivative,
                    (variable,),
                )

                wrong_payload = solve_chapter(
                    "derivatives",
                    "derivative",
                    {"expression": expression_text, "variable": "x"},
                    candidate=f"({derivative}) + 1",
                )
                self.assertIs(False, wrong_payload["is_correct"])

                order = rng.randint(1, 3)
                higher_derivative = sympy.diff(expression, variable, order)
                higher_payload = solve_chapter(
                    "derivatives",
                    "higher_derivative",
                    {
                        "expression": expression_text,
                        "variable": "x",
                        "order": order,
                    },
                    candidate=str(higher_derivative),
                )
                self.assertIs(True, higher_payload["is_correct"])
                self.assert_equivalent(
                    higher_payload["result"],
                    higher_derivative,
                    (variable,),
                )

                antiderivative = sympy.integrate(expression, variable)
                integral_payload = solve_chapter(
                    "integrals",
                    "indefinite",
                    {"expression": expression_text, "variable": "x"},
                    candidate=str(antiderivative),
                )
                self.assertIs(True, integral_payload["is_correct"])
                result = sympy.sympify(
                    integral_payload["result"],
                    locals={"x": variable},
                )
                self.assertEqual(
                    sympy.Integer(0),
                    sympy.simplify(sympy.diff(result, variable) - expression),
                )

                lower = rng.randint(-3, 2)
                upper = lower + rng.randint(1, 4)
                definite_value = sympy.integrate(
                    expression,
                    (variable, lower, upper),
                )
                definite_payload = solve_chapter(
                    "integrals",
                    "definite",
                    {
                        "expression": expression_text,
                        "variable": "x",
                        "lower": str(lower),
                        "upper": str(upper),
                    },
                    candidate=str(definite_value),
                )
                self.assertIs(True, definite_payload["is_correct"])
                self.assert_equivalent(
                    definite_payload["result"],
                    definite_value,
                    (),
                )

                point = rng.randint(-3, 3)
                limit_value = sympy.limit(expression, variable, point)
                limit_payload = solve_chapter(
                    "limits",
                    "limit",
                    {
                        "expression": expression_text,
                        "variable": "x",
                        "point": str(point),
                    },
                    candidate=str(limit_value),
                )
                self.assertIs(True, limit_payload["is_correct"])
                self.assert_equivalent(
                    limit_payload["result"],
                    limit_value,
                    (),
                )

    def test_seeded_random_quadratic_interval_extrema(self):
        rng = random.Random(20260925)
        for case_index in range(24):
            with self.subTest(case=case_index):
                a = rng.choice((-5, -4, -3, -2, -1, 1, 2, 3, 4, 5))
                b = rng.randint(-8, 8)
                c = rng.randint(-8, 8)
                lower = rng.randint(-6, 1)
                upper = lower + rng.randint(1, 6)
                expression = a * sympy.Symbol("x") ** 2 + b * sympy.Symbol("x") + c
                vertex = sympy.Rational(-b, 2 * a)
                candidates = [
                    expression.subs(sympy.Symbol("x"), lower),
                    expression.subs(sympy.Symbol("x"), upper),
                ]
                if lower <= vertex <= upper:
                    candidates.append(
                        expression.subs(sympy.Symbol("x"), vertex)
                    )

                for kind, label, expected in (
                    (
                        "max",
                        "\u6700\u5927\u503c",
                        sympy.simplify(max(candidates)),
                    ),
                    (
                        "min",
                        "\u6700\u5c0f\u503c",
                        sympy.simplify(min(candidates)),
                    ),
                ):
                    question = (
                        f"\u51fd\u6570 f(x)={expression} "
                        f"\u5728\u533a\u95f4 [{lower},{upper}] "
                        f"\u4e0a\u7684{label}"
                    )
                    payload = demo_interval_solver.solve_interval_extrema(question)
                    self.assertIsNotNone(payload)
                    self.assertEqual(label, payload["calculation"]["kind"])
                    self.assertEqual(
                        str(expected),
                        payload["calculation"]["result"],
                    )

                    chat_payload = demo_chat.build_chat_response(question)
                    self.assertEqual("solve", chat_payload["intent"])
                    self.assertEqual(label, chat_payload["calculation"]["kind"])
                    self.assertEqual(
                        str(expected),
                        chat_payload["calculation"]["result"],
                    )


class RandomizedArithmeticRegressionTest(unittest.TestCase):
    def random_fraction(self, rng):
        return Fraction(rng.randint(-12, 12), rng.randint(1, 12))

    def build_expression(self, rng):
        left = self.random_fraction(rng)
        right = self.random_fraction(rng)
        operator = rng.choice(("+", "-", "*", "/"))
        if operator == "+":
            expected = left + right
        elif operator == "-":
            expected = left - right
        elif operator == "*":
            expected = left * right
        else:
            expected = left / right

        symbol = {"*": "\u00d7", "/": "\u00f7"}.get(operator, operator)
        left_text = f"{left.numerator}/{left.denominator}"
        right_text = f"{right.numerator}/{right.denominator}"
        if symbol in {"\u00d7", "\u00f7"}:
            message = (
                f"\uff08{left_text}\uff09{symbol}\uff08{right_text}\uff09"
            )
        else:
            message = f"({left_text}){symbol}({right_text})"
        return message, expected

    def test_seeded_random_rational_arithmetic(self):
        rng = random.Random(20260925)
        for case_index in range(80):
            with self.subTest(case=case_index):
                message, expected = self.build_expression(rng)
                payload = demo_chat.build_chat_response(message)

                self.assertEqual("arithmetic", payload["intent"])
                self.assertEqual("ok", payload["status"])
                self.assertEqual(
                    str(expected),
                    payload["calculation"]["result"],
                )


class OcrSessionBoundaryRegressionTest(unittest.TestCase):
    def setUp(self):
        self.client = wsgi_app.application.test_client()
        wsgi_app._chat_response_cache.clear()
        wsgi_app._ocr_response_cache.clear()
        wsgi_app.rate_limiter.requests.clear()

    def post_image(self, session_id, marker):
        image_data = b"\x89PNG\r\n\x1a\n" + marker
        return self.client.post(
            "/demo/api/ocr",
            data={"image": (io.BytesIO(image_data), "question.png")},
            content_type="multipart/form-data",
            headers={"X-Demo-Session": session_id},
        )

    def confirm(self, session_id):
        return self.client.post(
            "/demo/api/chat",
            json={"message": "\u786e\u8ba4", "source": "text"},
            headers={"X-Demo-Session": session_id},
        )

    def test_new_image_replaces_pending_question_without_reocr(self):
        session_id = "random-regression-ocr-replace"
        with patch.object(
            wsgi_app,
            "_transcribe_demo_ocr",
            side_effect=[
                ("1+1", "vision", ""),
                ("2+2", "vision", ""),
            ],
        ) as transcribe:
            first = self.post_image(session_id, b"first")
            second = self.post_image(session_id, b"second")
            confirmation = self.confirm(session_id)

        self.assertEqual(200, first.status_code)
        self.assertEqual("1+1", first.get_json()["text"])
        self.assertEqual(200, second.status_code)
        self.assertEqual("2+2", second.get_json()["text"])
        self.assertEqual(200, confirmation.status_code)
        payload = confirmation.get_json()
        self.assertEqual("2+2", payload["history_used"])
        self.assertEqual("4", payload["calculation"]["result"])
        self.assertEqual(2, transcribe.call_count)

    def test_failed_replacement_clears_old_pending_question(self):
        session_id = "random-regression-ocr-failure"
        with patch.object(
            wsgi_app,
            "_transcribe_demo_ocr",
            side_effect=[
                ("1+1", "vision", ""),
                wsgi_app.HTTPException(status_code=502, detail="ocr failed"),
            ],
        ):
            first = self.post_image(session_id, b"first")
            failed = self.post_image(session_id, b"failed")
            confirmation = self.confirm(session_id)

        self.assertEqual(200, first.status_code)
        self.assertEqual(502, failed.status_code)
        self.assertEqual("needs_input", confirmation.get_json()["status"])
        self.assertNotIn("history_used", confirmation.get_json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
