// Capture the structure of the current internetgoschool.com page.
//
// Paste this into the browser console (F12 > Console) on any page of the
// site. It downloads igs-<page>.html: the page's elements with their
// classes, ids and the few attributes the style matches on. All text is
// replaced by "…" and form values, numbers in ids and links are dropped,
// so the file holds no personal data.
//
// The site is a single-page app: after pasting once, click to another page
// and type igsCapture() in the console to capture that one too.
//
// Then run:  python3 tools/snapshot.py check
// (or `import` to make the downloaded files the new baseline).
window.igsCapture = () => {
  const SKIP = new Set(["SCRIPT", "NOSCRIPT", "STYLE", "LINK", "META", "TEMPLATE", "IFRAME", "BASE", "TITLE"]);
  const VOID = new Set(["AREA", "BR", "COL", "EMBED", "HR", "IMG", "INPUT", "SOURCE", "TRACK", "WBR"]);
  // attributes the style matches on, plus a few that help when reading a diff
  const KEEP = ["id", "class", "role", "type", "open", "disabled", "checked", "aria-selected", "src", "href", "style", "for", "name"];

  const clean = (name, v) => {
    if (name === "class") return v.split(/\s+/).filter(Boolean).sort().join(" ");
    if (name === "href" || name === "src") {
      if (v.startsWith("data:")) return "data:…";
      try { const u = new URL(v, location.href); v = (u.origin === location.origin ? "" : u.origin) + u.pathname; } catch (e) {}
    }
    if (name === "style") v = v.replace(/url\([^)]*\)/g, "url(…)").replace(/--(vh|wh-[\w-]+):[^;]*;?\s*/g, "").trim();
    return v.replace(/\d{3,}/g, (d) => (name === "src" && d.length <= 3 ? d : "N")).replace(/[&"<>]/g, (c) => `&#${c.charCodeAt(0)};`);
  };

  const out = [];
  const walk = (el, depth) => {
    const pad = "  ".repeat(depth);
    const tag = el.tagName.toLowerCase();
    let attrs = "";
    for (const name of KEEP) {
      if (el.hasAttribute(name)) attrs += ` ${name}="${clean(name, el.getAttribute(name))}"`;
    }
    out.push(`${pad}<${tag}${attrs}>`);
    if (VOID.has(el.tagName)) return;
    let text = false;
    for (const node of el.childNodes) {
      if (node.nodeType === 3) {
        if (node.textContent.trim() && !text) { out.push(`${pad}  …`); text = true; }
        continue;
      }
      if (node.nodeType !== 1 || SKIP.has(node.tagName)) continue;
      text = false;
      walk(node, depth + 1);
    }
    out.push(`${pad}</${tag}>`);
  };

  // custom properties the site's own stylesheets define or use
  const vars = new Set();
  for (const sheet of document.styleSheets) {
    const owner = sheet.ownerNode;
    if (owner && (owner.id || "").startsWith("stylus") || owner && owner.classList && owner.classList.contains("stylus")) continue;
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }
    const scan = (list) => { for (const r of list) { (r.cssText.match(/--[\w-]+/g) || []).forEach((v) => vars.add(v)); } };
    scan(rules);
  }

  const page = location.pathname.split("/").filter(Boolean).map((p) => (/\d/.test(p) ? "N" : p)).join("_") || "home";
  walk(document.documentElement, 0);
  const html =
    `<!-- igs-page: ${page} -->\n` +
    `<!-- igs-route: ${location.pathname.replace(/\d+/g, "N")} -->\n` +
    `<!-- igs-captured: ${new Date().toISOString().slice(0, 10)} -->\n` +
    `<!-- igs-vars: ${[...vars].filter((v) => !v.startsWith("--igs-")).sort().join(" ")} -->\n` +
    out.join("\n") + "\n";

  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  a.download = `igs-${page}.html`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  return `igs-${page}.html (${out.length} lines)`;
};
igsCapture();
