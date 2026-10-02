#!/usr/bin/env python3
"""Self-test for guard.py. Builds a throwaway repo + worktree in a temp dir
(so it never touches real merge state) and feeds the hook fake events.
Run: python3 .claude/hooks/test_guard.py"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")
tmp = tempfile.mkdtemp(prefix="guardtest-")
primary = os.path.join(tmp, "repo")
wt = os.path.join(tmp, "repo-feature")

def sh(*a, cwd=None):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)

sh("git", "init", "-q", "-b", "main", primary)
sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init", cwd=primary)
sh("git", "worktree", "add", "-q", wt, "-b", "feature/x", cwd=primary)

def run(mode, payload):
    r = subprocess.run([sys.executable, GUARD, mode], input=json.dumps(payload),
                       capture_output=True, text=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}

def bash(cmd, cwd=primary, sid="s1", **extra):
    o = run("pretool", dict(tool_name="Bash", tool_input={"command": cmd}, cwd=cwd, session_id=sid, **extra))
    return o.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

def edit(path, cwd=primary, content="x", **extra):
    o = run("pretool", dict(tool_name="Write", tool_input={"file_path": path, "content": content}, cwd=cwd, session_id="s1", **extra))
    return o.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

def prompt(text, sid="s1", cwd=primary, **extra):
    o = run("prompt", dict(hook_event_name="UserPromptSubmit", prompt=text, cwd=cwd, session_id=sid, **extra))
    return o.get("hookSpecificOutput", {}).get("additionalContext", "")

cases = [
    # (description, blocked?, actual)
    ("push feature branch allowed",            False, lambda: bash("git push -u origin feature/x", cwd=wt)),
    ("push origin main blocked",               True,  lambda: bash("git push origin main", cwd=wt)),
    ("push HEAD:main blocked",                 True,  lambda: bash("git push origin HEAD:main", cwd=wt)),
    ("bare push while on main blocked",        True,  lambda: bash("git push")),
    ("push --all blocked",                     True,  lambda: bash("git push --all", cwd=wt)),
    ("cd + push main blocked",                 True,  lambda: bash("cd %s && git push origin main" % wt, cwd=tmp)),
    ("git -C primary merge blocked",           True,  lambda: bash("git -C %s merge feature/x" % primary, cwd=wt)),
    ("merge on feature branch allowed",        False, lambda: bash("git merge main", cwd=wt)),
    ("commit on main blocked",                 True,  lambda: bash("git commit -am wip")),
    ("commit TASKS.md only on main allowed",   False, lambda: bash("git add TASKS.md && git commit -m 'tasks'")),
    ("commit -- TASKS.md on main allowed",     False, lambda: bash("git commit -m 'TASKS: claim x' -- TASKS.md")),
    ("commit -- other file on main blocked",   True,  lambda: bash("git commit -m 'x' -- TASKS.md backend/app/api.py")),
    ("pull --ff-only on main allowed",         False, lambda: bash("git pull --ff-only")),
    ("heredoc text not parsed as command",     False, lambda: bash("git commit -m \"$(cat <<'EOF'\nnever git push origin main\nEOF\n)\"", cwd=wt)),
    ("switch branch in primary blocked",       True,  lambda: bash("git checkout feature/x")),
    ("checkout -b in primary blocked",         True,  lambda: bash("git checkout -b feature/y")),
    ("switch branch in worktree allowed",      False, lambda: bash("git switch -c feature/z", cwd=wt)),
    ("open http URL blocked",                  True,  lambda: bash("open http://localhost:8080")),
    ("open -a Chrome blocked",                 True,  lambda: bash("open -a 'Google Chrome' index.html")),
    ("open html file blocked",                 True,  lambda: bash("open frontend/index.html")),
    ("headed playwright blocked",              True,  lambda: bash("npx playwright test --headed")),
    ("python webbrowser blocked",              True,  lambda: bash("python3 -m webbrowser http://x")),
    ("curl localhost allowed",                 False, lambda: bash("curl -s http://localhost:5000/health")),
    ("open a folder allowed",                  False, lambda: bash("open .")),
    ("hand-writing approval file blocked",     True,  lambda: bash("touch .git/agent-os/approvals/s1.json")),
    ("edit app file in primary blocked",       True,  lambda: edit(os.path.join(primary, "backend/app/api.py"))),
    ("edit TASKS.md in primary allowed",       False, lambda: edit(os.path.join(primary, "TASKS.md"))),
    ("edit drafts/ in primary allowed",        False, lambda: edit(os.path.join(primary, "drafts/prompts/x.md"))),
    ("edit file in worktree allowed",          False, lambda: edit(os.path.join(wt, "backend/app/api.py"), cwd=wt)),
    ("write headless=False blocked",           True,  lambda: edit(os.path.join(wt, "shot.py"), cwd=wt, content="launch(headless=False)")),
    ("ui-checker writing in repo blocked",     True,  lambda: edit(os.path.join(wt, "x.py"), cwd=wt, agent_id="a1", agent_type="ui-checker")),
    ("ui-checker writing to /tmp allowed",     False, lambda: edit("/tmp/guardtest-shot.mjs", cwd=wt, agent_id="a1", agent_type="ui-checker")),
    ("placeholder flagged",                    True,  lambda: "PLACEHOLDER" in prompt("email (the real email) about the demo")),
    ("normal prompt not flagged",              False, lambda: bool(prompt("fix the rent roll import bug"))),
    ("'merge' alone does not approve",         True,  lambda: bash("git merge feature/x") if not prompt("should we merge this later?") or True else None),
    # approval flow
    ("/merge-branch records approval",         True,  lambda: "merge approval" in prompt("/merge-branch feature/x")),
    ("approved session may merge",             False, lambda: bash("git merge feature/x")),
    ("approved session may push main",         False, lambda: bash("git push origin main")),
    ("other session blocked by lock",          True,  lambda: (prompt("/merge-branch feature/x", sid="s2"), bash("git merge feature/x", sid="s2"))[1]),
    ("subagent blocked even when approved",    True,  lambda: bash("git push origin main", agent_id="a9", agent_type="general-purpose")),
]

fails = 0
for desc, expect, fn in cases:
    got = bool(fn())
    ok = got == expect
    fails += not ok
    print("%s  %s" % ("ok  " if ok else "FAIL", desc))

r = subprocess.run([sys.executable, GUARD, "merge-lock", "release", "s1"], cwd=primary, capture_output=True, text=True)
print("ok  " if "released" in r.stdout else "FAIL", " lock release:", r.stdout.strip())
fails += "released" not in r.stdout
o = run("session-start", dict(cwd=primary, session_id="s3", source="clear", hook_event_name="SessionStart"))
ctx = o.get("hookSpecificOutput", {}).get("additionalContext", "")
ok = "PRIMARY CHECKOUT" in ctx and "resume-task" in ctx
print("ok  " if ok else "FAIL", " session-start context")
fails += not ok
print("\n%d failure(s)" % fails)
sys.exit(1 if fails else 0)
