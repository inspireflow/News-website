(() => {
  const sidebar = document.querySelector("#dashboard-sidebar");
  const toggle = document.querySelector(".dashboard-menu-toggle");
  const overlay = document.querySelector(".sidebar-overlay");

  if (!sidebar || !toggle || !overlay) return;

  document.body.classList.add("js-enabled");

  const closeSidebar = () => {
    sidebar.classList.remove("is-open");
    document.body.classList.remove("sidebar-open");
    toggle.setAttribute("aria-expanded", "false");
    overlay.hidden = true;
  };

  toggle.addEventListener("click", () => {
    if (!window.matchMedia("(max-width: 650px)").matches) {
      const collapsed = document.body.classList.toggle("sidebar-collapsed");
      toggle.setAttribute("aria-expanded", String(!collapsed));
      window.localStorage.setItem("newswebDashboardSidebarCollapsed", String(collapsed));
      return;
    }
    const isOpen = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!isOpen));
    sidebar.classList.toggle("is-open", !isOpen);
    document.body.classList.toggle("sidebar-open", !isOpen);
    overlay.hidden = isOpen;
    if (!isOpen) sidebar.querySelector("a")?.focus();
  });

  overlay.addEventListener("click", closeSidebar);
  sidebar.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("a")) closeSidebar();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      closeSidebar();
      toggle.focus();
    }
  });
  if (window.localStorage.getItem("newswebDashboardSidebarCollapsed") === "true"
      && !window.matchMedia("(max-width: 650px)").matches) {
    document.body.classList.add("sidebar-collapsed");
    toggle.setAttribute("aria-expanded", "false");
  }

  const searchForm = document.querySelector(".topbar-search");
  const searchButton = searchForm?.querySelector(".search-toggle");
  const searchInput = searchForm?.querySelector('input[type="search"]');
  if (searchForm && searchButton && searchInput) {
    searchForm.addEventListener("submit", (event) => {
      if (window.matchMedia("(max-width: 1023px)").matches && !searchForm.classList.contains("is-expanded")) {
        event.preventDefault();
        searchForm.classList.add("is-expanded");
        searchButton.setAttribute("aria-expanded", "true");
        searchInput.focus();
      }
    });
    document.addEventListener("click", (event) => {
      if (!(event.target instanceof Element) || !searchForm.contains(event.target)) {
        if (!searchInput.value.trim()) {
          searchForm.classList.remove("is-expanded");
          searchButton.setAttribute("aria-expanded", "false");
        }
      }
    });
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        searchForm.classList.remove("is-expanded");
        searchButton.setAttribute("aria-expanded", "false");
        searchButton.focus();
      }
    });
    window.addEventListener("resize", () => {
      if (!window.matchMedia("(max-width: 1023px)").matches) {
        searchForm.classList.remove("is-expanded");
        searchButton.setAttribute("aria-expanded", "false");
      }
    });
  }

  const customizer = document.querySelector("#theme-customizer");
  const customizerToggle = document.querySelector(".customizer-toggle");
  const customizerClose = document.querySelector(".customizer-close");
  const customizerOverlay = document.querySelector(".customizer-overlay");
  const preferenceKey = "newswebDashboardAppearance";
  const allowedPresets = new Set(["cream-orange", "ocean-blue", "soft-orange", "mint-teal", "lavender-rose", "midnight-glass"]);
  const allowedBlur = new Set(["low", "medium", "high"]);
  const allowedDensity = new Set(["compact", "comfortable"]);
  const allowedModes = new Set(["light", "dark"]);
  let preferences = {};
  const savedPreferences = window.localStorage.getItem(preferenceKey);
  if (savedPreferences) {
    try {
      preferences = JSON.parse(savedPreferences);
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
      console.warn("Ignoring malformed dashboard appearance preferences.");
    }
  }
  const normalizedPreferences = {
    theme: allowedPresets.has(preferences.theme) ? preferences.theme : "cream-orange",
    background: preferences.background !== false,
    blur: allowedBlur.has(preferences.blur) ? preferences.blur : "medium",
    density: allowedDensity.has(preferences.density) ? preferences.density : "comfortable",
    mode: allowedModes.has(preferences.mode)
      ? preferences.mode
      : preferences.theme === "midnight-glass" ? "dark" : "light",
  };
  let overlayHideTimer;
  const applyPreferences = () => {
    const root = document.documentElement;
    root.dataset.theme = normalizedPreferences.theme;
    root.dataset.background = normalizedPreferences.background ? "on" : "off";
    root.dataset.glassBlur = normalizedPreferences.blur;
    root.dataset.density = normalizedPreferences.density;
    root.dataset.glassMode = normalizedPreferences.mode;
    for (const button of document.querySelectorAll("[data-theme-choice]")) {
      button.setAttribute("aria-pressed", String(button.dataset.themeChoice === normalizedPreferences.theme));
    }
    const backgroundInput = document.querySelector("#animated-background");
    const blurInput = document.querySelector("#glass-blur");
    const densityInput = document.querySelector("#layout-density");
    const modeInput = document.querySelector("#glass-mode");
    if (backgroundInput) backgroundInput.checked = normalizedPreferences.background;
    if (blurInput) blurInput.value = normalizedPreferences.blur;
    if (densityInput) densityInput.value = normalizedPreferences.density;
    if (modeInput) modeInput.value = normalizedPreferences.mode;
    window.dispatchEvent(new CustomEvent("dashboardthemechange"));
  };
  const savePreferences = () => {
    window.localStorage.setItem(preferenceKey, JSON.stringify(normalizedPreferences));
    applyPreferences();
  };
  applyPreferences();

  const closeCustomizer = () => {
    if (!customizer || !customizerToggle || !customizerOverlay) return;
    customizer.classList.remove("is-open");
    customizerOverlay.classList.remove("is-open");
    customizer.setAttribute("aria-hidden", "true");
    customizerToggle.setAttribute("aria-expanded", "false");
    window.clearTimeout(overlayHideTimer);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      customizerOverlay.hidden = true;
    } else {
      overlayHideTimer = window.setTimeout(() => {
        if (!customizer.classList.contains("is-open")) customizerOverlay.hidden = true;
      }, 350);
    }
  };
  customizerToggle?.addEventListener("click", () => {
    if (!customizer || !customizerOverlay) return;
    const open = !customizer.classList.contains("is-open");
    window.clearTimeout(overlayHideTimer);
    customizer.classList.toggle("is-open", open);
    customizer.setAttribute("aria-hidden", String(!open));
    customizerToggle.setAttribute("aria-expanded", String(open));
    if (open) {
      customizerOverlay.hidden = false;
      window.requestAnimationFrame(() => customizerOverlay.classList.add("is-open"));
      customizer.querySelector("button")?.focus();
    } else {
      customizerOverlay.classList.remove("is-open");
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        customizerOverlay.hidden = true;
      } else {
        overlayHideTimer = window.setTimeout(() => {
          if (!customizer.classList.contains("is-open")) customizerOverlay.hidden = true;
        }, 350);
      }
    }
  });
  customizerClose?.addEventListener("click", closeCustomizer);
  customizerOverlay?.addEventListener("click", closeCustomizer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && customizer?.classList.contains("is-open")) {
      closeCustomizer();
      customizerToggle?.focus();
    }
  });
  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.addEventListener("click", () => {
      normalizedPreferences.theme = button.dataset.themeChoice;
      if (normalizedPreferences.theme === "midnight-glass") normalizedPreferences.mode = "dark";
      savePreferences();
    });
  }
  document.querySelector("#animated-background")?.addEventListener("change", (event) => {
    normalizedPreferences.background = event.currentTarget.checked;
    savePreferences();
  });
  document.querySelector("#glass-blur")?.addEventListener("change", (event) => {
    normalizedPreferences.blur = event.currentTarget.value;
    savePreferences();
  });
  document.querySelector("#layout-density")?.addEventListener("change", (event) => {
    normalizedPreferences.density = event.currentTarget.value;
    savePreferences();
  });
  document.querySelector("#glass-mode")?.addEventListener("change", (event) => {
    normalizedPreferences.mode = event.currentTarget.value;
    savePreferences();
  });

  for (const [buttonSelector, menuSelector] of [
    [".profile-toggle", "#profile-menu"],
    [".notification-toggle", "#notification-menu"],
  ]) {
    const button = document.querySelector(buttonSelector);
    const menu = document.querySelector(menuSelector);
    if (!button || !menu) continue;
    button.addEventListener("click", () => {
      const open = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(open));
      menu.hidden = !open;
    });
    document.addEventListener("click", (event) => {
      if (!(event.target instanceof Element) || !event.target.closest(".menu-anchor")) {
        button.setAttribute("aria-expanded", "false");
        menu.hidden = true;
      }
    });
  }
  document.addEventListener("visibilitychange", () => {
    document.body.classList.toggle("is-page-hidden", document.hidden);
  });

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const formatNumber = (value) => Math.round(value).toLocaleString();
  const animateCardCounters = (card) => {
    for (const counter of card.querySelectorAll("[data-value], [data-counter]")) {
      if (counter.dataset.animated === "true") continue;
      counter.dataset.animated = "true";
      const raw = counter.dataset.value ?? counter.dataset.counter ?? counter.textContent.trim();
      const parts = raw.split("/").map((part) => Number(part.trim().replaceAll(",", "")));
      if (!parts.length || parts.some((value) => !Number.isFinite(value) || value < 0)) {
        counter.textContent = raw;
        continue;
      }
      if (prefersReducedMotion || parts.every((value) => value === 0)) {
        counter.textContent = parts.map(formatNumber).join(" / ");
        continue;
      }
      const startedAt = performance.now();
      const duration = 1500;
      const animate = (now) => {
        const progress = Math.min((now - startedAt) / duration, 1);
        const eased = 1 - ((1 - progress) ** 3);
        counter.textContent = parts.map((value) => formatNumber(value * eased)).join(" / ");
        if (progress < 1) window.requestAnimationFrame(animate);
      };
      window.requestAnimationFrame(animate);
    }
  };
  const statCards = document.querySelectorAll(".stat-card");
  if ("IntersectionObserver" in window && !prefersReducedMotion) {
    const counterObserver = new IntersectionObserver((entries, observer) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        animateCardCounters(entry.target);
        observer.unobserve(entry.target);
      }
    }, { threshold: .18 });
    statCards.forEach((card) => counterObserver.observe(card));
  } else {
    statCards.forEach(animateCardCounters);
  }

  const bars = document.querySelectorAll(".chart-bar > span");
  for (const bar of bars) {
    const height = bar.style.getPropertyValue("--bar-height");
    if (prefersReducedMotion) continue;
    bar.style.height = "0";
    window.requestAnimationFrame(() => {
      bar.style.height = height;
    });
  }

  for (const button of document.querySelectorAll("button")) {
    button.addEventListener("click", (event) => {
      if (prefersReducedMotion) return;
      const bounds = button.getBoundingClientRect();
      const ripple = document.createElement("span");
      ripple.className = "button-ripple";
      ripple.style.left = `${event.detail ? event.clientX - bounds.left : bounds.width / 2}px`;
      ripple.style.top = `${event.detail ? event.clientY - bounds.top : bounds.height / 2}px`;
      button.append(ripple);
      window.setTimeout(() => ripple.remove(), 650);
    });
  }

  for (const form of document.querySelectorAll(".dashboard-form, .login-card form")) {
    form.addEventListener("submit", () => {
      const button = form.querySelector('button[type="submit"]');
      if (!button) return;
      button.classList.add("is-loading");
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
      const label = button.textContent.trim();
      button.dataset.originalLabel = label;
      button.textContent = "Saving…";
    });
  }

  for (const upload of document.querySelectorAll("[data-image-upload]")) {
    const input = upload.querySelector('input[type="file"]');
    const dropZone = upload.querySelector(".image-drop-zone");
    const preview = upload.querySelector("[data-image-preview]");
    const previewImage = preview?.querySelector("img");
    const name = upload.querySelector("[data-image-name]");
    if (!input || !dropZone || !preview || !previewImage) continue;

    let previewUrl;
    const showPreview = (file) => {
      if (!file || !file.type.startsWith("image/")) return;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(file);
      previewImage.src = previewUrl;
      if (name) name.textContent = file.name;
      preview.hidden = false;
    };

    input.addEventListener("change", () => showPreview(input.files?.[0]));
    for (const eventName of ["dragenter", "dragover"]) {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("is-dragging");
      });
    }
    for (const eventName of ["dragleave", "drop"]) {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("is-dragging");
      });
    }
    dropZone.addEventListener("drop", (event) => {
      const [file] = event.dataTransfer?.files || [];
      if (!file || !file.type.startsWith("image/")) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    window.addEventListener("pagehide", () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    }, { once: true });
  }
})();
