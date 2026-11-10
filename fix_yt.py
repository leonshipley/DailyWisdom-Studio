import os, re
files_to_fix = {
    "main.py": (
        r'"status":\s*\{\s*"privacyStatus":\s*"public",\s*"selfDeclaredMadeForKids":\s*False\s*\}',
        '"status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}'
    ),
    "run_brain.py": (
        r'"status":\s*\{\s*"privacyStatus":\s*UPLOAD_PRIVACY,\s*"selfDeclaredMadeForKids":\s*False\s*\}',
        '"status": {\n            "privacyStatus": UPLOAD_PRIVACY,\n            "selfDeclaredMadeForKids": False,\n            "containsSyntheticMedia": False\n        }'
    )
}
for filename, (pattern, replacement) in files_to_fix.items():
    if os.path.exists(filename):
        content = open(filename, "r", encoding="utf-8").read()
        new_content, count = re.subn(pattern, replacement, content)
        if count > 0:
            open(filename, "w", encoding="utf-8").write(new_content)
            print(f"✅ Successfully patched {filename}!")
        elif "containsSyntheticMedia" in content:
            print(f"⚡ {filename} is already updated!")
        else:
            print(f"⚠️ Could not find target code in {filename}")
