#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-End Test Suite for GitHub IssueOps Agent
==============================================
验证断网探测、指令解析、状态机流转与任务自动认领闭环。
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.network_detector import is_network_available
from src.github_client import MockGitHubClient
from src.task_dispatcher import TaskDispatcher
from src.issueops_engine import IssueOpsEngine

class TestIssueOpsFlow(unittest.TestCase):

    def test_01_network_detector(self):
        """测试网络连通性探测"""
        online = is_network_available(timeout=3.0)
        self.assertIsInstance(online, bool)

    def test_02_task_dispatcher_command(self):
        """测试指令解析与执行"""
        dispatcher = TaskDispatcher(workspace_root=PROJECT_ROOT)
        issue = {
            "number": 42,
            "title": "单元测试指令",
            "body": "请执行测试命令:\n/run echo 'IssueOps Task Passed'"
        }
        res = dispatcher.parse_and_execute(issue)
        self.assertTrue(res["success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("IssueOps Task Passed", res["report_md"])

    def test_03_task_dispatcher_python_block(self):
        """测试 Python 代码块执行"""
        dispatcher = TaskDispatcher(workspace_root=PROJECT_ROOT)
        issue = {
            "number": 43,
            "title": "执行动态 Python 任务",
            "body": "计算数学结果：\n```python\nprint(f'CALC_RESULT_{21 * 2}')\n```"
        }
        res = dispatcher.parse_and_execute(issue)
        self.assertTrue(res["success"])
        self.assertIn("CALC_RESULT_42", res["report_md"])

    def test_04_full_engine_mock_lifecycle(self):
        """测试引擎完整状态机闭环 (认领 -> 执行 -> 回复报告 -> 自动关闭)"""
        mock_issues = [
            {
                "number": 88,
                "title": "手机端安排乒乓数据统计",
                "body": "测试 IssueOps 调度\n/run echo 'PONG_STATS_OK'",
                "labels": [{"name": "agent-task"}],
                "state": "open"
            }
        ]
        mock_client = MockGitHubClient(initial_issues=mock_issues)
        config_path = os.path.join(PROJECT_ROOT, "config.json")
        engine = IssueOpsEngine(config_path=config_path, mock_client=mock_client)

        # 执行一次巡检
        processed = engine.run_once()
        self.assertEqual(processed, 1)

        # 验证 Issue 状态已被关闭
        closed_issue = mock_client.issues[0]
        self.assertEqual(closed_issue["state"], "closed")
        self.assertEqual(closed_issue["state_reason"], "completed")

        # 验证评论包含认领通知与执行报告 (共 2 条评论)
        comments = mock_client.comments.get(88, [])
        self.assertEqual(len(comments), 2)
        self.assertIn("任务自动认领", comments[0]["body"])
        self.assertIn("任务执行报告", comments[1]["body"])
        self.assertIn("PONG_STATS_OK", comments[1]["body"])

        # 验证标签包含 status:completed
        label_names = [l["name"] for l in closed_issue["labels"]]
        self.assertIn("status:completed", label_names)
        self.assertNotIn("status:running", label_names)

if __name__ == "__main__":
    unittest.main()
