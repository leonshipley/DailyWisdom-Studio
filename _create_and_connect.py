import os, re, json, time, shutil, pickle, webbrowser
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

base = Path(".").resolve()
target_secret = base / "client_secret.json"

# Get existing project_id if available so we open the exact project's Credentials page
proj_id = ""
if target_secret.exists():
    try:
        d = json.loads(target_secret.read_text(encoding="utf-8"))
        proj_id = (d.get("installed") or d.get("web") or {}).get("project_id", "")
    except Exception:
        pass

cred_url = f"https://console.cloud.google.com/apis/credentials/oauthclient?project={proj_id}" if proj_id else "https://console.cloud.google.com/apis/credentials"
print("\n" + "="*72)
print("👉 STEP 1: Creating a Fresh Desktop OAuth Client (Takes 15 Seconds):")
print("   1. In the browser tab opening now, select Application type: 'Desktop app'")
print("   2. Click 'CREATE'")
print("   3. Click 'DOWNLOAD JSON' on the popup window!")
print("="*72)
webbrowser.open(cred_url)

input("\n⏸️  Press [ENTER] here right after you click 'DOWNLOAD JSON' in your browser...")

# Automatically find the newest client_secret*.json downloaded in the last 10 minutes
dl_folders = [
    Path.home() / "Downloads",
    Path.home() / "OneDrive" / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "OneDrive" / "Desktop",
    base
]

candidates = []
for d in dl_folders:
    if d.exists():
        for f in d.glob("client_secret*.json"):
            if f.is_file() and f.resolve() != target_secret.resolve():
                candidates.append(f)

if candidates:
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    shutil.copy(newest, target_secret)
    print(f"\n✅ Automatically grabbed your new JSON from: {newest}")
else:
    print("\n📂 Select your newly downloaded JSON file in the File Picker window...")
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    picked = filedialog.askopenfilename(
        title="Select your newly downloaded client_secret JSON file",
        initialdir=str(Path.home() / "Downloads"),
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    root.destroy()
    if picked and Path(picked).exists():
        shutil.copy(picked, target_secret)
        print(f"✅ Copied: {picked} -> client_secret.json")

new_data = json.loads(target_secret.read_text(encoding="utf-8"))
new_cid = (new_data.get("installed") or new_data.get("web") or {}).get("client_id", "")
print(f"🔑 Active New Client ID: {new_cid}")

SAFE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

flow = InstalledAppFlow.from_client_secrets_file(str(target_secret), SAFE_SCOPES)
print("\n🌐 Opening Google Sign-In for your YouTube Channel...")
creds = flow.run_local_server(port=0, prompt="select_account consent")

yt = build("youtube", "v3", credentials=creds)
res = yt.channels().list(mine=True, part="snippet").execute()
items = res.get("items", [])

if not items:
    print("❌ Login worked, but this Google Account has no YouTube channel created yet! Go to youtube.com and click 'Create channel' first.")
else:
    ch_title = items[0]["snippet"]["title"]
    ch_handle = items[0]["snippet"].get("customUrl", "")
    disp_name = f"{ch_title} ({ch_handle})" if ch_handle and ch_handle not in ch_title else ch_title

    channels_dir = base / "channels"
    channels_dir.mkdir(exist_ok=True)
    safe_name = re.sub(r'[\\/*?:"<>| ]', "_", ch_title)
    token_file = channels_dir / f"{safe_name}.pickle"

    with open(token_file, "wb") as f:
        pickle.dump(creds, f)

    cfg_file = base / "channels.json"
    channels_map = {}
    if cfg_file.exists():
        try:
            channels_map = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            channels_map = {}

    channels_map[disp_name] = str(token_file)
    cfg_file.write_text(json.dumps(channels_map, indent=2), encoding="utf-8")
    os.utime(base / "app.py", None)
    print("\n" + "="*72)
    print(f"🎉 SUCCESS! CONNECTED YOUTUBE CHANNEL: '{disp_name}'!")
    print(f"📺 Channels Available in Studio: {list(channels_map.keys())}")
    print("="*72)
