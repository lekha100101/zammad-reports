(function () {
  if (!window.jQuery) return;

  const $ = window.jQuery;
  const $body = $("body");
  const $toggle = $("#menuToggle");
  const $sideNav = $("#sideNav");
  const $overlay = $("#menuOverlay");
  const mobileQuery = window.matchMedia("(max-width: 1100px)");

  const initJqueryButtons = () => {
    const guessIcon = (label) => {
      const text = (label || "").toLowerCase();
      if (text.includes("excel")) return "fa-file-excel";
      if (text.includes("удал")) return "fa-trash";
      if (text.includes("сохран")) return "fa-floppy-disk";
      if (text.includes("созда")) return "fa-user-plus";
      if (text.includes("синхрон")) return "fa-rotate";
      if (text.includes("примен")) return "fa-filter";
      if (text.includes("очист")) return "fa-eraser";
      if (text.includes("выход")) return "fa-right-from-bracket";
      return "fa-circle-dot";
    };

    $("button, input[type='submit'], input[type='button'], a[role='button']")
      .not(".drp-buttons button")
      .not(".applyBtn")
      .not(".cancelBtn")
      .each((_, element) => {
      const $el = $(element);
      const icon = $el.data("icon") || guessIcon($el.text());
      if (icon && $el.find("i").length === 0) {
        $el.prepend(`<i class="fa-solid ${icon}" aria-hidden="true"></i> `);
      }
      if ($el.is("a")) {
        $el.addClass("ui-button ui-corner-all ui-widget");
      } else if ($.fn.button) {
        $el.button();
      }
    });
  };

  const initCreateUserDialog = () => {
    const $dialog = $("#createUserDialog");
    const $open = $("#openCreateUserDialog");
    if (!$dialog.length || !$open.length || !$.fn.dialog) return;

    $dialog.dialog({
      autoOpen: false,
      modal: true,
      width: 540,
      draggable: false,
      resizable: false,
    });

    $open.on("click", () => $dialog.dialog("open"));
  };

  const initProgressTables = () => {
    const $cells = $(".inline-progress-cell");
    if (!$cells.length) return;

    const values = $cells
      .map((_, cell) => Number.parseFloat($(cell).data("progress-value")) || 0)
      .get();
    const max = Math.max(...values, 1);

    $cells.each((idx, cell) => {
      const $cell = $(cell);
      const value = values[idx];
      const percent = Math.max(0, Math.min(100, Math.round((value / max) * 100)));
      const hue = Math.round((percent / 100) * 120);
      const baseColor = `hsl(${hue}, 70%, 82%)`;
      const text = $cell.text().trim();

      $cell
        .addClass("inline-progress-ready")
        .css("background", `linear-gradient(90deg, ${baseColor} ${percent}%, transparent ${percent}%)`)
        .attr("title", `Прогресс: ${percent}%`)
        .html(`<span class=\"inline-progress-text\">${text}</span>`);
    });
  };

  const initDataTables = () => {
    if (!$.fn.DataTable) return;

    $("table.compact-table")
      .not(".regional-report-flat")
      .not(".exec-table")
      .each((_, tableEl) => {
        const $table = $(tableEl);
        if ($.fn.dataTable.isDataTable(tableEl)) return;

        const noRows = $table.find("tbody tr").length === 0;

        $table.DataTable({
          paging: true,
          searching: true,
          info: true,
          lengthMenu: [10, 25, 50, 100],
          pageLength: 25,
          autoWidth: false,
          order: [],
          language: {
            search: "Поиск:",
            lengthMenu: "Показывать _MENU_ строк",
            info: "Показано _START_–_END_ из _TOTAL_",
            infoEmpty: "Нет данных",
            zeroRecords: "Ничего не найдено",
            paginate: { previous: "Назад", next: "Вперед" },
          },
          columnDefs: [],
          dom: "ftip",
        });

        if (noRows) {
          $table.closest(".dataTables_wrapper").find(".dataTables_filter").hide();
          $table.closest(".dataTables_wrapper").find(".dataTables_paginate").hide();
        }
      });
  };

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
    const $range = $form.find(".js-date-range");
    const $from = $form.find('input[name="date_from"]');
    const $to = $form.find('input[name="date_to"]');
    const $status = $form.find("[data-filter-status]");
    if (!$range.length || !$from.length || !$to.length || !window.moment || !$.fn.daterangepicker) return;

    const fmt = (date) => date.format("YYYY-MM-DD");
    const parseInputRange = () => {
      const raw = ($range.val() || "").trim();
      const parts = raw.split(" - ");
      if (parts.length !== 2) return null;
      const start = window.moment(parts[0], "YYYY-MM-DD", true);
      const end = window.moment(parts[1], "YYYY-MM-DD", true);
      if (!start.isValid() || !end.isValid()) return null;
      return { start, end };
    };
    const setRange = (start, end) => {
      $from.val(fmt(start));
      $to.val(fmt(end));
      $range.val(`${fmt(start)} - ${fmt(end)}`);
    };
    const setStatus = () => {
      const from = $from.val();
      const to = $to.val();
      if (from && to) $status.text(`Период: ${from} → ${to}`);
      else if (from || to) $status.text("Период задан частично");
      else $status.text("Период не выбран");
    };

    const startInit = $from.val() ? window.moment($from.val()) : window.moment().startOf("month");
    const endInit = $to.val() ? window.moment($to.val()) : window.moment();

    $range.daterangepicker(
      {
        autoUpdateInput: true,
        autoApply: false,
        locale: {
          format: "YYYY-MM-DD",
          separator: " - ",
          applyLabel: "Применить",
          cancelLabel: "Отмена",
          fromLabel: "С",
          toLabel: "По",
          customRangeLabel: "Произвольный",
          weekLabel: "Нд",
          daysOfWeek: ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"],
          monthNames: [
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь",
          ],
          firstDay: 1,
        },
        startDate: startInit,
        endDate: endInit,
        ranges: {
          Сегодня: [window.moment(), window.moment()],
          "7 дней": [window.moment().subtract(6, "days"), window.moment()],
          "30 дней": [window.moment().subtract(29, "days"), window.moment()],
          "Этот месяц": [window.moment().startOf("month"), window.moment()],
        },
      },
      (start, end) => {
        setRange(start, end);
        setStatus();
      },
    );
    setRange(startInit, endInit);
    $range.on("apply.daterangepicker", (_, picker) => {
      setRange(picker.startDate, picker.endDate);
      setStatus();
    });

    $form.find('[data-action="clear-dates"]').on("click", () => {
      $from.val("");
      $to.val("");
      $range.val("");
      setStatus();
    });

    $from.on("change", setStatus);
    $to.on("change", setStatus);
    $form.on("submit", () => {
      const parsed = parseInputRange();
      if (parsed) setRange(parsed.start, parsed.end);
    });
    setStatus();
  });

  initJqueryButtons();
  initCreateUserDialog();
  initProgressTables();
  initDataTables();
})();
