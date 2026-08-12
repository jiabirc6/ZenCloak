import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CREATE_NO_WINDOW = 0x08000000


@pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome not available")
def test_ui_url_opener_sends_normalized_request():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    with tempfile.TemporaryDirectory(prefix="zencloak-ui-") as data_dir:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "zencloak",
                "--headless-ui",
                "--data-dir",
                data_dir,
            ],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        url = None
        try:
            for _ in range(60):
                line = proc.stdout.readline()
                match = re.search(r"http://127\.0\.0\.1:\d+", line or "")
                if match:
                    url = match.group(0)
                    break
            assert url, "ZenCloak UI server did not start"
            with urllib.request.urlopen(url + "/api/profiles", timeout=5) as response:
                profile = json.loads(response.read().decode("utf-8"))[0]

            recorded = []
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=CHROME, headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 860})
                page.route(
                    "**/api/sessions",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            [
                                {
                                    "profile_id": profile["id"],
                                    "status": "running",
                                    "started_at": None,
                                    "stopped_at": None,
                                    "error": None,
                                }
                            ]
                        ),
                    ),
                )
                page.route(
                    "**/api/sessions/*/open",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"opened": True}),
                    ),
                )

                def on_request(request):
                    if "/api/" in request.url:
                        recorded.append((request.method, request.url, request.post_data or ""))

                page.on("request", on_request)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("#profileList .profile-item", timeout=10000)
                page.wait_for_selector("#openUrlInput", timeout=5000)
                page.locator("#openUrlInput").fill("google.com")
                page.locator("#openUrlBtn").click()
                page.wait_for_timeout(800)
                opens = [r for r in recorded if r[0] == "POST" and "/open" in r[1]]
                assert page.locator("#openUrlInput").is_visible()
                assert opens, f"open request missing: {recorded}"
                assert '"url":"https://google.com"' in opens[0][2]
                page.locator("#openUrlTranslateBtn").click()
                page.wait_for_timeout(800)
                translated = [
                    r
                    for r in recorded
                    if r[0] == "POST"
                    and "/open" in r[1]
                    and "translate.google.com/translate" in r[2]
                ]
                assert translated, f"translate request missing: {recorded}"
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
