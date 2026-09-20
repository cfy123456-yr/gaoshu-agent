import itertools
import json
import unittest
from unittest.mock import patch

from deploy import demo_chat, wsgi_app


class DemoPageTest(unittest.TestCase):
    def setUp(self):
        self.client = wsgi_app.application.test_client()
        wsgi_app._chat_response_cache.clear()
        self.session_counter = itertools.count(1)

    def chat(self, message, history=None, session=None):
        session_id = session or next(self.session_counter)
        headers = {"X-Demo-Session": f"test-session-{session_id}"}
        return self.client.post(
            "/demo/api/chat",
            json={"message": message, "history": history or []},
            headers=headers,
        )

    def test_demo_page_is_available(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("知微老师", html)
        self.assertIn("/demo/api/chat", html)
        self.assertIn('id="chatInput"', html)
        self.assertIn('id="messageList"', html)
        self.assertIn("/static/katex/katex.min.css", html)
        self.assertIn("/static/katex/katex.min.js", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertIn("controller.abort(), 6000", html)

    def test_demo_page_exposes_chapter_solver(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn('id="solverDialog"', html)
        self.assertIn('id="openSolverButton"', html)
        self.assertIn("const SOLVER_CHAPTERS = {", html)
        self.assertIn('fetch("/demo/api/solve"', html)
        self.assertIn('data.intent === "solve"', html)
        self.assertIn("populateSolverChapters();", html)
        self.assertIn('solverDialog.showModal()', html)
        self.assertIn("parametric_derivative", html)
        self.assertIn("参数方程求导", html)
        self.assertIn("system_implicit_derivative", html)
        self.assertIn("方程组确定函数求偏导", html)
        self.assertIn("conditional_extrema", html)
        self.assertIn("条件极值", html)
        self.assertIn("double_polar", html)
        self.assertIn("极坐标二重积分", html)
        self.assertIn("triple_cylindrical", html)
        self.assertIn("柱面坐标三重积分", html)
        self.assertIn("triple_spherical", html)
        self.assertIn("球面坐标三重积分", html)

    def test_demo_page_exposes_formula_guides(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn('id="formulaDialog"', html)
        self.assertIn('data-formula-type="derivative"', html)
        self.assertIn('data-formula-type="integral"', html)
        self.assertIn('data-formula-type="limit"', html)
        self.assertIn("const FORMULA_GUIDES = {", html)
        self.assertIn(
            "openFormulaDialog(formulaButton.dataset.formulaType)",
            html,
        )
        self.assertNotIn('data-prompt="求导 x^2"', html)
        self.assertNotIn('data-prompt="积分 x^2"', html)
        self.assertNotIn('data-prompt="lim x→0 sin(x)/x"', html)

    def test_demo_health_is_available(self):
        response = self.client.get("/demo/api/health")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertTrue(payload["demo"]["available"])
        self.assertEqual("/demo", payload["demo"]["page"])

    def test_health_and_static_requests_do_not_consume_rate_limit(self):
        with patch.object(wsgi_app.rate_limiter, "check") as check:
            self.client.get("/demo/api/health")
            self.client.get("/health")
            self.client.get("/static/katex/katex.min.css").close()

        check.assert_not_called()

    def test_chat_requests_still_consume_rate_limit(self):
        with patch.object(wsgi_app.rate_limiter, "check") as check:
            self.client.post(
                "/demo/api/chat",
                json={"message": "x"},
            )

        check.assert_called_once()

    def test_missing_route_returns_json_404(self):
        response = self.client.get("/not-found")

        self.assertEqual(404, response.status_code)
        self.assertIn("not found", response.get_json()["detail"].lower())

    def test_demo_calculates_derivative(self):
        response = self.client.post(
            "/demo/api/verify",
            json={"expression": "x^2", "variable": "x", "candidate": "2x"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("2*x", payload["derivative"])
        self.assertIs(True, payload["is_correct"])

    def test_demo_calculates_definite_integral(self):
        response = self.client.post(
            "/demo/api/integrate",
            json={
                "expression": "x^2",
                "variable": "x",
                "lower": "0",
                "upper": "1",
                "candidate": "1/3",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("1/3", payload["integral"])
        self.assertIs(True, payload["is_correct"])

    def test_demo_calculates_limit(self):
        response = self.client.post(
            "/demo/api/limit",
            json={
                "expression": "sin(x)/x",
                "variable": "x",
                "point": "0",
                "candidate": "1",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("1", payload["limit"])
        self.assertIs(True, payload["is_correct"])

    def test_query_candidate_must_be_ignored_when_blank(self):
        cases = (
            (
                "/verify-query",
                {"expression": "x^2", "variable": "x", "candidate": ""},
            ),
            (
                "/integrate-query",
                {
                    "expression": "x^2",
                    "variable": "x",
                    "lower": "",
                    "upper": "",
                    "candidate": "",
                },
            ),
            (
                "/limit-query",
                {
                    "expression": "sin(x)/x",
                    "variable": "x",
                    "point": "0",
                    "direction": "",
                    "candidate": "",
                },
            ),
        )
        for path, params in cases:
            with self.subTest(path=path):
                response = self.client.post(path, query_string=params)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertIsNone(payload["candidate"])
                self.assertIsNone(payload["is_correct"])

    def test_demo_calculates_extended_chapter_solve(self):
        response = self.client.post(
            "/demo/api/solve",
            json={
                "chapter": "series",
                "topic": "sum",
                "inputs": {
                    "expression": "1/n^2",
                    "variable": "n",
                    "lower": 1,
                    "upper": "oo",
                },
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("pi**2/6", payload["result"])

    def test_demo_generates_function_plot(self):
        response = self.client.post(
            "/demo/api/plot",
            json={"expression": "sin(x)", "x_min": -3, "x_max": 3},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("sin(x)", payload["expression"])
        self.assertIn("<svg", payload["svg"])
        self.assertIn('stroke="#2868d8"', payload["svg"])

    def test_demo_serves_function_plot_as_svg(self):
        response = self.client.get(
            "/demo/api/plot.svg",
            query_string={"expression": "x^2", "x_min": -2, "x_max": 2},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("image/svg+xml", response.mimetype)
        self.assertIn("<svg", response.get_data(as_text=True))

    def test_demo_chat_returns_function_plot(self):
        response = self.chat("画函数 y=sin(x)，x 从 -3 到 3")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("plot", payload["intent"])
        self.assertEqual("sin(x)", payload["calculation"]["expression"])

        plot_url = payload["calculation"]["plot_url"]
        self.assertIn("/demo/api/plot.svg?", plot_url)

        image = self.client.get(plot_url)
        self.assertEqual(200, image.status_code)
        self.assertEqual("image/svg+xml", image.mimetype)
        self.assertIn("<svg", image.get_data(as_text=True))
    def test_demo_chat_solves_series_convergence(self):
        cases = (
            ("判断级数 1/n^2 收敛", "收敛"),
            ("判断级数 n^2 收敛", "发散"),
        )
        for message, expected in cases:
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("solve", payload["intent"])
                self.assertEqual(expected, payload["calculation"]["result"])

    def test_demo_chat_solves_multiple_integrals(self):
        response = self.chat("积分 0 到 1 0 到 1 x*y")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("1/4", payload["calculation"]["result"])

        triple = self.chat("三重积分 x+y+z 变量 x,y,z")
        self.assertEqual("solve", triple.get_json()["intent"])
        self.assertEqual("3/2", triple.get_json()["calculation"]["result"])

    def test_demo_chat_solves_polar_double_integral(self):
        response = self.chat(
            "极坐标二重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi"
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("pi/2", payload["calculation"]["result"])
        self.assertEqual("二重积分（极坐标）", payload["calculation"]["method"])

    def test_demo_chat_solves_coordinate_triple_integrals(self):
        cylindrical = self.chat(
            "柱面坐标三重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi z 0 到 1"
        )

        self.assertEqual(200, cylindrical.status_code)
        payload = cylindrical.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("pi/2", payload["calculation"]["result"])
        self.assertEqual("三重积分（柱面坐标）", payload["calculation"]["method"])

        spherical = self.chat(
            "球面坐标三重积分 1 rho 0 到 1 phi 0 到 pi theta 0 到 2*pi"
        )

        self.assertEqual(200, spherical.status_code)
        payload = spherical.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("4*pi/3", payload["calculation"]["result"])
        self.assertEqual("三重积分（球面坐标）", payload["calculation"]["method"])

    def test_demo_chat_solves_differential_equation(self):
        response = self.chat("解微分方程 y'-y=0")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertIn("C1*exp(x)", payload["calculation"]["result"])

    def test_demo_chat_solves_parametric_derivative(self):
        response = self.chat("参数方程 x=t^2, y=t^3 求 dy/dx")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("3*t/2", payload["calculation"]["result"])

    def test_demo_chat_solves_system_implicit_derivative(self):
        response = self.chat(
            "方程组 u+v=x; u-v=y，因变量 u,v，自变量 x，求 ∂u/∂x"
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("1/2", payload["calculation"]["result"])

    def test_demo_chat_solves_conditional_extrema(self):
        response = self.chat("条件极值 x*y 约束 x+y=1 变量 x,y")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual(
            "条件极值（拉格朗日乘数法）",
            payload["calculation"]["method"],
        )
        self.assertIn("x: 1/2", payload["calculation"]["result"])
        self.assertIn("'kind': '极大值'", payload["calculation"]["result"])

    def test_demo_chat_solves_conditional_extrema_with_multiple_constraints(self):
        response = self.chat(
            "条件极值 x^2+y^2+z^2 约束 x=0; y=0 变量 x,y,z"
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual(
            "条件极值（拉格朗日乘数法）",
            payload["calculation"]["method"],
        )
        self.assertIn("lambda1: 0", payload["calculation"]["result"])
        self.assertIn("'kind': '极小值'", payload["calculation"]["result"])

    def test_demo_chat_solves_vector_dot_product(self):
        response = self.chat("向量 (1,2,3) 点乘 (4,5,6)")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("32", payload["calculation"]["result"])

    def test_demo_chat_calculates_derivative(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "求导 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertEqual("verify", payload["intent"])
        self.assertEqual("2*x", payload["calculation"]["derivative"])
        self.assertIsNone(payload["calculation"]["is_correct"])
        self.assertIn(r"\frac{d}{dx}", payload["formula_latex"])

    def test_demo_chat_checks_derivative_candidate(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "判断 2x 是不是 x^2 的导数"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertIs(True, payload["calculation"]["is_correct"])
        self.assertIn("答案正确", payload["reply"])

    def test_demo_chat_calculates_indefinite_integral(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "积分 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("integrate", payload["intent"])
        self.assertEqual("x**3/3", payload["calculation"]["integral"])
        self.assertIn("+C", payload["formula_latex"])

    def test_demo_chat_calculates_definite_integral(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "积分 0 到 1 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("integrate", payload["intent"])
        self.assertEqual("1/3", payload["calculation"]["integral"])
        self.assertIn(r"\int_{0}^{1}", payload["formula_latex"])

    def test_demo_chat_calculates_limit(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "lim x→0 sin(x)/x"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("limit", payload["intent"])
        self.assertEqual("1", payload["calculation"]["limit"])
        self.assertIn(r"\lim_{x\to 0}", payload["formula_latex"])

    def test_demo_chat_calculates_one_sided_limit(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "求 x趋近于0时 1/x 的右极限"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("limit", payload["intent"])
        self.assertEqual("1/x", payload["calculation"]["expression"])
        self.assertEqual("+", payload["calculation"]["direction"])
        self.assertEqual("oo", payload["calculation"]["limit"])

    def test_demo_chat_requests_missing_information(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "今天天气怎么样"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("needs_input", payload["status"])
        self.assertEqual("unknown", payload["intent"])
        self.assertIsNone(payload["calculation"])

    def test_demo_chat_answers_general_question_when_configured(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {"message": {"content": "这是普通问答的回答。"}}
                        ]
                    },
                    ensure_ascii=False,
                ).encode("utf-8")

        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(demo_chat, "urlopen", return_value=FakeResponse()),
        ):
            response = self.chat("帮我制定一份复习计划")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertEqual("general", payload["intent"])
        self.assertEqual("这是普通问答的回答。", payload["reply"])
        self.assertIsNone(payload["calculation"])

    def test_demo_chat_keeps_math_questions_out_of_general_chat(self):
        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(demo_chat, "urlopen") as mocked_urlopen,
        ):
            response = self.chat("求导 x^2")

        self.assertEqual("verify", response.get_json()["intent"])
        mocked_urlopen.assert_not_called()

    def test_demo_chat_reuses_the_previous_question(self):
        response = self.client.post(
            "/demo/api/chat",
            json={
                "message": "再算一遍上一题",
                "history": [
                    {"role": "user", "text": "求导 x^2"},
                    {"role": "assistant", "text": "导数是 2*x。"},
                ],
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertEqual("2*x", payload["calculation"]["derivative"])
        self.assertIn("x^2", payload["history_used"])

    def test_demo_chat_lists_recent_questions(self):
        response = self.client.post(
            "/demo/api/chat",
            json={
                "message": "我以前做过哪些题",
                "history": [
                    {"role": "user", "text": "求导 x^2"},
                    {"role": "user", "text": "积分 0 到 1 x^2"},
                ],
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("history", payload["intent"])
        self.assertEqual(2, len(payload["history_questions"]))

    def test_demo_page_sends_limited_history_and_caches_repeated_questions(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("MAX_REQUEST_HISTORY = 20", html)
        self.assertIn("history }", html)
        self.assertIn("responseCache", html)
        self.assertIn("REQUEST_TIMEOUT_MS = 20000", html)
        self.assertIn("X-Demo-Session", html)

    def test_demo_chat_caches_repeated_questions_per_session(self):
        first = self.chat("求导 x^2", session="shared")
        second = self.chat("求导 x^2", session="shared")
        other_session = self.chat("求导 x^2", session="other")

        self.assertEqual(200, first.status_code)
        self.assertIsNot(True, first.get_json().get("cached"))
        self.assertIs(True, second.get_json()["cached"])
        self.assertIsNot(True, other_session.get_json().get("cached"))

    def test_demo_chat_does_not_cache_history_answers(self):
        first = self.chat("我以前做过哪些题", session="history")
        second = self.chat("我以前做过哪些题", session="history")

        self.assertEqual("history", first.get_json()["intent"])
        self.assertIsNot(True, second.get_json().get("cached"))

    def test_demo_chat_does_not_repeat_a_history_followup(self):
        response = self.chat(
            "再算一遍上一题",
            history=[
                {"role": "user", "text": "继续"},
                {"role": "user", "text": "求导 x^2"},
                {"role": "user", "text": "再算一遍上一题"},
            ],
            session="followup",
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertEqual("2*x", payload["calculation"]["derivative"])
        self.assertEqual("求导 x^2", payload["history_used"])

    def test_demo_remains_public_when_api_key_is_enabled(self):
        with patch.object(wsgi_app, "API_KEY", "test-secret"):
            page = self.client.get("/demo")
            demo_api = self.client.post(
                "/demo/api/verify",
                json={"expression": "x^2", "variable": "x"},
            )
            chat_api = self.client.post(
                "/demo/api/chat",
                json={"message": "求导 x^2"},
            )
            protected_api = self.client.post(
                "/verify",
                json={"expression": "x^2", "variable": "x"},
            )
            public_plot = self.client.get(
                "/plot.svg",
                query_string={
                    "expression": "sin(x)",
                    "variable": "x",
                    "x_min": "-3",
                    "x_max": "3",
                    "samples": 80,
                    "width": 320,
                    "height": 240,
                },
            )
            protected_plot = self.client.post(
                "/plot-query",
                query_string={
                    "expression": "sin(x)",
                    "variable": "x",
                },
            )

        self.assertEqual(200, page.status_code)
        self.assertEqual(200, demo_api.status_code)
        self.assertEqual(200, chat_api.status_code)
        self.assertEqual(401, protected_api.status_code)
        self.assertEqual(200, public_plot.status_code)
        self.assertTrue(
            public_plot.content_type.startswith("image/svg+xml")
        )
        self.assertEqual(401, protected_plot.status_code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
