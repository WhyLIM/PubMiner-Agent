"""规则辅助验证测试：p 值提取、显著性预判。"""
from pubminer.workflows.verification_rules import extract_p_value, rule_assess


class TestExtractPValue:
    def test_standard(self):
        assert extract_p_value("HR 2.1, p = 0.04") == 0.04

    def test_less_than(self):
        assert extract_p_value("p < 0.001") == 0.001

    def test_none(self):
        assert extract_p_value("no statistics here") is None


class TestRuleAssess:
    def test_significant(self):
        r = rule_assess("worse OS (p = 0.008)")
        assert r["statistically_significant"] is True

    def test_not_significant(self):
        r = rule_assess("p = 0.3")
        assert r["statistically_significant"] is False

    def test_no_signal(self):
        r = rule_assess("no statistics in this text")
        assert r["statistically_significant"] is None
        assert r["rule_reasons"] == []

    def test_statistics_override(self):
        r = rule_assess("no p in span", statistics={"p_value": "0.01"})
        assert r["statistically_significant"] is True
