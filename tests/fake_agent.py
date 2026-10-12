"""冒烟用的假 agent：被 watcher 唤起后，按 prompt 里的回帖命令逐条回复。"""
import re
import subprocess
import sys


def main():
    prompt = " ".join(sys.argv[1:])
    m = re.search(r'"([^"]+)" -m brainstorm\.room post --config "([^"]+)" --from (\S+)',
                  prompt)
    if not m:
        print("fake-agent: no post command in prompt")
        return 2
    py, cfg, name = m.group(1), m.group(2), m.group(3)
    posts = re.findall(r"- seq=(\d+)\s+from=(\S+)\s+to=(\S+)\s+内容：(.*)", prompt)
    if not posts:
        print("fake-agent: no todo in prompt")
        return 3
    for seq, frm, _to, content in posts:
        cmd = [py, "-m", "brainstorm.room", "post", "--config", cfg,
               "--from", name, "--to", frm, "--reply-to", seq,
               "--text", "已收到（fake agent）：%s" % content[:40]]
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        print("fake-agent reply seq=%s rc=%s" % (seq, p.returncode))
        if p.returncode != 0:
            return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
