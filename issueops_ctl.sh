#!/usr/bin/env bash
# ==============================================================================
# GitHub IssueOps Agent Unified Controller (异步任务调度层控制脚本)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${SCRIPT_DIR}/.issueops.pid"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/issueops.log"
CRON_LOG="${LOG_DIR}/cron.log"
PYTHON_BIN="$(which python3 || echo 'python3')"

mkdir -p "${LOG_DIR}"

GREEN="\033[38;2;52;211;153m"
CYAN="\033[38;2;56;189;248m"
INDIGO="\033[38;2;129;140;248m"
YELLOW="\033[38;2;251;191;36m"
RED="\033[38;2;248;113;113m"
RESET="\033[0m"
BOLD="\033[1m"

get_daemon_pid() {
  if [ -f "${PID_FILE}" ]; then
    local pid=$(cat "${PID_FILE}")
    if ps -p "${pid}" > /dev/null 2>&1; then
      echo "${pid}"
      return 0
    fi
  fi
  # Fallback search by process command
  pgrep -f "src/main.py --daemon" | head -n1 || true
}

cmd_status() {
  echo -e "\n${BOLD}${CYAN}🧭 GitHub IssueOps 异步调度层 · 状态诊断${RESET}"
  echo "----------------------------------------------------------------------"
  local pid=$(get_daemon_pid)
  if [ -n "${pid}" ]; then
    local mem=$(ps -o rss= -p "${pid}" 2>/dev/null | awk '{print int($1/1024) " MB"}' || echo "—")
    local elapsed=$(ps -o etime= -p "${pid}" 2>/dev/null | tr -d ' ' || echo "—")
    echo -e "  [1] 守护进程状态: ${GREEN}● 正在运行 (ONLINE)${RESET}"
    echo -e "      - 进程 PID: ${BOLD}${pid}${RESET}"
    echo -e "      - 内存占用: ${mem}"
    echo -e "      - 连续运行: ${elapsed}"
    echo -e "      - 日志位置: ${LOG_FILE}"
  else
    echo -e "  [1] 守护进程状态: ${YELLOW}○ 未启动守护进程 (OFFLINE)${RESET}"
    echo -e "      - 提示: 可通过 ./issueops_ctl.sh start 启动，或使用系统 Cron 定时执行"
  fi

  # 网络连通性
  echo -e "\n  [2] 宿主机网络连通性:"
  if "${PYTHON_BIN}" "${SCRIPT_DIR}/src/main.py" --check-network > /dev/null 2>&1; then
    echo -e "      - GitHub API: ${GREEN}● 畅通 (OK)${RESET}"
  else
    echo -e "      - GitHub API: ${RED}○ 暂无法连通 (可能正处于睡眠唤醒或断网阶段)${RESET}"
  fi

  # 缓存与调度统计
  local cache_file="${SCRIPT_DIR}/.issueops_cache.json"
  if [ -f "${cache_file}" ]; then
    local count=$("${PYTHON_BIN}" -c "import json; data=json.load(open('${cache_file}')); print(len(data.get('processed_issues', {})))" 2>/dev/null || echo "0")
    local last_poll=$("${PYTHON_BIN}" -c "import json, time; data=json.load(open('${cache_file}')); t=data.get('last_poll_time', 0); print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t)) if t else '从未')" 2>/dev/null || echo "未知")
    echo -e "\n  [3] 任务调度历史:"
    echo -e "      - 已闭环任务数: ${GREEN}${count}${RESET} 个"
    echo -e "      - 最近巡检时间: ${last_poll}"
  fi
  echo "----------------------------------------------------------------------"
  echo ""
}

