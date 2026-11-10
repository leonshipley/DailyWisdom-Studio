import os

app_path = "app.py"
if not os.path.exists(app_path):
    print("❌ app.py not found!")
    exit()

with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

start_marker = "# CSS STYLING & SACRED JESUS GLASSMORPHISM"
end_marker = "# MASTER SETTINGS STRIP"

start_idx = content.find(start_marker)
if start_idx != -1:
    start_idx = content.rfind("# ====", 0, start_idx)

end_idx = content.find(end_marker)
if end_idx != -1:
    end_idx = content.rfind("# ====", 0, end_idx)

if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
    new_css = """# ==============================================================================
# CSS STYLING: ELITE SILICON VALLEY SAAS AESTHETIC (VERCEL / LINEAR STYLE)
# ==============================================================================
st.markdown('''
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
    
    /* Deep Dark Mode Background */
    .stApp { 
        background-color: #000000 !important; 
        background-image: radial-gradient(circle at 50% 0%, rgba(29, 35, 41, 0.4) 0%, transparent 70%) !important; 
    }
    
    /* Layout & Header */
    .block-container { padding-top: 2.5rem !important; padding-bottom: 2.5rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { background: transparent !important; z-index: 10 !important; }
    
    /* Sleek Sidebar */
    section[data-testid="stSidebar"] { background-color: #050505 !important; border-right: 1px solid rgba(255, 255, 255, 0.08) !important; }
    
    /* Container Cards (Flat & Minimal) */
    div[data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #0A0A0A !important; 
        border: 1px solid rgba(255, 255, 255, 0.08) !important; 
        border-radius: 10px !important; 
        box-shadow: 0 8px 32px -12px rgba(0, 0, 0, 0.8) !important; 
    }
    
    /* Pills & Badges */
    .status-pill { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); color: #E4E4E7; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 500; letter-spacing: 0.3px; }
    .status-pill-red { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.25); color: #93C5FD; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 500; }
    .budget-badge { background: #111111; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 6px 12px; font-size: 12.5px; color: #A1A1AA; font-weight: 500; margin: 8px 0; display: inline-block; }
    
    /* Content Cards */
    .verse-card { background: #0A0A0A; border: 1px solid rgba(255, 255, 255, 0.08); border-left: 3px solid #EDEDED; border-radius: 8px; padding: 16px; margin: 10px 0; }
    .verse-hdr { font-size: 13px; font-weight: 600; color: #A1A1AA; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
    .verse-body { font-size: 15px; color: #EDEDED; line-height: 1.6; }
    
    /* Inputs & Media */
    img { border-radius: 8px; }
    video { width: 100% !important; max-height: 620px !important; border-radius: 8px; background: #000; border: 1px solid rgba(255,255,255,0.08); }
    
    /* Elite Primary Buttons (White on Black glow) */
    .stButton>button { 
        background: #FFFFFF !important; 
        color: #000000 !important; 
        font-weight: 600 !important; 
        border-radius: 6px !important; 
        border: none !important; 
        padding: 8px 16px !important; 
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important; 
    }
    .stButton>button:hover { background: #E4E4E7 !important; transform: translateY(-1px); box-shadow: 0 4px 14px rgba(255, 255, 255, 0.15) !important; }
    .stButton>button:active { transform: scale(0.98); }
    
    /* Secondary Buttons (Sidebar & Grid) */
    div[data-testid="stHorizontalBlock"] .stButton>button, section[data-testid="stSidebar"] .stButton>button { 
        background: #111111 !important; 
        color: #E4E4E7 !important; 
        border: 1px solid rgba(255, 255, 255, 0.12) !important; 
        box-shadow: none !important; 
        font-weight: 500 !important;
    }
    div[data-testid="stHorizontalBlock"] .stButton>button:hover, section[data-testid="stSidebar"] .stButton>button:hover { 
        background: #1A1A1A !important; 
        border-color: rgba(255, 255, 255, 0.2) !important; 
    }
    
    /* Minimalist Tabs */
    .stTabs [data-baseweb="tab"] { background: transparent !important; border: none !important; color: #71717A !important; font-weight: 500 !important; padding: 12px 16px !important; border-bottom: 2px solid transparent !important; border-radius: 0 !important; }
    .stTabs [aria-selected="true"] { color: #EDEDED !important; border-bottom: 2px solid #EDEDED !important; }
    
    /* Animated Loaders */
    @keyframes studio-spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .live-loader-card { background: #0A0A0A; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 16px 20px; margin: 10px 0; display: flex; align-items: center; gap: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
    .live-spinner-ring { width: 22px; height: 22px; min-width: 22px; border: 2px solid rgba(255, 255, 255, 0.05); border-top: 2px solid #EDEDED; border-right: 2px solid transparent; border-radius: 50%; animation: studio-spin 0.7s linear infinite; }
    .live-loader-title { font-size: 14px; font-weight: 600; color: #EDEDED; }
    .live-loader-sub { font-size: 12.5px; color: #A1A1AA; font-weight: 400; margin-top: 2px; }
</style>
''', unsafe_allow_html=True)

# ==============================================================================
# TOP BANNER (SaaS Style)
# ==============================================================================
ch_disp = channel_names[0] if channel_names else "Grace of the Lord (@GraceAndDailyPrayer)"

with st.container(border=True):
    tb_c1, tb_c2 = st.columns([1.5, 1.2], gap="medium")
    with tb_c1:
        st.markdown(
            f'<div style="display:flex;flex-direction:column;gap:4px;">'
            f'<span style="font-size:22px;font-weight:700;color:#EDEDED;letter-spacing:-0.5px;">DailyWisdom Studio</span>'
            f'<span style="font-size:13px;color:#A1A1AA;font-weight:400;">Active Workspace: <b style="color:#EDEDED;font-weight:500;">{ch_disp}</b></span>'
            f'</div>',
            unsafe_allow_html=True
        )
    with tb_c2:
        st.markdown(
            f'<div style="display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap;padding-top:6px;">'
            f'<span class="status-pill">Workspace: {ch_disp}</span>'
            f'<span class="status-pill">{len(all_videos)} Renders</span>'
            f'<span class="status-pill-red">Production Ready</span>'
            f'</div>',
            unsafe_allow_html=True
        )

"""
    new_content = content[:start_idx] + new_css + content[end_idx:]
    with open(app_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("✅ Successfully updated app.py with Elite SaaS Design!")
else:
    if "ELITE SILICON VALLEY SAAS AESTHETIC" in content:
        print("⚡ The design is already updated!")
    else:
        print("⚠️ Could not find the sections to replace. Make sure you haven't already modified it.")
