import os

app_path = "app.py"
if not os.path.exists(app_path):
    print("❌ app.py not found!")
    exit()

with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# Locate the CSS injection block reliably
start_idx = content.find("# CSS STYLING")
if start_idx != -1:
    start_idx = content.rfind("# ====", 0, start_idx)

end_idx = content.find("# MASTER SETTINGS STRIP")
if end_idx != -1:
    end_idx = content.rfind("# ====", 0, end_idx)

if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
    new_css = """# ==============================================================================
# CSS STYLING: ANIMATED PREMIUM GLASSMORPHISM
# ==============================================================================
st.markdown('''
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', -apple-system, sans-serif; }
    
    /* 1. Slow Animated Deep Gradient Background */
    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    .stApp { 
        background: linear-gradient(-45deg, #050B14, #12182B, #1B1018, #050711) !important;
        background-size: 400% 400% !important;
        animation: gradientShift 15s ease infinite !important;
    }
    
    .block-container { padding-top: 3rem !important; padding-bottom: 2.5rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { background: transparent !important; z-index: 10 !important; }
    
    /* 2. Floating Frosted Glass Cards */
    div[data-testid="stVerticalBlockBorderWrapper"] { 
        background: rgba(15, 20, 35, 0.6) !important; 
        backdrop-filter: blur(16px) !important; 
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important; 
        border-radius: 16px !important; 
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.5), inset 0 0 0 1px rgba(255, 255, 255, 0.05) !important; 
        transition: transform 0.3s ease, box-shadow 0.3s ease !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 40px 0 rgba(59, 130, 246, 0.25), inset 0 0 0 1px rgba(255, 255, 255, 0.15) !important;
    }

    /* 3. Animated Gradient Buttons */
    .stButton>button { 
        background: linear-gradient(90deg, #DC2626 0%, #991B1B 50%, #DC2626 100%) !important; 
        background-size: 200% auto !important;
        color: #FFFFFF !important; 
        font-weight: 800 !important; 
        border-radius: 10px !important; 
        border: 1px solid rgba(255,255,255,0.2) !important; 
        padding: 10px 20px !important; 
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4) !important; 
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important; 
    }
    .stButton>button:hover { 
        background-position: right center !important;
        transform: translateY(-2px) scale(1.02); 
        box-shadow: 0 8px 25px rgba(220, 38, 38, 0.6) !important; 
    }
    
    div[data-testid="stHorizontalBlock"] .stButton>button, section[data-testid="stSidebar"] .stButton>button { 
        background: linear-gradient(90deg, #2563EB 0%, #1E40AF 50%, #2563EB 100%) !important; 
        background-size: 200% auto !important;
        box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4) !important; 
    }
    div[data-testid="stHorizontalBlock"] .stButton>button:hover, section[data-testid="stSidebar"] .stButton>button:hover {
        background-position: right center !important;
        box-shadow: 0 8px 25px rgba(37, 99, 235, 0.6) !important; 
    }

    section[data-testid="stSidebar"] { 
        background: rgba(8, 12, 20, 0.75) !important; 
        backdrop-filter: blur(20px) !important; 
        border-right: 1px solid rgba(59, 130, 246, 0.2) !important; 
    }

    /* 4. Smooth Tabs */
    .stTabs [data-baseweb="tab"] { 
        background: rgba(15, 20, 35, 0.5) !important; 
        border: 1px solid rgba(255, 255, 255, 0.05) !important; 
        border-radius: 10px 10px 0 0 !important; 
        color: #94A3B8 !important; 
        transition: all 0.3s ease !important;
        font-weight: 700 !important;
    }
    .stTabs [data-baseweb="tab"]:hover { background: rgba(30, 41, 59, 0.8) !important; color: #E2E8F0 !important; }
    .stTabs [aria-selected="true"] { background: rgba(30, 41, 59, 0.95) !important; border-color: #3B82F6 !important; color: #60A5FA !important; border-bottom: 3px solid #DC2626 !important; }
    
    /* 5. Pulsing Title Glow */
    .studio-title {
        background: linear-gradient(to right, #60A5FA, #A78BFA, #F472B6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.5px;
        animation: pulseGlow 3s infinite alternate;
    }
    @keyframes pulseGlow {
        0% { filter: drop-shadow(0 0 4px rgba(96,165,250,0.3)); }
        100% { filter: drop-shadow(0 0 12px rgba(96,165,250,0.7)); }
    }

    /* Dynamic Badges & Spinners */
    @keyframes studio-spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .live-loader-card { background: rgba(15, 23, 42, 0.8); backdrop-filter: blur(10px); border: 2px solid #3B82F6; border-left: 6px solid #DC2626; border-radius: 14px; padding: 14px 20px; margin: 10px 0; display: flex; align-items: center; gap: 16px; box-shadow: 0 8px 32px rgba(59,130,246,0.3); }
    .live-spinner-ring { width: 32px; height: 32px; min-width: 32px; border: 4px solid rgba(96,165,250,0.2); border-top: 4px solid #EF4444; border-right: 4px solid #3B82F6; border-radius: 50%; animation: studio-spin 0.85s linear infinite; }
    .live-loader-title { font-size: 15px; font-weight: 800; color: #FFFFFF; }
    .live-loader-sub { font-size: 12.5px; color: #93C5FD; font-weight: 600; margin-top: 2px; }
    
    .status-pill { background: linear-gradient(135deg, rgba(30,58,138,0.8), rgba(17,24,39,0.9)); border: 1px solid #3B82F6; color: #F8FAFC; padding: 5px 14px; border-radius: 999px; font-size: 13px; font-weight: 700; box-shadow: 0 0 10px rgba(59,130,246,0.3); }
    .status-pill-red { background: linear-gradient(135deg, rgba(153,27,27,0.8), rgba(17,24,39,0.9)); border: 1px solid #EF4444; color: #FCA5A5; padding: 5px 14px; border-radius: 999px; font-size: 13px; font-weight: 700; box-shadow: 0 0 10px rgba(239,68,68,0.3); }
    .budget-badge { background: rgba(15, 23, 42, 0.6); border: 1px solid #3B82F6; border-radius: 8px; padding: 8px 14px; font-size: 13px; color: #93C5FD; font-weight: 700; display: inline-block; box-shadow: inset 0 0 8px rgba(59,130,246,0.2); }
    
    /* Verse Cards */
    .verse-card { background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(8px); border: 1px solid rgba(59, 130, 246, 0.4); border-left: 5px solid #DC2626; border-radius: 12px; padding: 16px; margin: 10px 0; transition: transform 0.2s; }
    .verse-card:hover { transform: scale(1.01); box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
    .verse-hdr { font-size: 15px; font-weight: 800; color: #60A5FA; margin-bottom: 5px; }
    .verse-body { font-size: 14.5px; color: #F8FAFC; line-height: 1.5; }
    
    img { border-radius: 10px; }
    video { width: 100% !important; max-height: 620px !important; border-radius: 12px; background: #000; border: 1px solid rgba(255,255,255,0.15); box-shadow: 0 8px 30px rgba(0,0,0,0.6); }
</style>
''', unsafe_allow_html=True)

# ==============================================================================
# TOP BANNER
# ==============================================================================
ch_disp = channel_names[0] if channel_names else "Grace of the Lord (@GraceAndDailyPrayer)"

with st.container(border=True):
    tb_c1, tb_c2 = st.columns([1.5, 1.2], gap="medium")
    with tb_c1:
        st.markdown(
            f'<div style="display:flex;flex-direction:column;gap:4px;">'
            f'<span class="studio-title">✝️ DailyWisdom Sacred AI Studio</span>'
            f'<span style="font-size:13px;color:#CBD5E1;font-weight:600;">Active Workspace: <b style="color:#FFFFFF;">{ch_disp}</b></span>'
            f'</div>',
            unsafe_allow_html=True
        )
    with tb_c2:
        st.markdown(
            f'<div style="display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap;padding-top:6px;">'
            f'<span class="status-pill">📺 {ch_disp}</span>'
            f'<span class="status-pill">🎬 {len(all_videos)} Renders</span>'
            f'<span class="status-pill-red">⚡ Studio Ready</span>'
            f'</div>',
            unsafe_allow_html=True
        )

"""
    new_content = content[:start_idx] + new_css + content[end_idx:]
    with open(app_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("✅ Successfully updated app.py with Animated Premium Glassmorphism!")
else:
    print("⚠️ Could not find the sections to replace.")
