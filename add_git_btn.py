import re
from pathlib import Path

BASE_DIR = Path.cwd()

# 1. Create a clickable Save_To_Git.bat launcher in the folder
bat_content = """@echo off
cd /d "%~dp0"
python -c "import main; ok, msg = main.save_everything_to_git(); print(msg)"
pause
"""
(BASE_DIR / "Save_To_Git.bat").write_text(bat_content, encoding="utf-8")

# 2. Add save_everything_to_git() and Option [11] to main.py
with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

git_func_code = r'''# --- 1-CLICK GIT & GITHUB AUTO-BACKUP ---
def save_everything_to_git() -> tuple[bool, str]:
    """Stages all safe project files, commits with a timestamp, and pushes to GitHub."""
    from datetime import datetime
    print("\n☁️ [Git Backup] Saving & pushing project to GitHub (leonshipley/DailyWisdom-Studio)...")
    try:
        # Ensure secrets stay untracked
        subprocess.run(
            ["git", "rm", "-r", "--cached", ".env", "client_secret*.json", "youtube_token.pickle", "channels/", "--ignore-unmatch"],
            cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        subprocess.run(["git", "add", "."], cwd=str(BASE_DIR), check=True)

        status = subprocess.run(["git", "status", "--porcelain"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if status.stdout.strip():
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            subprocess.run(["git", "commit", "-m", f"Studio Auto-Save: {ts}"], cwd=str(BASE_DIR), check=True)

        push_res = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if push_res.returncode == 0:
            msg = "✅ Successfully saved & pushed everything to GitHub (leonshipley/DailyWisdom-Studio)!"
            print(msg)
            return True, msg
        else:
            err = push_res.stderr.strip() or push_res.stdout.strip()
            msg = f"⚠️ Committed locally, but push returned: {err}"
            print(msg)
            return False, msg
    except Exception as e:
        msg = f"❌ Git save error: {e}"
        print(msg)
        return False, msg
'''

if "def save_everything_to_git" not in code:
    code = code.replace("# --- 9. MAIN INTERACTIVE BACKEND MENU ---", git_func_code + "\n\n# --- 9. MAIN INTERACTIVE BACKEND MENU ---", 1)

if "[11]" not in code:
    code = code.replace(
        'print("  [10] 📌 Download Pinterest Image or Video (Auto-Sorted in Pinterest/)")',
        'print("  [10] 📌 Download Pinterest Image or Video (Auto-Sorted in Pinterest/)")\n        print("  [11] ☁️ Save & Push Everything to GitHub")'
    )
    code = code.replace('Select an option (0-10):', 'Select an option (0-11):')
    code = code.replace('Enter 0 to 10.', 'Enter 0 to 11.')
    code = code.replace(
        'elif opt == "10":\n            run_cli_pinterest_downloader()',
        'elif opt == "10":\n            run_cli_pinterest_downloader()\n        elif opt == "11":\n            save_everything_to_git()'
    )

compile(code, "main.py", "exec")
with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)
print("✅ Added save_everything_to_git() & Option [11] to main.py!")

# 3. Add the 1-Click "☁️ Save to GitHub" button to the top bar of app.py (Frontend)
with open("app.py", "r", encoding="utf-8") as f:
    app_code = f.read()

old_topbar = '''col_ch1, col_ch2, col_ch3 = st.columns([2, 2, 1])'''
new_topbar = '''col_ch1, col_ch2, col_ch3, col_ch4 = st.columns([2, 1.5, 1, 1.2])'''

old_ch3_block = '''with col_ch3:
    st.write("")
    if st.button("➕ Connect Channel", width="stretch"):
        new_ch = backend.connect_new_channel()
        if new_ch:
            st.success(f"Connected {new_ch}!")
            st.rerun()'''

new_ch3_ch4_block = '''with col_ch3:
    st.write("")
    if st.button("➕ Connect Channel", width="stretch"):
        new_ch = backend.connect_new_channel()
        if new_ch:
            st.success(f"Connected {new_ch}!")
            st.rerun()

with col_ch4:
    st.write("")
    if st.button("☁️ Save to GitHub", width="stretch"):
        with st.spinner("Saving & pushing to GitHub..."):
            ok, msg = backend.save_everything_to_git()
            if ok:
                st.toast("Saved to GitHub!", icon="✅")
                st.success(msg)
            else:
                st.warning(msg)'''

if "Save to GitHub" not in app_code:
    app_code = app_code.replace(old_topbar, new_topbar, 1)
    app_code = app_code.replace(old_ch3_block, new_ch3_ch4_block, 1)

compile(app_code, "app.py", "exec")
with open("app.py", "w", encoding="utf-8") as f:
    f.write(app_code)
print("✅ Added '☁️ Save to GitHub' button to the top bar of app.py!")

# 4. Run an immediate backup right now so all new features are pushed to GitHub
import main
main.save_everything_to_git()
