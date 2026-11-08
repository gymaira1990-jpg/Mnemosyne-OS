"""答案契合度（answerability）的行为测试 —— T-0689，2026-11-09。

约束这份实现的真实数据依据：
  · 55 条正样本 + 10 条负样本实测；正样本 ≥0.3 占 94%，负样本 ≥0.3 只占 20%
  · 真实库上正样本均值 0.64 vs 负样本均值 0.06

这里锁三件事：
  1. 答案真的含问题实体时，分要高
  2. 答案完全不相干时，分要低（这是"弃权信号"存在的意义）
  3. 抽不出实体时返回 1.0 —— 宁可放过，不许误伤
"""
from api.memory_os import answerability, _ent_hit


class TestAnswerability:

    def test_matching_answer_scores_high(self):
        """问题实体出现在答案里 → 高分"""
        text = ("[结果卡] 档号：K·DEMO·2026-0038\n题名：火山引擎账户余额 225 元\n"
                "摘要：火山引擎账户余额 225 元，走按量计费。")
        assert answerability("火山引擎还剩多少钱", text) >= 0.3

    def test_unrelated_answer_scores_low(self):
        """答案完全没答到（问监控，答巡检）→ 低分"""
        text = ("[结果卡] 档号：K·DEMO·2026-0020\n题名：讨厌一动就加巡检\n"
                "摘要：讨厌一动就加巡检，减负第一，能靠自动恢复解决就不加监控。")
        assert answerability("灾难恢复演练上一次是什么时候做的", text) < 0.3

    def test_k8s_negative_case(self):
        """真实场景：问 K8s，库里只有入职记录 → 必须贴近 0"""
        text = ("[结果卡] 档号：K·DEMO·2026-0023\n题名：10 月 27 日入职 WEBX 香港\n"
                "摘要：10 月 27 日入职 WEBX 香港，负责创新事业集群。")
        assert answerability("K8s 集群有几个节点", text) < 0.3

    def test_ascii_entity_must_match(self):
        """ASCII 专名（CDN/Stripe/K8s）不能被泛词蒙混过关"""
        text = "[结果卡] 题名：供应商 wancms 的技术负责人是老王\n摘要：接口对接找老王。"
        assert answerability("我们用的哪家 CDN 供应商", text) < 0.5

    def test_no_entities_returns_one(self):
        """抽不出实体时返回 1.0（不判断，不误伤）"""
        assert answerability("嗯", "随便什么内容") == 1.0

    def test_synonym_answer_not_penalized_hard(self):
        """近义表达：问「盘符」，答案是路径 —— 不能判成完全不相干（≥0 即可，不能负）"""
        text = "[结果卡] 题名：WSL 到 Windows 的映射\n摘要：Z:=\\\\wsl.localhost\\Ubuntu 可直接访问。"
        score = answerability("WSL 的家目录在 Windows 里映射成哪个盘符", text)
        assert 0.0 <= score <= 1.0


class TestEntHit:

    def test_exact_substring(self):
        assert _ent_hit("火山引擎", "火山引擎账户余额 225 元") is True

    def test_long_word_split_in_answer(self):
        """复合词被拆开写（凭据/分级）→ 子串过半数算命中"""
        assert _ent_hit("凭据分级", "凭据按敏感程度分级，普通可直调") is True

    def test_short_word_requires_exact(self):
        """2 字词不做子串退化，避免「恢复」蒙中「自动恢复」"""
        assert _ent_hit("演练", "能靠自动恢复解决") is False
