// Vid web app: loads Pyodide, writes Vid's input layer (pkg.js) into it, and
// checks pasted text. Kept out of index.html so a strict Content-Security-Policy
// needs no inline script.
// Embedded in the product page, which has its own main landmark: this becomes a named region.
if (new URLSearchParams(location.search).has("embed")) {
  document.documentElement.classList.add("embed");
  const app = document.getElementById("app");
  app.setAttribute("role", "region");
  app.setAttribute("aria-label", "Vid");
}

(async function () {
  const $ = (id) => document.getElementById(id);
  const statusEl = $("status"), checkBtn = $("check");

  // Benign examples: they only show that Vid undoes a disguise. No attack text.
  const EXAMPLES = {
    "Base64": "Please read: " + btoa("the quick brown fox"),
    "Invisible characters": "Have a nice day" + Array.from("the quick brown fox").map(c => String.fromCodePoint(0xE0000 + c.charCodeAt(0))).join(""),
    "Look-alike letters": "Please vіsіt the pаge",   // Cyrillic і, а
    "Hidden in JSON": '{"task":"summarise","note":"the quick brown fox"}',
    "Reversed": "xof nworb kciuq eht",
  };
  const exWrap = $("examples");
  Object.keys(EXAMPLES).forEach((name) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = name;
    b.onclick = () => { $("in").value = EXAMPLES[name]; if (!checkBtn.disabled) run(); };
    exWrap.appendChild(b);
  });
  // ?example=<name> fills in one of the examples and checks it once the engine is ready.
  const wanted = new URLSearchParams(location.search).get("example");
  if (wanted && EXAMPLES[wanted]) $("in").value = EXAMPLES[wanted];

  let pyodide, analyze;
  try {
    pyodide = await loadPyodide();
    // Write Vid's own Python into the in-browser filesystem, then import it.
    const files = window.VID_FILES || {};
    pyodide.FS.mkdirTree("/pkg/vid/input_layer");
    for (const [rel, src] of Object.entries(files)) {
      pyodide.FS.writeFile("/pkg/" + rel, src);
    }
    pyodide.runPython("import sys; sys.path.insert(0, '/pkg')");
    analyze = pyodide.runPython("from vid.input_layer import analyze; analyze");
    statusEl.textContent = "Ready. Everything runs here, in your browser.";
    checkBtn.disabled = false;
    checkBtn.textContent = "Check";
    if (wanted && EXAMPLES[wanted]) setTimeout(run, 0);
  } catch (e) {
    statusEl.textContent = "Could not start the in-browser engine: " + e;
    return;
  }

  function esc(s) { return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  function run() {
    const text = $("in").value;
    if (!text.trim()) { statusEl.textContent = "Paste some text first."; return; }
    let res;
    try {
      const proxy = analyze(text);
      res = proxy.as_dict().toJs({ dict_converter: Object.fromEntries });
      proxy.destroy();
    } catch (e) {
      statusEl.textContent = "Error: " + e; return;
    }
    const verdict = $("verdict"), findings = $("findings");
    findings.innerHTML = "";
    const list = res.findings || [];
    if (!res.hidden && list.length === 0) {
      verdict.className = "verdict clean";
      verdict.textContent = "Nothing hidden found. Vid read this as ordinary text.";
      $("readableWrap").style.display = "none";
      return;
    }
    verdict.className = "verdict hidden";
    verdict.textContent = list.length + " thing" + (list.length === 1 ? "" : "s") + " found in this text.";
    for (const f of list) {
      const div = document.createElement("div");
      div.className = "finding";
      let html = '<div class="k">' + esc(f.code) + " · " + esc(f.name) + "</div>";
      html += '<p class="d">' + esc(f.detail) + "</p>";
      if (f.revealed) html += '<div class="rev">' + esc(f.revealed) + "</div>";
      div.innerHTML = html;
      findings.appendChild(div);
    }
    $("readable").textContent = res.readable || "";
    $("readableWrap").style.display = res.readable ? "block" : "none";
  }

  checkBtn.onclick = run;
})();
