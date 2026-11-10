// Tiny static server for the prototype (ES modules do not load from file://). node tools/physics/serve.mjs [port]
import http from "node:http";
import {readFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import path from "node:path";
const root = path.dirname(fileURLToPath(import.meta.url));
const types = {".html": "text/html", ".mjs": "text/javascript", ".js": "text/javascript"};
export function serve(port = 0) {
  const s = http.createServer(async (q, r) => {
    const f = path.join(root, new URL(q.url, "http://x").pathname.replace(/^\/$/, "/index.html"));
    if (!f.startsWith(root) || f.includes("node_modules")) { r.writeHead(404).end(); return; }
    try { r.writeHead(200, {"content-type": types[path.extname(f)] || "application/octet-stream"}).end(await readFile(f)); } catch { r.writeHead(404).end(); }
  });
  return new Promise(res => s.listen(port, () => res(s)));
}
if (import.meta.url === `file://${process.argv[1]}`) { const s = await serve(+process.argv[2] || 8123); console.log("http://localhost:" + s.address().port + "/  (?engine=rapier for Rapier)"); }
