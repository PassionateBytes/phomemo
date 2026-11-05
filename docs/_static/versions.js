/*
 * This file is part of phomemo-driver.
 * Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
 *
 * Licensed under CC BY-SA 4.0, like the rest of the documentation.
 */

/**
 * Version menu and version notice. The site keeps one directory per version
 * next to versions.json ({"stable": "0.3.0", "versions": ["latest", ...]}).
 * Switching versions keeps the current page and falls back to the version's
 * start page when that page does not exist there.
 */
(() => {
  const menu = document.getElementById("version-menu");
  if (!menu) return;

  const current = menu.dataset.version;
  const versionRoot = new URL(document.documentElement.dataset.content_root || "./", location.href);
  const siteRoot = new URL("../", versionRoot);
  const page = location.pathname.slice(versionRoot.pathname.length);

  /** URL of the current page in another version's directory. */
  const pageIn = (dir) => new URL(dir + "/" + page, siteRoot).href;

  /** Opens the current page in another version, or its start page if missing. */
  const open = async (dir) => {
    const target = pageIn(dir);
    try {
      const response = await fetch(target, { method: "HEAD" });
      location.href = response.ok ? target : new URL(dir + "/", siteRoot).href;
    } catch {
      location.href = target;
    }
  };

  /** Shows a notice above the page content. */
  const notice = (html) => {
    const box = document.createElement("div");
    box.className = "version-notice";
    box.innerHTML = html;
    const anchor = document.querySelector("article.yue") || document.querySelector("main");
    anchor?.prepend(box);
  };

  const label = (name, stable) => {
    if (name === "latest") return "latest (main, unreleased)";
    if (name === stable) return `${name} (stable)`;
    return name;
  };

  fetch(new URL("versions.json", siteRoot))
    .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
    .then(({ stable, versions }) => {
      const list = menu.querySelector("ul");
      for (const name of versions) {
        const item = document.createElement("li");
        const link = document.createElement("a");
        link.href = pageIn(name);
        link.textContent = label(name, stable);
        if (name === current) link.setAttribute("aria-current", "page");
        link.addEventListener("click", (event) => {
          event.preventDefault();
          open(name);
        });
        item.append(link);
        list.append(item);
      }

      const toStable = stable
        ? `<a href="${pageIn("stable")}">the current release (${stable})</a>`
        : null;
      if (current === "latest") {
        notice(
          "These pages are built from the <code>main</code> branch and describe unreleased changes." +
            (toStable ? ` For the installed package see ${toStable}.` : "")
        );
      } else if (stable && current !== stable) {
        notice(`These pages describe version ${current}. See ${toStable}.`);
      }
    })
    .catch(() => menu.remove());
})();
