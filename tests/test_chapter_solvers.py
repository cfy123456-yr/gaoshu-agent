import unittest

from app.chapter_solvers import SUPPORTED_TOPICS, SolveError, solve_chapter


ALL_TOPIC_CASES = {
    ("limits", "limit"): {
        "expression": "sin(x)/x",
        "variable": "x",
        "point": "0",
    },
    ("limits", "sequence_limit"): {"expression": "(1+1/n)^n", "variable": "n"},
    ("derivatives", "derivative"): {"expression": "x^2", "variable": "x"},
    ("derivatives", "higher_derivative"): {
        "expression": "x^3",
        "variable": "x",
        "order": 2,
    },
    ("derivatives", "differential"): {"expression": "x^2", "variable": "x"},
    ("derivatives", "tangent"): {
        "expression": "x^2",
        "variable": "x",
        "point": "1",
    },
    ("derivatives", "normal"): {
        "expression": "x^2",
        "variable": "x",
        "point": "1",
    },
    ("derivatives", "mean_value"): {
        "expression": "x^2",
        "variable": "x",
        "lower": "0",
        "upper": "2",
    },
    ("derivatives", "critical_points"): {"expression": "x^2-2x", "variable": "x"},
    ("derivatives", "monotonicity"): {"expression": "x^2-2x", "variable": "x"},
    ("derivatives", "extrema"): {"expression": "x^2", "variable": "x"},
    ("derivatives", "taylor"): {
        "expression": "sin(x)",
        "variable": "x",
        "point": "0",
        "order": 3,
    },
    ("derivatives", "curvature"): {
        "expression": "x^2",
        "variable": "x",
        "point": "0",
    },
    ("derivatives", "parametric_derivative"): {
        "x_expression": "t^2",
        "y_expression": "t^3",
        "parameter": "t",
    },
    ("integrals", "indefinite"): {"expression": "x", "variable": "x"},
    ("integrals", "definite"): {
        "expression": "x",
        "variable": "x",
        "lower": "0",
        "upper": "1",
    },
    ("integrals", "improper"): {
        "expression": "1/x^2",
        "variable": "x",
        "lower": "1",
        "upper": "oo",
    },
    ("differential_equations", "dsolve"): {
        "equation": "y' - y",
        "variable": "x",
        "function": "y",
    },
    ("vectors", "dot"): {"left": ["1", "2"], "right": ["3", "4"]},
    ("vectors", "cross"): {"left": ["1", "0", "0"], "right": ["0", "1", "0"]},
    ("vectors", "norm"): {"vector": ["3", "4"]},
    ("vectors", "angle"): {
        "left": ["1", "0"],
        "right": ["0", "1"],
    },
    ("vectors", "distance"): {
        "left": ["0", "0"],
        "right": ["3", "4"],
    },
    ("vectors", "projection"): {
        "left": ["1", "1"],
        "right": ["1", "0"],
    },
    ("multivariable_calculus", "partial"): {
        "expression": "x^2*y",
        "variables": ["x"],
    },
    ("multivariable_calculus", "mixed_partial"): {
        "expression": "x^2*y",
        "variables": ["x", "y"],
    },
    ("multivariable_calculus", "gradient"): {
        "expression": "x^2*y",
        "variables": ["x", "y"],
    },
    ("multivariable_calculus", "hessian"): {
        "expression": "x^2*y",
        "variables": ["x", "y"],
    },
    ("multivariable_calculus", "directional_derivative"): {
        "expression": "x^2+y^2",
        "variables": ["x", "y"],
        "point": ["1", "1"],
        "direction": ["1", "0"],
    },
    ("multivariable_calculus", "implicit_derivative"): {
        "equation": "x^2+y^2=1",
        "variable": "x",
        "dependent": "y",
    },
    ("multivariable_calculus", "system_implicit_derivative"): {
        "equations": ["u+v=x", "u-v=y"],
        "dependents": ["u", "v"],
        "variable": "x",
        "dependent": "u",
    },
    ("multivariable_calculus", "multivariable_extrema"): {
        "expression": "x^2+y^2",
        "variables": ["x", "y"],
    },
    ("multivariable_calculus", "conditional_extrema"): {
        "expression": "x*y",
        "variables": ["x", "y"],
        "constraint": "x+y=1",
    },
    ("multiple_integrals", "double"): {
        "expression": "x*y",
        "variables": ["x", "y"],
        "lower_x": "0",
        "upper_x": "1",
        "lower_y": "0",
        "upper_y": "1",
    },
    ("multiple_integrals", "double_polar"): {
        "expression": "x^2+y^2",
        "lower_r": "0",
        "upper_r": "1",
        "lower_theta": "0",
        "upper_theta": "2*pi",
    },
    ("multiple_integrals", "triple"): {
        "expression": "x+y+z",
        "variables": ["x", "y", "z"],
        "lower_x": "0",
        "upper_x": "1",
        "lower_y": "0",
        "upper_y": "1",
        "lower_z": "0",
        "upper_z": "1",
    },
    ("line_surface_integrals", "line_scalar"): {
        "expression": "x+y",
        "parameter": "t",
        "components": {"x": "t", "y": "t"},
        "lower": "0",
        "upper": "1",
    },
    ("line_surface_integrals", "line_vector"): {
        "vector_field": ["x", "y"],
        "parameter": "t",
        "components": {"x": "t", "y": "t"},
        "lower": "0",
        "upper": "1",
    },
    ("line_surface_integrals", "surface_scalar"): {
        "expression": "1",
        "parameters": ["u", "v"],
        "components": {"x": "u", "y": "v", "z": "0"},
        "u_lower": "0",
        "u_upper": "1",
        "v_lower": "0",
        "v_upper": "1",
    },
    ("line_surface_integrals", "flux"): {
        "vector_field": ["0", "0", "1"],
        "parameters": ["u", "v"],
        "components": {"x": "u", "y": "v", "z": "0"},
        "u_lower": "0",
        "u_upper": "1",
        "v_lower": "0",
        "v_upper": "1",
    },
    ("series", "sum"): {
        "expression": "1/n^2",
        "variable": "n",
        "lower": 1,
        "upper": "oo",
    },
    ("series", "convergence"): {"expression": "1/n^2", "variable": "n"},
    ("series", "power_radius"): {"coefficient": "1/n", "variable": "n"},
}


