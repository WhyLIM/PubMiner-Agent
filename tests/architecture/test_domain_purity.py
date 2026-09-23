"""PR-005 验收门禁：domain 层不得依赖 FastAPI/SQLAlchemy/厂商 SDK。"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_DIR = REPO_ROOT / "src" / "pubminer" / "domain"

FORBIDDEN_MODULES = ("fastapi", "sqlalchemy", "alembic", "pydantic_settings", "zhipuai", "openai", "anthropic", "aiohttp", "biopython", "Bio", "pubex")


class TestDomainPurity:
    def test_domain_files_have_no_forbidden_imports(self):
        offenders = []
        for path in DOMAIN_DIR.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = None
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                for module in modules:
                    root = module.split(".")[0]
                    if root in FORBIDDEN_MODULES:
                        offenders.append(f"{path.name}: import {module}")
        assert offenders == [], "domain 违规导入:\n" + "\n".join(offenders)

    def test_domain_package_imports_clean(self):
        import pubminer.domain as domain

        assert hasattr(domain, "Claim") and hasattr(domain, "Evidence")
        assert hasattr(domain, "AgentSession") and hasattr(domain, "EvidenceSpan")
