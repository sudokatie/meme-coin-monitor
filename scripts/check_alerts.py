#!/usr/bin/env python3
"""Check for new alerts and log them to Katie's alert journal."""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.storage.database import Database
from src.storage.repositories import AlertRepository


LAST_CHECK_FILE = Path("data/last_alert_check.json")
ALERT_JOURNAL = Path("/Users/halvo/clawd/memory/meme-coin-alerts.md")


def load_last_check() -> datetime:
    """Load timestamp of last check."""
    if LAST_CHECK_FILE.exists():
        try:
            with open(LAST_CHECK_FILE) as f:
                data = json.load(f)
                return datetime.fromisoformat(data["timestamp"])
        except Exception:
            pass
    # Default to 5 minutes ago
    return datetime.now(timezone.utc) - timedelta(minutes=5)


def save_last_check(ts: datetime) -> None:
    """Save timestamp of last check."""
    LAST_CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_CHECK_FILE, "w") as f:
        json.dump({"timestamp": ts.isoformat()}, f)


def format_alert_entry(alert) -> str:
    """Format alert for journal entry."""
    severity_prefix = {
        "CRITICAL": "[!!!]",
        "HIGH": "[!]",
        "MEDIUM": "[*]",
        "LOW": "[-]",
    }.get(alert.severity, "[?]")
    
    token_name = alert.data.get("token_name", "Unknown")
    token_symbol = alert.data.get("token_symbol", "???")
    risk_score = alert.data.get("risk_score", "N/A")
    risk_category = alert.data.get("risk_category", "")
    
    lines = [
        f"### {severity_prefix} {token_symbol} - {alert.alert_type}",
        f"**Time:** {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Token:** {token_name} ({token_symbol})",
        f"**Address:** `{alert.token_address}`",
        f"**Risk:** {risk_score}/100 ({risk_category})",
        f"**Message:** {alert.message}",
    ]
    
    signals = alert.data.get("signals", [])
    if signals:
        signal_strs = [f"{s.get('name', '?')} (+{s.get('contribution', 0)})" for s in signals[:5]]
        lines.append(f"**Signals:** {', '.join(signal_strs)}")
    
    lines.append(f"**Solscan:** https://solscan.io/token/{alert.token_address}")
    lines.append("")
    
    return "\n".join(lines)


def append_to_journal(entries: list[str], stats: dict) -> None:
    """Append new alerts to journal file."""
    # Create or update journal
    if not ALERT_JOURNAL.exists():
        header = """# Meme Coin Alert Journal

My log of detected rug pull risks and suspicious tokens. Learning patterns.

---

"""
        ALERT_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with open(ALERT_JOURNAL, "w") as f:
            f.write(header)
    
    # Append new entries
    with open(ALERT_JOURNAL, "a") as f:
        f.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} Check\n\n")
        if entries:
            f.write(f"Found {len(entries)} new alert(s):\n\n")
            for entry in entries:
                f.write(entry + "\n")
        else:
            f.write("No new alerts.\n\n")
        
        # Add stats summary
        if stats.get("critical", 0) > 0:
            f.write(f"**Summary:** {stats.get('critical', 0)} CRITICAL, {stats.get('high', 0)} HIGH\n\n")
        
        f.write("---\n")


async def check_alerts() -> tuple[list[str], dict]:
    """Check for new alerts since last check."""
    config = load_config()
    db = Database(config.database)
    await db.init()
    
    last_check = load_last_check()
    now = datetime.now(timezone.utc)
    
    entries = []
    stats = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    
    try:
        async with db.session() as session:
            repo = AlertRepository(session)
            alerts = await repo.get_recent(limit=50)
            
            # Filter to alerts since last check
            new_alerts = [
                a for a in alerts 
                if a.created_at and a.created_at > last_check
            ]
            
            for alert in new_alerts:
                entries.append(format_alert_entry(alert))
                severity = alert.severity.lower()
                if severity in stats:
                    stats[severity] += 1
        
        save_last_check(now)
        
    finally:
        await db.close()
    
    return entries, stats


async def main():
    """Main entry point."""
    entries, stats = await check_alerts()
    
    # Always log to journal
    append_to_journal(entries, stats)
    
    # Output for cron job
    if entries:
        total = len(entries)
        critical = stats.get("critical", 0)
        high = stats.get("high", 0)
        
        print(f"ALERTS_LOGGED:{total}")
        if critical > 0:
            print(f"CRITICAL_COUNT:{critical}")
        if high > 0:
            print(f"HIGH_COUNT:{high}")
        
        # Flag if something needs human attention
        if critical >= 2 or (critical >= 1 and high >= 2):
            print("NOTIFY_JORDAN:Multiple critical alerts detected")
    else:
        print("NO_NEW_ALERTS")


if __name__ == "__main__":
    asyncio.run(main())
