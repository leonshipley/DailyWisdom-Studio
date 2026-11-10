import os, sys, pathlib, subprocess
from dotenv import load_dotenv

git_path = sys.argv[1].strip() if len(sys.argv) > 1 else ""
base = pathlib.Path(".").resolve()

# Save exact GIT_EXECUTABLE path into .env so Streamlit ALWAYS finds it!
env_f = base / ".env"
env_txt = env_f.read_text(encoding="utf-8") if env_f.exists() else ""
lines = [ln for ln in env_txt.splitlines() if not ln.startswith("GIT_EXECUTABLE=")]
if git_path and pathlib.Path(git_path).exists():
    lines.append(f"GIT_EXECUTABLE={git_path}")
    env_f.write_text("\n".join(lines) + "\n", encoding="utf-8")

# Patch _find_git_executable() in main.py to read GIT_EXECUTABLE from .env first and use shell fallback
p_main = base / "main.py"
c_main = p_main.read_text(encoding="utf-8")
old_finder = c_main[c_main.find("def _find_git_executable()"):c_main.find("def save_everything_to_git()")]
new_finder = '''def _find_git_executable() -> str | None:
    """Finds git.exe from .env, PATH, Windows where.exe, or common directories."""
    import shutil
    load_dotenv(BASE_DIR / ".env", override=True)
    env_git = os.getenv("GIT_EXECUTABLE", "").strip()
    if env_git and Path(env_git).exists():
        return env_git
    w = shutil.which("git")
    if w:
        return w
    try:
        r = subprocess.run("where git", shell=True, capture_output=True, text=True, timeout=4)
        for ln in r.stdout.splitlines():
            if ln.strip() and Path(ln.strip()).exists():
                return ln.strip()
    except Exception:
        pass
    home = Path.home()
    for c in [
        Path("C:/Program Files/Git/cmd/git.exe"),
        Path("C:/Program Files/Git/bin/git.exe"),
        Path("C:/Program Files (x86)/Git/cmd/git.exe"),
        home / "AppData/Local/Programs/Git/cmd/git.exe",
        home / "AppData/Local/Programs/Git/bin/git.exe",
    ]:
        if c.exists():
            return str(c)
    return None

'''
if old_finder:
    c_main = c_main.replace(old_finder, new_finder)

# Also ensure remote origin is set to https://github.com/leonshipley/DailyWisdom-Studio.git
c_main = c_main.replace(
    'push_res = subprocess.run([git_exe, "push", "-u", "origin", "main"], cwd=str(BASE_DIR), capture_output=True, text=True)',
    'subprocess.run([git_exe, "remote", "add", "origin", "https://github.com/leonshipley/DailyWisdom-Studio.git"], cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n        push_res = subprocess.run([git_exe, "push", "-u", "origin", "main"], cwd=str(BASE_DIR), capture_output=True, text=True)'
)
p_main.write_text(c_main, encoding="utf-8")
os.utime(base / "app.py", None)

# Run the backup right now to verify!
import main as backend
ok, msg = backend.save_everything_to_git()
print(msg)
