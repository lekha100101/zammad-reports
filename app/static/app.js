(function () {
  if (!window.jQuery) return;

  const $ = window.jQuery;
  const $body = $("body");
  const $toggle = $("#menuToggle");
  const $sideNav = $("#sideNav");
  const $overlay = $("#menuOverlay");
  const $densityToggle = $("#densityToggle");
  const mobileQuery = window.matchMedia("(max-width: 1100px)");

  const syncMenuState = () => {
    const mobile = mobileQuery.matches;
    const open = $body.hasClass("menu-open");

    if (!mobile) {
      $body.removeClass("menu-open");
      $sideNav.prop("hidden", false);
      $overlay.prop("hidden", true);
      $toggle.attr("aria-expanded", "false");
      return;
    }

    $sideNav.prop("hidden", !open);
    $overlay.prop("hidden", !open);
    $toggle.attr("aria-expanded", open ? "true" : "false");
  };

  const closeMenu = () => {
    $body.removeClass("menu-open");
    syncMenuState();
  };

  if ($toggle.length && $sideNav.length && $overlay.length) {
    $toggle.on("click", () => {
      $body.toggleClass("menu-open");
      syncMenuState();
    });
    $overlay.on("click", closeMenu);
    $(document).on("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
    });
    mobileQuery.addEventListener("change", syncMenuState);
    syncMenuState();
  }

  const applyDensity = (isCompact) => {
    $body.toggleClass("density-compact", isCompact);
    if ($densityToggle.length) {
      $densityToggle.attr("aria-pressed", isCompact ? "true" : "false");
      $densityToggle.text(isCompact ? "Стандартный режим" : "Компактный режим");
    }
    window.localStorage.setItem("ui_density_compact", isCompact ? "1" : "0");
  };

  if ($densityToggle.length) {
    const savedDensity = window.localStorage.getItem("ui_density_compact") === "1";
    applyDensity(savedDensity);
    $densityToggle.on("click", () => applyDensity(!$body.hasClass("density-compact")));
  }

  $("[data-nav-toggle]").each((_, element) => {
    const $btn = $(element);
    const $group = $btn.next("[data-nav-group]");
    if (!$group.length) return;

    const hasActive = $group.find(".menu-btn.active").length > 0;
    $btn.attr("aria-expanded", hasActive ? "true" : "false");
    if (!hasActive) $group.hide();

    $btn.on("click", () => {
      const expanded = $btn.attr("aria-expanded") === "true";
      $btn.attr("aria-expanded", expanded ? "false" : "true");
      $group.stop(true, true).slideToggle(140);
    });
  });

  $(".js-filter-bar").each((_, formEl) => {
    const $form = $(formEl);
    const $from = $form.find('input[name="date_from"]');
    const $to = $form.find('input[name="date_to"]');
    const $status = $form.find("[data-filter-status]");
    if (!$from.length || !$to.length) return;

    const fmt = (date) => date.toISOString().slice(0, 10);
    const setStatus = () => {
      const from = $from.val();
      const to = $to.val();
      if (from && to) {
        $status.text(`Период: ${from} → ${to}`);
      } else if (from || to) {
        $status.text(`Период задан частично`);
      } else {
        $status.text("Период не выбран");
      }
    };

    $form.find("[data-range]").on("click", function () {
      const range = $(this).data("range");
      const now = new Date();
      let from = new Date(now);
      const to = new Date(now);

      if (range === "7d") from.setDate(now.getDate() - 6);
      if (range === "30d") from.setDate(now.getDate() - 29);
      if (range === "month") from = new Date(now.getFullYear(), now.getMonth(), 1);

      $from.val(fmt(from));
      $to.val(fmt(to));
      setStatus();
      $form.trigger("submit");
    });

    $form.find('[data-action="clear-dates"]').on("click", () => {
      $from.val("");
      $to.val("");
      setStatus();
    });

    $from.on("change", setStatus);
    $to.on("change", setStatus);
    setStatus();
  });
})();
