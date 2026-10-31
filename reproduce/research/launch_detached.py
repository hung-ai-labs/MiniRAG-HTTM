"""Start a long run as a process that outlives the Claude Code session that launched it.

On MultiHop-RAG, background runs died whenever the agent session ended: they were children of it, and on
Windows usually members of its job object. This starts the command detached, in a new process group,
and -- where the job allows it -- broken away from that job; stdout and stderr go to a log file, and the
PID, command and start time go to <log>.pid.json for monitoring. Only shutting the machine down stops it.

    python reproduce/research/launch_detached.py --log runs/lihua_world/ablation_v2/judge_s101.log -- \
        .venv/Scripts/python.exe reproduce/research/judge_session.py ...
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def launch(command, log, cwd, env=None):
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    exe = Path(cwd) / command[0]
    if exe.exists():  # CreateProcess does not resolve a relative program against cwd
        command = [str(exe.resolve())] + list(command[1:])
    out = open(log, "ab")
    kwargs = {"cwd": cwd, "stdout": out, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL, "env": env}
    if os.name == "nt":
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            proc = subprocess.Popen(command, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **kwargs)
            broke_away = True
        except OSError as exc:
            if getattr(exc, "winerror", None) != 5:  # only "access denied" means the job forbids breakaway
                raise
            proc = subprocess.Popen(command, creationflags=flags, **kwargs)  # still detached from console/group
            broke_away = False
    else:
        proc = subprocess.Popen(command, start_new_session=True, **kwargs)
        broke_away = None
    info = {"pid": proc.pid, "command": command, "cwd": str(cwd), "log": str(log),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "broke_away_from_job": broke_away}
    Path(f"{log}.pid.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return info


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--log", required=True)
    p.add_argument("--cwd", default=str(Path(__file__).resolve().parents[2]))
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        p.error("no command given")
    env = os.environ | {"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    print(json.dumps(launch(command, args.log, args.cwd, env), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
