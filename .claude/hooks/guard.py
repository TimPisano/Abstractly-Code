#!/usr/bin/env python3
"""Abstractly agent-safety hooks. One script, several entry points:

    guard.py pretool        PreToolUse   (Bash, Edit, Write, NotebookEdit)
    guard.py prompt         UserPromptSubmit / UserPromptExpansion
    guard.py session-start  SessionStart
    guard.py merge-lock status | release <session-id> [--force]   (merge-branch skill)

Each check exists because of a real failure this project had; see
docs/HOW_TO_RUN_AGENTS.md ("The safety hooks") for the plain-English version.

Design rules for this file:
- Fast: stdlib only, a handful of `git` calls at most, no network.
- Fail open: if the hook itself crashes, it exits 0 so a bug in the guard
  never bricks a session. The things it protects (pushing main, merging)
  are also covered by CLAUDE.md rules, so failing open is a soft landing.
- Block with a reason the agent can act on, never a bare "no".

Approval model. A hook can't know what the user *meant*, but it can see what
the user *typed*. When the user types `/merge-branch ...` or the words
"approve merge", the prompt hook writes an approval file for that session
(2-hour TTL). Commands that change `main` (merge/commit/push to main...) are
denied unless the session holds an approval AND the single repo-wide merge
lock, so two sessions can never merge at once. Subagents never get approval.
State lives in <git-common-dir>/agent-os/, shared by every worktree.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time

APPROVAL_TTL = 2 * 60 * 60   # seconds a "merge" approval stays valid
LOCK_TTL = 2 * 60 * 60       # a lock older than this is treated as abandoned
MAIN = "main"

# Files an agent may still edit directly in the primary checkout (which must
# stay on main). TASKS.md is the shared task board; drafts/ is local-only
# output (outreach drafts, prompt-builder prompts) and is gitignored.
PRIMARY_EDIT_ALLOW = re.compile(r"^(TASKS\.md|drafts/.*|\.claude/settings\.local\.json)$")

# Agents that must never change files inside a repo.
READ_ONLY_AGENTS = {"reviewer", "security-auditor", "ui-checker"}


# ---------------------------------------------------------------- helpers

def out(obj):
    sys.stdout.write(json.dumps(obj))
    sys.exit(0)


def deny(reason):
    out({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "[agent-os guard] " + reason,
    }})


def context(event, text):
    out({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def git(cwd, *args):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def existing_dir(path):
    path = os.path.realpath(path)
    while path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def repo_info(cwd):
    """(toplevel, primary_root, common_dir, branch) for the repo at cwd."""
    cwd = existing_dir(cwd)
    top = git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return None
    common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    primary = os.path.dirname(common) if common.endswith("/.git") else ""
    branch = git(cwd, "branch", "--show-current")
    return top, primary, common, branch


def state_dir(common):
    d = os.path.join(common, "agent-os")
    os.makedirs(os.path.join(d, "approvals"), exist_ok=True)
    return d


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path, data):
    tmp = path + ".tmp%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def approval_for(common, session_id):
    a = read_json(os.path.join(state_dir(common), "approvals", session_id + ".json"))
    if a and time.time() - a.get("at", 0) < APPROVAL_TTL:
        return a
    return None


def lock_holder(common):
    lock = read_json(os.path.join(state_dir(common), "merge.lock"))
    if lock and time.time() - lock.get("at", 0) < LOCK_TTL:
        return lock
    return None


# ------------------------------------------------------- shell parsing

def segments(command):
    """Split a shell command into simple-command word lists. Good enough for
    the git/open invocations we care about; not a full shell parser."""
    # Drop heredoc bodies (commit messages etc.) so their text is not
    # mistaken for commands.
    cmd = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n.*?\n\s*\1\b", " ", command, flags=re.S)
    cmd = re.sub(r"\\\n", " ", cmd)
    parts = re.split(r"&&|\|\||;|\||\n|\$\(|`|\(|\)", cmd)
    result = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        try:
            words = shlex.split(p)
        except ValueError:
            words = p.split()
        # drop leading VAR=value assignments
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        if words:
            result.append(words)
    return result


GIT_GLOBAL_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def parse_git(words, cwd):
    """For a `git ...` word list return (dir, subcommand, args) or None."""
    if not words or os.path.basename(words[0]) != "git":
        return None
    i, d = 1, cwd
    while i < len(words) and words[i].startswith("-"):
        if words[i] == "-C" and i + 1 < len(words):
            d = os.path.join(d, os.path.expanduser(words[i + 1]))
            i += 2
        elif words[i] in GIT_GLOBAL_WITH_ARG:
            i += 2
        else:
            i += 1
    if i >= len(words):
        return None
    return d, words[i], words[i + 1:]


def positional(args):
    return [a for a in args if not a.startswith("-")]


def push_targets_main(args, branch):
    if "--all" in args or "--mirror" in args:
        return True
    if "--delete" in args or "-d" in args:
        return any(a.split("/")[-1] == MAIN for a in positional(args)[1:])
    pos = positional(args)
    refspecs = pos[1:]
    if not refspecs:
        return branch == MAIN           # bare `git push` / `git push origin`
    for spec in refspecs:
        dst = spec.lstrip("+").split(":")[-1]
        if dst in (MAIN, "refs/heads/" + MAIN):
            return True
        if dst == "HEAD" and branch == MAIN:
            return True
    return False


MAIN_MUTATING = {"merge", "commit", "cherry-pick", "rebase", "revert", "reset",
                 "am", "pull"}


def touches_main_ref(sub, args):
    names_main = any(a in (MAIN, "refs/heads/" + MAIN) for a in args)
    if sub == "update-ref":
        return names_main
    if sub == "branch":
        return names_main and any(a in args for a in ("-f", "--force", "-D", "-d", "-M", "-m"))
    return False


# --------------------------------------------------------- browser rules

BROWSER_PATTERNS = [
    (r"(^|[\s;&|(])(open|xdg-open)\s+(-[a-zA-Z]+\s+)*['\"]?(https?://|localhost|127\.0\.0\.1|file://|[^\s'\"]+\.html?\b)",
     "`open` on a URL or HTML file launches the user's browser"),
    (r"(^|[\s;&|(])open\s+(-[a-zA-Z]*\s+)*-a\s+['\"]?(Google Chrome|Chrome|Safari|Firefox|Arc|Brave|Microsoft Edge|Chromium)",
     "`open -a <browser>` launches the user's browser"),
    (r"python3?\s+-m\s+webbrowser|webbrowser\.open", "the webbrowser module opens the user's browser"),
    (r"osascript.*(Chrome|Safari|Firefox|Arc)", "AppleScript-driving a browser"),
    (r"chrome-devtools-mcp", "chrome-devtools-mcp launches a visible, automated Chrome"),
    (r"--headed\b|headless\s*[=:]\s*(False|false|0)\b", "headed (visible) Playwright/Puppeteer browser"),
    (r"playwright\s+(open|codegen|show-report|show-trace)\b", "this Playwright subcommand opens a visible browser"),
    (r"/Applications/(Google Chrome|Safari|Firefox|Chromium)", "launching a browser binary directly"),
]
HEADED_IN_FILE = re.compile(r"headless\s*[=:]\s*(False|false)\b|['\"]--headed['\"]")

BROWSER_FIX = (" Rule 1 in CLAUDE.md: never open the user's browser. For a visual "
               "check run headless Playwright: `node .claude/tools/screenshots.mjs <url>` "
               "(or the ui-checker subagent), then Read the PNGs. To show the user a page, "
               "start the server in the background and give them the URL.")


# ---------------------------------------------------------------- pretool

def pretool(data):
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    session = data.get("session_id") or "unknown"
    agent_type = data.get("agent_type") or ""
    is_subagent = bool(data.get("agent_id"))

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if not path:
            return
        path = os.path.realpath(os.path.join(cwd, os.path.expanduser(path)))
        body = (ti.get("content") or "") + (ti.get("new_string") or "")
        if HEADED_IN_FILE.search(body) and not path.endswith("guard.py"):
            deny("This edit configures a visible (headed) browser." + BROWSER_FIX)
        info = repo_info(os.path.dirname(path))
        if not info:
            return
        top, primary, _common, _branch = info
        if is_subagent and agent_type in READ_ONLY_AGENTS:
            deny("The %s subagent is read-only inside the repo. Write scratch "
                 "files (screenshots, scripts) to the session scratchpad or /tmp "
                 "instead, and report findings rather than fixing them." % agent_type)
        if primary and top == primary:
            rel = os.path.relpath(path, primary)
            if not PRIMARY_EDIT_ALLOW.match(rel):
                deny("%s is in the shared primary checkout (%s), which other "
                     "sessions use and which must stay on main. Do the work in "
                     "this task's own worktree under ~/dev/projects/ (start-task "
                     "skill creates one). Only TASKS.md and drafts/ may be edited "
                     "here." % (rel, primary))
        return

    if tool != "Bash":
        return
    command = ti.get("command") or ""

    for pattern, why in BROWSER_PATTERNS:
        if re.search(pattern, command):
            deny("Blocked: %s." % why + BROWSER_FIX)

    # Nobody hand-edits the approval/lock files; only the hooks do.
    if re.search(r"agent-os/(approvals|merge\.lock)", command) and "guard.py" not in command:
        deny("Merge approvals and the merge lock are written only by the hooks "
             "when the user types /merge-branch. Don't create or delete them by hand.")

    cur = cwd
    staged_hint = []
    for words in segments(command):
        if words[0] == "cd" and len(words) > 1:
            cur = os.path.join(cur, os.path.expanduser(words[1]))
            continue
        g = parse_git(words, cur)
        if not g:
            continue
        d, sub, args = g
        info = repo_info(d)
        if not info:
            continue
        top, primary, common, branch = info

        if sub == "add":
            staged_hint += positional(args) or ["."]
            if "-A" in args or "--all" in args:
                staged_hint.append(".")

        # Rule: the primary checkout stays on main. Switching it moves the
        # ground under every other session that is reading from it.
        if primary and top == primary and sub in ("checkout", "switch"):
            pos = positional(args)
            creating = any(a in args for a in ("-b", "-B", "-c", "-C", "--orphan", "--detach"))
            if "--" not in args and (creating or (pos and pos[0] != MAIN and
                                                  (sub == "switch" or git(d, "rev-parse", "--verify", "--quiet", pos[0] + "^{commit}")))):
                deny("Don't switch branches in the primary checkout (%s); other "
                     "sessions depend on it staying on main. Create a worktree "
                     "instead: git worktree add ~/dev/projects/abstractly-<topic> "
                     "-b <type>/<topic> main" % primary)

        gated = False
        what = ""
        if sub == "push" and push_targets_main(args, branch):
            gated, what = True, "push to main"
        elif touches_main_ref(sub, args):
            gated, what = True, "rewrite the main branch ref"
        elif branch == MAIN and sub in MAIN_MUTATING:
            if sub == "pull" and "--ff-only" in args:
                continue
            if sub == "commit" and not any(a in args for a in ("-a", "--all", "--amend")):
                if "--" in args:   # `git commit -m msg -- TASKS.md` commits only those paths
                    staged = args[args.index("--") + 1:]
                else:
                    staged = git(d, "diff", "--cached", "--name-only").splitlines() + staged_hint
                if staged and all(s in ("TASKS.md", "./TASKS.md") for s in staged):
                    continue  # task-board bookkeeping is allowed on main
            gated, what = True, "`git %s` on main" % sub
        if not gated:
            continue

        if is_subagent:
            deny("Subagents may never %s. Report back to the main session; only "
                 "the user-approved merger session changes main." % what)
        appr = approval_for(common, session)
        if not appr:
            deny("Blocked: %s. Changing main needs the user's explicit approval "
                 "in THIS session: the user must type `/merge-branch <branch>` (or "
                 "the words \"approve merge\"). Don't ask them to approve "
                 "something they haven't reviewed; if this wasn't a merge task, "
                 "you're in the wrong checkout or branch." % what)
        holder = lock_holder(common)
        if holder and holder.get("session") != session:
            deny("Blocked: another session (%s, since %s) holds the merge lock. "
                 "Only one session merges at a time. Wait for it to finish, or "
                 "ask the user; if it is truly dead the lock expires after 2h or "
                 "the user can run: python3 .claude/hooks/guard.py merge-lock release --force"
                 % (holder.get("session", "?")[:8], time.strftime("%H:%M", time.localtime(holder.get("at", 0)))))
        write_json(os.path.join(state_dir(common), "merge.lock"),
                   {"session": session, "at": time.time(), "branch": appr.get("branch", ""),
                    "cwd": cwd})


# ----------------------------------------------------------------- prompt

PLACEHOLDER_PATTERNS = [
    r"\((?:the |your |insert |real |actual |put |add )[^()\n]{1,40}\)",
    r"\[(?:insert|your|the real|real|actual|placeholder|tbd|todo)[^\]\n]{0,40}\]",
    r"<(?:your|insert|the real|real|actual|placeholder)[^<>\n]{0,40}>",
    r"\{\{[^{}\n]{1,40}\}\}",
    r"\b(?:TBD|XXX+|FIXME|lorem ipsum)\b",
    r"\b[\w.]*@example\.(?:com|org)\b",
]
APPROVE_RE = re.compile(r"^\s*/merge-branch\b|\bapprove(?:d)? merge\b|\bmerge approved\b", re.I)


def prompt(data):
    event = data.get("hook_event_name") or "UserPromptSubmit"
    text = data.get("prompt") or data.get("prompt_text") or ""
    cmd_name = (data.get("command_name") or "").lstrip("/")
    if cmd_name:
        args = data.get("arguments") or []
        args = " ".join(args) if isinstance(args, list) else str(args)
        text = ("/%s %s\n%s" % (cmd_name, args, text)).strip()
    notes = []

    if (cmd_name == "merge-branch" or APPROVE_RE.search(text)) and not data.get("agent_id"):
        info = repo_info(data.get("cwd") or os.getcwd())
        if info:
            m = re.search(r"/merge-branch\s+(\S+)", text)
            write_json(os.path.join(state_dir(info[2]), "approvals",
                                    (data.get("session_id") or "unknown") + ".json"),
                       {"at": time.time(), "branch": m.group(1) if m else "",
                        "prompt": text[:200]})
            notes.append("[agent-os] The user typed a merge approval in this session, so "
                         "the hooks will allow changes to main for the next 2 hours, "
                         "for the branch the user named only. Use the merge-branch skill. "
                         "If another session holds the merge lock you will be blocked; "
                         "say so and wait.")

    hits = []
    for p in PLACEHOLDER_PATTERNS:
        hits += [m.group(0) for m in re.finditer(p, text, re.I)]
    if hits:
        uniq = list(dict.fromkeys(hits))[:6]
        notes.append("[agent-os] This prompt contains what looks like PLACEHOLDER text: %s. "
                     "Do not use any placeholder literally (no sending to example "
                     "addresses, no committing '(the real email)'). Before any step "
                     "that depends on it, stop and ask the user for the real value. If "
                     "it is clearly intentional (e.g. a code sample), say why you're "
                     "treating it as such." % ", ".join(repr(u) for u in uniq))
    if notes:
        context(event, "\n".join(notes))


# ---------------------------------------------------------- session start

def keep_awake():
    """Hold a macOS idle-sleep assertion for as long as the Claude process
    lives. `caffeinate -w PID` exits by itself when that process exits.
    It does NOT stop lid-close sleep; see docs/HOW_TO_RUN_AGENTS.md."""
    if sys.platform != "darwin":
        return
    pid, target = os.getppid(), None
    for _ in range(6):
        try:
            line = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                                  capture_output=True, text=True, timeout=2).stdout.strip()
        except Exception:
            break
        if not line:
            break
        ppid, comm = line.split(None, 1)
        if "claude" in comm.lower():
            target = pid
            break
        pid = int(ppid)
    args = ["caffeinate", "-i", "-w", str(target)] if target else ["caffeinate", "-i", "-t", "14400"]
    if target and subprocess.run(["pgrep", "-f", "caffeinate -i -w %d$" % target],
                                 capture_output=True).returncode == 0:
        return
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def session_start(data):
    try:
        keep_awake()
    except Exception:
        pass
    cwd = data.get("cwd") or os.getcwd()
    info = repo_info(cwd)
    src = data.get("source") or ""
    lines = ["[agent-os] Session %s. cwd: %s" % (src or "start", cwd)]
    if info:
        top, primary, common, branch = info
        lines.append("Branch here: %s" % (branch or "(detached)"))
        if primary and top == primary:
            lines.append("You are in the SHARED PRIMARY CHECKOUT, which stays on main. "
                         "Read-only here except TASKS.md; for any task, use or create "
                         "its own worktree (start-task / resume-task skill).")
        holder = lock_holder(common)
        if holder:
            lines.append("Merge lock currently held by session %s (branch %s). Do not merge."
                         % (holder.get("session", "?")[:8], holder.get("branch") or "?"))
    lines.append("First: read CLAUDE.md and TASKS.md. If you are continuing a task, run "
                 "/resume-task <task or branch name>; its handoff notes are in TASKS.md.")
    if src in ("clear", "compact"):
        lines.append("Context was just %sed. Don't guess at prior work: reload it from "
                     "TASKS.md and the worktree's docs/plans/ file." % src.rstrip("e"))
    context("SessionStart", "\n".join(lines))


# --------------------------------------------------------------- merge-lock

def merge_lock(argv):
    info = repo_info(os.getcwd())
    if not info:
        print("not in a git repo")
        return
    common = info[2]
    path = os.path.join(state_dir(common), "merge.lock")
    holder = lock_holder(common)
    if not argv or argv[0] == "status":
        print(json.dumps(holder) if holder else "merge lock: free")
    elif argv[0] == "release":
        rest = [a for a in argv[1:] if not a.startswith("-")]
        sid = rest[0] if rest else os.environ.get("CLAUDE_SESSION_ID", "")
        if holder and sid and holder.get("session") != sid and "--force" not in argv:
            print("lock is held by another session (%s); not releasing. Use --force only "
                  "if the user confirms that session is dead." % holder.get("session"))
            sys.exit(1)
        for p in (path,):
            if os.path.exists(p):
                os.remove(p)
        if holder:
            ap = os.path.join(state_dir(common), "approvals", holder.get("session", "") + ".json")
            if os.path.exists(ap):
                os.remove(ap)
        print("merge lock released")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "merge-lock":
        merge_lock(sys.argv[2:])
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    try:
        {"pretool": pretool, "prompt": prompt, "session-start": session_start}[mode](data)
    except SystemExit:
        raise
    except Exception as e:  # fail open, but say so
        sys.stderr.write("[agent-os guard] internal error (%s); allowing.\n" % e)


if __name__ == "__main__":
    main()
