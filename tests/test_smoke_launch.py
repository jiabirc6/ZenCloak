import tempfile

from cloakbrowser import launch_persistent_context


def test_cloakbrowser_real_launch_is_stealthy():
    with tempfile.TemporaryDirectory(prefix="zencloak-smoke-") as user_data_dir:
        context = launch_persistent_context(
            user_data_dir,
            headless=True,
            timezone="Asia/Shanghai",
            locale="zh-CN",
            args=["--fingerprint=54321"],
        )
        try:
            page = context.new_page()
            page.goto("https://example.com", timeout=60_000)
            probe = page.evaluate(
                """() => ({
                    webdriver: navigator.webdriver,
                    userAgent: navigator.userAgent,
                    plugins: navigator.plugins.length,
                })"""
            )
            assert probe["webdriver"] is False
            assert "HeadlessChrome" not in probe["userAgent"]
            assert probe["plugins"] > 0
        finally:
            context.close()
