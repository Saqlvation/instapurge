# InstaPurge 🧹

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Clean your Instagram followers in one pass.**  
> Detect bots, mass-followers, and ghost accounts. Remove them automatically.  
> No API keys. No paid services. No manual scrolling for hours.

---

## The Problem

You have 8,000 followers. Maybe 300 are bots, mass-followers, or empty accounts with 5,000 following and 3 followers. Instagram doesn't give you a "remove bots" button. You can:

- **Remove manually** → 8 hours of clicking, scrolling, crying  
- **Pay $50/month** for some sketchy SaaS that wants your password  
- **Use InstaPurge** → Free, open-source, runs on your machine, done in 45 minutes

---

## What It Does

1. **Logs in** to your Instagram via browser automation (Playwright)
2. **Fetches your full follower list** using network interception — it catches the JSON that Instagram's own web app loads
3. **Scans every follower** with 50 concurrent API requests — checks follower/following ratios, post counts, privacy status, profile pictures
4. **Removes bots in one pass** through your followers dialog — finds them, clicks Remove, confirms, moves on
5. **Saves progress** — if Instagram rate-limits you, resume tomorrow without re-scanning or re-removing

---

## Features

- ⚡ **Fast** — 8,000 followers scanned in ~10 minutes, removed in ~30 minutes
- 🔒 **Secure** — Runs entirely on your machine, zero data sent to third parties
- 🧠 **Smart detection** — Flags accounts with high following + low followers, no posts, no profile pic, suspicious usernames
- 🔄 **Resumable** — Rate-limited? Save progress and continue later from where you stopped
- 🖥️ **Clean UI** — Rich terminal interface with progress bars, tables, and a settings menu
- 🚫 **Rate-limit aware** — Detects Instagram action blocks and pauses gracefully
- 🆓 **Free & open source** — No paywalls, no subscriptions, no account access sold to advertisers

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/Saqlvation/instapurge.git
cd instapurge
pip install -r requirements.txt
playwright install chromium
```

> **Windows users**: Run the commands in PowerShell or CMD. If `playwright` isn't found after pip install, use `python -m playwright install chromium`.

### 2. Configure

Copy the example config and fill in your Instagram credentials:

```bash
# Edit config.json with your credentials
```

### 3. Run

```bash
python instapurge.py
```

You'll see a menu:

```
┌─────────── Menu ───────────┐
│                            │
│  1. Dry Run (scan only)    │
│  2. Live Run (scan + remove│
│  3. Settings               │
│  4. Clear Cache & Session  │
│  5. Exit                   │
│                            │
└────────────────────────────┘
```

**Always start with Dry Run (Option 1)** to preview what would be removed.

---

## How It Works

| Phase | What Happens | Time |
|-------|-------------|------|
| **Login** | Playwright opens Chrome, logs you in, steals session cookies | ~10s |
| **Fetch** | Opens your followers dialog, intercepts Instagram's API responses as you scroll | 5–10 min |
| **Scan** | Fires 50 concurrent `httpx` requests to Instagram's `web_profile_info` endpoint for stats | ~5 min |
| **Remove** | One pass through the followers dialog — removes flagged accounts as they appear | 20–40 min |

**Total for 8,000 followers: ~45 minutes.**

---

## Configuration

Edit `config.json`:

```json
{
  "username": "your_username",
  "password": "your_password",
  "following_threshold": 500,
  "min_follower_ratio": 0.1,
  "headless": false,
  "dry_run": true,
  "max_removals_per_session": 50,
  "delay_min": 3.0,
  "delay_max": 6.0
}
```

| Setting | Description | Default |
|---------|-------------|---------|
| `username` / `password` | Your Instagram login | *(required)* |
| `following_threshold` | Flag accounts following more than this number | `500` |
| `min_follower_ratio` | Flag if `followers / following` is below this | `0.1` |
| `max_removals_per_session` | Stop after removing this many (prevents rate limits) | `50` |
| `delay_min` / `delay_max` | Random delay between removals, in seconds | `3.0` / `6.0` |
| `headless` | Run browser without visible window | `false` |
| `dry_run` | Preview mode — scan but don't remove | `true` |

**Tip**: If you have 8000+ followers and 200+ bots, start with `max_removals_per_session: 30` and `delay: 4-7s`. Run once per day until clean.

---

## Bot Detection

An account is flagged when it hits **2 or more** of these:

- 🔴 **Following > threshold** (default 500) — mass-follower behavior
- 🔴 **Follower ratio < 0.1** — follows 1000 people, followed by 50
- 🔴 **No profile picture** — default silhouette
- 🔴 **Private + 0 posts** — dead or bot account
- 🔴 **Suspicious username** — random strings, excessive numbers

---

## Screenshots

*Add your own screenshots here — terminal menu, scan progress, flagged results table.*

```
┌─ Flagged Accounts (47 total) ─┐
│ Username    │ Following │ Followers │ Reason                │
├─────────────┼───────────┼───────────┼───────────────────────┤
│ @bot_123456 │      5421 │         3 │ following>500, ratio  │
│ @spam_acc   │      3200 │        12 │ following>500, ratio  │
│ @fake_user  │       890 │         0 │ following>500, 0-foll │
└─────────────┴───────────┴───────────┴───────────────────────┘
```

---

## Rate Limits & Safety

Instagram limits bulk actions to prevent spam. If you remove too many too fast, you'll see:

> "Action Blocked. Please try again later."

**InstaPurge handles this automatically:**
- Detects the block and stops immediately
- Saves which accounts were already removed to `progress.json`
- Tells you to wait 24 hours
- On next run, skips already-removed accounts

**To avoid rate limits:**
- Keep `max_removals_per_session` at 30–50
- Keep `delay_min` / `delay_max` at 3–7 seconds
- Don't run multiple Instagram automations at the same time
- Don't log in and out repeatedly

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'playwright'` | Run `pip install -r requirements.txt` then `playwright install chromium` |
| Login fails / stuck on login page | Check `error_debug.png` in the folder. Instagram may require 2FA or a security check. Complete it manually in the browser window, then the script continues. |
| Only finds a few followers | Delete `followers_cache.json` and re-run. Instagram sometimes serves partial lists. |
| "Rate limited" / "Action Blocked" | Wait 24 hours. Your progress is saved in `progress.json`. |
| Browser window doesn't open | Run `playwright install chromium`. If on Linux, you may need `xvfb`. |
| `division by zero` error | Fixed in latest version — pull the latest code. |
| Removal says "not found in list" | The user may have already unfollowed you, or the dialog hasn't scrolled far enough. The script retries automatically. |

---

## How It Compares

| | **InstaPurge** | Paid SaaS (e.g. HypeAuditor) | Manual Removal |
|---|:---:|:---:|:---:|
| Cost | Free | $30–100/mo | Free |
| Privacy | Your machine only | Their servers | Your machine |
| Speed (8K followers) | ~45 min | ~30 min | 8+ hours |
| Open source | ✅ | ❌ | N/A |
| Rate limit handling | ✅ Auto-save & resume | ❌ Often ignored | N/A |
| No password sharing | ✅ | ❌ | ✅ |
| Works offline | ✅ (after login) | ❌ | ✅ |

---

## File Structure

```
instapurge/
├── instapurge.py          # Main script
├── config.example.json    # Example configuration
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── LICENSE                # MIT License
├── .gitignore             # Ignores config.json, caches, reports
├── session.json           # Auto-generated: login session
├── followers_cache.json   # Auto-generated: your follower list
├── progress.json          # Auto-generated: removal progress
└── report_*.json          # Auto-generated: scan reports
```

---

## Contributing

PRs welcome. Especially:
- Better bot detection heuristics
- GUI version (Tkinter / Electron)
- Support for Threads, TikTok, Twitter
- Multi-account support
- Docker container

1. Fork the repo
2. Create a branch: `git checkout -b feature/amazing-thing`
3. Commit: `git commit -m 'Add amazing thing'`
4. Push: `git push origin feature/amazing-thing`
5. Open a Pull Request

---

## Disclaimer

This tool is for **cleaning your own Instagram account**. Use it responsibly. Instagram's Terms of Service prohibit automated actions — while this tool mimics human behavior with delays and randomization, there is always a risk of temporary action blocks. The authors are not responsible for any account restrictions.

**Do not use this to harass, spam, or target other users.**

---

## License

MIT © Saqlvation — see [LICENSE](LICENSE) for details.

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Saqlvation/instapurge&type=Date)](https://star-history.com/#Saqlvation/instapurge&Date)

---

**If InstaPurge saved you hours of clicking, give it a ⭐ and tell a friend.**
