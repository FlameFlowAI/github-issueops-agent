#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IssueOps Agent CLI Main Entrypoint (调度层主入口)
==============================================
"""

import os
import sys
import argparse
import logging

# 确保引入当前目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.issueops_engine import IssueOpsEngine
from src.github_client import MockGitHubClient
from src.network_detector import is_network_available

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=format_str, datefmt="%Y-%m-%d %H:%M:%S")

def main():
    parser = argparse.ArgumentParser(
        description="GitHub 异步任务调度层 IssueOps · 家用电脑断网自愈与自动执行闭环"
    )
    parser.add_argument(
        "--config",
        default=os.path.join(PROJECT_ROOT, "config.json"),
        help="配置文件路径 (默认: config.json)"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="以后台守护进程模式运行 (每隔 N 分钟轮询一次)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="仅执行一次巡检并退出 (适合由系统的 crontab 调度)"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="使用虚拟 Issue 运行端到端模拟测试 (无需 GitHub Token)"
    )
    parser.add_argument(
        "--check-network",
        action="store_true",
        help="仅测试当前网络到 GitHub API 的连通性"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="输出详细调试日志"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.check_network:
        print("🔍 正在探测网络到 api.github.com 的连通性...")
        online = is_network_available()
        if online:
            print("✅ 网络连通正常！可以与 GitHub 进行无缝通信。")
            sys.exit(0)
        else:
            print("❌ 当前网络无法连通 api.github.com。")
            sys.exit(1)

    if args.mock:
        print("=" * 60)
        print("🧪 启动 IssueOps Mock 端到端全流程模拟验证...")
        print("=" * 60)
        mock_issues = [
            {
                "number": 101,
                "title": "测试手机端下发战术复盘回写指令",
                "body": "手机在外临时安排：请在家用电脑上运行复盘回写管线。\n\n/backfeed",
                "labels": [{"name": "agent-task"}, {"name": "priority:high"}],
                "state": "open"
            },
            {
                "number": 102,
                "title": "测试执行状态自检与系统健康检查",
                "body": "请运行双中枢状态诊断：\n\n```bash\n/data/workspace/command_center_ctl.sh status\n```",
                "labels": [{"name": "[agent-task]"}],
                "state": "open"
            }
        ]
        mock_client = MockGitHubClient(initial_issues=mock_issues)
        engine = IssueOpsEngine(config_path=args.config, mock_client=mock_client)
        count = engine.run_once()
        print("=" * 60)
        print(f"🎉 Mock 测试圆满完成！共成功模拟调度与关闭 {count} 个任务。")
        print("=" * 60)
        sys.exit(0)

    # 真实运行逻辑
    engine = IssueOpsEngine(config_path=args.config)

    if args.daemon:
        engine.run_daemon()
    else:
        # 默认执行一次
        engine.run_once()

if __name__ == "__main__":
    main()
