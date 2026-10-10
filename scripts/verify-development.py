"""Verify reloads in disposable containers using the already-built dev image."""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def until(check, description):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError, subprocess.CalledProcessError):
            pass
        time.sleep(0.3)
    raise AssertionError(description)


with tempfile.TemporaryDirectory(prefix="triage-dev-smoke-") as temporary:
    directory = Path(temporary)
    shutil.copytree(ROOT / "backend/src", directory / "src")
    config = directory / "compose.json"
    environment = {
        "DATABASE_URL": "postgresql://postgres:smoke-only@postgres:5432/smoke",
        "WATCHFILES_FORCE_POLLING": "true",
    }
    python = {
        "image": "triage-processor-backend-dev:local",
        "init": True,
        "environment": environment,
        "volumes": [f"{directory / 'src'}:/app/src:ro"],
        "depends_on": {"postgres": {"condition": "service_healthy"}},
    }
    config.write_text(json.dumps({"name": "triage-dev-smoke", "services": {
        "postgres": {
            "image": "pgvector/pgvector:pg17",
            "environment": {"POSTGRES_DB": "smoke", "POSTGRES_USER": "postgres", "POSTGRES_PASSWORD": "smoke-only"},
            "tmpfs": ["/var/lib/postgresql/data"],
            "volumes": [f"{ROOT / 'infrastructure/postgres/init.sql'}:/docker-entrypoint-initdb.d/init.sql:ro",
                        f"{ROOT / 'infrastructure/postgres/migrations'}:/docker-entrypoint-initdb.d/migrations:ro"],
            "healthcheck": {"test": ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U postgres -d smoke"], "interval": "1s", "timeout": "3s", "retries": 30},
        },
        "api": {**python, "command": ["uvicorn", "triage_processor.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src"], "ports": ["127.0.0.1::8000"]},
        "worker": {**python, "command": ["python", "-m", "watchfiles", "--filter", "python", "--sigint-timeout", "120", "--sigkill-timeout", "5", "python -m triage_processor.workers.embeddings", "/app/src"], "stop_grace_period": "130s"},
        "missing-credentials": {"image": python["image"], "profiles": ["negative"], "command": ["sh", "-c", "test -f /run/secrets/google-sheets.json && test -r /run/secrets/google-sheets.json"],
            "volumes": [{"type": "bind", "source": str(directory / "absent.json"), "target": "/run/secrets/google-sheets.json", "read_only": True, "bind": {"create_host_path": False}}]},
    }}))

    def compose(*arguments, check=True):
        return subprocess.run(["docker", "compose", "-f", str(config), *arguments], check=check, capture_output=True, text=True)

    def worker_pid():
        code = "from pathlib import Path; import json; print(json.dumps([p.name for p in Path('/proc').iterdir() if p.name.isdigit() and (p/'cmdline').exists() and b'triage_processor.workers.embeddings' in (p/'cmdline').read_bytes().split(bytes([0]))]))"
        pids = json.loads(compose("exec", "-T", "worker", "python", "-c", code).stdout)
        return pids[0] if len(pids) == 1 else None

    def images():
        return compose("images", "-q", "api", "worker").stdout

    try:
        compose("up", "-d", "api", "worker")
        address = compose("port", "api", "8000").stdout.strip()

        def status():
            with urllib.request.urlopen(f"http://{address}/healthz", timeout=2) as response:
                return json.load(response)["status"]

        until(lambda: status() == "ok", "API did not start")
        old_pid = until(worker_pid, "worker child did not start")
        original_images = images()
        main = directory / "src/triage_processor/api/main.py"
        text = main.read_text()
        assert 'return {"status": "ok"}' in text
        main.write_text(text.replace('return {"status": "ok"}', 'return {"status": "dev-reloaded"}'))
        until(lambda: status() == "dev-reloaded", "API did not reflect Python edit")
        until(lambda: worker_pid() not in (None, old_pid), "worker did not restart after Python edit")
        assert images() == original_images, "source edit changed image identity"
        compose("stop", "-t", "15", "worker", "api")
        assert not compose("ps", "--status", "running", "-q", "worker", "api").stdout.strip()
        missing = compose("run", "--rm", "--no-deps", "missing-credentials", check=False)
        assert missing.returncode != 0, "missing credential file was accepted"
        print("PASS: API source reload, single worker child restart, unchanged images, clean stop, missing credentials rejected.")
    except Exception:
        # Only disposable logs; this fixture contains no user data or credentials.
        print(compose("logs", "--tail", "30", check=False).stdout)
        raise
    finally:
        compose("--profile", "negative", "down", check=False)
