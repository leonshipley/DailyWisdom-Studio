import os, re, json, shutil, pickle, pathlib
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

base = Path(".").resolve()
target_secret = base / "client_secret.json"
search_prefix = "client_secret_36816817355-plenkbufjt2a116j0jhh5j67a4ajpeti"

# 1. Locate the exact JSON file across ShortsClipper, Downloads, Desktop, and OneDrive
search_dirs = [
    base,
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "OneDrive" / "Desktop",
    Path.home() / "OneDrive" / "Downloads",
]

found_json = None
for d in search_dirs:
    if d.exists():
        matches = list(d.glob(f"{search_prefix}*"))
        if matches:
            found_json = matches[0]
            break

if found_json and found_json.exists():
    shutil.copy(found_json, target_secret)
    print(f"✅ Found and activated: {found_json.name} -> client_secret.json")
elif target_secret.exists():
    print("✅ Using existing client_secret.json in ShortsClipper folder.")
else:
    raise FileNotFoundError(f"❌ Could not find {search_prefix}.json! Please make sure it is in Downloads or ShortsClipper.")

# 2. Launch OAuth login with account/channel selector and full YouTube + Analytics scopes
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

print("\n🌐 Opening Google Login in your browser — select your Google Account & YouTube Channel...")
flow = InstalledAppFlow.from_client_secrets_file(str(target_secret), SCOPES)
creds = flow.run_local_server(port=0, prompt="select_account consent")

yt = build("youtube", "v3", credentials=creds)
res = yt.channels().list(mine=True, part="snippet").execute()

items = res.get("items", [])
if not items:
    print("❌ Connected Google account has no YouTube channel created yet! Create a channel on YouTube first.")
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

    # Also keep a copy of this channel's specific client_secret JSON so it never gets lost
    shutil.copy(target_secret, channels_dir / f"{safe_name}_client_secret.json")

    cfg_file = base / "channels.json"
    channels_map = {}
    if cfg_file.exists():
        try:
            channels_map = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            channels_map = {}

    channels_map[disp_name] = str(token_file)
    cfg_file.write_text(json.dumps(channels_map, indent=2), encoding="utf-8")

    # Touch app.py so Streamlit refreshes the Target Channel dropdown immediately
    os.utime(base / "app.py", None)
    print("\n" + "="*68)
    print(f"🎉 SUCCESSFULLY CONNECTED YOUTUBE CHANNEL: '{disp_name}'!")
    print(f"📂 Saved token: {token_file.name}")
    print(f"📺 Total Channels in Studio: {list(channels_map.keys())}")
    print("="*68)
