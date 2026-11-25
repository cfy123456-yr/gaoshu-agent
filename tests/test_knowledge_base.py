import unittest
from pathlib import Path

from deploy.demo_knowledge import KnowledgeBase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CHAPTERS = {
    "01_函数与极限.md",
    "02_导数与微分.md",
    "03_微分中值定理与导数的应用.md",
    "04_不定积分.md",
    "05_定积分.md",
    "06_定积分的应用.md",
    "07_微分方程.md",
    "08_向量代数与空间解析几何.md",
    "09_多元函数微分法及其应用.md",
    "10_重积分.md",
    "11_曲线积分与曲面积分.md",
    "12_无穷级数.md",
}


class TongjiKnowledgeBaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.knowledge_base = KnowledgeBase(PROJECT_ROOT)

    def test_indexes_all_twelve_tongji_chapter_files(self):
        sources = {section.source for section in self.knowledge_base.sections}

        self.assertEqual(
            {f"knowledge/{name}" for name in EXPECTED_CHAPTERS},
            sources,
        )

    def test_every_section_uses_the_single_knowledge_directory(self):
        for section in self.knowledge_base.sections:
            with self.subTest(source=section.source):
                self.assertTrue(section.source.startswith("knowledge/"))
                self.assertNotIn("knowledge_tongji", section.source)

    def test_obsolete_sources_are_not_indexed(self):
        indexed_text = "\n".join(
            f"{section.source}\n{section.title}\n{section.body}"
            for section in self.knowledge_base.sections
        )

        for obsolete_name in (
            "02_积分基础.md",
            "05_反常积分补充.md",
            "knowledge_tongji",
        ):
            self.assertNotIn(obsolete_name, indexed_text)

    def test_integral_definition_returns_tongji_source(self):
        results = self.knowledge_base.search("积分的定义", limit=3)

        self.assertTrue(results)
        self.assertEqual("knowledge/05_定积分.md", results[0].source)
        self.assertIn("定积分的概念", results[0].title)

    def test_definite_integral_definition_prefers_the_definition_section(self):
        results = self.knowledge_base.search("定积分的定义", limit=3)

        self.assertTrue(results)
        self.assertEqual("knowledge/05_定积分.md", results[0].source)
        self.assertIn("定积分的概念", results[0].title)


if __name__ == "__main__":
    unittest.main(verbosity=2)
