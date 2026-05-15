import datetime
import json
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import notion_api as notion
from config import (
    DIGEST_EMAIL_FROM,
    DIGEST_EMAIL_TO,
    DIGEST_SMTP_HOST,
    DIGEST_SMTP_PASSWORD,
    DIGEST_SMTP_PORT,
    DIGEST_SMTP_USER,
)

_LAST_RUN_FILE = Path("/tmp/job_sweep_last_run.json")

_PIPELINE_STAGES = ["Qualification", "Prioritized", "Create Resume", "Contacted / Applied"]


def build_digest(sweep_stats: dict) -> str:
    today = datetime.date.today()
    new_roles = sweep_stats.get("new_roles", [])
    discovery_roles = sweep_stats.get("discovery_new_roles", [])
    closed_roles = sweep_stats.get("closed_roles", [])
    errors = sweep_stats.get("errors", [])

    lines: list[str] = []
    lines.append(f"Job Sweep Digest — {today.isoformat()}")
    lines.append("=" * 42)
    lines.append("")

    # 1. New roles
    lines.append(f"NEW ROLES ADDED ({len(new_roles)})")
    lines.append("-" * 30)
    if new_roles:
        for r in new_roles:
            lines.append(f"  {r}")
    else:
        lines.append("  No new roles found in this period.")
    lines.append("")

    # 2. Discovery finds (omit when empty)
    if discovery_roles:
        lines.append(f"DISCOVERY FINDS ({len(discovery_roles)})")
        lines.append("-" * 30)
        for r in discovery_roles:
            lines.append(f"  {r}")
        lines.append("")

    # 3. Auto-closed roles (omit when empty)
    if closed_roles:
        lines.append(f"AUTO-CLOSED ROLES ({len(closed_roles)})")
        lines.append("-" * 30)
        for r in closed_roles:
            lines.append(f"  {r}")
        lines.append("")

    # 4. Pipeline snapshot
    snapshot = notion.fetch_pipeline_snapshot()
    lines.append("PIPELINE SNAPSHOT")
    lines.append("-" * 30)
    total = 0
    for stage in _PIPELINE_STAGES:
        count = snapshot.get(stage, 0)
        total += count
        lines.append(f"  {stage:<30} {count}")
    lines.append(f"  {'─' * 32}")
    lines.append(f"  {'Total active':<30} {total}")
    lines.append("")

    # 5. Errors (omit when empty)
    if errors:
        lines.append(f"ERRORS ({len(errors)})")
        lines.append("-" * 30)
        for e in errors:
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                lines.append(f"  {e[0]}: {e[1]}")
            else:
                lines.append(f"  {e}")
        lines.append("")

    # 6. Footer
    lines.append("─" * 42)
    lines.append(f"Next sweep: {today.isoformat()} 10pm ET")

    return "\n".join(lines)


def build_subject(sweep_stats: dict) -> str:
    today = datetime.date.today()
    n = len(sweep_stats.get("new_roles", [])) + len(sweep_stats.get("discovery_new_roles", []))
    return f"Job Sweep Digest — {today.isoformat()} ({n} new roles)"


def send_digest(subject: str, body: str) -> None:
    if not DIGEST_SMTP_HOST:
        print("Digest skipped (not configured)")
        return

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = DIGEST_EMAIL_FROM
    msg["To"] = DIGEST_EMAIL_TO

    with smtplib.SMTP(DIGEST_SMTP_HOST, DIGEST_SMTP_PORT) as server:
        server.starttls()
        server.login(DIGEST_SMTP_USER, DIGEST_SMTP_PASSWORD)
        server.sendmail(DIGEST_EMAIL_FROM, [DIGEST_EMAIL_TO], msg.as_string())

    print("Digest sent")


def merge_stats(current: dict, previous: dict) -> dict:
    return {
        "new_roles": previous.get("new_roles", []) + current.get("new_roles", []),
        "discovery_new_roles": previous.get("discovery_new_roles", []) + current.get("discovery_new_roles", []),
        "closed_roles": previous.get("closed_roles", []) + current.get("closed_roles", []),
        "errors": previous.get("errors", []) + current.get("errors", []),
        "geo_filtered": previous.get("geo_filtered", 0) + current.get("geo_filtered", 0),
        "red_flagged": previous.get("red_flagged", 0) + current.get("red_flagged", 0),
    }


def write_last_run(stats: dict) -> None:
    _LAST_RUN_FILE.write_text(json.dumps(stats))


def read_and_clear_last_run() -> dict | None:
    if not _LAST_RUN_FILE.exists():
        return None
    try:
        data = json.loads(_LAST_RUN_FILE.read_text())
        return data
    except Exception:
        return None
    finally:
        try:
            _LAST_RUN_FILE.unlink(missing_ok=True)
        except Exception:
            pass