cmd_start() {
  local pid=$(get_daemon_pid)
  if [ -n "${pid}" ]; then
    echo -e "${YELLOW}⚠ IssueOps 守护进程已在运行 (PID: ${pid})${RESET}"
    return 0
  fi

  echo -e "${INDIGO}🚀 正在启动 GitHub IssueOps 守护进程...${RESET}"
  cd "${SCRIPT_DIR}"
  nohup "${PYTHON_BIN}" "${SCRIPT_DIR}/src/main.py" --daemon >> "${LOG_FILE}" 2>&1 &
  local new_pid=$!
  echo "${new_pid}" > "${PID_FILE}"
  sleep 1

  if ps -p "${new_pid}" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 启动成功！(PID: ${new_pid})${RESET}"
    echo -e "  👉 实时查看日志: ${CYAN}./issueops_ctl.sh logs${RESET}"
  else
    echo -e "${RED}✗ 启动失败，请检查日志: ${LOG_FILE}${RESET}"
    rm -f "${PID_FILE}"
    exit 1
  fi
}

cmd_stop() {
  local pid=$(get_daemon_pid)
  if [ -z "${pid}" ]; then
    echo -e "${YELLOW}IssueOps 守护进程未在运行。${RESET}"
    rm -f "${PID_FILE}"
    return 0
  fi

  echo -e "${YELLOW}🛑 正在停止 IssueOps 守护进程 (PID: ${pid})...${RESET}"
  kill "${pid}" 2>/dev/null || true
  sleep 1
  if ps -p "${pid}" > /dev/null 2>&1; then
    kill -9 "${pid}" 2>/dev/null || true
  fi
  rm -f "${PID_FILE}"
  echo -e "${GREEN}✓ 守护进程已停止。${RESET}"
}

cmd_restart() {
  cmd_stop
  sleep 1
  cmd_start
}

cmd_run_once() {
  echo -e "${INDIGO}⚡ 手动触发一次 IssueOps 巡检与任务认领...${RESET}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/src/main.py" --once
}

cmd_test() {
  echo -e "${BOLD}${CYAN}🧪 运行单元测试与 Mock 端到端闭环验证...${RESET}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/tests/test_issueops_flow.py"
  echo ""
  "${PYTHON_BIN}" "${SCRIPT_DIR}/src/main.py" --mock
}

cmd_logs() {
  if [ -f "${LOG_FILE}" ]; then
    tail -f -n 50 "${LOG_FILE}"
  else
    echo "暂无日志文件: ${LOG_FILE}"
  fi
}

cmd_cron() {
  local cron_entry="*/5 * * * * ${SCRIPT_DIR}/issueops_ctl.sh run-once >> ${CRON_LOG} 2>&1"
  echo -e "\n${BOLD}${CYAN}🕒 Linux Cron 定时任务配置建议 (推荐: 每 5 分钟执行一次)${RESET}"
  echo "----------------------------------------------------------------------"
  echo -e "在终端执行 ${BOLD}crontab -e${RESET} 并将以下行粘贴至末尾："
  echo ""
  echo -e "  ${GREEN}${cron_entry}${RESET}"
  echo ""
  echo "----------------------------------------------------------------------"
  echo -e "说明: 即使电脑进入睡眠状态，重新联网唤醒后 Cron 会在下一个 5 分钟周期自动认领手机端创建的 Issue。"
}

case "$1" in
  start)
    cmd_start
    ;;
  stop)
    cmd_stop
    ;;
  restart)
    cmd_restart
    ;;
  status)
    cmd_status
    ;;
  run-once)
    cmd_run_once
    ;;
  test)
    cmd_test
    ;;
  logs)
    cmd_logs
    ;;
  cron)
    cmd_cron
    ;;
  *)
    echo -e "${BOLD}GitHub IssueOps 异步任务调度层控制脚本${RESET}"
    echo "用法: $0 {start|stop|restart|status|run-once|test|logs|cron}"
    echo ""
    echo "常用指令:"
    echo "  ./issueops_ctl.sh start      启动后台定时轮询守护进程"
    echo "  ./issueops_ctl.sh status     查看运行状态与已处理任务统计"
    echo "  ./issueops_ctl.sh run-once   单次巡检并认领执行任务"
    echo "  ./issueops_ctl.sh test       运行单元测试与端到端模拟测试"
    echo "  ./issueops_ctl.sh cron       生成 Linux crontab 每 5 分钟定时指令"
    echo "  ./issueops_ctl.sh logs       实时跟踪守护进程日志"
    echo "  ./issueops_ctl.sh stop       停止后台守护进程"
    exit 1
    ;;
esac
