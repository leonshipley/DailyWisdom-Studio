import os, re, json, shutil, pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

base = Path(".").resolve()
target_secret = base / "client_secret.json"

# 1. Check what Client ID is currently inside client_secret.json
old_cid = ""
if target_secret.exists():
    try:
        d = json.loads(target_secret.read_text(encoding="utf-8"))
        old_cid = (d.get("installed") or d.get("web") or {}).get("client_id", "")
        print(f"⚠️ Current client_secret.json has Client ID: {old_cid}")
    except Exception:
        pass

# 2. Search entire user folder for the new 36816817355 JSON file (or any newer client_secret JSON)
found_new = None
user_root = Path.home()
for sub in ["Downloads", "Desktop", "Documents", "OneDrive/Downloads", "OneDrive/Desktop", "OneDrive"]:
    p_dir = user_root / sub
    if p_dir.exists():
        for f in p_dir.glob("*36816817355*.json"):
            found_new = f
            break
    if found_new:
        break

if not found_new:
    # Check if there is any other .json file in ShortsClipper or Downloads with "36816817355" inside its text
    for p_dir in [base, user_root / "Downloads", user_root / "Desktop", user_root / "OneDrive/Downloads"]:
        if p_dir.exists():
            for f in p_dir.glob("*.json"):
                try:
                    txt = f.read_text(encoding="utf-8", errors="ignore")
                    if "36816817355" in txt and f.resolve() != target_secret.resolve():
                        found_new = f
                        break
                except Exception:
                    pass
        if found_new:
            break

if found_new and found_new.exists():
    shutil.copy(found_new, target_secret)
    print(f"✅ Replaced deleted client with your active file: {found_new}")
else:
    print("\n📂 Opening Windows File Picker — please select your newly downloaded 'Desktop client 2' JSON file!")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        picked = filedialog.askopenfilename(
            title="Select your new Google OAuth JSON file (Desktop client 2)",
            initialdir=str(user_root / "Downloads"),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        root.destroy()
        if picked and Path(picked).exists():
            shutil.copy(picked, target_secret)
            print(f"✅ Copied selected file: {picked} -> client_secret.json")
    except Exception as e:
        print(f"Picker note: {e}")

# 3. Verify the active Client ID now
new_data = json.loads(target_secret.read_text(encoding="utf-8"))
new_info = new_data.get("installed") or new_data.get("web") or {}
new_cid = new_info.get("client_id", "")
new_pid = new_info.get("project_id", "")

print("\n" + "="*72)
print(f"🔑 NOW USING CLIENT ID : {new_cid}")
print(f"🏢 GOOGLE PROJECT ID   : {new_pid}")
print("="*72)

if not new_cid:
    raise RuntimeError("❌ This JSON file is not a valid OAuth Client Secret JSON!")

SAFE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

flow = InstalledAppFlow.from_client_secrets_file(str(target_secret), SAFE_SCOPES)
print("\n🌐 Opening Google Login for leonshipley12@gmail.com...")
creds = flow.run_local_server(port=0, prompt="select_account consent")

yt = build("youtube", "v3", credentials=creds)
res = yt.channels().list(mine=True, part="snippet").execute()
items = res.get("items", [])

if not items:
    print("❌ Login succeeded, but leonshipley12@gmail.com does not have a YouTube channel created yet! Go to youtube.com and click 'Create channel'.")
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
    print(f"🎉 SUCCESS! CONNECTED NEW CHANNEL: '{disp_name}'")
    print(f"📺 Channels Available in Studio: {list(channels_map.keys())}")
    print("="*72)
