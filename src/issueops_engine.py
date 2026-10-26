#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IssueOps Core Orchestration Engine (核心状态机与轮询调度引擎)
===========================================================
连接网络探测器、GitHub 客户端与任务执行器，
实现不依赖实时在线、睡眠唤醒后自愈认领与任务闭环。
"""

import os
import sys
import json
import time
import logging
from typing import Dict, Any, Optional

from .network_detector import is_network_available, wait_until_online
from .github_client import GitHubClient, MockGitHubClient
from .task_dispatcher import TaskDispatcher

logger = logging.getLogger("IssueOps.Engine")

class IssueOpsEngine:
    def __init__(self, config_path: str = "config.json", mock_client: Optional[Any] = None):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.workspace_root = self.config.get("workspace_root", "/data/workspace")
        self.target_labels = self.config.get("target_labels", ["agent-task", "[agent-task]"])
        self.repo = self.config.get("repo", "FlameFlowAI/my-agent-memory")
        self.token = self.config.get("github_token", "")
        self.poll_interval = self.config.get("poll_interval_seconds", 300)
        self.cache_file = os.path.join(os.path.dirname(os.path.abspath(config_path)), ".issueops_cache.json")
        self.cache = self._load_cache()

        # 初始化客户端
        if mock_client is not None:
            self.client = mock_client
            logger.info("🧪 使用 Mock GitHub Client 进行测试调度")
        else:
            self.client = GitHubClient(token=self.token, repo=self.repo)

        self.dispatcher = TaskDispatcher(workspace_root=self.workspace_root)

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            example_path = path.replace(".json", ".example.json")
            if os.path.exists(example_path):
                with open(example_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"processed_issues": {}, "last_poll_time": 0}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    def run_once(self) -> int:
        """
        单次检查并处理所有未完成的任务 (适合系统定时 Cron 调用)
        返回成功处理的任务数量
        """
        logger.info("🔍 开始执行 IssueOps 巡检...")

        # 1. 检查网络连通性 (睡眠唤醒或断网时等待恢复)
        if not is_network_available():
            logger.warning("⚠ 当前未检测到网络连接，可能处于睡眠唤醒恢复期，等待网络自愈...")
            online = wait_until_online(check_interval=5, max_wait_seconds=60)
            if not online:
                logger.error("❌ 网络持续离线，跳过本次巡检，等待下次调度。")
                return 0

        # 2. 查询待处理的 Issues (获取全部 open Issues，智能兼容手机端未手动选标签的情况)
        try:
            all_open_issues = self.client.get_open_issues(labels=None)
        except Exception as e:
            logger.error(f"❌ 访问 GitHub Issues 失败: {e}")
            return 0

        self.cache["last_poll_time"] = int(time.time())
        auto_claim_all = self.config.get("auto_claim_all_open", True)

        processed_count = 0
        for issue in all_open_issues:
            issue_number = issue.get("number")
            title = issue.get("title", "")
            body = issue.get("body", "")

            # 避免重复认领正在执行或已处理的任务
            labels = [l if isinstance(l, str) else l["name"] for l in issue.get("labels", [])]
            if "status:running" in labels or "status:completed" in labels:
                logger.info(f"⏭ Issue #{issue_number} 已处于 {labels} 状态，跳过重复认领")
                continue

            # 智能判断是否为待调度任务：
            # 1. 明确携带目标标签 (agent-task / [agent-task])
            has_target_label = any(l in labels for l in self.target_labels)
            # 2. 含有调度指令 (/backfeed, /run, /sync, ``` 等)
            has_command = any(k in (title + " " + body) for k in ["/backfeed", "/run", "/sync", "/card", "```"])
            # 3. 专属任务仓库默认处理所有未关闭 Issue
            is_dedicated_repo = "github-issueops-agent" in self.repo or auto_claim_all

            if not (has_target_label or has_command or is_dedicated_repo):
                logger.info(f"⏭ Issue #{issue_number} 未匹配调度指令且未打标签，跳过")
                continue

            # 自动补齐 agent-task 标签 (便于在 GitHub 界面清晰归类)
            if not has_target_label:
                try:
                    self.client.add_labels(issue_number, ["agent-task"])
                except Exception:
                    pass

            # 处理单个任务
            try:
                self._process_single_issue(issue)
                processed_count += 1
            except Exception as e:
                logger.error(f"❌ 处理 Issue #{issue_number} 时出错: {e}", exc_info=True)

        self._save_cache()
        logger.info(f"✨ 本轮巡检完成，成功闭环处理 {processed_count} 个任务")
        return processed_count

    def _process_single_issue(self, issue: Dict[str, Any]):
        issue_number = issue.get("number")
        title = issue.get("title")
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        logger.info(f"🎯 自动认领任务: #{issue_number} - {title}")

        # 1. 发布认领评论
        claim_msg = (
            f"🤖 **[IssueOps 任务自动认领]**\n\n"
            f"家用主机已恢复联网并成功认领该异步任务！\n"
            f"- **认领时间**: `{now_str}`\n"
            f"- **执行节点**: `{self.dispatcher.hostname}` (Linux)\n"
            f"- **当前状态**: 正在本地环境调度执行中，完成后将自动汇报并关闭...\n"
        )
        self.client.add_comment(issue_number, claim_msg)

        # 2. 标记状态为 running
        try:
            self.client.add_labels(issue_number, ["status:running"])
        except Exception as e:
            logger.warning(f"添加 running 标签警告 (非致命): {e}")

        # 3. 执行任务
        exec_result = self.dispatcher.parse_and_execute(issue)

        # 4. 发布执行总结报告
        report_md = exec_result["report_md"]
        self.client.add_comment(issue_number, report_md)

        # 5. 更新标签并关闭 Issue
        try:
            self.client.remove_label(issue_number, "status:running")
        except Exception:
            pass

        try:
            self.client.add_labels(issue_number, ["status:completed"])
        except Exception:
            pass

        self.client.close_issue(issue_number, reason="completed")

        # 6. 记录到本地已处理缓存
        self.cache.setdefault("processed_issues", {})[str(issue_number)] = {
            "title": title,
            "completed_at": now_str,
            "success": exec_result["success"],
            "duration": exec_result["duration"]
        }
        logger.info(f"🏁 任务 #{issue_number} 已成功汇报并关闭 Issue！")

        # 7. 若为真实 GitHub 任务（非 Mock 测试），自动联动飞书网关向手机推送闭环通知卡片
        if not isinstance(self.client, MockGitHubClient):
            try:
                bus_dir = "/data/workspace/my-agent-memory/scripts"
                if bus_dir not in sys.path:
                    sys.path.insert(0, bus_dir)
                from agent_collab_bus import push_feishu_notification
                push_feishu_notification(
                    title=f"🛰️ IssueOps 离线工单已闭环 [#{issue_number}]",
                    markdown_body=(
                        f"**工单标题**：{title}\n"
                        f"**任务类型**：`{exec_result.get('task_type')}`\n"
                        f"**执行耗时**：`{exec_result.get('duration', 0):.1f}s`\n"
                        f"**执行结果**：{'✅ 成功并自动关单' if exec_result.get('success') else '❌ 执行异常'}\n\n"
                        f"*详细执行报告已回写至 GitHub Issue #{issue_number} 评论区。*"
                    ),
                    color="green" if exec_result.get("success") else "red"
                )
            except Exception as notify_err:
                logger.warning(f"联动推送飞书通知失败 (非致命): {notify_err}")

    def run_daemon(self):
        """
        后台守护进程模式：每隔 poll_interval_seconds 自动检查一次
        """
        logger.info(f"🛡️ IssueOps 调度守护进程启动！轮询间隔: {self.poll_interval} 秒 ({self.poll_interval / 60:.1f} 分钟)")
        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"调度循环异常: {e}", exc_info=True)

            logger.info(f"⏳ 休眠等待下一次轮询 ({self.poll_interval}s)...")
            time.sleep(self.poll_interval)
