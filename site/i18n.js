/* ============================================================
   ZENCLOAK SITE - i18n (中文 / English)
   Chinese lives in the HTML; switching to EN swaps text via the
   dictionary below, and back again restores the captured originals.
   ============================================================ */
(function () {
  "use strict";

  var STORAGE = "zencloak_site_lang";
  var TITLES = {
    zh: "ZenCloak · 每个身份都有自己的浏览器",
    en: "ZenCloak · Every identity deserves its own browser"
  };
  var DESCRIPTIONS = {
    zh: "ZenCloak 是一款基于 stealth Chromium 内核的开源指纹浏览器。一个档案，一个隔离的浏览器身份。",
    en: "An open-source anti-detect browser for Windows powered by a stealth Chromium kernel. One profile, one isolated browser identity."
  };

  var EN = {
    "nav-how": "How it works",
    "nav-opensource": "Open source",
    "nav-docs": "Docs",
    "btn-download": "Download",
    "btn-how": "How it works",

    "hero-h1": "Every identity,<br>its own browser.",
    "hero-sub": "One profile, one real, isolated browser. ZenCloak keeps fingerprints, cookies and history separate for every identity — kernel, proxy and stealth details included.",

    "stat1-num": "1 click",
    "stat1-suffix": " to launch",
    "stat1-lbl": "a profile's browser",
    "stat2-num": "Zero state",
    "stat2-lbl": "sessions fully isolated",
    "stat3-lbl": "real stealth kernel",

    "problem-h2": "One browser is not enough.",
    "problem-lead": "Chromium was built for one person browsing one set of sites. Running a shop, work accounts and side projects in the same profile leaks fingerprints, cookies and history across every identity.",
    "problem-1-h": "Your fingerprint follows you",
    "problem-1-p": "Screen, timezone, language, hardware and User-Agent stay identical across every tab, so sites can link the accounts you tried to keep apart.",
    "problem-2-h": "State crosses between accounts",
    "problem-2-p": "Cookies, login state and cache carry over from one run to the next, polluting sessions and breaking reproducibility.",
    "problem-3-h": "Everything is manual",
    "problem-3-p": "Every new identity means digging through flags, extensions, proxies and browser settings all over again.",

    "engine-h2": "A browser identity, redefined.",
    "engine-lead": "ZenCloak keeps only what a real identity needs: clean persistent browser profiles, stable fingerprints, per-profile data that never crosses.",
    "feat-1-m": "1 click",
    "feat-1-h": "Launch any profile",
    "feat-1-p": "Fingerprint seeds are set once. ZenCloak opens a real stealth browser window with the identity already in place.",
    "feat-2-m": "Zero state",
    "feat-2-h": "Isolated every time",
    "feat-2-p": "Cookies, login state and history live only in their own profile directory. Nothing is shared between profiles, nothing leaks between sessions.",
    "feat-3-h": "Built-in proxy management",
    "feat-3-p": "Subscription import/refresh, airport node expansion, region filtering, concurrent real-latency tests and egress IP detection — all built in.",
    "feat-4-h": "Encrypted full backup",
    "feat-4-p": "Profiles and login state are packed into a passphrase-protected archive; caches are excluded and running profiles are safely skipped.",
    "feat-5-h": "Voice-pack spoofing",
    "feat-5-p": "The voice list follows the profile language, eliminating \u201cvoice-pack country vs IP country\u201d flags; timezone/locale consistency is pre-checked automatically.",
    "feat-6-h": "Scripts & AI ready",
    "feat-6-p": "A local API on a random 127.0.0.1 port, an MCP server for AI assistants, and CDP attach for external Playwright/Selenium scripts.",

    "how-h2": "One call, from profile to browser.",
    "how-lead": "Use the desktop client, or drive it from your own scripts. The local API creates profiles, launches sessions and opens URLs over plain HTTP.",
    "step-1-h": "Create",
    "step-1-p": "A profile is an identity: fingerprint seed, timezone, language, screen, proxy and behavior settings.",
    "step-2-h": "Launch",
    "step-2-p": "One click opens a real stealth browser window; cookies and history persist only inside this profile.",
    "step-3-h": "Automate",
    "step-3-p": "Scripts via the local API, AI assistants via MCP, and Playwright/Selenium can attach over CDP.",

    "oss-h2": "How you run it is up to you.",
    "oss-p": "ZenCloak is fully open source. Install it or build from source — the browser kernel and your profiles always stay on your machine. Nothing is locked in.",
    "oss-github": "View GitHub",
    "oss-docs": "Read the docs",

    "cta-h2": "A better browser<br>for every identity.",
    "cta-p": "Install ZenCloak, create a profile, and open a real, isolated browser window within a minute.",

    "footer-tagline": "An open-source anti-detect browser for Windows.",
    "footer-github": "GitHub",
    "footer-license": "MIT License",
    "footer-rights": "© 2026 ZenCloak · All rights reserved."
  };

  var nodes = [];
  var suffixes = [];

  function capture() {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      nodes.push({ el: el, text: el.textContent });
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      nodes.push({ el: el, html: el.innerHTML });
    });
    document.querySelectorAll("[data-i18n-suffix]").forEach(function (el) {
      suffixes.push({ el: el, value: el.getAttribute("data-suffix") });
    });
  }

  function apply(lang) {
    var en = lang === "en";
    nodes.forEach(function (n) {
      var key = n.el.getAttribute("data-i18n") || n.el.getAttribute("data-i18n-html");
      if (en) {
        var v = EN[key];
        if (v == null) return;
        if (n.html != null) n.el.innerHTML = v;
        else n.el.textContent = v;
      } else if (n.text != null) {
        n.el.textContent = n.text;
      } else {
        n.el.innerHTML = n.html;
      }
    });
    suffixes.forEach(function (s) {
      var key = s.el.getAttribute("data-i18n-suffix");
      s.el.setAttribute("data-suffix", en ? (EN[key] || s.value) : s.value);
    });
    document.documentElement.lang = en ? "en" : "zh-CN";
    document.title = en ? TITLES.en : TITLES.zh;
    var meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", en ? DESCRIPTIONS.en : DESCRIPTIONS.zh);
    document.querySelectorAll(".lang-btn").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-lang") === lang);
    });
    try { localStorage.setItem(STORAGE, lang); } catch (e) {}
    window.dispatchEvent(new CustomEvent("langchange", { detail: lang }));
  }

  capture();
  var want = "en";  // 站点默认英文；?lang= 参数优先，其次 localStorage
  var params = new URLSearchParams(location.search);
  if (params.get("lang")) {
    want = params.get("lang");
  } else {
    try {
      var saved = localStorage.getItem(STORAGE);
      if (saved) want = saved;
    } catch (e) {}
  }
  apply(want === "en" ? "en" : "zh");

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".lang-btn");
    if (btn) apply(btn.getAttribute("data-lang"));
  });
})();