class ChapterSolverTest(unittest.TestCase):
    def solve(self, chapter, topic, inputs, candidate=None):
        return solve_chapter(chapter, topic, inputs, candidate)

    def test_derivative_and_candidate(self):
        payload = self.solve(
            "derivatives",
            "higher_derivative",
            {"expression": "x^3", "variable": "x", "order": 2},
            candidate="6x",
        )
        self.assertEqual("6*x", payload["result"])
        self.assertIs(True, payload["is_correct"])
        self.assertEqual("高阶导数", payload["method"])

    def test_tangent_line(self):
        payload = self.solve(
            "derivatives",
            "tangent",
            {"expression": "x^2", "variable": "x", "point": "1"},
        )
        self.assertIn("2*x - 1", payload["result"])

    def test_differential_equation(self):
        payload = self.solve(
            "differential_equations",
            "dsolve",
            {"equation": "y' - y", "variable": "x", "function": "y"},
        )
        self.assertIn("C1*exp(x)", payload["result"])

    def test_gradient(self):
        payload = self.solve(
            "multivariable_calculus",
            "gradient",
            {"expression": "x^2*y", "variables": ["x", "y"]},
        )
        self.assertIn("2*x*y", payload["result"])
        self.assertIn("x**2", payload["result"])

    def test_double_integral(self):
        payload = self.solve(
            "multiple_integrals",
            "double",
            {
                "expression": "x*y",
                "variables": ["x", "y"],
                "lower_x": "0",
                "upper_x": "1",
                "lower_y": "0",
                "upper_y": "1",
            },
        )
        self.assertEqual("1/4", payload["result"])

    def test_double_polar_integral(self):
        payload = self.solve(
            "multiple_integrals",
            "double_polar",
            {
                "expression": "x^2+y^2",
                "lower_r": "0",
                "upper_r": "1",
                "lower_theta": "0",
                "upper_theta": "2*pi",
            },
        )
        self.assertEqual("pi/2", payload["result"])
        self.assertEqual("二重积分（极坐标）", payload["method"])

    def test_vector_dot(self):
        payload = self.solve(
            "vectors",
            "dot",
            {"left": ["1", "2", "3"], "right": ["4", "5", "6"]},
            candidate="32",
        )
        self.assertEqual("32", payload["result"])
        self.assertIs(True, payload["is_correct"])

    def test_series_sum(self):
        payload = self.solve(
            "series",
            "sum",
            {"expression": "1/n^2", "variable": "n", "lower": 1, "upper": "oo"},
        )
        self.assertEqual("pi**2/6", payload["result"])

    def test_series_convergence(self):
        cases = (
            ("1/n^2", "收敛"),
            ("(-1)^n/n", "收敛"),
            ("sin(1/n)", "发散"),
            ("n^2", "发散"),
            ("2^n/n!", "收敛"),
        )
        for expression, expected in cases:
            with self.subTest(expression=expression):
                payload = self.solve(
                    "series",
                    "convergence",
                    {"expression": expression, "variable": "n"},
                )
                self.assertEqual(expected, payload["result"])

    def test_improper_integral(self):
        payload = self.solve(
            "integrals",
            "improper",
            {
                "expression": "1/x^2",
                "variable": "x",
                "lower": "1",
                "upper": "oo",
            },
        )
        self.assertEqual("1", payload["result"])
        self.assertEqual("反常积分", payload["method"])

    def test_limit(self):
        payload = self.solve(
            "limits",
            "limit",
            {"expression": "sin(x)/x", "variable": "x", "point": "0"},
        )
        self.assertEqual("1", payload["result"])

    def test_implicit_derivative(self):
        payload = self.solve(
            "multivariable_calculus",
            "implicit_derivative",
            {"equation": "x^2+y^2=1", "variable": "x", "dependent": "y"},
        )
        self.assertEqual("-x/y", payload["result"])

    def test_system_implicit_derivative(self):
        payload = self.solve(
            "multivariable_calculus",
            "system_implicit_derivative",
            {
                "equations": ["u+v=x", "u-v=y"],
                "dependents": ["u", "v"],
                "variable": "x",
                "dependent": "u",
            },
        )
        self.assertEqual("1/2", payload["result"])
        self.assertEqual("方程组确定函数求偏导", payload["method"])

    def test_system_implicit_derivative_requires_square_system(self):
        with self.assertRaises(SolveError):
            self.solve(
                "multivariable_calculus",
                "system_implicit_derivative",
                {
                    "equations": ["u+v=x"],
                    "dependents": ["u", "v"],
                    "variable": "x",
                    "dependent": "u",
                },
            )

    def test_conditional_extrema_lagrange(self):
        payload = self.solve(
            "multivariable_calculus",
            "conditional_extrema",
            {
                "expression": "x*y",
                "variables": ["x", "y"],
                "constraint": "x+y=1",
            },
        )
        self.assertIn("x: 1/2", payload["result"])
        self.assertIn("y: 1/2", payload["result"])
        self.assertIn("'lambda': -1/2", payload["result"])
        self.assertIn("'value': 1/4", payload["result"])
        self.assertIn("'kind': '极大值'", payload["result"])
        self.assertEqual("条件极值（拉格朗日乘数法）", payload["method"])

    def test_parametric_derivative(self):
        payload = self.solve(
            "derivatives",
            "parametric_derivative",
            {"x_expression": "t^2", "y_expression": "t^3", "parameter": "t"},
        )
        self.assertEqual("3*t/2", payload["result"])
        self.assertEqual("参数方程求导", payload["method"])

    def test_parametric_derivative_rejects_zero_dx(self):
        with self.assertRaises(SolveError):
            self.solve(
                "derivatives",
                "parametric_derivative",
                {"x_expression": "1", "y_expression": "t^2", "parameter": "t"},
            )

    def test_power_radius(self):
        payload = self.solve(
            "series",
            "power_radius",
            {"coefficient": "1/n", "variable": "n"},
        )
        self.assertEqual("1", payload["result"])

    def test_unknown_topic_is_rejected(self):
        with self.assertRaises(SolveError):
            self.solve("unknown", "unknown", {})

    def test_every_supported_topic_has_a_working_sample(self):
        expected = {
            (chapter, topic)
            for chapter, topics in SUPPORTED_TOPICS.items()
            for topic in topics
        }
        self.assertEqual(expected, set(ALL_TOPIC_CASES))
        for (chapter, topic), inputs in ALL_TOPIC_CASES.items():
            with self.subTest(chapter=chapter, topic=topic):
                payload = self.solve(chapter, topic, inputs)
                self.assertIn("result", payload)
                self.assertIsNotNone(payload["result"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
