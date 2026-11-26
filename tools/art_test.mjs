// The page is ready for a scene built in Blender (docs/BLENDER.md): when a scene has a model, the box room and the page's own lamps go, and only what moves and what the rules
// name is drawn; baked light shows unlit on the second UV set, with a night set the mall swaps to; an AO-only bake stays lit; lamp heads, lit windows and emergency lights follow
// the clock; and a backdrop picture is drawn round the camera, swapped at night. No real build exists for these scenes yet, so a tiny model (tools/fixtures, made by
// make_art_fixture.mjs) stands in for each, through the page's ART_TEST hook. With no model every scene must draw as it always did; a scene the game lists a real model
// for is also loaded as the game has it, and must show that model's baked light with no box room and no lamp of the page's.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/art_test.mjs
import {createRequire} from "node:module";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {createServer} from "../server/server.js";
import {secondsAt, DOORS} from "../shared/city.js";
import {REGISTRY} from "../shared/registry.js";
const {chromium} = createRequire(import.meta.url)("playwright");
const FIX = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const page = await browser.newPage({viewport: {width: 640, height: 400}}); page.on("pageerror", e => errors.push(e.message));
  await page.route("**/fixtures/**", r => r.fulfill({path: path.join(FIX, path.basename(new URL(r.request().url()).pathname))}));   // the stand-in model and its pictures are not part of the game
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const setT = (h, d = 2) => page.evaluate(t => { window.__game.CITY.t = t; window.__game.CITY.ui = 0; }, secondsAt(h, d));
  const ART = {glbs: ["fixtures/art_room.glb"]};
  const NONE = {glbs: []};                         // the scene as it draws with no model of its own (the box room), whether or not the game lists one
  // load a scene, with the stand-in model (and maybe a backdrop) or as the game has it
  const load = async (id, art, pos = [0, 0, 0]) => {
    await page.evaluate(([id, art, pos]) => { const g = window.__game; for (const k of Object.keys(g.ART_TEST)) delete g.ART_TEST[k]; if (art) g.ART_TEST[id] = art; return g.loadScene(id, {pos, face: [0, -1]}); }, [id, art, pos]);
    await settled(id); await frames(3);
  };
  // what the scene holds: the page's own lamps, its code-made solids (Lambert), its signs (a canvas texture on an unlit plane), and the model's materials
  const look = () => page.evaluate(() => {
    const g = window.__game, S = g.S, o = {lights: 0, solids: 0, signs: 0, baked: 0, ao: 0, emit: {}, set: S.lightSet, n: S.baked};
    S.root.traverse(x => {
      if (x.isLight) o.lights++; if (!x.isMesh && !x.isInstancedMesh) return; const m = x.material; if (Array.isArray(m)) return;
      if (m.isMeshLambertMaterial) o.solids++; if (m.isMeshBasicMaterial && m.map && m.map.isCanvasTexture) o.signs++;
      if (m.userData && m.userData.baked) { o.baked++; o.bakedOk = m.isMeshBasicMaterial && !!m.lightMap && m.lightMap.channel === 1 && !!x.geometry.attributes.uv1; o.bakedK = m.lightMapIntensity; }
      if (m.userData && m.userData.ao) { o.ao++; o.aoOk = m.isMeshStandardMaterial && !!m.aoMap && m.aoMap.channel === 1 && Math.abs(m.aoMapIntensity - 0.8) < 1e-6; }
      if (["Lamp_Emit", "Window_Lit", "Emergency_Emit"].includes(m.name)) o.emit[m.name] = m.emissiveIntensity;
    });
    return o;
  });
  await page.evaluate(() => window.__game.loadScene("street", {pos: [0, 0, 4], face: [0, -1]})); await settled("street"); await setT(12); await frames(3);

  // the rooms: with a model, the box room and the page's lamps are gone, and what the page keeps is still there
  const ROOMS = [
    ["laboratory", "the lab", {signs: 6, solids: 0}, "the five station signs and the B2 sign"],
    ["galleries", "the museum", {signs: 6, solids: 36}, "the six statues and their name plates"],
    ["factory_floor", "the factory", {signs: 3, solids: 1}, "the belt's top and the three bin signs"],
    ["main_floor", "the grocery", {signs: 4}, "the food, the carts, the camera and the price signs"],
    ["entrance", "the mall", {signs: 0, solids: 0}, "nothing of its own"],
  ];
  for (const [id, name, want, kept] of ROOMS) {
    await load(id, NONE); const plain = await look();
    check(`${name} with no model draws as it always did: its box room and its own lamp`, plain.lights >= 1 && plain.solids > 6 && plain.n === 0 && plain.baked === 0, JSON.stringify(plain));
    await load(id, ART); const a = await look();
    check(`${name} with a model: the box room and the page's lamps are gone`, a.lights === 0 && a.solids < plain.solids && (want.solids === undefined || a.solids === want.solids), JSON.stringify(a));
    check(`${name} with a model: the page keeps ${kept}`, a.signs === want.signs && (id === "entrance" || a.signs === plain.signs), JSON.stringify({signs: a.signs, was: plain.signs, solids: a.solids}));
    check(`${name}: the model's baked material shows unlit on the second UV set, and its AO one stays lit`, a.n === 1 && a.baked === 1 && a.bakedOk && a.ao === 1 && a.aoOk, JSON.stringify(a));
    if (REGISTRY.pageScenes[id].glbs.length) {                          // the game's own Blender build (docs/BLENDER.md): as the game loads it
      await load(id, null); const own = await look();
      check(`${name} as the game has it: its own model's baked light, no box room, no lamp of the page's, and the page keeps ${kept}`, own.lights === 0 && own.n > 0 && own.baked === own.n && own.bakedOk && (want.solids === undefined || own.solids === want.solids) && own.signs === want.signs, JSON.stringify(own));
    }
  }
  const kept = await page.evaluate(async () => {
    const g = window.__game, inTree = o => { for (let p = o; p; p = p.parent) if (p === g.S.root) return true; return false; }, out = {};
    const go = async id => { for (const k of Object.keys(g.ART_TEST)) delete g.ART_TEST[k]; g.ART_TEST[id] = {glbs: ["fixtures/art_room.glb"]}; await g.loadScene(id, {pos: [0, 0, 0], face: [0, -1]}); };
    await go("galleries"); out.statues = g.CITY.mu.figs.length === 6 && g.CITY.mu.figs.every(inTree);
    await go("factory_floor"); out.parts = !!g.CITY.fa.parts && inTree(g.CITY.fa.parts);
    await go("main_floor"); out.cam = !!g.CITY.mats.cam && inTree(g.CITY.mats.cam) && g.CITY.mats.cam.children.length === 2;
    await go("entrance"); out.noMallLamp = g.CITY.mats.mallLamp === undefined;
    return out;
  });
  check("what moves is still the page's: the statues, the belt's parts, the camera's head (without its bracket); the mall has no lamp of the page's", kept.statues && kept.parts && kept.cam && kept.noMallLamp, JSON.stringify(kept));

  // the mall's two light sets and its emergency lights
  await load("entrance", ART); await setT(12); await frames(3); let m = await look();
  check("the mall by day: the day set, the lamps on, the emergency lights off", m.set === "day" && m.bakedK === 2 && m.emit.Lamp_Emit === 5 && m.emit.Emergency_Emit === 0, JSON.stringify(m));
  await setT(21); await frames(3); m = await look();
  check("the mall locked at night: the night set, the lamps off, the emergency lights on", m.set === "night" && m.bakedK === 1.5 && m.emit.Lamp_Emit === 0 && m.emit.Emergency_Emit === 4, JSON.stringify(m));
  await setT(12, 3); await frames(3); m = await look();
  check("and back to the day set in the morning", m.set === "day" && m.bakedK === 2 && m.emit.Lamp_Emit === 5, JSON.stringify(m));

  // the street: the page keeps the doors' signs, lamps and shutters and the anomalies; lit windows and lamp heads follow the clock; the backdrop
  await load("street", null, [0, 0, 4]); await setT(12, 3); await frames(3); const plainSt = await look();
  check("the street with no model draws as it always did, and has no backdrop", plainSt.solids > 30 && plainSt.n === 0 && await page.evaluate(() => window.__game.S.backdrop === null), JSON.stringify(plainSt));
  await load("street", {...ART, backdrop: {day: "fixtures/sky_day.png", night: "fixtures/sky_night.png"}}, [0, 0, 4]); await setT(12, 3); await frames(3);
  let s = await look();
  const doors = await page.evaluate(() => { const g = window.__game, inTree = o => { for (let p = o; p; p = p.parent) if (p === g.S.root) return true; return false; }; return {n: g.CITY.doors.length, in: g.CITY.doors.every(c => inTree(c.lamp) && inTree(c.shutter)), anom: !!g.CITY.anom && inTree(g.CITY.anom.sign)}; });
  check("the street with a model: the ground, the buildings and the lamp posts are gone; the doors' signs, lamps and shutters and the anomalies stay", s.solids < plainSt.solids && s.signs >= DOORS.length && doors.n === DOORS.length && doors.in && doors.anom, JSON.stringify({s, doors}));
  check("at noon the lit windows and the lamp heads are off", s.emit.Window_Lit === 0 && s.emit.Lamp_Emit === 0, JSON.stringify(s.emit));
  const bd = () => page.evaluate(() => {
    const g = window.__game, b = g.S.backdrop; if (!b) return null; b.updateMatrixWorld(true);
    const pos = b.geometry.attributes.position, uv = b.geometry.attributes.uv, dir = (u, v) => { let best = 0, d = 9; for (let i = 0; i < uv.count; i++) { const e = Math.abs(uv.getX(i) - u) + Math.abs(uv.getY(i) - v); if (e < d) { d = e; best = i; } }
      const p = b.localToWorld(new b.position.constructor(pos.getX(best), pos.getY(best), pos.getZ(best))).sub(b.position).normalize(); return [+p.x.toFixed(2), +p.y.toFixed(2), +p.z.toFixed(2)]; };
    const cam = new b.position.constructor(); g.camera.getWorldPosition(cam);
    return {set: b.userData.set, now: b.userData.now, map: !!b.material.map, atCamera: b.position.distanceTo(cam) < 0.01, middle: dir(0.5, 0.5), right: dir(0.75, 0.5), first: b.renderOrder < 0 && !b.material.depthTest && !b.material.fog};
  });
  let b = await bd();
  check("a backdrop is drawn round the camera, behind everything, showing the day picture", !!b && b.map && b.set === "day" && /sky_day/.test(b.now) && b.atCamera && b.first, JSON.stringify(b));
  check("the picture's middle faces north (-z) and its right-hand side east (+x)", !!b && b.middle[2] === -1 && Math.abs(b.middle[0]) < 0.01 && b.right[0] === 1 && Math.abs(b.right[2]) < 0.01, JSON.stringify(b));
  await setT(23, 3); await frames(3); s = await look(); b = await bd();
  check("at night the lit windows and the lamp heads are on, at the strengths they were exported with", s.emit.Window_Lit === 3 && s.emit.Lamp_Emit === 5, JSON.stringify(s.emit));
  check("and the backdrop is the night picture, still round the camera", !!b && b.set === "night" && /sky_night/.test(b.now) && b.atCamera, JSON.stringify(b));

  // the forest and the meadow keep the signpost, the gap's glow and the owner's buildings
  await load("forest", null, [0, 0, 6]); const plainF = await page.evaluate(() => { let n = 0; window.__game.S.root.traverse(o => { if (o.isInstancedMesh) n += o.count; }); return n; });
  await load("forest", {...ART, backdrop: {day: "fixtures/sky_day.png"}}, [0, 0, 6]);
  const f = await page.evaluate(() => { let trees = 0, sprites = 0; const S = window.__game.S; S.root.traverse(o => { if (o.isInstancedMesh) trees += o.count; if (o.isSprite) sprites++; }); return {trees, sprites, backdrop: !!S.backdrop, hazy: window.__game.FST.hazy()}; });
  check("the forest with a model: the page's trees are gone, the gap's glow stays, the haze stays, and with a backdrop the page draws no sky of its own", plainF > 400 && f.trees === 0 && f.sprites === 1 && f.backdrop && f.hazy, JSON.stringify({plainF, f}));
  await load("meadow", ART, [0, 0, 6]);
  const md = await page.waitForFunction(() => !!window.__game.FST.shed && !!window.__game.FST.house, null, {timeout: 30000}).then(() => true, () => false);
  const mf = await page.evaluate(() => { let inst = 0, lights = 0; window.__game.S.root.traverse(o => { if (o.isInstancedMesh) inst += o.count; if (o.isLight) lights++; }); return {inst, lights}; });
  check("the meadow with a model: the page's trees and flowers are gone; the shed, the house and the porch light stay", md && mf.inst === 0 && mf.lights === 1, JSON.stringify(mf));

  // and once the stand-in is taken away and no model is listed, the lab is its box room again
  await load("laboratory", NONE); const again = await look();
  check("without the model the lab is its box room again", again.lights === 1 && again.solids > 6 && again.n === 0, JSON.stringify(again));
  check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
