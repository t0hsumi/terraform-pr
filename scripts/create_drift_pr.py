#!/usr/bin/env python3
"""
Terraform drift PR creator.

Reads terraform plan output, calls Claude to analyze the drift and suggest
.tf file updates, then creates or updates a GitHub PR with the changes.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).parent.parent
TF_FILES = [
    "main/main.tf",
    "main/variables.tf",
    "main/outputs.tf",
    "main/providers.tf",
]
TF_DIR = "main"


def read_file(path: str) -> str | None:
    p = REPO_ROOT / path
    return p.read_text() if p.exists() else None


def write_file(path: str, content: str) -> None:
    (REPO_ROOT / path).write_text(content)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, cwd=REPO_ROOT, **kwargs)


def build_pr_body(summary: str, changed_files: list[str], plan_output: str, detected_at: str) -> str:
    files_list = "\n".join(f"- `{f}`" for f in changed_files)
    # Use ~~~ fence so backticks inside plan output don't break the markdown block
    return f"""\
## ドリフト概要

{summary}

## 変更ファイル

{files_list}

## 検出日時

{detected_at} (JST)

<details>
<summary>Terraform Plan Output</summary>

~~~
{plan_output}
~~~

</details>"""


JST = timezone(timedelta(hours=9))


def find_open_drift_pr() -> dict | None:
    result = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--limit", "100",
         "--json", "number,headRefName,title"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        return None
    prs = json.loads(result.stdout or "[]")
    return next((pr for pr in prs if pr["headRefName"].startswith("drift/")), None)


def main() -> None:
    plan_path = REPO_ROOT / "plan.txt"
    if not plan_path.exists():
        print("plan.txt not found", file=sys.stderr)
        sys.exit(1)

    plan_output = plan_path.read_text()

    tf_contents = {f: read_file(f) for f in TF_FILES if read_file(f) is not None}
    tf_files_text = "\n\n".join(
        f"=== {name} ===\n{content}" for name, content in tf_contents.items()
    )

    client = anthropic.Anthropic()

    prompt = f"""You are analyzing a Terraform drift detection report for an AWS environment.

Current .tf files:
{tf_files_text}

Terraform plan output (changes terraform wants to make to align infrastructure with .tf files):
{plan_output}

This drift likely means someone changed resources in the AWS Console.
Your job is to update the .tf files so they reflect the ACTUAL current AWS state (i.e., incorporate the console changes).

Instructions:
- If terraform plans to "destroy" a resource attribute or set it to an old value, the actual AWS value is what terraform CURRENTLY shows as "was".
- Update .tf files to match the actual AWS state so that terraform plan would show no changes after your edits.
- Keep formatting clean and idiomatic HCL.
- Only modify files that need changes.

Respond with ONLY a JSON object (no markdown fences) in this exact format:
{{
  "pr_title": "terraform: sync drift from AWS Console changes",
  "summary": "- bullet points describing what drifted (Japanese OK)",
  "file_changes": {{
    "main/main.tf": "full updated file content or null if unchanged",
    "main/variables.tf": "full updated file content or null if unchanged",
    "main/outputs.tf": "full updated file content or null if unchanged",
    "main/providers.tf": "full updated file content or null if unchanged"
  }}
}}"""

    print("Calling Claude API to analyze drift...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Failed to parse Claude response as JSON: {e}", file=sys.stderr)
        print("Raw response:", raw, file=sys.stderr)
        sys.exit(1)

    allowed_paths = set(TF_FILES)
    changed_files = {
        path: content
        for path, content in result.get("file_changes", {}).items()
        if content is not None and path in allowed_paths
    }

    if not changed_files:
        print("Claude detected no .tf changes needed. Skipping PR creation.")
        return

    run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])
    run(["git", "config", "user.name", "github-actions[bot]"])

    existing_pr = find_open_drift_pr()
    if existing_pr:
        print(f"Found existing drift PR #{existing_pr['number']} — updating branch {existing_pr['headRefName']}")
        run(["git", "fetch", "origin", existing_pr["headRefName"]])
        run(["git", "checkout", existing_pr["headRefName"]])
    else:
        timestamp = datetime.now(JST).strftime("%Y%m%d-%H%M%S")
        branch_name = f"drift/{timestamp}"
        run(["git", "checkout", "-b", branch_name])

    for filepath, content in changed_files.items():
        write_file(filepath, content)

    # fmt rewrites files in-place; run before staging so the formatted version is committed
    run(["terraform", "fmt"], cwd=REPO_ROOT / TF_DIR)

    validate = subprocess.run(
        ["terraform", "validate"],
        cwd=REPO_ROOT / TF_DIR,
        capture_output=True, text=True,
    )
    if validate.returncode != 0:
        print("terraform validate failed — aborting", file=sys.stderr)
        print(validate.stdout, file=sys.stderr)
        print(validate.stderr, file=sys.stderr)
        sys.exit(1)

    for filepath in changed_files:
        run(["git", "add", filepath])

    # Only commit if there are staged changes (fmt may have produced no diff)
    has_changes = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=REPO_ROOT,
    ).returncode != 0

    if not has_changes and not existing_pr:
        print("No file changes after fmt and no existing PR to update — skipping.")
        return

    if has_changes:
        run(["git", "commit", "-m", result["pr_title"]])

    detected_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    pr_body = build_pr_body(
        summary=result["summary"],
        changed_files=list(changed_files.keys()),
        plan_output=plan_output,
        detected_at=detected_at,
    )

    if existing_pr:
        run(["git", "push", "origin", existing_pr["headRefName"]])
        run([
            "gh", "pr", "edit", str(existing_pr["number"]),
            "--title", result["pr_title"],
            "--body", pr_body,
        ])
        print(f"PR #{existing_pr['number']} updated")
    else:
        branch_name = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT, check=True,
        ).stdout.strip()
        run(["git", "push", "origin", branch_name])
        run([
            "gh", "pr", "create",
            "--title", result["pr_title"],
            "--body", pr_body,
            "--base", "main",
            "--head", branch_name,
        ])
        print(f"PR created from branch {branch_name}")


if __name__ == "__main__":
    main()
