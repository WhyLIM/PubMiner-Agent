"""样例守护测试：保证 examples/ 下的示例始终可运行（作为项目使用样例）。"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


def test_offline_demo_runs_end_to_end():
    """离线样例：无需网络与 key，一条命令跑通 检索→筛选→抽取→归一化→验证→聚合。"""
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "offline_demo.py")],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "task: REVIEW_READY" in result.stdout
    assert "SUCCEEDED" in result.stdout
    assert "candidate claims: 1" in result.stdout
    assert "[SUPPORT]" in result.stdout
    assert "KRAS expression was associated with poor overall survival" in result.stdout
