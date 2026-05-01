"""
Generates a run summary report detailing crawler sweep metrics and network refresh timestamps.
"""

import os
import re
from datetime import datetime, timezone
from collections import defaultdict
from wikipediaGATN.paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR

def format_utc(ts: float) -> str:
    """Format a timestamp to UTC ISO 8601 string ending with Z."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def generate_summary():
    rooted_sweep_dir = os.path.join(TEMP_RESULTS_DIR, "airports_rooted_sweep")
    fillup_sweep_dir = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports")
    network_refresh_file = os.path.join(PUBLIC_DATA_DIR, "global-air-pax-network.csv")
    output_file = os.path.join(PUBLIC_DATA_DIR, "run_summary.md")

    # 1. Rooted sweep info
    rooted_latest_time = 0.0
    level_counts = defaultdict(int)
    total_rooted = 0
    
    # Matches <CODE>.<level>.json or wiki_<NAME>.<level>.json
    fname_re = re.compile(r"^(?:[A-Z0-9\-]{3,10}|wiki_[A-Za-z0-9_]+|unknown)\.(\d+)\.json$")
    
    if os.path.isdir(rooted_sweep_dir):
        for fname in os.listdir(rooted_sweep_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(rooted_sweep_dir, fname)
                mtime = os.path.getmtime(fpath)
                if mtime > rooted_latest_time:
                    rooted_latest_time = mtime
                
                # Parse level
                m = fname_re.match(fname)
                if m:
                    lvl = int(m.group(1))
                    level_counts[lvl] += 1
                    total_rooted += 1

    rooted_time_str = format_utc(rooted_latest_time) if rooted_latest_time > 0 else "N/A"

    # 2. Fill-up sweep info
    fillup_latest_time = 0.0
    total_fillup = 0
    
    if os.path.isdir(fillup_sweep_dir):
        for fname in os.listdir(fillup_sweep_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(fillup_sweep_dir, fname)
                mtime = os.path.getmtime(fpath)
                if mtime > fillup_latest_time:
                    fillup_latest_time = mtime
                total_fillup += 1

    fillup_time_str = format_utc(fillup_latest_time) if fillup_latest_time > 0 else "N/A"

    # 3. Network refresh info
    refresh_time_str = "N/A"
    if os.path.isfile(network_refresh_file):
        mtime = os.path.getmtime(network_refresh_file)
        refresh_time_str = format_utc(mtime)

    # 4. Generate Markdown
    md = [
        "# Wikipedia GATN Crawler Run Summary",
        "",
        f"**Total nodes in network**: {total_rooted + total_fillup}",
        "",
        "## Last Timestamps",
        f"- **Last Rooted Sweep**: {rooted_time_str}",
        f"- **Last Fill-Up Sweep**: {fillup_time_str}",
        f"- **Last Network Refresh**: {refresh_time_str}",
        "",
        "## Rooted Sweep Breakdown",
        f"**Total airports found**: {total_rooted}",
        ""
    ]
    
    if total_rooted > 0:
        md.append("| Level | Airport Count |")
        md.append("|-------|---------------|")
        for lvl in sorted(level_counts.keys()):
            label = "0 (Root)" if lvl == 0 else str(lvl)
            md.append(f"| {label} | {level_counts[lvl]} |")
    else:
        md.append("_No rooted sweep data found._")
        
    md.append("")
    md.append("## Fill-Up Sweep Breakdown")
    md.append(f"**Total airports found**: {total_fillup}")
    md.append("")
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
        
    print(f"Successfully generated run summary at {output_file}")

if __name__ == "__main__":
    generate_summary()
