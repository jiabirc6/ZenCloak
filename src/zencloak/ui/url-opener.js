(function () {
  function normalizeHttps(value) {
    const trimmed = value.trim();
    if (!trimmed) return null;
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmed)) return trimmed;
    return "https://" + trimmed;
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

    opener.appendChild(input);
    opener.appendChild(button);
    wrap.prepend(opener);

    opener.style.display = "flex";
    opener.style.gap = "8px";
    opener.style.flex = "1 1 320px";
    input.style.flex = "1";
    input.style.height = "36px";
    input.style.padding = "0 12px";
    input.style.border = "1px solid #d7d5cc";
    input.style.borderRadius = "8px";
    input.style.outline = "none";

    function open() {
      const url = normalizeHttps(input.value);
      if (!url) return;
      if (typeof window.openDetectUrl === "function") {
        window.openDetectUrl(url);
      }
    }

    button.addEventListener("click", open);
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
