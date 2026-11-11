import os, re, json, shutil, pickle, webbrowser, pathlib, py_compile
from pathlib import Path

base = Path(".").resolve()
dl_dir = Path.home() / "Downloads"

# 1. Auto-detect any newly downloaded client_secret*.json in Downloads or project folder
candidates = []
for folder in [base, dl_dir]:
    if folder.exists():
        for f in folder.glob("client_secret*.json"):
            if f.is_file() and f.stat().st_size > 100:
                candidates.append(f)

if candidates:
    newest_json = max(candidates, key=lambda p: p.stat().st_mtime)
    target_secret = base / "client_secret.json"
    if newest_json.resolve() != target_secret.resolve():
        shutil.copy(newest_json, target_secret)
        print(f"✅ Copied your newest OAuth JSON ({newest_json.name}) -> client_secret.json!")
    else:
        print(f"✅ Using existing client_secret.json (Modified: {newest_json.name})")

# Read project_id from client_secret.json to open the exact Google Cloud Test Users page!
proj_id = ""
try:
    s_data = json.loads((base / "client_secret.json").read_text(encoding="utf-8"))
    info = s_data.get("installed") or s_data.get("web") or {}
    proj_id = info.get("project_id", "")
except Exception:
    pass

print("\n" + "="*72)
print("🚨 WHY GOOGLE SHOWED 'ACCESS BLOCKED (403: access_denied)':")
print("="*72)
print("Because your Google Cloud project is in 'Testing' mode, Google blocks")
print("any Gmail account that is NOT listed under 'Test users'!")
print("\n👉 STEP 1: In the Google Cloud tab opening now:")
print("   1. Scroll down to 'Test users' -> Click '+ ADD USERS'")
print("   2. Type the Gmail address of your NEW YouTube channel & click SAVE!")
print("="*72)

consent_url = f"https://console.cloud.google.com/apis/credentials/consent?project={proj_id}" if proj_id else "https://console.cloud.google.com/apis/credentials/consent"
webbrowser.open(consent_url)

# 2. Upgrade connect_new_channel() in main.py so it always forces account chooser ('select_account consent')
p_main = base / "main.py"
c_main = p_main.read_text(encoding="utf-8")
c_main = c_main.replace(
    'credentials = flow.run_local_server(port=0, prompt="consent")',
    'credentials = flow.run_local_server(port=0, prompt="select_account consent")'
)
p_main.write_text(c_main, encoding="utf-8")

# 3. Add a client_secret.json uploader inside the Sidebar of app.py so you can drop any JSON anytime!
p_app = base / "app.py"
c_app = p_app.read_text(encoding="utf-8")
old_add_btn = '''    with sb_c1:
        if st.button("➕ Add Channel", width="stretch"):
            new_c = backend.connect_new_channel()
            if new_c:
                st.rerun()'''

new_add_btn = '''    with sb_c1:
        if st.button("➕ Add Channel", width="stretch"):
            new_c = backend.connect_new_channel()
            if new_c:
                st.rerun()
    with st.expander("🔑 Fix 'Access Blocked' / Upload New OAuth JSON", expanded=False):
        st.caption("1️⃣ If Google says **Access Blocked**, add your new channel's Gmail to **Test Users** in Google Cloud Console.\n2️⃣ Or drop your new `client_secret.json` below:")
        up_sec = st.file_uploader("Upload client_secret.json:", type=["json"], key="sb_up_secret_json")
        if up_sec is not None:
            (backend.BASE_DIR / "client_secret.json").write_bytes(up_sec.getvalue())
            st.success("✅ Updated client_secret.json! Click '➕ Add Channel' above now.")'''

if "sb_up_secret_json" not in c_app and old_add_btn in c_app:
    c_app = c_app.replace(old_add_btn, new_add_btn)
    p_app.write_text(c_app, encoding="utf-8")
    os.utime(p_app, None)

py_compile.compile("main.py", doraise=True)
py_compile.compile("app.py", doraise=True)

input("\n⏸️  Press [ENTER] here AFTER you added your Gmail to 'Test users' in the browser to launch the YouTube Channel Login...")
import main as backend
backend.connect_new_channel()
