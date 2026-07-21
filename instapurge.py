#!/usr/bin/env python3
"""
InstaPurge — Instagram Follower Cleaner
Automated bot detection and removal for Instagram followers.
"""

import asyncio
import json
import time
import random
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Optional, Tuple
from pathlib import Path
from datetime import datetime

import httpx
from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm


console = Console()


@dataclass
class Follower:
    username: str
    user_id: str = ""
    followers: int = 0
    following: int = 0
    posts: int = 0
    is_private: bool = False
    has_profile_pic: bool = True
    is_bot: bool = False
    reason: str = ""

    def to_dict(self):
        return asdict(self)


class InstaPurge:
    BASE_URL = "https://www.instagram.com"
    WEB_API = "https://www.instagram.com/api/v1"

    def __init__(self):
        self.config = self._load_config()
        self.username = self.config.get("username", "")
        self.password = self.config.get("password", "")
        self.following_threshold = self.config.get("following_threshold", 500)
        self.min_ratio = self.config.get("min_follower_ratio", 0.1)
        self.max_removals = self.config.get("max_removals_per_session", 50)
        self.dry_run = self.config.get("dry_run", True)
        self.headless = self.config.get("headless", False)
        self.delay_min = self.config.get("delay_min", 3.0)
        self.delay_max = self.config.get("delay_max", 6.0)

        self.cookies: Dict[str, str] = {}
        self.csrf = ""
        self.ds_user_id = ""
        self.ig_app_id = "936619743392459"

        self.followers: List[Follower] = []
        self.flagged: List[Follower] = []
        self.removed_count = 0
        self.rate_limited = False

    def _load_config(self) -> dict:
        path = Path("config.json")
        if not path.exists():
            default = {
                "username": "",
                "password": "",
                "following_threshold": 500,
                "min_follower_ratio": 0.1,
                "headless": False,
                "dry_run": True,
                "max_removals_per_session": 50,
                "delay_min": 3.0,
                "delay_max": 6.0
            }
            with open(path, "w") as f:
                json.dump(default, f, indent=2)
            console.print("[yellow]Created config.json. Please edit it with your credentials.[/yellow]")
            return default

        with open(path) as f:
            return json.load(f)

    def _save_config(self):
        with open("config.json", "w") as f:
            json.dump(self.config, f, indent=2)

    def _api_headers(self) -> Dict[str, str]:
        return {
            "X-IG-App-ID": self.ig_app_id,
            "X-ASBD-ID": "129477",
            "X-IG-WWW-Claim": "0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.BASE_URL}/",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }

    def _ensure_credentials(self):
        if not self.username or not self.password:
            console.print("[yellow]Please enter your Instagram credentials:[/yellow]")
            self.username = Prompt.ask("Username")
            self.password = Prompt.ask("Password", password=True)
            self.config["username"] = self.username
            self.config["password"] = self.password
            self._save_config()

    async def login(self, page: Page) -> bool:
        console.print(Panel.fit("[bold blue]Logging in...[/bold blue]"))

        await page.goto(f"{self.BASE_URL}/accounts/login/")
        await asyncio.sleep(2)

        # Cookie banner
        cookie_selectors = [
            "button:has-text('Allow all cookies')",
            "button:has-text('Accept')",
            "button:has-text('Agree')",
            "button:has-text('OK')",
            "div[role='button']:has-text('Accept')",
            "div[role='button']:has-text('Agree')",
            "._a9--", "._a9_1", "._a9_0",
        ]
        for sel in cookie_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(1)
                    break
            except:
                continue

        # Fill credentials
        try:
            await page.locator("input").nth(0).fill(self.username)
            await page.locator("input[type='password']").first.fill(self.password)
        except Exception as e:
            console.print(f"[red]Failed to fill credentials: {e}[/red]")
            return False

        await asyncio.sleep(0.5)

        # Submit
        clicked = False
        for sel in ["button[type='submit']", "button:has-text('Log in')", "div[role='button']:has-text('Log in')", "._acap"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    clicked = True
                    break
            except:
                continue

        if not clicked:
            await page.locator("input[type='password']").first.press("Enter")

        # 2FA
        try:
            two_fa = page.locator("input[name='verificationCode'], input[placeholder*='code' i]").first
            if await two_fa.is_visible(timeout=10000):
                code = Prompt.ask("[bold red]Enter 2FA code[/bold red]")
                await two_fa.fill(code)
                for sel in ["button:has-text('Confirm')", "button:has-text('Submit')"]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            break
                    except:
                        continue
        except:
            pass

        # Wait for feed
        try:
            await page.wait_for_selector("nav, [role='navigation'], svg[aria-label='Home'], main", timeout=20000)
        except:
            console.print("[red]Login failed — check if Instagram requires verification[/red]")
            return False

        # Extract cookies
        cookies = await page.context.cookies()
        for c in cookies:
            self.cookies[c["name"]] = c["value"]
            if c["name"] == "csrftoken":
                self.csrf = c["value"]
            if c["name"] == "ds_user_id":
                self.ds_user_id = c["value"]

        # Save session
        with open("session.json", "w") as f:
            json.dump(self.cookies, f)

        console.print("[bold green]Logged in successfully![/bold green]")
        return True

    async def fetch_followers_api(self) -> List[Follower]:
        if not self.ds_user_id:
            return []

        followers = []
        next_max_id = None

        async with httpx.AsyncClient(
            cookies=self.cookies,
            headers=self._api_headers(),
            timeout=30.0,
            follow_redirects=True
        ) as client:
            for batch_num in range(50):
                url = f"{self.WEB_API}/friendships/{self.ds_user_id}/followers/?count=200"
                if next_max_id:
                    url += f"&max_id={next_max_id}"

                try:
                    resp = await client.get(url)
                    data = resp.json()

                    if "users" not in data:
                        break

                    for user in data["users"]:
                        followers.append(Follower(
                            username=user.get("username", ""),
                            user_id=str(user.get("pk", "")),
                            has_profile_pic=not user.get("has_anonymous_profile_picture", False)
                        ))

                    next_max_id = data.get("next_max_id")
                    if not next_max_id:
                        break

                    await asyncio.sleep(random.uniform(0.3, 0.6))

                except Exception as e:
                    console.print(f"[dim]API batch {batch_num+1} failed: {e}[/dim]")
                    break

        return followers

    async def fetch_followers_interception(self, page: Page) -> List[Follower]:
        console.print(Panel.fit("[bold blue]Fetching followers via network interception...[/bold blue]"))

        followers = []
        seen_ids: Set[str] = set()

        async def handle_response(response):
            url = response.url
            if "friendships" in url and "followers" in url:
                try:
                    data = await response.json()
                    for user in data.get("users", []):
                        pk = str(user.get("pk", ""))
                        if pk and pk not in seen_ids:
                            seen_ids.add(pk)
                            followers.append(Follower(
                                username=user.get("username", ""),
                                user_id=pk,
                                has_profile_pic=not user.get("has_anonymous_profile_picture", False)
                            ))
                except:
                    pass

        page.on("response", lambda r: asyncio.create_task(handle_response(r)))

        await page.goto(f"{self.BASE_URL}/{self.username}/")
        await asyncio.sleep(1)

        for sel in [
            f"a[href='/{self.username}/followers/']",
            f"a[href='/{self.username}/followers']",
            "header a:has-text('followers')",
            "section a:has-text('followers')",
            "span:has-text('followers')",
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(2)
                    break
            except:
                continue

        try:
            await page.wait_for_selector("div[role='dialog']", timeout=10000)
        except:
            pass

        last_count = 0
        stagnant = 0

        for _ in range(500):
            current = len(followers)
            if current > last_count:
                last_count = current
                stagnant = 0
                console.print(f"[dim]Loaded {current} followers...[/dim]")
            else:
                stagnant += 1
                if stagnant >= 10:
                    break

            await page.evaluate("""
                () => {
                    const dialog = document.querySelector('div[role="dialog"]');
                    if (!dialog) return;
                    for (const div of dialog.querySelectorAll('div')) {
                        if (div.scrollHeight > div.clientHeight + 100 && div.scrollHeight > 500) {
                            div.scrollTop += 1200;
                            break;
                        }
                    }
                }
            """)
            await asyncio.sleep(random.uniform(0.5, 1.0))

        return followers

    async def fetch_followers(self, page: Page) -> List[Follower]:
        cache_path = Path("followers_cache.json")
        if cache_path.exists():
            if Confirm.ask("[yellow]Use cached follower list?[/yellow]", default=True):
                with open(cache_path) as f:
                    data = json.load(f)
                    return [Follower(**d) for d in data]

        api_followers = await self.fetch_followers_api()
        if len(api_followers) > 100:
            console.print(f"[green]Fetched {len(api_followers)} followers via API[/green]")
            self._save_cache(api_followers)
            return api_followers

        console.print("[yellow]API returned few results, using network interception...[/yellow]")
        intercepted = await self.fetch_followers_interception(page)
        self._save_cache(intercepted)
        return intercepted

    def _save_cache(self, followers: List[Follower]):
        with open("followers_cache.json", "w") as f:
            json.dump([f.to_dict() for f in followers], f, indent=2)

    async def scan_follower(self, client: httpx.AsyncClient, follower: Follower) -> Follower:
        try:
            url = f"{self.WEB_API}/users/web_profile_info/?username={follower.username}"
            resp = await client.get(url, headers=self._api_headers(), timeout=10.0)

            if resp.status_code == 429:
                await asyncio.sleep(5)
                resp = await client.get(url, headers=self._api_headers(), timeout=10.0)

            data = resp.json()
            if "data" not in data or "user" not in data["data"]:
                return follower

            user = data["data"]["user"]

            follower.followers = user.get("edge_followed_by", {}).get("count", 0)
            follower.following = user.get("edge_follow", {}).get("count", 0)
            follower.posts = user.get("edge_owner_to_timeline_media", {}).get("count", 0)
            follower.is_private = user.get("is_private", False)
            follower.has_profile_pic = not user.get("has_anonymous_profile_picture", False)

            reasons = []
            if follower.following > self.following_threshold:
                reasons.append(f"following>{self.following_threshold}")

            if follower.following > 0 and follower.followers > 0:
                if follower.followers / follower.following < self.min_ratio:
                    reasons.append(f"ratio<{self.min_ratio}")
            elif follower.following > 100 and follower.followers == 0:
                reasons.append("0-followers")

            if not follower.has_profile_pic:
                reasons.append("no-pfp")

            if follower.is_private and follower.posts == 0:
                reasons.append("private+0posts")

            if len(reasons) >= 2:
                follower.is_bot = True
                follower.reason = ", ".join(reasons)

        except Exception:
            pass

        return follower

    async def scan_all(self):
        console.print(Panel.fit("[bold blue]Scanning followers for bots...[/bold blue]"))

        semaphore = asyncio.Semaphore(50)

        async def check(client, f):
            async with semaphore:
                return await self.scan_follower(client, f)

        async with httpx.AsyncClient(
            cookies=self.cookies,
            headers=self._api_headers(),
            timeout=15.0,
            follow_redirects=True
        ) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Scanning...", total=len(self.followers))

                chunk_size = 100
                for i in range(0, len(self.followers), chunk_size):
                    chunk = self.followers[i:i + chunk_size]
                    results = await asyncio.gather(*[check(client, f) for f in chunk], return_exceptions=True)

                    for j, result in enumerate(results):
                        if isinstance(result, Follower):
                            self.followers[i + j] = result
                            if result.is_bot:
                                self.flagged.append(result)

                    progress.update(task, advance=len(chunk))
                    await asyncio.sleep(0.2)

        console.print(f"[bold green]Scan complete. Found {len(self.flagged)} suspicious accounts.[/bold green]")

    def show_results(self):
        if not self.flagged:
            console.print("[green]No suspicious followers found![/green]")
            return

        table = Table(
            title=f"Flagged Accounts ({len(self.flagged)} total)",
            show_header=True,
            header_style="bold red"
        )
        table.add_column("Username", style="cyan")
        table.add_column("Following", justify="right", style="red")
        table.add_column("Followers", justify="right", style="green")
        table.add_column("Posts", justify="right", style="yellow")
        table.add_column("Reason", style="white")

        for f in self.flagged[:50]:
            table.add_row(
                f"@{f.username}",
                str(f.following),
                str(f.followers),
                str(f.posts),
                f.reason
            )

        if len(self.flagged) > 50:
            table.add_row(f"... and {len(self.flagged) - 50} more", "", "", "", "")

        console.print(table)

    async def remove_all(self, page: Page):
        if not self.flagged:
            return

        to_remove = self.flagged[:self.max_removals]
        flagged_set = {f.username.lower() for f in to_remove}

        console.print(Panel.fit(
            f"[bold red]Removing {len(to_remove)} accounts...[/bold red]",
            border_style="red"
        ))

        if self.dry_run:
            console.print("[bold yellow]DRY RUN — preview only[/bold yellow]")
            for f in to_remove:
                console.print(f"[dim]Would remove @{f.username} — {f.reason}[/dim]")
            return

        progress_path = Path("progress.json")
        already_removed: Set[str] = set()
        if progress_path.exists():
            with open(progress_path) as f:
                data = json.load(f)
                already_removed = set(data.get("removed", []))

        await page.goto(f"{self.BASE_URL}/{self.username}/followers/")
        await asyncio.sleep(2)

        try:
            await page.wait_for_selector("div[role='dialog']", timeout=10000)
        except:
            pass

        removed_this_run: List[str] = []
        last_count = 0
        stagnant = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[red]Removing...", total=len(to_remove))

            for _ in range(600):
                # Check for rate limit
                try:
                    content = await page.content()
                    if "action blocked" in content.lower() or "restrict" in content.lower():
                        console.print("[bold red]Rate limited by Instagram! Saving progress...[/bold red]")
                        self.rate_limited = True
                        break
                except:
                    pass

                rows = await page.locator("div[role='dialog'] div:has(a[href^='/'])").all()
                removed_in_view = 0

                for row in rows:
                    try:
                        link = row.locator("a[href^='/']").first
                        if not link:
                            continue

                        href = await link.get_attribute("href")
                        if not href:
                            continue

                        username = href.strip("/").split("/")[0].lower()

                        if username not in flagged_set or username in already_removed:
                            continue

                        btn = row.locator("button:has-text('Remove'), [role='button']:has-text('Remove')").first
                        if not btn or not await btn.is_visible(timeout=500):
                            all_btns = await row.locator("button, [role='button']").all()
                            for b in all_btns:
                                try:
                                    if "remove" in (await b.inner_text()).lower():
                                        btn = b
                                        break
                                except:
                                    continue

                        if btn and await btn.is_visible(timeout=500):
                            await btn.click()
                            await asyncio.sleep(0.5)

                            try:
                                confirm = page.locator("button:has-text('Remove')").last
                                if await confirm.is_visible(timeout=2000):
                                    await confirm.click()
                                    await asyncio.sleep(0.5)
                            except:
                                pass

                            already_removed.add(username)
                            removed_this_run.append(username)
                            self.removed_count += 1
                            removed_in_view += 1
                            progress.update(task, advance=1)

                            await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))

                            if self.removed_count >= len(to_remove):
                                break

                    except Exception:
                        continue

                if self.removed_count >= len(to_remove):
                    break

                current_links = await page.locator("div[role='dialog'] a[href^='/']").count()
                if current_links > last_count:
                    last_count = current_links
                    stagnant = 0
                else:
                    stagnant += 1
                    if stagnant >= 8 and removed_in_view == 0:
                        break

                await page.evaluate("""
                    () => {
                        const dialog = document.querySelector('div[role="dialog"]');
                        if (!dialog) return;
                        for (const div of dialog.querySelectorAll('div')) {
                            if (div.scrollHeight > div.clientHeight + 100 && div.scrollHeight > 500) {
                                div.scrollTop += 1200;
                                break;
                            }
                        }
                    }
                """)
                await asyncio.sleep(random.uniform(0.5, 1.0))

        with open("progress.json", "w") as f:
            json.dump({
                "removed": list(already_removed),
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)

        console.print(f"[bold green]Removed {self.removed_count} accounts.[/bold green]")

        if self.rate_limited:
            console.print(Panel.fit(
                "[bold yellow]Instagram rate limited you.[/bold yellow]\n"
                "Wait 24 hours before running again.\n"
                "Progress has been saved — already-removed users will be skipped.",
                border_style="yellow"
            ))

    def save_report(self):
        report = {
            "timestamp": datetime.now().isoformat(),
            "account": self.username,
            "mode": "dry_run" if self.dry_run else "live",
            "total_followers": len(self.followers),
            "flagged": len(self.flagged),
            "removed": self.removed_count,
            "rate_limited": self.rate_limited,
            "thresholds": {
                "following_threshold": self.following_threshold,
                "min_follower_ratio": self.min_ratio
            },
            "flagged_accounts": [f.to_dict() for f in self.flagged],
        }

        filename = f"report_{int(time.time())}.json"
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)

        console.print(f"[dim]Report saved to {filename}[/dim]")

    def show_menu(self) -> str:
        console.print(Panel.fit(
            "[bold]InstaPurge[/bold]\n\n"
            "1. Dry Run (scan & preview)\n"
            "2. Live Run (scan & remove)\n"
            "3. Settings\n"
            "4. Clear Cache & Session\n"
            "5. Exit",
            title="Menu",
            border_style="blue"
        ))
        return console.input("[bold]Choice: [/bold]").strip()

    def show_settings(self):
        console.print(Panel.fit(
            f"[bold]Settings[/bold]\n\n"
            f"1. Following threshold: {self.following_threshold}\n"
            f"2. Min follower ratio: {self.min_ratio}\n"
            f"3. Max removals per session: {self.max_removals}\n"
            f"4. Delay between removals: {self.delay_min}-{self.delay_max}s\n"
            f"5. Headless mode: {self.headless}\n"
            f"6. Back to menu",
            border_style="blue"
        ))

        choice = console.input("[bold]Setting to change: [/bold]").strip()

        if choice == "1":
            self.following_threshold = int(Prompt.ask("New threshold", default=str(self.following_threshold)))
        elif choice == "2":
            self.min_ratio = float(Prompt.ask("New ratio", default=str(self.min_ratio)))
        elif choice == "3":
            self.max_removals = int(Prompt.ask("New max", default=str(self.max_removals)))
        elif choice == "4":
            self.delay_min = float(Prompt.ask("Min delay", default=str(self.delay_min)))
            self.delay_max = float(Prompt.ask("Max delay", default=str(self.delay_max)))
        elif choice == "5":
            self.headless = Confirm.ask("Headless mode?", default=self.headless)

        self.config.update({
            "following_threshold": self.following_threshold,
            "min_follower_ratio": self.min_ratio,
            "max_removals_per_session": self.max_removals,
            "delay_min": self.delay_min,
            "delay_max": self.delay_max,
            "headless": self.headless,
        })
        self._save_config()
        console.print("[green]Settings saved.[/green]")

    async def do_dry_run(self):
        self.dry_run = True
        await self._run_flow()

    async def do_live_run(self):
        if not Confirm.ask("[bold red]This will REMOVE followers. Continue?[/bold red]", default=False):
            return
        self.dry_run = False
        await self._run_flow()

    async def _run_flow(self):
        self._ensure_credentials()

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()

            try:
                if not await self.login(page):
                    console.print("[red]Failed to log in. Exiting.[/red]")
                    return

                self.followers = await self.fetch_followers(page)
                if not self.followers:
                    console.print("[red]No followers fetched. Exiting.[/red]")
                    return

                await self.scan_all()
                self.show_results()

                if not self.dry_run and self.flagged:
                    await self.remove_all(page)

                self.save_report()

            except Exception as e:
                console.print(f"[bold red]Error: {e}[/bold red]")
                try:
                    await page.screenshot(path="error_debug.png")
                    console.print("[dim]Screenshot saved to error_debug.png[/dim]")
                except:
                    pass
            finally:
                try:
                    await browser.close()
                except:
                    pass

    def clear_cache(self):
        files = ["session.json", "followers_cache.json", "progress.json"]
        for f in files:
            path = Path(f)
            if path.exists():
                path.unlink()
                console.print(f"[dim]Deleted {f}[/dim]")
        console.print("[green]Cache cleared.[/green]")

    async def run(self):
        while True:
            choice = self.show_menu()

            if choice == "1":
                await self.do_dry_run()
            elif choice == "2":
                await self.do_live_run()
            elif choice == "3":
                self.show_settings()
            elif choice == "4":
                self.clear_cache()
            elif choice == "5":
                console.print("[blue]Goodbye.[/blue]")
                break
            else:
                console.print("[red]Invalid choice.[/red]")


if __name__ == "__main__":
    cleaner = InstaPurge()
    asyncio.run(cleaner.run())
