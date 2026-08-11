if (window.location.protocol === "file:") {
  setTimeout(() => {
    document.querySelectorAll("input, select, textarea, button").forEach((el) => {
      el.disabled = true;
    });
    const title = document.getElementById("profileTitle");
    if (title) title.textContent = "请通过桌面程序打开";
    const badge = document.getElementById("statusBadge");
    if (badge) {
      badge.className = "badge error";
      badge.textContent = "未连接";
    }
    const toast = document.getElementById("toast");
    if (toast) {
      toast.textContent = "请运行 python -m zencloak 启动 ZenCloak";
      toast.className = "toast show error";
    }
  }, 300);
}
