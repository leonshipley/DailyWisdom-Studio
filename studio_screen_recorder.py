import os
import re
import sys
import time
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
import streamlit as st
import streamlit.components.v1 as components

BASE_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = BASE_DIR / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

PID_FILE = RECORDINGS_DIR / "active_rec.pid"
STOP_FLAG_FILE = RECORDINGS_DIR / "stop_rec.flag"
TARGET_FILE_TRACKER = RECORDINGS_DIR / "active_target.txt"
REC_LOG_FILE = RECORDINGS_DIR / "last_recorder_log.txt"
WORKER_SCRIPT = RECORDINGS_DIR / "_rec_worker.py"

def get_next_phase_filename(prefix: str = "Graceofthe lord phase") -> Path:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    nums = []
    pattern = re.compile(r"phase[\s_]*(\d+)", re.IGNORECASE)
    for f in RECORDINGS_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in (".mp4", ".webm", ".mkv") and f.stat().st_size > 5000:
            m = pattern.search(f.stem)
            if m:
                nums.append(int(m.group(1)))
    next_n = (max(nums) + 1) if nums else 1
    return RECORDINGS_DIR / f"{prefix} {next_n}.mp4"

def get_all_recordings() -> List[Path]:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        [
            f for f in RECORDINGS_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in (".mp4", ".webm", ".mkv")
            and not f.name.startswith("temp_") and f.stat().st_size > 5000
        ],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

def list_windows_microphones() -> List[str]:
    mics = []
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        out = (res.stderr or "") + "\n" + (res.stdout or "")
        lines = out.splitlines()
        for line in lines:
            if "(audio)" in line.lower():
                m = re.search(r'"([^"]+)"', line)
                if m and m.group(1) not in mics:
                    mics.append(m.group(1))
        if not mics:
            in_audio = False
            for line in lines:
                if "DirectShow audio devices" in line:
                    in_audio = True
                    continue
                if "DirectShow video devices" in line:
                    in_audio = False
                if in_audio and "Alternative name" not in line:
                    m = re.search(r'"([^"]+)"', line)
                    if m and m.group(1) not in mics:
                        mics.append(m.group(1))
    except Exception:
        pass
    return mics

def is_recording_active() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        res = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
        if str(pid) in res.stdout:
            return True
    except Exception:
        pass
    PID_FILE.unlink(missing_ok=True)
    return False

def _write_worker_script():
    lines = [
        "import sys, time, subprocess",
        "from pathlib import Path",
        "stop_flag = Path(sys.argv[1])",
        "log_file = Path(sys.argv[2])",
        "ffmpeg_cmd = sys.argv[3:]",
        "with open(log_file, 'w', encoding='utf-8', errors='replace') as lf:",
        "    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=lf, stderr=lf)",
        "    while proc.poll() is None:",
        "        if stop_flag.exists():",
        "            try:",
        "                proc.stdin.write(b'q\\n')",
        "                proc.stdin.flush()",
        "            except Exception:",
        "                pass",
        "            try:",
        "                proc.wait(timeout=5)",
        "            except Exception:",
        "                proc.kill()",
        "            break",
        "        time.sleep(0.25)"
    ]
    WORKER_SCRIPT.write_text("\n".join(lines), encoding="utf-8")

def start_desktop_mic_recording(enable_mic: bool = True, mic_device: str = "", custom_name: str = "") -> Tuple[bool, str, Path]:
    if is_recording_active():
        return False, "🔴 A recording is already running!", RECORDINGS_DIR

    STOP_FLAG_FILE.unlink(missing_ok=True)
    _write_worker_script()

    if custom_name.strip():
        clean_c = re.sub(r'[\\/*?:"<>|]', "", custom_name.strip())
        if not clean_c.lower().endswith(".mp4"):
            clean_c += ".mp4"
        out_mp4 = RECORDINGS_DIR / clean_c
    else:
        out_mp4 = get_next_phase_filename("Graceofthe lord phase")

    even_scale = "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"

    if enable_mic and mic_device and mic_device != "No Microphone Found":
        ff_cmd = [
            "ffmpeg", "-y",
            "-rtbufsize", "150M",
            "-f", "gdigrab", "-framerate", "24", "-draw_mouse", "1", "-i", "desktop",
            "-f", "dshow", "-i", f"audio={mic_device}",
            "-vf", even_scale,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "160k", "-ac", "2",
            "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
            str(out_mp4.absolute())
        ]
    else:
        ff_cmd = [
            "ffmpeg", "-y",
            "-f", "gdigrab", "-framerate", "24", "-draw_mouse", "1", "-i", "desktop",
            "-vf", even_scale,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
            str(out_mp4.absolute())
        ]

    try:
        CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
        proc = subprocess.Popen(
            [sys.executable, str(WORKER_SCRIPT.absolute()), str(STOP_FLAG_FILE.absolute()), str(REC_LOG_FILE.absolute()), *ff_cmd],
            creationflags=CREATE_NO_WINDOW
        )
        PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        TARGET_FILE_TRACKER.write_text(str(out_mp4.absolute()), encoding="utf-8")

        time.sleep(1.2)
        if proc.poll() is not None:
            if enable_mic:
                return start_desktop_mic_recording(enable_mic=False, mic_device="", custom_name=custom_name)
            err_tail = REC_LOG_FILE.read_text(encoding="utf-8", errors="replace")[-300:] if REC_LOG_FILE.exists() else "Unknown error"
            PID_FILE.unlink(missing_ok=True)
            return False, f"FFmpeg error: {err_tail}", out_mp4

        mic_lbl = f" + Mic ({mic_device[:20]})" if (enable_mic and mic_device and mic_device != "No Microphone Found") else " (Screen Only)"
        return True, f"🔴 Recording Live{mic_lbl} -> `{out_mp4.name}`", out_mp4
    except Exception as e:
        return False, f"Failed to start recorder: {e}", out_mp4

