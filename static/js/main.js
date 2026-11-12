(() => {
  const menuToggle = document.querySelector(".mobile-menu-toggle");
  const primaryNavigation = document.querySelector("#primary-navigation .nav-links");
  const searchForm = document.querySelector("#news-search-form");
  const searchInput = document.querySelector("#news-search-input");
  const searchResults = document.querySelector("#search-results");

  if (menuToggle && primaryNavigation) {
    const closeMenu = () => {
      menuToggle.setAttribute("aria-expanded", "false");
      menuToggle.setAttribute("aria-label", "Open navigation menu");
      primaryNavigation.classList.remove("is-open");
    };

    menuToggle.addEventListener("click", () => {
      const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
      menuToggle.setAttribute("aria-expanded", String(!isOpen));
      menuToggle.setAttribute(
        "aria-label",
        isOpen ? "Open navigation menu" : "Close navigation menu",
      );
      primaryNavigation.classList.toggle("is-open", !isOpen);
    });

    primaryNavigation.addEventListener("click", (event) => {
      if (event.target instanceof Element && event.target.closest("a")) closeMenu();
    });

    document.addEventListener("click", (event) => {
      if (
        menuToggle.getAttribute("aria-expanded") === "true"
        && !menuToggle.contains(event.target)
        && !primaryNavigation.contains(event.target)
      ) closeMenu();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menuToggle.getAttribute("aria-expanded") === "true") {
        closeMenu();
        menuToggle.focus();
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 760) closeMenu();
    });
  }

  if (searchForm && searchInput && searchResults) {
    let activeRequest;
    let debounceTimer;

    const closeSuggestions = () => {
      searchResults.hidden = true;
      searchInput.setAttribute("aria-expanded", "false");
    };

    const showMessage = (message) => {
      searchResults.replaceChildren();
      const item = document.createElement("p");
      item.textContent = message;
      searchResults.append(item);
      searchResults.hidden = false;
      searchInput.setAttribute("aria-expanded", "true");
    };

    const showResults = (items) => {
      searchResults.replaceChildren();
      if (!items.length) {
        showMessage("No matching stories found.");
        return;
      }

      for (const result of items) {
        if (
          typeof result.title !== "string"
          || typeof result.summary !== "string"
          || typeof result.category !== "string"
          || typeof result.url !== "string"
          || !result.url.startsWith("/article/")
        ) continue;

        const link = document.createElement("a");
        link.className = "search-result-item";
        link.href = result.url;
        link.setAttribute("role", "option");

        const title = document.createElement("strong");
        title.textContent = result.title;
        const summary = document.createElement("small");
        summary.textContent = `${result.category} · ${result.summary}`;
        link.append(title, summary);
        searchResults.append(link);
      }

      if (!searchResults.childElementCount) {
        showMessage("No matching stories found.");
        return;
      }

      searchResults.hidden = false;
      searchInput.setAttribute("aria-expanded", "true");
    };

    const loadSuggestions = async () => {
      const query = searchInput.value.trim();
      if (query.length < 2) {
        activeRequest?.abort();
        activeRequest = null;
        closeSuggestions();
        return;
      }

      const endpoint = searchForm.dataset.suggestionsUrl;
      if (!endpoint) return;

      activeRequest?.abort();
      activeRequest = new AbortController();
      const url = new URL(endpoint, window.location.origin);
      url.searchParams.set("q", query);

      try {
        const response = await fetch(url, {
          headers: { Accept: "application/json" },
          signal: activeRequest.signal,
        });
        if (!response.ok) throw new Error(`Suggestions request failed (${response.status}).`);
        const data = await response.json();
        showResults(Array.isArray(data.results) ? data.results : []);
      } catch (error) {
        if (error.name === "AbortError") return;
        console.error("Search suggestions could not be loaded.", error);
        showMessage("Suggestions are temporarily unavailable. Submit to search all stories.");
      }
    };

    searchInput.addEventListener("input", () => {
      activeRequest?.abort();
      activeRequest = null;
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(loadSuggestions, 180);
    });

    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeSuggestions();
        return;
      }
      if (event.key === "ArrowDown" && !searchResults.hidden) {
        const firstResult = searchResults.querySelector("a");
        if (firstResult) {
          event.preventDefault();
          firstResult.focus();
        }
      }
    });

    searchResults.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeSuggestions();
        searchInput.focus();
        return;
      }
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;

      const links = [...searchResults.querySelectorAll("a")];
      const index = links.indexOf(document.activeElement);
      const nextIndex = event.key === "ArrowDown"
        ? Math.min(index + 1, links.length - 1)
        : Math.max(index - 1, -1);
      event.preventDefault();
      if (nextIndex === -1) searchInput.focus();
      else links[nextIndex].focus();
    });

    document.addEventListener("click", (event) => {
      if (!searchForm.contains(event.target)) closeSuggestions();
    });
  }

  const header = document.querySelector(".site-header");
  if (header) {
    const updateHeader = () => header.classList.toggle("is-scrolled", window.scrollY > 12);
    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });
  }

  const themeToggle = document.querySelector("[data-theme-toggle]");
  if (themeToggle) {
    const label = themeToggle.querySelector("[data-theme-label]");
    let storedTheme;
    try {
      storedTheme = window.localStorage.getItem("newsroom-theme");
    } catch (error) {
      console.warn("The saved color theme could not be read.", error);
    }
    const initialTheme = storedTheme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = initialTheme;

    const updateThemeButton = () => {
      const dark = document.documentElement.dataset.theme === "dark";
      themeToggle.setAttribute("aria-label", `Switch to ${dark ? "light" : "dark"} theme`);
      if (label) label.textContent = dark ? "Light mode" : "Dark mode";
    };
    updateThemeButton();
    themeToggle.addEventListener("click", () => {
      const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = nextTheme;
      try {
        window.localStorage.setItem("newsroom-theme", nextTheme);
      } catch (error) {
        console.warn("The color theme could not be saved for the next visit.", error);
      }
      updateThemeButton();
    });
  }

  const readingProgress = document.querySelector(".reading-progress > span");
  if (readingProgress) {
    let ticking = false;
    const updateProgress = () => {
      const documentHeight = document.documentElement.scrollHeight - window.innerHeight;
      const progress = documentHeight > 0 ? window.scrollY / documentHeight : 0;
      readingProgress.style.width = `${Math.max(0, Math.min(progress, 1)) * 100}%`;
      ticking = false;
    };
    window.addEventListener("scroll", () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(updateProgress);
    }, { passive: true });
    updateProgress();
  }

  const articleContent = document.querySelector(".article-content");
  const readTime = document.querySelector("[data-read-time]");
  if (articleContent && readTime) {
    const words = articleContent.textContent.trim().split(/\s+/u).filter(Boolean).length;
    readTime.textContent = `${Math.max(1, Math.ceil(words / 220))} min read`;
  }

  for (const button of document.querySelectorAll("[data-copy-link]")) {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(window.location.href);
        button.textContent = "Link copied";
      } catch (error) {
        console.error("Could not copy the article link.", error);
        button.textContent = "Copy unavailable";
      }
    });
  }

  const revealTargets = document.querySelectorAll(
    ".lead-story, .editorial-card, .about-mission, .principle-card, .about-contact",
  );
  if (
    revealTargets.length
    && "IntersectionObserver" in window
    && !window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    const revealObserver = new IntersectionObserver((entries, observer) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    }, { threshold: 0.08 });
    for (const target of revealTargets) {
      target.classList.add("reveal-pending");
      revealObserver.observe(target);
    }
  }

  for (const image of document.querySelectorAll(".editorial-card-image img")) {
    if (image.complete) {
      image.classList.add("is-loaded");
    } else {
      image.addEventListener("load", () => image.classList.add("is-loaded"), { once: true });
      image.addEventListener("error", () => image.classList.add("is-loaded"), { once: true });
    }
  }

  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    for (const control of document.querySelectorAll(
      ".search-form button, .theme-toggle, .article-share a, .article-share button, .story-read-link",
    )) {
      control.addEventListener("click", (event) => {
        if (control.matches(":disabled")) return;
        const bounds = control.getBoundingClientRect();
        const ripple = document.createElement("span");
        ripple.className = "public-ripple";
        ripple.style.left = `${event.clientX - bounds.left}px`;
        ripple.style.top = `${event.clientY - bounds.top}px`;
        control.append(ripple);
        window.setTimeout(() => ripple.remove(), 520);
      });
    }
  }

})();
