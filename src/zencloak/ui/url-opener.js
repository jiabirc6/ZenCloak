(function () {
  function defaultScheme(value) {
    const host = value.split("/", 1)[0].split(":", 1)[0].toLowerCase();
    return host === "localhost" || host === "127.0.0.1" ? "http://" : "https://";
  }

  function normalizeHttps(value) {
    const trimmed = value.trim();
    if (!trimmed) return null;
    if (/^https?:\/\//i.test(trimmed)) return trimmed;
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmed)) return null;
    return defaultScheme(trimmed) + trimmed;
  }

  function buildOpener() {
    const wrap = document.querySelector(".detect-wrap");
    if (!wrap || document.getElementById("openUrlInput")) return;

    const opener = document.createElement("div");
    opener.className = "url-opener";

    const input = document.createElement("input");
    input.id = "openUrlInput";
    input.type = "text";
    input.placeholder = "google.com";
    input.spellcheck = false;

    const button = document.createElement("button");
    button.id = "openUrlBtn";
    button.className = "btn primary";
    button.type = "button";
    button.innerHTML = '<i data-lucide="external-link"></i>打开';

    const translateButton = document.createElement("button");
    translateButton.id = "openUrlTranslateBtn";
    translateButton.className = "btn";
    translateButton.type = "button";
    translateButton.title = "通过 Google 翻译打开为中文";
    translateButton.innerHTML = '<i data-lucide="languages"></i>翻译';

    opener.appendChild(input);
    opener.appendChild(button);
    opener.appendChild(translateButton);
    wrap.prepend(opener);

    function open() {
      const url = normalizeHttps(input.value);
      if (!url) return;
      if (typeof window.openDetectUrl === "function") {
        window.openDetectUrl(url);
      }
    }

    function translate() {
      const url = normalizeHttps(input.value);
      if (!url) return;
      const translated =
        "https://translate.google.com/translate?sl=auto&tl=zh-CN&u=" +
        encodeURIComponent(url);
      if (typeof window.openDetectUrl === "function") {
        window.openDetectUrl(translated);
      }
    }

    button.addEventListener("click", open);
    translateButton.addEventListener("click", translate);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") open();
    });

    if (window.lucide) window.lucide.createIcons();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildOpener);
  } else {
    buildOpener();
  }
})();