def stop_desktop_mic_recording() -> Tuple[bool, Optional[Path], str]:
    target_p = None
    if TARGET_FILE_TRACKER.exists():
        try:
            target_p = Path(TARGET_FILE_TRACKER.read_text(encoding="utf-8").strip())
        except Exception:
            target_p = None

    STOP_FLAG_FILE.write_text("STOP", encoding="utf-8")

    for _ in range(16):
        if not is_recording_active():
            break
        time.sleep(0.25)

    PID_FILE.unlink(missing_ok=True)
    STOP_FLAG_FILE.unlink(missing_ok=True)

    if target_p and target_p.exists() and target_p.stat().st_size > 2000:
        remux_p = target_p.with_name(f"temp_fast_{target_p.name}")
        subprocess.run([
            "ffmpeg", "-y", "-i", str(target_p.absolute()),
            "-c", "copy", "-movflags", "+faststart", str(remux_p.absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if remux_p.exists() and remux_p.stat().st_size > 2000:
            shutil.move(str(remux_p), str(target_p))
        return True, target_p, f"✅ Saved `{target_p.name}` in `recordings/`!"

    err_tail = REC_LOG_FILE.read_text(encoding="utf-8", errors="replace")[-250:] if REC_LOG_FILE.exists() else ""
    return False, None, f"⚠️ Recording did not save. Log: {err_tail}"

def render_browser_screen_mic_widget(next_phase_name: str):
    safe_dl_name = next_phase_name if next_phase_name.endswith(".webm") else f"{next_phase_name}.webm"
    html_code = f"""
    <div style="background:rgba(15,23,42,0.92);border:1px solid #EBB937;border-radius:10px;padding:10px;color:#F8FAFC;font-family:sans-serif;font-size:12px;">
        <div style="font-weight:700;color:#FDE047;margin-bottom:6px;">🌐 Browser Recorder (Screen + Tab Audio + Mic)</div>
        <div style="display:flex;gap:6px;margin-bottom:6px;">
            <button id="bStartBtn" style="flex:1;background:#DC2626;color:#fff;border:none;border-radius:6px;padding:7px;font-weight:700;cursor:pointer;">🔴 Start Browser Rec</button>
            <button id="bStopBtn" disabled style="flex:1;background:#2563EB;color:#fff;border:none;border-radius:6px;padding:7px;font-weight:700;cursor:pointer;opacity:0.4;">⏹️ Stop</button>
        </div>
        <div id="bStatus" style="color:#93C5FD;font-size:11px;">Saves as: <b>{next_phase_name}</b></div>
    </div>
    <script>
    const nav = (window.parent && window.parent.navigator && window.parent.navigator.mediaDevices)
                ? window.parent.navigator.mediaDevices
                : navigator.mediaDevices;
    let rec;
    let chunks = [];
    let activeStreams = [];
    const sBtn = document.getElementById('bStartBtn');
    const eBtn = document.getElementById('bStopBtn');
    const st = document.getElementById('bStatus');

    sBtn.onclick = async () => {{
        try {{
            chunks = [];
            const disp = await nav.getDisplayMedia({{ video: true, audio: true }});
            activeStreams.push(disp);

            const ctx = new AudioContext();
            const dest = ctx.createMediaStreamDestination();
            if (disp.getAudioTracks().length > 0) {{
                ctx.createMediaStreamSource(disp).connect(dest);
            }}
            try {{
                const mic = await nav.getUserMedia({{ audio: true }});
                activeStreams.push(mic);
                ctx.createMediaStreamSource(mic).connect(dest);
            }} catch (me) {{
                console.warn("Mic skipped:", me);
            }}

            const tracks = [...disp.getVideoTracks(), ...dest.stream.getAudioTracks()];
            const mixed = new MediaStream(tracks);
            rec = new MediaRecorder(mixed);
            rec.ondataavailable = e => {{ if (e.data && e.data.size > 0) chunks.push(e.data); }};
            rec.onstop = () => {{
                const blob = new Blob(chunks, {{ type: 'video/webm' }});
                const u = URL.createObjectURL(blob);
                const a = (window.parent ? window.parent.document : document).createElement('a');
                a.href = u;
                a.download = "{safe_dl_name}";
                a.click();
                st.innerHTML = "✅ Downloaded! Or use '🔴 Rec Desktop+Mic' above to save directly in recordings/";
                activeStreams.forEach(s => s.getTracks().forEach(t => t.stop()));
                activeStreams = [];
            }};
            disp.getVideoTracks()[0].onended = () => {{ if (rec && rec.state !== 'inactive') eBtn.click(); }};
            rec.start(250);
            sBtn.disabled = true; sBtn.style.opacity = '0.4';
            eBtn.disabled = false; eBtn.style.opacity = '1.0';
            st.innerHTML = "🔴 <b>RECORDING SCREEN + MIC LIVE...</b>";
        }} catch (err) {{
            st.innerHTML = "⚠️ Use '🔴 Rec Desktop+Mic' button above (Browser blocked popup: " + err.message + ")";
        }}
    }};

    eBtn.onclick = () => {{
        if (rec && rec.state !== 'inactive') {{
            rec.stop();
            sBtn.disabled = false; sBtn.style.opacity = '1.0';
            eBtn.disabled = true; eBtn.style.opacity = '0.4';
        }}
    }};
    </script>
    """
    getattr(st, 'iframe', components.html)(html_code, height=110)
