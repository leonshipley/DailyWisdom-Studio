import os, re, json, shutil, pickle, webbrowser
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

base = Path(".").resolve()

# 1. Scan all client_secret JSON files on your PC (ShortsClipper, channels/, Downloads, Desktop)
json_candidates = []
for folder in [base, base / "channels", Path.home() / "Downloads", Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop", Path.home() / "OneDrive" / "Downloads"]:
    if folder.exists():
        for f in folder.glob("*client_secret*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                info = data.get("installed") or data.get("web") or {}
                cid = info.get("client_id", "")
                pid = info.get("project_id", "unknown-project")
                if cid:
                    json_candidates.append((f, pid, cid))
            except Exception:
                pass

# Deduplicate by client_id
unique_clients = {}
for f, pid, cid in json_candidates:
    if cid not in unique_clients:
        unique_clients[cid] = (f, pid, cid)

client_list = list(unique_clients.values())
print("\n" + "="*75)
print("🔎 FOUND THESE GOOGLE OAUTH CLIENTS ON YOUR PC:")
print("="*75)
for idx, (f_path, pid, cid) in enumerate(client_list, start=1):
    tag = " (Desktop client 2 - 36816817355)" if "36816817355" in cid else " (Original Working Client)"
    print(f"  [{idx}] Project: {pid}{tag}")
    print(f"      File   : {f_path}")
    print(f"      ID     : {cid[:42]}...")
print("="*75)

choice = input(f"\n👉 Which Client do you want to use? (Press [ENTER] for #1, or type 1-{len(client_list)}): ").strip()
sel_idx = (int(choice) - 1) if (choice.isdigit() and 1 <= int(choice) <= len(client_list)) else 0
chosen_file, chosen_pid, chosen_cid = client_list[sel_idx]

target_secret = base / "client_secret.json"
if chosen_file.resolve() != target_secret.resolve():
    shutil.copy(chosen_file, target_secret)
print(f"\n✅ Activated Client from Project '{chosen_pid}' -> client_secret.json")

# 2. Open the EXACT Audience / Test Users page for THIS project
audience_url = f"https://console.cloud.google.com/auth/audience?project={chosen_pid}"
print("\n" + "="*75)
print(f"🚨 DO THIS IN THE BROWSER TAB OPENING NOW (Project: {chosen_pid}):")
print(f"   URL: {audience_url}")
print("   1. Under 'Publishing status', make sure it says 'Testing' (if it says 'In production', click 'Back to testing').")
print("   2. Under 'Test users', click '+ ADD USERS' and type the EXACT Gmail address")
print("      of the YouTube channel you are logging into right now, then click SAVE!")
print("   3. Wait 10 seconds after clicking Save, then come back here and press ENTER.")
print("="*75)
webbrowser.open(audience_url)

input("\n⏸️  Press [ENTER] here after you have saved your Gmail under Test Users...")

# 3. Use ONLY the 2 safest scopes (NO force-ssl, NO yt-analytics) so Google NEVER blocks Desktop client 2!
SAFE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

# Update main.py with SAFE_SCOPES as well
p_main = base / "main.py"
if p_main.exists():
    cm = p_main.read_text(encoding="utf-8")
    cm = re.sub(
        r"YOUTUBE_SCOPES\s*=\s*\[[\s\S]*?\]",
        'YOUTUBE_SCOPES = [\n    "https://www.googleapis.com/auth/youtube.upload",\n    "https://www.googleapis.com/auth/youtube.readonly"\n]',
        cm,
        count=1
    )
    p_main.write_text(cm, encoding="utf-8")

flow = InstalledAppFlow.from_client_secrets_file(str(target_secret), SAFE_SCOPES)
print("\n🌐 Launching Google Sign-In...")
print("💡 When you see 'Google hasn't verified this app', click 'Continue' (or 'Advanced' -> 'Go to ... (unsafe)').")
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
    print("\n" + "="*75)
    print(f"🎉 SUCCESS! CONNECTED NEW CHANNEL: '{disp_name}'")
    print(f"📺 All Connected Channels in Studio: {list(channels_map.keys())}")
    print("="*75)
