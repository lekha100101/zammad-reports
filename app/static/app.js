(() => {
  const toggle = document.getElementById("menuToggle");
  const sideNav = document.getElementById("sideNav");
  const overlay = document.getElementById("menuOverlay");
  const body = document.body;

  if (!toggle || !sideNav || !overlay) return;

  const mobileQuery = window.matchMedia("(max-width: 1100px)");

  const syncMenuState = () => {
    const mobile = mobileQuery.matches;
    const open = body.classList.contains("menu-open");

    if (!mobile) {
      body.classList.remove("menu-open");
      sideNav.hidden = false;
      overlay.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      return;
    }

    sideNav.hidden = !open;
    overlay.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  };

  const closeMenu = () => {
    body.classList.remove("menu-open");
    syncMenuState();
  };

  toggle.addEventListener("click", () => {
    body.classList.toggle("menu-open");
    syncMenuState();
  });

  overlay.addEventListener("click", closeMenu);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
    }
  });

  mobileQuery.addEventListener("change", syncMenuState);
  syncMenuState();
})();
