import sys
import subprocess
import argparse


VALID_TYPES = [
    "feat", "fix", "docs", "style", "refactor",
    "perf", "test", "chore", "build", "ci", "revert"
]


def main():
    parser = argparse.ArgumentParser(
        description="Commit using Conventional Commits rules."
    )
    parser.add_argument("type", choices=VALID_TYPES, help="Commit type")
    parser.add_argument("scope", help="Scope (e.g. core, frontend, dbt)")
    parser.add_argument("description", help="Short description (max 50 chars)")
    parser.add_argument("--body", help="Extended description body", default="")
    parser.add_argument("files", nargs="+", help="Files to stage and commit")

    args = parser.parse_args()

    # Rule: description max 50 chars
    if len(args.description) > 50:
        print(
            f"❌ ERROR: Description is {len(args.description)} chars. "
            f"Max is 50.\n   '{args.description}'"
        )
        sys.exit(1)

    header = f"{args.type}({args.scope}): {args.description}"

    # Stage files
    print(f"📦 Staging: {args.files}")
    try:
        subprocess.check_call(["git", "add"] + args.files)
    except subprocess.CalledProcessError:
        print("❌ git add failed.")
        sys.exit(1)

    # Commit
    print(f"📝 Committing: {header}")
    commit_cmd = ["git", "commit", "-m", header]
    if args.body:
        commit_cmd += ["-m", args.body]
    try:
        subprocess.check_call(commit_cmd)
        print("✅ Done!")
    except subprocess.CalledProcessError as e:
        print(f"❌ git commit failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
