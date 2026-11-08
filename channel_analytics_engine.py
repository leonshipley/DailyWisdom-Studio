import os
import re
import json
import pickle
import collections
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import main as backend

BASE_DIR = Path(__file__).resolve().parent

FULL_ANALYTICS_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

COUNTRY_MAP = {
    "IN": "India \U0001f1ee\U0001f1f3",
    "US": "United States \U0001f1fa\U0001f1f8",
    "GB": "United Kingdom \U0001f1ec\U0001f1e7",
    "PH": "Philippines \U0001f1f5\U0001f1ed",
    "CA": "Canada \U0001f1e8\U0001f1e6",
    "AU": "Australia \U0001f1e6\U0001f1fa",
    "NG": "Nigeria \U0001f1f3\U0001f1ec",
    "ZA": "South Africa \U0001f1ff\U0001f1e6",
    "KE": "Kenya \U0001f1f0\U0001f1ea",
    "BR": "Brazil \U0001f1e7\U0001f1f7",
    "DE": "Germany \U0001f1e9\U0001f1ea",
    "GH": "Ghana \U0001f1ec\U0001f1ed",
    "SG": "Singapore \U0001f1f8\U0001f1ec",
    "NZ": "New Zealand \U0001f1f3\U0001f1ff",
    "PK": "Pakistan \U0001f1f5\U0001f1f0",
    "ID": "Indonesia \U0001f1ee\U0001f1e9",
    "MY": "Malaysia \U0001f1f2\U0001f1fe",
    "AE": "UAE \U0001f1e6\U0001f1ea",
    "UG": "Uganda \U0001f1fa\U0001f1ec",
    "MX": "Mexico \U0001f1f2\U0001f1fd",
}

TRAFFIC_SOURCE_MAP = {
    "SHORTS": "\U0001f4f1 YouTube Shorts Feed",
    "YT_SEARCH": "\U0001f50d YouTube Search",
    "BROWSE": "\U0001f3e0 Home / Browse Features",
    "RELATED_VIDEO": "\U0001f449 Suggested Videos",
    "YT_CHANNEL": "\U0001f4fa Channel Page",
    "EXT_URL": "\U0001f310 External Websites / WhatsApp",
    "NOTIFICATION": "\U0001f514 Subscriber Notifications",
    "PLAYLIST": "\U0001f4cb Playlists",
    "SUBSCRIBER": "\U0001f465 Subscriptions Feed",
    "END_SCREEN": "\U0001f3ac End Screens",
    "NO_LINK_OTHER": "\U0001f4ca Direct / Other",
}

def parse_iso_sec(dur_str: str) -> int:
    if not dur_str:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur_str)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)

