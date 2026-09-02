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
        api_token = None
        try:
            for _ in range(120):
                line = proc.stdout.readline()
                if not line:
                    break
                match = re.search(r"http://127\.0\.0\.1:\d+", line)
                if match and url is None:
                    url = match.group(0)
                token_match = re.search(r"API token: (\S+)", line)
                if token_match and api_token is None:
                    api_token = token_match.group(1)
                if url and api_token:
                    break
            assert url, "ZenCloak UI server did not start"
            assert api_token, "API token not printed"
            request = urllib.request.Request(
                url + "/api/profiles",
                headers={"Authorization": f"Bearer {api_token}"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
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
                page.evaluate(
                    "localStorage.setItem('zencloak_api_token', "
                    + json.dumps(api_token)
                    + ")"
                )
                page.reload(wait_until="domcontentloaded")
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


@pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome not available")
def test_ui_node_dropdown_selects_and_saves():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    with tempfile.TemporaryDirectory(prefix="zencloak-node-") as data_dir:
        proc = subprocess.Popen(
            [
                sys.executable, "-u", "-m", "zencloak",
                "--headless-ui", "--data-dir", data_dir,
            ],
            cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        try:
            url = api_token = None
            for _ in range(120):
                line = proc.stdout.readline()
                if not line:
                    break
                match = re.search(r"http://127\.0\.0\.1:\d+", line)
                if match and url is None:
                    url = match.group(0)
                token_match = re.search(r"API token: (\S+)", line)
                if token_match and api_token is None:
                    api_token = token_match.group(1)
                if url and api_token:
                    break
            assert url and api_token, "UI server did not start"

            headers = {"Authorization": f"Bearer {api_token}"}
            request = urllib.request.Request(
                url + "/api/profiles", headers={**headers, "Content-Type": "application/json"},
                data=json.dumps({"name": "节点测试"}).encode(), method="POST",
            )
            profile = json.loads(urllib.request.urlopen(request, timeout=5).read())
            source = """
proxies:
  - {name: 美国A, type: vless, server: 1.2.3.4, port: 443}
  - {name: 美国B, type: ss, server: 5.6.7.8, port: 8388}
"""
            request = urllib.request.Request(
                url + "/api/proxy/subscriptions/import", headers={**headers, "Content-Type": "application/json"},
                data=json.dumps({"source": source, "name": "测试订阅"}).encode(), method="POST",
            )
            sub = json.loads(urllib.request.urlopen(request, timeout=10).read())

            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=CHROME, headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 860})
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.evaluate("localStorage.setItem('zencloak_api_token', %s)" % json.dumps(api_token))
                page.reload(wait_until="domcontentloaded")
                page.wait_for_selector("#profileList .profile-item", timeout=10000)
                page.locator("#profileList .profile-item", has_text="节点测试").click()
                page.wait_for_timeout(400)

                page.locator(".tab[data-tab='proxy']").click()
                page.locator("#proxyBuiltin").check()
                page.locator("#proxySubscription").select_option(sub["id"])
                page.wait_for_timeout(500)

                trigger = page.locator("#proxyNodeTrigger")
                assert "选择节点" in trigger.inner_text()
                trigger.click()
                rows = page.locator("#proxyNodeList .node-row")
                assert rows.count() == 2
                rows.nth(1).click()
                assert "美国B" in trigger.inner_text()

                page.locator("#saveBtn").click()
                page.wait_for_timeout(800)
                request = urllib.request.Request(
                    url + f"/api/profiles/{profile['id']}", headers=headers
                )
                saved = json.loads(urllib.request.urlopen(request, timeout=5).read())
                assert saved["proxy_node"] == "美国B"
                assert saved["proxy_subscription_id"] == sub["id"]
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
