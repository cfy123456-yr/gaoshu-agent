import unittest

import sympy

from app.plotting import render_function_svg


class FunctionPlotTest(unittest.TestCase):
    def test_renders_expression_to_svg(self):
        x = sympy.Symbol("x")

        payload = render_function_svg(
            sympy.sin(x),
            x,
            x_min=-3,
            x_max=3,
            y_min=None,
            y_max=None,
            samples=120,
            width=720,
            height=420,
        )

        self.assertEqual("sin(x)", payload["expression"])
        self.assertIn("<svg", payload["svg"])
        self.assertIn('stroke="#2868d8"', payload["svg"])
        self.assertIn("</svg>", payload["svg"])

    def test_splits_curve_at_discontinuity(self):
        x = sympy.Symbol("x")

        payload = render_function_svg(
            1 / x,
            x,
            x_min=-1,
            x_max=1,
            y_min=-10,
            y_max=10,
            samples=101,
            width=640,
            height=360,
        )

        self.assertGreaterEqual(payload["svg"].count("M "), 2)

    def test_rejects_invalid_x_range(self):
        x = sympy.Symbol("x")

        with self.assertRaises(ValueError):
            render_function_svg(
                x,
                x,
                x_min=1,
                x_max=1,
                y_min=None,
                y_max=None,
                samples=80,
                width=320,
                height=240,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
