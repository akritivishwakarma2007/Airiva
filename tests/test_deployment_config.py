"""
tests/test_deployment_config.py — Tests verifying deployment preparation:
- Dockerfile structure and non-root execution
- .dockerignore exclusions
- /health endpoint
- requirements.txt vs requirements-dev.txt pinning and package separation
- Settings loading from environment variables and refusal to start when required vars are missing.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apix.api.main import app


class TestHealthEndpoint:
    def test_health_check_returns_ok(self):
        client = TestClient(app)
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_v1_health_check_returns_ok(self):
        client = TestClient(app)
        res = client.get("/v1/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


class TestDockerfileAndDockerignore:
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def test_dockerfile_contents(self):
        dockerfile = self.repo_root / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile must exist"
        content = dockerfile.read_text(encoding="utf-8")

        # 1. Base image: python:3.12-slim
        assert "FROM python:3.12-slim" in content

        # 2. Non-root user
        assert "useradd" in content
        assert "USER appuser" in content

        # 3. Expose $PORT
        assert "EXPOSE $PORT" in content

        # 4. Start command
        assert "uvicorn apix.api.main:app --host 0.0.0.0 --port $PORT" in content

        # 5. No playwright install
        assert "playwright install" not in content

    def test_dockerignore_exclusions(self):
        dockerignore = self.repo_root / ".dockerignore"
        assert dockerignore.exists(), ".dockerignore must exist"
        content = dockerignore.read_text(encoding="utf-8")

        lines = [line.strip().rstrip("/") for line in content.splitlines() if line.strip() and not line.startswith("#")]

        # Required exclusions
        required_excludes = [".env", ".git", "data/raw", "htmlcov", "apix.db", "tests"]
        for exc in required_excludes:
            assert any(exc in line for line in lines), f"Expected '{exc}' in .dockerignore"


class TestRequirementsPinning:
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def test_requirements_pinned_and_no_dev_packages(self):
        req_file = self.repo_root / "requirements.txt"
        assert req_file.exists()
        lines = [line.strip() for line in req_file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]

        for line in lines:
            assert "==" in line, f"Requirement '{line}' must be pinned with '=='"

        # Production requirements must not contain testing / dev tools
        content = req_file.read_text(encoding="utf-8").lower()
        assert "pytest" not in content
        assert "pytest-cov" not in content
        assert "coverage" not in content
        assert "playwright" not in content

    def test_requirements_dev_contains_dev_packages(self):
        dev_file = self.repo_root / "requirements-dev.txt"
        assert dev_file.exists()
        content = dev_file.read_text(encoding="utf-8").lower()

        assert "-r requirements.txt" in content
        assert "pytest==" in content
        assert "coverage==" in content
        assert "playwright==" in content


class TestEnvironmentVariableSettings:
    def test_app_refuses_to_start_when_required_env_vars_missing(self):
        """Confirm app fails at startup with clear message when required env vars are missing."""
        repo_root = Path(__file__).resolve().parent.parent
        base_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(repo_root),
        }

        # Run in temporary directory where no .env file exists
        with tempfile.TemporaryDirectory() as tmpdir:
            res = subprocess.run(
                ["python", "-c", "from apix.config import settings"],
                cwd=tmpdir,
                env=base_env,
                capture_output=True,
                text=True,
            )

            assert res.returncode != 0, "App must refuse to start without required environment variables"
            assert "FastAPI Startup Failed" in res.stderr
            assert "SUPABASE_URL" in res.stderr
            assert "SUPABASE_SERVICE_ROLE_KEY" in res.stderr
            assert "ALLOWED_ORIGINS" in res.stderr
            assert "APP_ENV" in res.stderr

    def test_app_starts_when_all_required_env_vars_provided(self):
        """Confirm app starts cleanly when all required environment variables are set."""
        repo_root = Path(__file__).resolve().parent.parent
        test_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(repo_root),
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test_secret_key",
            "ALLOWED_ORIGINS": "http://localhost:3000,http://localhost:8000",
            "APP_ENV": "test",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            res = subprocess.run(
                ["python", "-c", "from apix.config import settings; print('CONFIG_OK', settings.app_env)"],
                cwd=tmpdir,
                env=test_env,
                capture_output=True,
                text=True,
            )

            assert res.returncode == 0, f"Failed with: {res.stderr}"
            assert "CONFIG_OK test" in res.stdout
