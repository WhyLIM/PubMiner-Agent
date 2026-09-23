"""安全基线门禁：源代码树内禁止 Sci-Hub 与 TLS 绕过。

门禁覆盖整个 src/（pubminer + pubex 两个包），防止安全债务回潮。
"""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_SCIHUB = ("sci-hub", "scihub")
FORBIDDEN_TLS = ("CERT_NONE", "_create_unverified_context", "disable_warnings", "check_hostname = False")


class TestNoSciHubInSource:
    def test_no_scihub_strings_in_product_source(self):
        offenders = []
        for path in SRC_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for token in FORBIDDEN_SCIHUB:
                if token in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
        assert offenders == [], "源代码不得引用 Sci-Hub:\n" + "\n".join(offenders)

    def test_no_legacy_scihub_archive_in_tree(self):
        assert not (SRC_ROOT / "scihub_downloader.py").exists()
        assert not (REPO_ROOT / "core" / "scihub_downloader.py").exists()
        assert not (REPO_ROOT / "legacy" / "scihub_downloader.py").exists()


class TestNoTLSBypass:
    @pytest.mark.parametrize("package", ["pubminer", "pubex"])
    def test_no_tls_bypass_strings(self, package):
        offenders = []
        for path in (SRC_ROOT / package).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in FORBIDDEN_TLS:
                if token in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
        assert offenders == [], "生产代码不得禁用 TLS 校验:\n" + "\n".join(offenders)

    @pytest.mark.parametrize("package", ["pubminer", "pubex"])
    def test_import_does_not_mutate_global_ssl(self, package):
        code = (
            "import ssl, sys\n"
            f"sys.path.insert(0, r'{SRC_ROOT}')\n"
            "before = ssl._create_default_https_context\n"
            f"import {package}\n"
            "after = ssl._create_default_https_context\n"
            "sys.exit(0 if before is after else 1)\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, f"import {package} 修改了全局 SSL 上下文: {result.stderr[-300:]}"


class TestCertificateFailurePolicy:
    def test_pubex_retry_fails_fast_on_tls_error(self):
        import asyncio

        from pubex.clients.retry import retry_async
        from pubex.errors import PubExTLSVerificationError

        async def scenario():
            calls = {"n": 0}

            async def op():
                calls["n"] += 1
                raise PubExTLSVerificationError("certificate verify failed")

            with pytest.raises(PubExTLSVerificationError):
                await retry_async(op, max_retries=5, base_wait=0, sleep=lambda *_: asyncio.sleep(0))
            return calls["n"]

        import asyncio

        assert asyncio.run(scenario()) == 1, "证书错误必须快速失败，不得重试"

    def test_domain_layer_has_no_vendor_imports(self):
        """domain 纯净性（ADR-011）：domain 不得导入框架/厂商模块。"""
        domain_dir = SRC_ROOT / "pubminer" / "domain"
        forbidden = ("fastapi", "sqlalchemy", "alembic", "zhipuai", "openai", "anthropic", "aiohttp", "Bio", "pandas")
        offenders = []
        for path in domain_dir.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                for module in modules:
                    if module.split(".")[0] in forbidden:
                        offenders.append(f"{path.name}: {module}")
        assert offenders == [], "domain 违规导入:\n" + "\n".join(offenders)
