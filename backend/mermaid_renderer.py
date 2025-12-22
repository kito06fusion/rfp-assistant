from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_mmdc() -> Optional[str]:
    env_path = os.environ.get("MERMAID_CLI_PATH")
    if env_path:
        if Path(env_path).exists():
            logger.info("MERMAID_CLI_PATH set and found: %s", env_path)
            return env_path
        resolved = shutil.which(env_path)
        if resolved:
            logger.info("Resolved MERMAID_CLI_PATH via PATH: %s", resolved)
            return resolved

    bin_path = shutil.which("mmdc")
    if bin_path:
        logger.info("Found mmdc on PATH: %s", bin_path)
    else:
        logger.info("mmdc not found on PATH")
    return bin_path


def render_mermaid_to_bytes(diagram: str, fmt: str = "png", timeout: int = 30) -> bytes:
    fmt = (fmt or "png").lower()
    if fmt not in ("png", "svg"):
        raise ValueError("fmt must be 'png' or 'svg'")

    mmdc = find_mmdc()
    if not mmdc:
        raise FileNotFoundError("mmdc (Mermaid CLI) not found. Install with: npm install -g @mermaid-js/mermaid-cli")

    logger.info("Rendering mermaid diagram to %s using mmdc", fmt)
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = Path(tmpdir) / "diagram.mmd"
        out_path = Path(tmpdir) / ("diagram." + fmt)

        in_path.write_text(diagram, encoding="utf-8")

        cmd = [mmdc, "-i", str(in_path), "-o", str(out_path)]

        try:
            euid = getattr(os, "geteuid", lambda: None)()
        except Exception:
            euid = None

        force_no_sandbox = os.environ.get("MERMAID_CLI_NO_SANDBOX", "").lower() in ("1", "true", "yes")
        if force_no_sandbox or (euid is not None and euid == 0):
            logger.info("Adding --no-sandbox flags for mmdc (root or MERMAID_CLI_NO_SANDBOX)")
            cmd += ["--no-sandbox", "--disable-setuid-sandbox"]

        logger.debug("Running mmdc: %s", " ".join(cmd))


        try:
            proc = subprocess.run(cmd, capture_output=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            logger.exception("mmdc timed out: %s", e)
            raise RuntimeError(f"mmdc timed out after {timeout}s") from e

        stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        if proc.returncode != 0:
            logger.error("mmdc failed (code=%s). stdout: %s stderr: %s", proc.returncode, stdout[:200], stderr[:200])
            raise RuntimeError(f"mmdc rendering failed: {stderr or stdout}")
        else:
            logger.info("mmdc completed successfully; stdout: %s", stdout[:200])

        if not out_path.exists():
            raise RuntimeError("mmdc did not produce an output file")

        data = out_path.read_bytes()
        return data
