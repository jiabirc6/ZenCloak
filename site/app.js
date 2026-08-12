/* ============================================================
   ZENCLOAK - interactions (adapted from Obscura, Apache-2.0)
   ============================================================ */
(function () {
  "use strict";

  /* ---------- mobile nav ---------- */
  var navToggle = document.getElementById("navToggle");
  var mnav = document.getElementById("mnav");
  if (navToggle && mnav) {
    function setMenu(open) {
      mnav.classList.toggle("open", open);
      navToggle.classList.toggle("open", open);
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
      document.body.style.overflow = open ? "hidden" : "";
    }
    navToggle.addEventListener("click", function () {
      setMenu(!mnav.classList.contains("open"));
    });
    mnav.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () { setMenu(false); });
    });
  }

  /* ---------- scroll reveal ---------- */
  var reveals = document.querySelectorAll(".reveal");
  function inViewport(el) {
    var r = el.getBoundingClientRect();
    return r.top < (window.innerHeight || 800) * 0.98 && r.bottom > 0;
  }
  if ("IntersectionObserver" in window) {
    var ro = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add("in");
          ro.unobserve(e.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    reveals.forEach(function (el) { ro.observe(el); });
    requestAnimationFrame(function () {
      reveals.forEach(function (el) { if (inViewport(el)) el.classList.add("in"); });
    });
    setTimeout(function () {
      reveals.forEach(function (el) { el.classList.add("in"); });
    }, 2500);
  } else {
    reveals.forEach(function (el) { el.classList.add("in"); });
  }

  /* ---------- count-up for numeric metrics ---------- */
  function countUp(el) {
    var target = parseFloat(el.getAttribute("data-count"));
    var prefix = el.getAttribute("data-prefix") || "";
    var suffix = el.getAttribute("data-suffix") || "";
    var dur = 1100, start = null;
    var tmp = document.createElement("div"); tmp.innerHTML = prefix; prefix = tmp.textContent;
    function frame(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      var val = Math.round(eased * target);
      el.textContent = prefix + val + suffix;
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  var counters = document.querySelectorAll("[data-count]");
  if ("IntersectionObserver" in window) {
    var co = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { countUp(e.target); co.unobserve(e.target); }
      });
    }, { threshold: 0.6 });
    counters.forEach(function (el) { co.observe(el); });
  }

  /* ---------- code panel: language tabs + syntax highlight ---------- */
  var codeBody = document.getElementById("codeBody");
  var K = function (s) { return '<span class="tok-kw">' + s + "</span>"; };
  var C = function (s) { return '<span class="tok-cls">' + s + "</span>"; };
  var F = function (s) { return '<span class="tok-fn">' + s + "</span>"; };
  var S = function (s) { return '<span class="tok-str">' + s + "</span>"; };
  var M = function (s) { return '<span class="tok-com">' + s + "</span>"; };
  var P = function (s) { return '<span class="tok-pun">' + s + "</span>"; };

  var snippets = {
    py: [
      M("# 通过本地 API 启动 ZenCloak 档案"),
      K("import") + " requests",
      "",
      "API " + P("=") + " " + S('"http://127.0.0.1:PORT"'),
      "",
      "profile " + P("=") + " requests." + F("post") + "(API " + P("+") + " " + S('"/api/profiles"') + ",",
      "    json" + P("=") + " {" + S('"name"') + P(":") + " " + S('"shop-01"') + "})." + F("json") + "()",
      "pid " + P("=") + " profile[" + S('"id"') + "]",
      "requests." + F("post") + "(API " + P("+") + " " + S('"/api/sessions/"') + " " + P("+") + " pid " + P("+") + " " + S('"/launch"') + ")",
      "requests." + F("post") + "(API " + P("+") + " " + S('"/api/sessions/"') + " " + P("+") + " pid " + P("+") + " " + S('"/open"') + ",",
      "    json" + P("=") + " {" + S('"url"') + P(":") + " " + S('"https://example.com"') + "})"
    ],
    js: [
      M("// 用 Node.js 启动 ZenCloak 档案"),
      K("const") + " API " + P("=") + " " + S('"http://127.0.0.1:PORT"') + ";",
      K("const") + " res " + P("=") + " " + K("await") + " fetch(API " + P("+") + " " + S('"/api/profiles"') + ", {",
      "  method" + P(":") + " " + S('"POST"') + ",",
      "  headers" + P(":") + " { " + S('"content-type"') + P(":") + " " + S('"application/json"') + " },",
      "  body" + P(":") + " JSON." + F("stringify") + "({ name" + P(":") + " " + S('"shop-01"') + " })",
      "});",
      K("const") + " profile " + P("=") + " " + K("await") + " res." + F("json") + "();",
      K("await") + " fetch(API " + P("+") + " " + S('"/api/sessions/"') + " " + P("+") + " profile.id " + P("+") + " " + S('"/launch"') + ", { method" + P(":") + " " + S('"POST"') + " });"
    ],
    pwsh: [
      M("# 用 PowerShell 启动档案"),
      "$API " + P("=") + " " + S('"http://127.0.0.1:PORT"'),
      "$body " + P("=") + " " + S('"{\\"name\\":\\"shop-01\\"}"'),
      "$profile " + P("=") + " Invoke-RestMethod -Method Post -Uri ($API " + P("+") + " " + S('"/api/profiles"') + ") -ContentType " + S('"application/json"') + " -Body $body",
      "Invoke-RestMethod -Method Post -Uri ($API " + P("+") + " " + S('"/api/sessions/$($profile.id)/launch"') + ")"
    ],
    http: [
      "POST " + S('"/api/profiles"') + " HTTP/1.1",
      "Host" + P(":") + " 127.0.0.1" + P(":") + "PORT",
      "Content-Type" + P(":") + " application/json",
      "",
      "{" + S('"name"') + P(":") + " " + S('"shop-01"') + "}",
      "",
      "HTTP/1.1 200 OK",
      "{" + S('"id"') + P(":") + " " + S('"4f8c2a"') + ", " + S('"name"') + P(":") + " " + S('"shop-01"') + "}"
    ]
  };
  var curLang = "py";

  function renderCode() {
    if (!codeBody) return;
    var rows = snippets[curLang] || [];
    var html = "<pre>";
    rows.forEach(function (r) {
      html += '<span class="code-line">' + (r && r.length ? r : " ") + "</span>";
    });
    html += "</pre>";
    codeBody.innerHTML = html;
  }
  renderCode();

  document.querySelectorAll(".code-tab[data-lang]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".code-tab").forEach(function (t) { t.classList.remove("active"); });
      tab.classList.add("active");
      curLang = tab.getAttribute("data-lang");
      renderCode();
    });
  });

  /* ---------- nudge hero video to play (mobile autoplay can stall) ---------- */
  var heroVideo = document.querySelector(".hero-video");
  if (heroVideo) {
    heroVideo.muted = true;
    var tryPlay = function () {
      var p = heroVideo.play();
      if (p && p.catch) p.catch(function () {});
    };
    tryPlay();
    heroVideo.addEventListener("loadeddata", tryPlay);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) tryPlay();
    });
    ["touchstart", "click"].forEach(function (ev) {
      window.addEventListener(ev, tryPlay, { once: true, passive: true });
    });
  }

  /* ---------- nav background on scroll + sticky stack ---------- */
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var nav = document.querySelector(".nav");
  var probBody = document.querySelector("#problem .panel-body");
  var engBody = document.querySelector("#engine .panel-body");
  var engPanel = document.getElementById("engine");
  var enableStack = !reduceMotion && probBody && engBody && engPanel && window.innerWidth > 760;
  var smooth = function (t) { return t * t * (3 - 2 * t); };
  var clamp01 = function (v) { return v < 0 ? 0 : v > 1 ? 1 : v; };

  var ticking = false;
  function frame() {
    ticking = false;
    var y = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;

    if (nav) nav.style.background = y > 8 ? "rgba(0,0,0,0.78)" : "rgba(0,0,0,0.55)";

    if (enableStack) {
      var vh = window.innerHeight;
      var top = engPanel.getBoundingClientRect().top;
      var e = smooth(clamp01(1 - top / vh));
      probBody.style.transform = "scale(" + (1 - 0.06 * e).toFixed(4) + ")";
      probBody.style.opacity = (1 - 0.6 * e).toFixed(3);
      probBody.style.filter = e > 0.001 ? "blur(" + (e * 2.4).toFixed(2) + "px)" : "none";
      engBody.style.transform = "translateY(" + ((1 - e) * 34).toFixed(2) + "px)";
      engBody.style.opacity = (0.35 + 0.65 * e).toFixed(3);
    }
  }
  function onScroll() { if (!ticking) { ticking = true; requestAnimationFrame(frame); } }
  window.addEventListener("scroll", onScroll, { passive: true, capture: true });
  window.addEventListener("resize", onScroll);
  frame();

  /* ---------- live GitHub star count (cached 1h; falls back to the markup value) ---------- */
  var starEl = document.getElementById("starCount");
  if (starEl && "fetch" in window) {
    var fmtStars = function (n) {
      if (n >= 1000) { var k = (n / 1000).toFixed(1); return k.replace(/\.0$/, "") + "k"; }
      return String(n);
    };
    var renderStars = function (n) { starEl.textContent = fmtStars(n); };
    var KEY = "zencloak_gh_stars", TTL = 3600 * 1000;
    try {
      var c = JSON.parse(localStorage.getItem(KEY) || "null");
      if (c && typeof c.n === "number" && Date.now() - c.t < TTL) renderStars(c.n);
    } catch (e) {}
    fetch("https://api.github.com/repos/jiabirc6/ZenCloak", { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && typeof d.stargazers_count === "number") {
          renderStars(d.stargazers_count);
          try { localStorage.setItem(KEY, JSON.stringify({ n: d.stargazers_count, t: Date.now() })); } catch (e) {}
        }
      })
      .catch(function () {});
  }
})();
