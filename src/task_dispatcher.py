#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Task Dispatcher (任务解析与调度执行器)
============================================
负责解析 GitHub Issue 的指令内容（支持 /run, /backfeed, 代码块, 自然语言等），
并在本地沙箱或工作区中执行，捕获完整的执行证据与标准输出。
"""

import os
import re
import sys
import time
import socket
import subprocess
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("IssueOps.Dispatcher")

class TaskDispatcher:
    def __init__(self, workspace_root: str = "/data/workspace"):
        self.workspace_root = workspace_root
        self.hostname = socket.gethostname()

    def parse_and_execute(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 Issue 标题和正文并执行任务
        """
        title = issue.get("title", "").strip()
        body = issue.get("body", "").strip()
        issue_number = issue.get("number", 0)

        logger.info(f"🚀 开始调度任务 #{issue_number}: {title}")
        start_time = time.time()
        start_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))

        cmd_to_run = None
        task_type = "general"

        # 1. 优先提取 /run 命令
        m_run = re.search(r"^\s*/run\s+(.+)$", body, re.MULTILINE)
        if m_run:
            cmd_to_run = m_run.group(1).strip()
            task_type = "slash_command"

        # 2. 提取周复盘沉淀快捷命令 /backfeed
        elif "/backfeed" in body or "沉淀到外脑" in title or "反向复盘" in title:
            cmd_to_run = "/data/workspace/command_center_ctl.sh backfeed"
            task_type = "memory_backfeed"

        # 3. 提取同步命令 /sync
        elif "/sync" in body or "同步上下文" in title:
            cmd_to_run = "/data/workspace/command_center_ctl.sh sync"
            task_type = "context_sync"

        # 4. 提取 Markdown 中的 bash 代码块
        elif "```bash" in body or "```sh" in body:
            m_code = re.search(r"```(?:bash|sh)\s*\n(.*?)\n```", body, re.DOTALL)
            if m_code:
                cmd_to_run = m_code.group(1).strip()
                task_type = "bash_script"

        # 5. 提取 Python 代码块并临时执行
        elif "```python" in body:
            m_py = re.search(r"```python\s*\n(.*?)\n```", body, re.DOTALL)
            if m_py:
                py_code = m_py.group(1).strip()
                cmd_to_run = f"{sys.executable} -c {subprocess.list2cmdline([py_code])}"
                task_type = "python_script"

        # 6. 普通自然语言任务或未指定命令：执行默认记录与健康自检
        if not cmd_to_run:
            cmd_to_run = f"echo '已成功接收手机端指令: {title}' && /data/workspace/command_center_ctl.sh status"
            task_type = "task_acknowledgement"

        # 执行命令
        exit_code, stdout, stderr = self._run_command(cmd_to_run)
        duration = time.time() - start_time

        success = (exit_code == 0)
        report_md = self._format_report(
            issue_number=issue_number,
            title=title,
            task_type=task_type,
            command=cmd_to_run,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration=duration,
            start_time_str=start_time_str,
            success=success
        )

        return {
            "success": success,
            "exit_code": exit_code,
            "duration": duration,
            "task_type": task_type,
            "report_md": report_md
        }

    def _run_command(self, command: str, timeout: int = 600) -> Tuple[int, str, str]:
        """
        在工作区执行命令并捕获输出
        """
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except subprocess.TimeoutExpired:
            return 124, "", f"执行超时 ({timeout} 秒)"
        except Exception as e:
            return 1, "", str(e)

    def _format_report(
        self,
        issue_number: int,
        title: str,
        task_type: str,
        command: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration: float,
        start_time_str: str,
        success: bool
    ) -> str:
        """
        格式化 GitHub Markdown 格式的执行总结报告
        """
        status_badge = "✅ **任务执行成功 (COMPLETED)**" if success else "❌ **任务执行异常 (FAILED)**"
        
        # 截断过长输出以防超出 GitHub 评论限制
        max_len = 3500
        stdout_display = stdout if len(stdout) <= max_len else stdout[:max_len] + "\n...[输出过长已截断]"
        stderr_display = stderr if len(stderr) <= max_len else stderr[:max_len] + "\n...[错误过长已截断]"

        # 隐藏敏感 Token 字符串
        token_pattern = r"(ghp_[a-zA-Z0-9]{30,}|github_pat_[a-zA-Z0-9_]{50,})"
        stdout_display = re.sub(token_pattern, "[MASKED_TOKEN]", stdout_display)
        stderr_display = re.sub(token_pattern, "[MASKED_TOKEN]", stderr_display)

        lines = [
            f"## 🤖 IssueOps 任务执行报告 · #{issue_number}",
            "",
            f"{status_badge}",
            "",
            "### 📊 执行指标与环境参数",
            "| 指标项 | 运行数值 / 详情 |",
            "| :--- | :--- |",
            f"| **任务名称** | {title} |",
            f"| **任务类型** | `{task_type}` |",
            f"| **开始时间** | {start_time_str} |",
            f"| **执行耗时** | {duration:.2f} 秒 |",
            f"| **退出状态码** | `{exit_code}` |",
            f"| **执行节点** | `{self.hostname}` (Linux) |",
            "",
            "### ⚙️ 实际调用指令",
            "```bash",
            command,
            "```",
            ""
        ]

        if stdout_display:
            lines.extend([
                "### 📝 标准输出 (stdout)",
                "<details open>",
                "<summary>点击折叠/展开详细日志</summary>",
                "",
                "```text",
                stdout_display,
                "```",
                "</details>",
                ""
            ])

        if stderr_display:
            lines.extend([
                "### ⚠️ 错误信息 (stderr)",
                "```text",
                stderr_display,
                "```",
                ""
            ])

        lines.extend([
            "---",
            "💡 *本任务由家用主机后台定时检测并在联网恢复后自动认领执行。任务已闭环沉淀，Issue 自动关闭。*"
        ])

        return "\n".join(lines)
