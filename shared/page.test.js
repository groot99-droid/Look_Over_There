// The page's own script must at least parse (slice 19). index.html is one big module; a duplicate top-level name (an import that shadows a function of the page, say)
// is an early error that stops the whole game before the lobby appears, and only a browser test would otherwise notice. This parses it with Node, without a browser.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";

test("index.html's module script parses (no duplicate names, no syntax errors)", () => {
  const html = fs.readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const m = html.match(/<script type="module">([\s\S]*?)<\/script>/);
  assert.ok(m, "the page has its module script");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "page-")), file = path.join(dir, "page.mjs");
  try {
    fs.writeFileSync(file, m[1]);
    const r = spawnSync(process.execPath, ["--check", file], {encoding: "utf8"});
    assert.equal(r.status, 0, r.stderr);
  } finally { fs.rmSync(dir, {recursive: true, force: true}); }
});
