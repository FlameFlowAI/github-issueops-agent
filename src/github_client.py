#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub REST API Client (Zero-Dependency)
========================================
使用 Python 标准库实现的轻量级 GitHub Issues API 客户端。
支持任务获取、自动认领回复、打标签以及任务完成自动关闭。
"""

import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Dict, Any, Optional

logger = logging.getLogger("IssueOps.GitHub")

class GitHubClient:
    def __init__(self, token: str, repo: str):
        self.token = token.strip()
        self.repo = repo.strip()
        self.base_url = f"https://api.github.com/repos/{self.repo}"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "IssueOps-Agent-Client/1.0"
        }
        if self.token and self.token != "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN":
            self.headers["Authorization"] = f"Bearer {self.token}"

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        body_bytes = None
        headers = dict(self.headers)

        if data is not None:
            body_bytes = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_text = resp.read().decode("utf-8")
                return json.loads(resp_text) if resp_text else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"GitHub API HTTPError [{e.code}] on {method} {url}: {error_body}")
            raise
        except urllib.error.URLError as e:
            logger.error(f"GitHub API URLError on {method} {url}: {e.reason}")
            raise

    def get_open_issues(self, labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """获取所有处于 open 状态的 Issues"""
        query_params = {"state": "open", "per_page": 50}
        if labels and len(labels) == 1:
            query_params["labels"] = labels[0]

        endpoint = f"/issues?{urllib.parse.urlencode(query_params)}"
        issues = self._request("GET", endpoint)

        # 过滤掉 Pull Requests (GitHub Issues API 默认会包含 PR)
        task_issues = [i for i in issues if "pull_request" not in i]

        # 如果指定了多个候选标签，做本地匹配
        if labels and len(labels) > 1:
            filtered = []
            for issue in task_issues:
                issue_label_names = [lbl["name"] for lbl in issue.get("labels", [])]
                if any(lbl in issue_label_names for lbl in labels):
                    filtered.append(issue)
            return filtered

        return task_issues

    def add_comment(self, issue_number: int, body: str) -> Dict[str, Any]:
        """在 Issue 下发表评论"""
        endpoint = f"/issues/{issue_number}/comments"
        return self._request("POST", endpoint, {"body": body})

    def add_labels(self, issue_number: int, labels: List[str]) -> List[Dict[str, Any]]:
        """给 Issue 添加标签"""
        endpoint = f"/issues/{issue_number}/labels"
        return self._request("POST", endpoint, {"labels": labels})

    def remove_label(self, issue_number: int, label_name: str) -> bool:
        """从 Issue 移除某个标签"""
        encoded_label = urllib.parse.quote(label_name)
        endpoint = f"/issues/{issue_number}/labels/{encoded_label}"
        try:
            self._request("DELETE", endpoint)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            raise

    def close_issue(self, issue_number: int, reason: str = "completed") -> Dict[str, Any]:
        """关闭 Issue"""
        endpoint = f"/issues/{issue_number}"
        return self._request("PATCH", endpoint, {
            "state": "closed",
            "state_reason": reason
        })


class MockGitHubClient:
    """
    用于离线演示与自动化测试的 Mock 客户端
    模拟 GitHub IssueOps 完整的获取、认领、评论与关闭状态机
    """
    def __init__(self, initial_issues: Optional[List[Dict[str, Any]]] = None):
        self.issues = initial_issues or []
        self.comments = {} # issue_number -> list of comments

    def get_open_issues(self, labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        results = []
        for issue in self.issues:
            if issue.get("state") != "open":
                continue
            issue_labels = [l if isinstance(l, str) else l["name"] for l in issue.get("labels", [])]
            if not labels or any(l in issue_labels for l in labels):
                results.append(issue)
        return results

    def add_comment(self, issue_number: int, body: str) -> Dict[str, Any]:
        comment = {
            "id": len(self.comments.get(issue_number, [])) + 1,
            "body": body,
            "user": {"login": "issueops-bot"}
        }
        self.comments.setdefault(issue_number, []).append(comment)
        logger.info(f"[Mock] Issue #{issue_number} 新增评论:\n{body[:120]}...")
        return comment

    def add_labels(self, issue_number: int, labels: List[str]) -> List[Dict[str, Any]]:
        for issue in self.issues:
            if issue["number"] == issue_number:
                current = [l if isinstance(l, str) else l["name"] for l in issue.get("labels", [])]
                for l in labels:
                    if l not in current:
                        issue.setdefault("labels", []).append({"name": l})
                logger.info(f"[Mock] Issue #{issue_number} 增加标签: {labels}")
                return issue["labels"]
        return []

    def remove_label(self, issue_number: int, label_name: str) -> bool:
        for issue in self.issues:
            if issue["number"] == issue_number:
                issue["labels"] = [
                    l for l in issue.get("labels", [])
                    if (l if isinstance(l, str) else l["name"]) != label_name
                ]
                logger.info(f"[Mock] Issue #{issue_number} 移除标签: {label_name}")
                return True
        return False

    def close_issue(self, issue_number: int, reason: str = "completed") -> Dict[str, Any]:
        for issue in self.issues:
            if issue["number"] == issue_number:
                issue["state"] = "closed"
                issue["state_reason"] = reason
                logger.info(f"[Mock] Issue #{issue_number} 已关闭 (原因: {reason})")
                return issue
        return {}
