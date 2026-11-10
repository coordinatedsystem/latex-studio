import unittest
from studio_assistant_context import layout_requested,conversation_history,runtime_instruction

class TurnContextTests(unittest.TestCase):
    def test_only_explicit_current_layout_requests_start_layout_checks(self):
        for question in ['检查一下文章的排版','检查一下排版，别改实验日期','不要动日期，检查一下排版','不要检查引用，检查排版','review the layout']:
            self.assertTrue(layout_requested(question),question)
        for question in ['配套文件与复现方法不用说这么仔细','你的回复简短一点','不用重新检查整篇排版，只精简这一节','别再检查排版了','排版不用检查','继续']:
            self.assertFalse(layout_requested(question),question)
    def test_recent_reply_keeps_its_ending_instead_of_only_the_first_2500_characters(self):
        text='Earlier details. '*400+'配套文件与复现方法：只需交代入口和依赖。'
        messages=[{'role':'user','content':'检查排版'},{'role':'assistant','content':text}]
        history=conversation_history(messages);self.assertTrue(history[-1]['content'].endswith('只需交代入口和依赖。'))
    def test_history_budget_is_bounded(self):
        history=conversation_history([{'role':'assistant' if i%2 else 'user','content':str(i)+'x'*20000} for i in range(20)])
        self.assertLessEqual(sum(len(m['content']) for m in history),18000);self.assertTrue(history[-1]['content'].startswith('19'))
    def test_current_mode_overrides_historical_mode_advice(self):
        self.assertIn('当前是 Agent',runtime_instruction('agent'));self.assertIn('当前是 Chat',runtime_instruction('chat'))

if __name__=='__main__':unittest.main()
