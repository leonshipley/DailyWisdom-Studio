import os, re, json, shutil, pickle, webbrowser, subprocess
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

base = Path(".").resolve()
target_secret = base / "client_secret.json"
target_id = "36816817355-plenkbufjt2a116j0jhh5j67a4ajpeti"

# 1. Search everywhere on user profile for the 36816817355 JSON file
found_files = []
for root_p in [base, Path.home() / "Downloads", Path.home() / "Desktop", Path.home() / "OneDrive"]:
    if root_p.exists():
        try:
            for p in root_p.rglob(f"*{target_id}*.json"):
                found_files.append(p)
        except Exception:
            pass

if found_files:
    best_f = max(found_files, key=lambda x: x.stat().st_mtime)
    shutil.copy(best_f, target_secret)
    print(f"✅ Copied exact JSON: {best_f} -> {target_secret}")
else:
    print("⚠️ Could not find a file with '36816817355' in Downloads/Desktop. Checking current client_secret.json...")

if not target_secret.exists():
    raise FileNotFoundError("❌ client_secret.json does not exist in ShortsClipper!")

raw_json = json.loads(target_secret.read_text(encoding="utf-8"))
app_cfg = raw_json.get("installed") or raw_json.get("web") or {}
client_id = app_cfg.get("client_id", "UNKNOWN")
project_id = app_cfg.get("project_id", "UNKNOWN")

print("\n" + "="*72)
print(f"🔍 ACTIVE OAUTH PROJECT ID : {project_id}")
print(f"🔍 ACTIVE CLIENT ID        : {client_id}")
print("="*72)
print("🚨 CRITICAL CHECK IN GOOGLE CLOUD CONSOLE (IF IT STILL SAYS BLOCKED):")
print(f"   1. Open: https://console.cloud.google.com/auth/audience?project={project_id}")
print("   2. Look at 'Publishing status':")
print("      👉 It MUST say 'Testing' (NOT 'In production'!).")
print("      👉 If it says 'In production', click 'BACK TO TESTING' — Google blocks")
print("         unverified YouTube apps in production, but allows them in Testing!")
print("   3. Under 'Test users', make sure the EXACT Gmail you are logging in with is listed.")
print("   4. When the login screen says 'Google hasn't verified this app',")
print("      click 'Advanced' (small grey text) -> 'Go to ... (unsafe)' -> 'Continue'.")
print("="*72)

# 2. Use ONLY low-friction YouTube scopes so Google's automated risk filter doesn't block login!
CLEAN_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

# Also update main.py to use CLEAN_SCOPES so future '+ Add Channel' clicks never get blocked
p_main = base / "main.py"
if p_main.exists():
    cm = p_main.read_text(encoding="utf-8")
    cm = re.sub(
        r"YOUTUBE_SCOPES\s*=\s*\[[\s\S]*?\]",
        'YOUTUBE_SCOPES = [\n    "https://www.googleapis.com/auth/youtube.upload",\n    "https://www.googleapis.com/auth/youtube.readonly",\n    "https://www.googleapis.com/auth/youtube.force-ssl"\n]',
        cm,
        count=1
    )
    p_main.write_text(cm, encoding="utf-8")

flow = InstalledAppFlow.from_client_secrets_file(str(target_secret), CLEAN_SCOPES)
print("\n🌐 Starting local OAuth listener (Copy the URL below into an Incognito window if your default browser has the wrong Gmail signed in):")
creds = flow.run_local_server(port=0, prompt="select_account consent", authorization_prompt_message="\n👉 OPEN THIS URL IN YOUR BROWSER (OR INCOGNITO):\n{url}\n")

yt = build("youtube", "v3", credentials=creds)
res = yt.channels().list(mine=True, part="snippet").execute()
items = res.get("items", [])

if not items:
    print("❌ Login succeeded, but this Google Account does not have a YouTube Channel created yet!")
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
    print(f"\n🎉 CONNECTED CHANNEL: '{disp_name}'!")
