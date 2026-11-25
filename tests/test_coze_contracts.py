import unittest
from pathlib import Path

from app.main import parse_math_expression
from app.math_text import normalize_math_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CozePromptContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prompt = (PROJECT_ROOT / "COZE_AGENT_PROMPT.md").read_text(
            encoding="utf-8"
        )

    def test_spoken_math_must_reach_the_backend_without_pre_rewriting(self):
        for expected in (
            "口语数学直通规则",
            "后端 `v0.6.11` 已统一负责口语数学归一化",
            "必须保持学生原话",
            "不得由智能体预先改写成猜测的公式",
            "x的平方",
            "根号下x",
            "x的立方",
            "sinx除以x",
            "0到1 x平方的定积分",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.prompt)

    def test_missing_standard_expression_is_not_a_reason_to_ask_again(self):
        self.assertNotIn(
            "如果题目缺少 `expression`、`variable` 等必要参数，先追问，不猜测条件和答案。",
            self.prompt,
        )
        self.assertIn("不得仅因没有写成标准公式而追问", self.prompt)

    def test_knowledge_lookup_is_limited_to_the_tongji_textbook(self):
        for expected in (
            "同济大学《高等数学》本科教材知识库",
            "唯一知识库",
            "不得检索或混用其他教材",
            "先完成计算，再检索知识库补充讲解",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.prompt)

    def test_ocr_requires_confirmation_before_calculation(self):
        self.assertIn("学生在第一轮只确认题目，不调用计算工作流", self.prompt)
        self.assertIn("下一轮再按题型调用对应工作流", self.prompt)
        self.assertIn("多道题时先请学生选择一道", self.prompt)


class CozeWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = (PROJECT_ROOT / "COZE_WORKFLOWS.md").read_text(
            encoding="utf-8"
        )

    def test_all_agent_workflows_are_documented(self):
        for workflow_name in (
            "math_verify",
            "math_integrate",
            "math_limit",
            "math_solve",
            "math_plot",
            "knowledge_lookup",
            "ocr_question",
        ):
            with self.subTest(workflow=workflow_name):
                self.assertIn(f"## {workflow_name}", self.workflows)

    def test_all_backend_endpoints_are_documented(self):
        for endpoint in (
            "https://cfyyy.pythonanywhere.com/verify-query",
            "https://cfyyy.pythonanywhere.com/integrate-query",
            "https://cfyyy.pythonanywhere.com/limit-query",
            "https://cfyyy.pythonanywhere.com/solve-query",
            "https://cfyyy.pythonanywhere.com/plot-query",
            "https://cfyyy.pythonanywhere.com/demo/api/knowledge",
            "https://cfyyy.pythonanywhere.com/demo/api/ocr",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, self.workflows)

    def test_workflow_fields_accept_spoken_math(self):
        for expected in (
            "接受学生原始口语",
            "不得把“x的平方、根号下x、x的立方、sinx除以x”等片段改写成猜测的公式",
            "expression=x平方&lower=0&upper=1",
            "expression=sinx除以x&point=0",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.workflows)

    def test_workflows_do_not_claim_unverified_cloud_publication(self):
        self.assertNotIn("统一提示词已替换到扣子并发布", self.workflows)
        self.assertIn("不等同于云端已经发布", self.workflows)


class SpokenMathNormalizationTest(unittest.TestCase):
    def test_common_spoken_math_fragments_are_normalized(self):
        cases = (
            ("x的平方", "x^2"),
            ("根号下x", "sqrt(x)"),
            ("x的立方", "x^3"),
            ("sinx除以x", "sin(x)/x"),
            ("1/n的平方", "1/n^2"),
            ("x的立方减2x", "x^3-2x"),
            ("3x平方减2", "3x^2-2"),
            ("x的平方加1", "x^2+1"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(expected, normalize_math_text(source))

    def test_spoken_fragments_are_accepted_by_the_math_parser(self):
        cases = (
            ("x的平方", "x**2"),
            ("根号下x", "sqrt(x)"),
            ("sinx除以x", "sin(x)/x"),
            ("x的立方减2x", "x**3 - 2*x"),
            ("3x平方减2", "3*x**2 - 2"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(expected, str(parse_math_expression(source)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