def format_dur_mmss(seconds: int) -> str:
    h, rem = divmod(max(0, int(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def reauthorize_channel_full_analytics(channel_name: str) -> Tuple[bool, str]:
    """Opens Google OAuth consent screen with full YouTube Data + YouTube Analytics scopes."""
    secret_f = backend.CLIENT_SECRET_FILE
    if not secret_f.exists():
        return False, "Missing client_secret.json in project root!"
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(secret_f), FULL_ANALYTICS_SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
        yt = build("youtube", "v3", credentials=creds)
        res = yt.channels().list(mine=True, part="snippet").execute()
        if not res.get("items"):
            return False, "No YouTube channel found on the selected Google account."
        actual_title = res["items"][0]["snippet"]["title"]
        safe_name = re.sub(r'[\/*?:"<>| ]', "_", actual_title)
        token_file = backend.CHANNELS_DIR / f"{safe_name}.pickle"
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)
        channels = backend.load_channels()
        channels[actual_title] = str(token_file)
        backend.save_channels(channels)
        return True, actual_title
    except Exception as e:
        return False, str(e)

def _load_creds(channel_name: str):
    channels = backend.load_channels()
    token_path = channels.get(channel_name)
    if not token_path or not Path(token_path).exists():
        return None
    try:
        with open(token_path, "rb") as f:
            creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "wb") as f:
                    pickle.dump(creds, f)
            else:
                return None
        return creds
    except Exception:
        return None

def fetch_complete_channel_intelligence(channel_name: str, days_back: int = 90) -> Dict[str, Any]:
    """
    Fetches comprehensive channel & video analytics:
    - Channel Overview: Subscribers, Lifetime Views, Total Videos, Handle, Age, Avatar
    - All Uploaded Videos (up to 150 videos, both Shorts and Long-Form)
    - Aggregated Likes, Comments, Engagement Rate %, Views in last 7d / 28d
    - YouTube Analytics v2 Reports:
      1. Daily Views, Watch Minutes & Net Subscribers
      2. Geographical Country Breakdown (Views, Watch Minutes, Avg View %, Subs Gained)
      3. Traffic Sources (Shorts Feed, Search, Browse, Suggested)
      4. Device Types (Mobile, TV, Desktop, Tablet)
      5. Best Posting Hours in IST (UTC+5:30)
    """
    result: Dict[str, Any] = {
        "ok": False,
        "error": None,
        "needs_reauth": False,
        "analytics_api_notice": None,
        "overview": {
            "title": channel_name,
            "handle": "",
            "channel_id": "",
            "published_at": "",
            "channel_age_days": 1,
            "country": "IN",
            "subscribers": 0,
            "hidden_subscribers": False,
            "lifetime_views": 0,
            "total_videos": 0,
        },
        "totals": {
            "analyzed_videos": 0,
            "shorts_count": 0,
            "longform_count": 0,
            "shorts_views": 0,
            "longform_views": 0,
            "total_likes": 0,
            "total_comments": 0,
            "engagement_rate_pct": 0.0,
            "views_last_7d_uploads": 0,
            "views_last_28d_uploads": 0,
            "avg_views_per_short": 0,
            "avg_views_per_longform": 0,
            "watch_time_minutes_period": 0,
            "avg_view_duration_sec": 0,
            "subs_gained_period": 0,
        },
        "videos": [],
        "daily_rows": [],
        "geo_rows": [],
        "traffic_rows": [],
        "device_rows": [],
        "best_hours_ist": [],
    }

    creds = _load_creds(channel_name)
    if not creds:
        result["error"] = f"Channel '{channel_name}' is not authenticated. Click 'Grant Full Analytics Permission' below."
        result["needs_reauth"] = True
        return result

    now_utc = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # PART 1: YOUTUBE DATA API v3 (CHANNEL OVERVIEW + ALL VIDEOS)
    # ------------------------------------------------------------------
    try:
        yt = build("youtube", "v3", credentials=creds)
        ch_res = yt.channels().list(mine=True, part="snippet,statistics,contentDetails").execute()
        if not ch_res.get("items"):
            result["error"] = "No YouTube channel found on this token."
            return result

        ch_item = ch_res["items"][0]
        snip = ch_item.get("snippet", {})
        stats = ch_item.get("statistics", {})
        c_details = ch_item.get("contentDetails", {})

        pub_str = snip.get("publishedAt", "")
        try:
            ch_pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            ch_age = max(1, int((now_utc - ch_pub_dt).total_seconds() // 86400))
        except Exception:
            ch_age = 1

        result["overview"] = {
            "title": snip.get("title", channel_name),
            "handle": snip.get("customUrl", ""),
            "channel_id": ch_item.get("id", ""),
            "published_at": pub_str[:10] if pub_str else "N/A",
            "channel_age_days": ch_age,
            "country": snip.get("country", "IN"),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "hidden_subscribers": bool(stats.get("hiddenSubscriberCount", False)),
            "lifetime_views": int(stats.get("viewCount", 0)),
            "total_videos": int(stats.get("videoCount", 0)),
        }

        uploads_pl = c_details.get("relatedPlaylists", {}).get("uploads", "")
        vid_ids: List[str] = []
        next_page = None

        # Fetch up to 150 recent uploads (3 pages of 50)
        for _ in range(3):
            if not uploads_pl:
                break
            pl_req = yt.playlistItems().list(
                playlistId=uploads_pl,
                part="contentDetails",
                maxResults=50,
                pageToken=next_page
            ).execute()
            for it in pl_req.get("items", []):
                v_id = it.get("contentDetails", {}).get("videoId")
                if v_id:
                    vid_ids.append(v_id)
            next_page = pl_req.get("nextPageToken")
            if not next_page:
                break

        all_vids: List[Dict[str, Any]] = []
        for i in range(0, len(vid_ids), 50):
            batch_ids = vid_ids[i:i+50]
            v_res = yt.videos().list(
                id=",".join(batch_ids),
                part="snippet,statistics,contentDetails"
            ).execute()
            for v in v_res.get("items", []):
                v_snip = v.get("snippet", {})
                v_stat = v.get("statistics", {})
                v_cd = v.get("contentDetails", {})

                dur_s = parse_iso_sec(v_cd.get("duration", ""))
                is_short = (0 < dur_s <= 180)
                v_pub = v_snip.get("publishedAt", "")
                try:
                    v_dt = datetime.fromisoformat(v_pub.replace("Z", "+00:00"))
                except Exception:
                    v_dt = now_utc

                age_d = max(0.1, (now_utc - v_dt).total_seconds() / 86400.0)
                views = int(v_stat.get("viewCount", 0))
                likes = int(v_stat.get("likeCount", 0))
                comments = int(v_stat.get("commentCount", 0))
                vpd = round(views / max(1.0, age_d), 1)
                eng_pct = round(((likes + comments) / max(1, views)) * 100.0, 2) if views > 0 else 0.0

                # Convert publish time to IST (UTC+5:30)
                ist_dt = v_dt + timedelta(hours=5, minutes=30)

                all_vids.append({
                    "id": v["id"],
                    "title": v_snip.get("title", "Untitled"),
                    "type": "\U0001f4f1 Short" if is_short else "\U0001f4fa Long-Form",
                    "is_short": is_short,
                    "duration_sec": dur_s,
                    "duration_str": format_dur_mmss(dur_s),
                    "views": views,
                    "views_per_day": vpd,
                    "likes": likes,
                    "comments": comments,
                    "engagement_pct": eng_pct,
                    "age_days": round(age_d, 1),
                    "published_date": ist_dt.strftime("%Y-%m-%d"),
                    "published_hour_ist": ist_dt.hour,
                    "url": f"https://www.youtube.com/watch?v={v['id']}"
                })

        all_vids.sort(key=lambda x: x["views"], reverse=True)
        result["videos"] = all_vids

        # Compute granular totals
        sh_vids = [x for x in all_vids if x["is_short"]]
        lf_vids = [x for x in all_vids if not x["is_short"]]

        sh_views = sum(x["views"] for x in sh_vids)
        lf_views = sum(x["views"] for x in lf_vids)
        tot_likes = sum(x["likes"] for x in all_vids)
        tot_comments = sum(x["comments"] for x in all_vids)
        tot_v_analyzed = sh_views + lf_views

        v_7d = sum(x["views"] for x in all_vids if x["age_days"] <= 7.0)
        v_28d = sum(x["views"] for x in all_vids if x["age_days"] <= 28.0)

        result["overview"]["lifetime_views"] = max(result["overview"]["lifetime_views"], tot_v_analyzed)
        result["overview"]["total_videos"] = max(result["overview"]["total_videos"], len(all_vids))
        est_watch_mins = int(round(sum(x["views"] * max(12, min(x["duration_sec"], 60)) * 0.78 for x in all_vids) / 60.0))

        result["totals"].update({
            "analyzed_videos": len(all_vids),
            "shorts_count": len(sh_vids),
            "longform_count": len(lf_vids),
            "shorts_views": sh_views,
            "longform_views": lf_views,
            "total_likes": tot_likes,
            "total_comments": tot_comments,
            "engagement_rate_pct": round(((tot_likes + tot_comments) / max(1, tot_v_analyzed)) * 100.0, 2) if tot_v_analyzed > 0 else 0.0,
            "views_last_7d_uploads": v_7d,
            "views_last_28d_uploads": v_28d,
            "avg_views_per_short": int(sh_views // max(1, len(sh_vids))) if sh_vids else 0,
            "avg_views_per_longform": int(lf_views // max(1, len(lf_vids))) if lf_vids else 0,
            "watch_time_minutes_period": est_watch_mins,
        })

        day_groups = collections.defaultdict(lambda: {"Views": 0, "Likes": 0, "Comments": 0, "Videos": 0, "Watch Minutes": 0})
        for x in all_vids:
            dk = x["published_date"]
            day_groups[dk]["Views"] += x["views"]
            day_groups[dk]["Likes"] += x["likes"]
            day_groups[dk]["Comments"] += x["comments"]
            day_groups[dk]["Videos"] += 1
            day_groups[dk]["Watch Minutes"] += int(round((x["views"] * max(12, x["duration_sec"]) * 0.78) / 60.0))
        result["daily_rows"] = [{"Date": k, **v} for k, v in sorted(day_groups.items())]

        # Best Posting Hour in IST
        hour_buckets = collections.defaultdict(list)
        for x in all_vids:
            hour_buckets[x["published_hour_ist"]].append(x["views"])
        best_hours = []
        for hr, v_list in hour_buckets.items():
            ampm = f"{hr % 12 or 12}:00 {'AM' if hr < 12 else 'PM'} IST"
            best_hours.append({
                "hour_ist": ampm,
                "videos_posted": len(v_list),
                "avg_views": int(sum(v_list) // max(1, len(v_list))),
                "total_views": sum(v_list)
            })
        best_hours.sort(key=lambda x: x["avg_views"], reverse=True)
        result["best_hours_ist"] = best_hours
        result["ok"] = True

    except Exception as e_data:
        err_s = str(e_data)
        result["error"] = f"YouTube Data API Error: {err_s[:180]}"
        if "insufficientPermissions" in err_s or "403" in err_s:
            result["needs_reauth"] = True
        return result

    # ------------------------------------------------------------------
    # PART 2: YOUTUBE ANALYTICS API v2 (DAILY, GEOGRAPHY, TRAFFIC, DEVICES)
    # ------------------------------------------------------------------
    try:
        yt_ana = build("youtubeAnalytics", "v2", credentials=creds)
        end_str = now_utc.strftime("%Y-%m-%d")
        start_str = (now_utc - timedelta(days=days_back)).strftime("%Y-%m-%d")

        # A. Daily Views, Watch Time & Subscribers Gained
        try:
            rep_day = yt_ana.reports().query(
                ids="channel==MINE",
                startDate=start_str,
                endDate=end_str,
                metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
                dimensions="day",
                sort="day"
            ).execute()
            d_rows = []
            tot_wm = 0
            tot_sg = 0
            dur_weighted = 0.0
            v_sum = 0
            for r in rep_day.get("rows", []):
                day_str, v_c, wm, avd, sg, sl = r[0], int(r[1]), int(r[2]), float(r[3]), int(r[4]), int(r[5])
                net_s = sg - sl
                tot_wm += wm
                tot_sg += net_s
                dur_weighted += v_c * avd
                v_sum += v_c
                d_rows.append({
                    "Date": day_str,
                    "Views": v_c,
                    "Watch Minutes": wm,
                    "Avg Duration (s)": round(avd, 1),
                    "Net Subscribers": net_s
                })
            if d_rows and sum(x["Views"] for x in d_rows) > 0:
                result["daily_rows"] = d_rows
            if tot_wm > 0:
                result["totals"]["watch_time_minutes_period"] = tot_wm
            result["totals"]["subs_gained_period"] = tot_sg
            if v_sum > 0:
                result["totals"]["avg_view_duration_sec"] = round(dur_weighted / v_sum, 1)
        except Exception as e_day:
            result["analytics_api_notice"] = str(e_day)[:160]

        # B. Geography (Country Breakdown with Watch Time & Retention)
        try:
            rep_geo = yt_ana.reports().query(
                ids="channel==MINE",
                startDate=start_str,
                endDate=end_str,
                metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained",
                dimensions="country",
                sort="-views",
                maxResults=15
            ).execute()
            g_rows = rep_geo.get("rows", [])
            tot_gv = sum(int(r[1]) for r in g_rows) or 1
            for r in g_rows:
                cc = str(r[0]).upper()
                v_c = int(r[1])
                wm = int(r[2])
                avd = round(float(r[3]), 1)
                apv = round(float(r[4]), 1)
                sg = int(r[5])
                result["geo_rows"].append({
                    "Country": COUNTRY_MAP.get(cc, f"{cc} \U0001f310"),
                    "Code": cc,
                    "Views": v_c,
                    "Share %": round((v_c / tot_gv) * 100.0, 1),
                    "Watch Minutes": wm,
                    "Avg View (s)": avd,
                    "Avg Retention %": apv,
                    "Subs Gained": sg
                })
        except Exception as e_geo:
            if not result["analytics_api_notice"]:
                result["analytics_api_notice"] = str(e_geo)[:160]

        # C. Traffic Sources (Shorts Feed vs Search vs Suggested)
        try:
            rep_tr = yt_ana.reports().query(
                ids="channel==MINE",
                startDate=start_str,
                endDate=end_str,
                metrics="views,estimatedMinutesWatched",
                dimensions="insightTrafficSourceType",
                sort="-views"
            ).execute()
            t_rows = rep_tr.get("rows", [])
            tot_tv = sum(int(r[1]) for r in t_rows) or 1
            for r in t_rows:
                raw_src = str(r[0])
                v_c = int(r[1])
                wm = int(r[2])
                result["traffic_rows"].append({
                    "Traffic Source": TRAFFIC_SOURCE_MAP.get(raw_src, raw_src),
                    "Views": v_c,
                    "Share %": round((v_c / tot_tv) * 100.0, 1),
                    "Watch Minutes": wm
                })
        except Exception:
            pass

        # D. Device Types (Mobile vs TV vs Desktop)
        try:
            rep_dev = yt_ana.reports().query(
                ids="channel==MINE",
                startDate=start_str,
                endDate=end_str,
                metrics="views,estimatedMinutesWatched",
                dimensions="deviceType",
                sort="-views"
            ).execute()
            dv_rows = rep_dev.get("rows", [])
            tot_dv = sum(int(r[1]) for r in dv_rows) or 1
            for r in dv_rows:
                dev_name = str(r[0]).title()
                v_c = int(r[1])
                wm = int(r[2])
                result["device_rows"].append({
                    "Device": dev_name,
                    "Views": v_c,
                    "Share %": round((v_c / tot_dv) * 100.0, 1),
                    "Watch Minutes": wm
                })
        except Exception:
            pass

    except Exception as e_ana:
        result["analytics_api_notice"] = str(e_ana)[:160]

    return result
