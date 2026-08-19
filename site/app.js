/* Population to 2150 — the public site.
 *
 * Three pieces, in order: the globe on the fixed canvas, the scroll
 * choreography that drives it, and the figures. No frameworks and no network
 * requests: the data is in two JSON blocks in this page and the whole thing
 * still opens in 2050.
 */
(function () {
  "use strict";

  var GLOBE = JSON.parse(document.getElementById("globe-data").textContent);
  var STORY = JSON.parse(document.getElementById("story-data").textContent);
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------- helpers */

  function decode(b64, Type) {
    var bin = atob(b64), n = bin.length, bytes = new Uint8Array(n);
    for (var i = 0; i < n; i++) bytes[i] = bin.charCodeAt(i);
    return new Type(bytes.buffer);
  }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function smooth(t) { return t * t * (3 - 2 * t); }
  function fmt(n, dp) {
    return n.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }
  function el(tag, attrs, parent) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (var k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) {
      node.setAttribute(k, attrs[k]);
    }
    if (parent) parent.appendChild(node);
    return node;
  }
  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  /* ---------------------------------------------------------- globe data */

  var lightXYZ, lightOffsets, outlineXYZ, outlineOffsets, popArray, ringCentre, ringSpan;
  var nCountries = GLOBE.iso.length;
  var nYears = GLOBE.lastYear - GLOBE.firstYear + 1;

  (function prepare() {
    var lights = decode(GLOBE.lights, Int16Array);
    lightOffsets = decode(GLOBE.lightOffsets, Uint32Array);
    popArray = decode(GLOBE.population, Uint16Array);
    var outline = decode(GLOBE.outline, Int16Array);
    outlineOffsets = decode(GLOBE.outlineOffsets, Uint32Array);

    function toXYZ(source) {
      var count = source.length / 2, out = new Float32Array(count * 3);
      for (var i = 0; i < count; i++) {
        var lon = source[i * 2] / 100 * Math.PI / 180;
        var lat = source[i * 2 + 1] / 100 * Math.PI / 180;
        var cosLat = Math.cos(lat);
        out[i * 3] = cosLat * Math.cos(lon);
        out[i * 3 + 1] = Math.sin(lat);
        out[i * 3 + 2] = cosLat * Math.sin(lon);
      }
      return out;
    }
    lightXYZ = toXYZ(lights);
    outlineXYZ = toXYZ(outline);

    /* One bounding cap per ring, so a ring wholly behind the horizon can be
       skipped without projecting any of its points. */
    var ringCount = outlineOffsets.length - 1;
    ringCentre = new Float32Array(ringCount * 3);
    ringSpan = new Float32Array(ringCount);
    for (var r = 0; r < ringCount; r++) {
      var from = outlineOffsets[r], to = outlineOffsets[r + 1];
      var ax = 0, ay = 0, az = 0;
      for (var i = from; i < to; i++) {
        ax += outlineXYZ[i * 3]; ay += outlineXYZ[i * 3 + 1]; az += outlineXYZ[i * 3 + 2];
      }
      var norm = Math.hypot(ax, ay, az) || 1;
      ax /= norm; ay /= norm; az /= norm;
      ringCentre[r * 3] = ax; ringCentre[r * 3 + 1] = ay; ringCentre[r * 3 + 2] = az;
      var widest = 1;
      for (var j = from; j < to; j++) {
        var dot = ax * outlineXYZ[j * 3] + ay * outlineXYZ[j * 3 + 1] + az * outlineXYZ[j * 3 + 2];
        if (dot < widest) widest = dot;
      }
      ringSpan[r] = Math.sqrt(Math.max(0, 1 - widest * widest));
    }
  })();

  /* The depth of a ring's bounding-cap centre, in the same units project()
     returns: positive is toward the viewer. */
  function ringZ(r, cosR, sinR, cosT, sinT) {
    var x = ringCentre[r * 3], y = ringCentre[r * 3 + 1], z = ringCentre[r * 3 + 2];
    var z1 = x * sinR + z * cosR;
    return z1 * cosT - y * sinT;
  }

  /* Millions of people in country `c` at a fractional `year`. */
  function millions(c, year) {
    var t = clamp(year - GLOBE.firstYear, 0, nYears - 1);
    var i = Math.floor(t), f = t - i;
    var base = c * nYears + i;
    var a = popArray[base];
    var b = f > 0 && i + 1 < nYears ? popArray[base + 1] : a;
    return (a + (b - a) * f) * GLOBE.populationUnit / 1e6;
  }
  function worldBillions(year) {
    var t = clamp(year - GLOBE.firstYear, 0, nYears - 1);
    var i = Math.floor(t), f = t - i;
    var a = GLOBE.world[i], b = i + 1 < nYears ? GLOBE.world[i + 1] : a;
    return a + (b - a) * f;
  }

  /* ------------------------------------------------------------- the sky */

  var canvas = document.getElementById("sky");
  var ctx = canvas.getContext("2d", { alpha: false });
  var W = 0, H = 0, dpr = 1;
  var stars = document.createElement("canvas");
  var lamp = document.createElement("canvas");
  var stride = 1, frameCost = 16;

  function buildLamp() {
    var size = 34;
    lamp.width = lamp.height = size;
    var g = lamp.getContext("2d");
    var grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    grad.addColorStop(0.00, "rgba(255,247,232,1)");
    grad.addColorStop(0.16, "rgba(255,214,152,0.82)");
    grad.addColorStop(0.42, "rgba(255,158,66,0.24)");
    grad.addColorStop(1.00, "rgba(255,140,40,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, size, size);
  }

  function buildStars() {
    stars.width = Math.max(1, Math.floor(W * dpr));
    stars.height = Math.max(1, Math.floor(H * dpr));
    var g = stars.getContext("2d");
    g.scale(dpr, dpr);
    g.fillStyle = "#05070c";
    g.fillRect(0, 0, W, H);
    var seed = 7;
    function rand() { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; }
    var count = Math.round(W * H / 5200);
    for (var i = 0; i < count; i++) {
      var x = rand() * W, y = rand() * H;
      var r = rand();
      var size = r > 0.985 ? 1.7 : r > 0.9 ? 1.15 : 0.75;
      var alpha = 0.16 + rand() * 0.55;
      var warm = rand();
      g.fillStyle = warm > 0.88 ? "rgba(255,222,190," + alpha + ")"
        : warm < 0.12 ? "rgba(196,220,255," + alpha + ")"
        : "rgba(235,242,255," + alpha + ")";
      g.beginPath();
      g.arc(x, y, size, 0, 6.283);
      g.fill();
    }
    /* One faint band of milky-way haze, so the field is not uniform. */
    var haze = g.createLinearGradient(0, H * 0.1, W, H * 0.85);
    haze.addColorStop(0, "rgba(70,90,140,0)");
    haze.addColorStop(0.45, "rgba(80,100,150,0.055)");
    haze.addColorStop(1, "rgba(70,90,140,0)");
    g.fillStyle = haze;
    g.fillRect(0, 0, W, H);
  }

  function resize() {
    W = window.innerWidth;
    H = window.innerHeight;
    dpr = Math.min(window.devicePixelRatio || 1, W < 700 ? 1.6 : 2);
    canvas.width = Math.floor(W * dpr);
    canvas.height = Math.floor(H * dpr);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    buildStars();
    measureStops();
  }

  /* Orthographic projection. Points on the far side are pushed out to the
     limb so a country straddling the horizon still fills to the edge. */
  var proj = new Float32Array(3);
  function project(xyz, i, cosR, sinR, cosT, sinT) {
    var x = xyz[i * 3], y = xyz[i * 3 + 1], z = xyz[i * 3 + 2];
    var x1 = x * cosR - z * sinR;
    var z1 = x * sinR + z * cosR;
    proj[0] = x1;
    proj[1] = y * cosT + z1 * sinT;
    proj[2] = z1 * cosT - y * sinT;
    return proj;
  }

  /* The sun, the ocean, the air and the flare do not move when the Earth
     turns, so they are painted into two cached layers and blitted. Only the
     land and the lights are redrawn each frame. */
  var under = document.createElement("canvas");
  var over = document.createElement("canvas");
  var layerKey = "";
  var SUN_ANGLE = -0.62;

  function sunAt(cx, cy, R) {
    return [cx + Math.cos(SUN_ANGLE) * R * 1.02, cy + Math.sin(SUN_ANGLE) * R * 1.02];
  }

  function buildLayers(cx, cy, R, flare) {
    [under, over].forEach(function (layer) {
      layer.width = canvas.width;
      layer.height = canvas.height;
    });
    var sun = sunAt(cx, cy, R), sx = sun[0], sy = sun[1];

    var u = under.getContext("2d");
    u.setTransform(dpr, 0, 0, dpr, 0, 0);
    u.clearRect(0, 0, W, H);
    u.drawImage(stars, 0, 0, W, H);

    /* backlight, which the planet then eclipses */
    var halo = u.createRadialGradient(sx, sy, 0, sx, sy, R * 2.3);
    halo.addColorStop(0, "rgba(255,236,205,0.30)");
    halo.addColorStop(0.22, "rgba(255,196,130,0.10)");
    halo.addColorStop(0.6, "rgba(120,150,210,0.035)");
    halo.addColorStop(1, "rgba(90,120,190,0)");
    u.globalCompositeOperation = "lighter";
    u.fillStyle = halo;
    u.beginPath();
    u.arc(sx, sy, R * 2.3, 0, 6.283);
    u.fill();
    u.globalCompositeOperation = "source-over";

    var ocean = u.createRadialGradient(
      cx + Math.cos(SUN_ANGLE) * R * 0.55, cy + Math.sin(SUN_ANGLE) * R * 0.55, R * 0.05,
      cx, cy, R);
    ocean.addColorStop(0, "#0a1421");
    ocean.addColorStop(0.55, "#070e18");
    ocean.addColorStop(1, "#04070d");
    u.beginPath();
    u.arc(cx, cy, R, 0, 6.283);
    u.fillStyle = ocean;
    u.fill();

    var o = over.getContext("2d");
    o.setTransform(dpr, 0, 0, dpr, 0, 0);
    o.clearRect(0, 0, W, H);
    o.globalCompositeOperation = "lighter";

    /* the lit limb, inside the disc and over the lights */
    o.save();
    o.beginPath();
    o.arc(cx, cy, R, 0, 6.283);
    o.clip();
    var limb = o.createRadialGradient(sx, sy, R * 0.02, sx, sy, R * 1.15);
    limb.addColorStop(0, "rgba(255,225,185,0.42)");
    limb.addColorStop(0.35, "rgba(150,190,255,0.055)");
    limb.addColorStop(1, "rgba(120,170,255,0)");
    o.fillStyle = limb;
    o.fillRect(cx - R, cy - R, R * 2, R * 2);
    o.restore();

    var air = o.createRadialGradient(cx, cy, R * 0.965, cx, cy, R * 1.10);
    air.addColorStop(0, "rgba(120,190,255,0)");
    air.addColorStop(0.30, "rgba(126,196,255,0.20)");
    air.addColorStop(0.55, "rgba(110,175,255,0.085)");
    air.addColorStop(1, "rgba(90,150,240,0)");
    o.fillStyle = air;
    o.beginPath();
    o.arc(cx, cy, R * 1.12, 0, 6.283);
    o.fill();

    drawFlare(o, sx, sy, cx, cy, R, flare);
    o.globalCompositeOperation = "source-over";
  }

  function drawGlobe(state) {
    var R = state.R, cx = state.cx, cy = state.cy;
    var rot = state.rot * Math.PI / 180, tilt = 16 * Math.PI / 180;
    var cosR = Math.cos(rot), sinR = Math.sin(rot);
    var cosT = Math.cos(tilt), sinT = Math.sin(tilt);

    var key = Math.round(R) + "|" + Math.round(cx) + "|" + Math.round(cy) +
      "|" + Math.round(state.flare * 20) + "|" + canvas.width;
    if (key !== layerKey) { buildLayers(cx, cy, R, state.flare); layerKey = key; }

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    ctx.drawImage(under, 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, 6.283);
    ctx.clip();

    /* land: rings whose bounding cap is entirely behind the horizon are skipped */
    ctx.beginPath();
    for (var r = 0; r < outlineOffsets.length - 1; r++) {
      if (ringZ(r, cosR, sinR, cosT, sinT) < -ringSpan[r]) continue;
      var from = outlineOffsets[r], to = outlineOffsets[r + 1];
      var started = false;
      for (var i = from; i < to; i++) {
        var p = project(outlineXYZ, i, cosR, sinR, cosT, sinT);
        var px = p[0], py = p[1];
        if (p[2] < 0) {
          var len = Math.hypot(px, py) || 1e-6;
          px /= len; py /= len;
        }
        var X = cx + px * R, Y = cy - py * R;
        if (!started) { ctx.moveTo(X, Y); started = true; } else { ctx.lineTo(X, Y); }
      }
      if (started) ctx.closePath();
    }
    ctx.fillStyle = "#0e1826";
    ctx.fill("evenodd");
    ctx.strokeStyle = "rgba(76,108,146,0.30)";
    ctx.lineWidth = 0.7;
    ctx.stroke();

    /* the lights */
    ctx.globalCompositeOperation = "lighter";
    var size = Math.max(3.8, R * 0.019);
    for (var c = 0; c < nCountries; c++) {
      var count = millions(c, state.year);
      if (count <= 0) continue;
      var from2 = lightOffsets[c], to2 = lightOffsets[c + 1];
      var pool = to2 - from2;
      var full = Math.min(Math.floor(count), pool);
      var step = stride * state.detail;
      for (var k = 0; k < pool; k += step) {
        var alpha = k < full ? 1 : (k === full ? count - full : 0);
        if (alpha <= 0.02) break;
        var q = project(lightXYZ, from2 + k, cosR, sinR, cosT, sinT);
        if (q[2] <= 0) continue;
        ctx.globalAlpha = alpha * (0.30 + 0.70 * q[2]);
        var sSize = size * (0.72 + 0.28 * q[2]) * (step > 1 ? 1 + 0.16 * step : 1);
        ctx.drawImage(lamp, cx + q[0] * R - sSize / 2, cy - q[1] * R - sSize / 2, sSize, sSize);
      }
    }
    ctx.globalAlpha = 1;
    ctx.restore();

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "lighter";
    ctx.drawImage(over, 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalCompositeOperation = "source-over";
  }

  var GHOSTS = [
    [-0.42, 0.085, "rgba(255,208,150,0.10)"],
    [0.24, 0.042, "rgba(120,220,255,0.11)"],
    [0.52, 0.115, "rgba(255,180,110,0.075)"],
    [0.82, 0.055, "rgba(170,140,255,0.10)"],
    [1.12, 0.155, "rgba(120,200,255,0.055)"],
    [1.45, 0.075, "rgba(255,190,120,0.075)"],
    [1.85, 0.215, "rgba(150,175,255,0.04)"]
  ];

  function drawFlare(ctx, sx, sy, cx, cy, R, strength) {
    if (strength <= 0.01) return;
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = strength;

    /* core */
    var core = ctx.createRadialGradient(sx, sy, 0, sx, sy, R * 0.26);
    core.addColorStop(0, "rgba(255,252,244,0.95)");
    core.addColorStop(0.10, "rgba(255,232,196,0.55)");
    core.addColorStop(0.45, "rgba(255,190,120,0.13)");
    core.addColorStop(1, "rgba(255,170,90,0)");
    ctx.fillStyle = core;
    ctx.beginPath();
    ctx.arc(sx, sy, R * 0.26, 0, 6.283);
    ctx.fill();

    /* anamorphic streak */
    var reach = R * 2.05;
    var streak = ctx.createLinearGradient(sx - reach, sy, sx + reach, sy);
    streak.addColorStop(0, "rgba(120,180,255,0)");
    streak.addColorStop(0.36, "rgba(150,200,255,0.055)");
    streak.addColorStop(0.5, "rgba(226,238,255,0.22)");
    streak.addColorStop(0.64, "rgba(150,200,255,0.055)");
    streak.addColorStop(1, "rgba(120,180,255,0)");
    ctx.fillStyle = streak;
    ctx.fillRect(sx - reach, sy - R * 0.009, reach * 2, R * 0.018);

    /* ghosts along the optical axis */
    var vx = cx - sx, vy = cy - sy;
    for (var i = 0; i < GHOSTS.length; i++) {
      var g = GHOSTS[i];
      var gx = sx + vx * (1 + g[0]), gy = sy + vy * (1 + g[0]);
      var gr = R * g[1];
      var grad = ctx.createRadialGradient(gx, gy, gr * 0.35, gx, gy, gr);
      grad.addColorStop(0, g[2]);
      grad.addColorStop(0.72, g[2].replace(/[\d.]+\)$/, "0.03)"));
      grad.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(gx, gy, gr, 0, 6.283);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  /* --------------------------------------------------- scroll choreography */

  var stops = [].slice.call(document.querySelectorAll("[data-stage]")).map(function (node) {
    return { node: node, state: JSON.parse(node.dataset.stage), anchor: 0 };
  });
  function measureStops() {
    stops.forEach(function (stop) {
      var box = stop.node.getBoundingClientRect();
      stop.anchor = box.top + window.scrollY + Math.min(box.height * 0.42, window.innerHeight * 0.5);
    });
  }

  var view = { year: 1950, scale: 1, cx: 0.5, cy: 0.5, veil: 0, hud: 0 };
  function readScroll() {
    var focus = window.scrollY + window.innerHeight * 0.5;
    var prev = stops[0], next = stops[0];
    for (var i = 0; i < stops.length; i++) {
      if (stops[i].anchor <= focus) { prev = stops[i]; next = stops[Math.min(i + 1, stops.length - 1)]; }
    }
    if (focus < stops[0].anchor) { prev = next = stops[0]; }
    var span = next.anchor - prev.anchor;
    var t = span > 0 ? smooth(clamp((focus - prev.anchor) / span, 0, 1)) : 0;
    for (var key in view) view[key] = lerp(prev.state[key], next.state[key], t);
  }

  var hud = document.getElementById("hud");
  var hudYear = document.getElementById("hud-year");
  var hudPeople = document.getElementById("hud-people");
  var hudBasis = document.getElementById("hud-basis");
  var veil = document.getElementById("veil");
  var lastYearShown = null, lastHud = null;

  function paint(time) {
    readScroll();
    var minSide = Math.min(W, H * 1.25);
    var state = {
      R: minSide * 0.37 * view.scale,
      cx: W * view.cx,
      cy: H * view.cy,
      year: view.year,
      rot: (reduced ? 0 : time * 0.0042) + window.scrollY * 0.012 + 18,
      flare: clamp(1 - view.veil * 0.85, 0.12, 1),
      /* Behind a nearly opaque veil the globe is a suggestion, so it is drawn
         as one: most of the story is figures, and this is most of the scroll. */
      detail: view.veil > 0.88 ? 3 : view.veil > 0.78 ? 2 : 1
    };
    drawGlobe(state);

    veil.style.opacity = view.veil;
    var on = view.hud > 0.5;
    if (on !== lastHud) { hud.classList.toggle("on", on); lastHud = on; }
    var year = Math.round(view.year);
    if (year !== lastYearShown) {
      lastYearShown = year;
      hudYear.textContent = year;
      hudPeople.textContent = fmt(worldBillions(year), 2) + " billion";
      hudBasis.textContent = year <= GLOBE.estimatesTo
        ? "UN estimate" : "UN medium projection, run here";
    }
  }

  var last = performance.now();
  function frame(time) {
    var dt = time - last; last = time;
    frameCost = frameCost * 0.9 + dt * 0.1;
    if (frameCost > 26 && stride < 3) stride++;
    else if (frameCost < 15 && stride > 1) stride--;
    paint(time);
    requestAnimationFrame(frame);
  }

  buildLamp();
  resize();
  window.addEventListener("resize", resize);
  window.addEventListener("orientationchange", resize);
  requestAnimationFrame(function (t) { last = t; frame(t); });

  /* ------------------------------------------------------------- reveals */

  if ("IntersectionObserver" in window) {
    var seen = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { entry.target.classList.add("seen"); seen.unobserve(entry.target); }
      });
    }, { rootMargin: "0px 0px -12% 0px", threshold: 0.08 });
    [].forEach.call(document.querySelectorAll(".rise"), function (node) { seen.observe(node); });
  } else {
    [].forEach.call(document.querySelectorAll(".rise"), function (n) { n.classList.add("seen"); });
  }

  /* ------------------------------------------------------------- tooltip */

  var tip = document.getElementById("tip");
  function showTip(event, html) {
    tip.innerHTML = html;
    tip.style.opacity = "1";
    var x = clamp(event.clientX, 150, window.innerWidth - 150);
    tip.style.left = x + "px";
    tip.style.top = (event.clientY - 14) + "px";
  }
  function hideTip() { tip.style.opacity = "0"; }
  function hoverable(node, html) {
    node.style.cursor = "crosshair";
    node.addEventListener("mousemove", function (e) { showTip(e, html); });
    node.addEventListener("mouseleave", hideTip);
    /* Keyboard users get the same reading, anchored to the mark itself. */
    node.addEventListener("focus", function () {
      var box = node.getBoundingClientRect();
      showTip({ clientX: box.left + box.width / 2, clientY: box.top }, html);
    });
    node.addEventListener("blur", hideTip);
  }

  /* ------------------------------------------------------------- figures */

  var GOLD = css("--gold") || "#c38617";
  var CYAN = css("--cyan") || "#1aa1d2";
  var ROSE = css("--rose") || "#fb4374";
  var VIOLET = css("--violet") || "#a571fb";
  var SEQ = ["--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6"].map(css);
  var LAMPC = css("--seq-6") || "#fdcb84";
  var GRID = "#141d2a";

  function axisLabel(parent, x, y, text, cls, anchor) {
    var node = el("text", { x: x, y: y, class: cls || "ax-text", "text-anchor": anchor || "middle" }, parent);
    node.textContent = text;
    return node;
  }

  /* --- world population, 1950-2150 ------------------------------------- */
  (function worldFigure() {
    var svg = document.getElementById("fig-world");
    if (!svg) return;
    var Wd = 960, Ht = 440, L = 54, Rm = 22, T = 26, B = 46;
    svg.setAttribute("viewBox", "0 0 " + Wd + " " + Ht);
    var x0 = 1950, x1 = 2150, y1max = 11.5;
    var X = function (y) { return L + (y - x0) / (x1 - x0) * (Wd - L - Rm); };
    var Y = function (v) { return Ht - B - v / y1max * (Ht - T - B); };

    for (var v = 0; v <= 10; v += 2) {
      el("line", { x1: L, x2: Wd - Rm, y1: Y(v), y2: Y(v), class: "grid-line" }, svg);
      axisLabel(svg, L - 10, Y(v) + 4, v === 0 ? "0" : v + (v === 10 ? " bn" : ""), "ax-text", "end");
    }
    [1950, 1975, 2000, 2025, 2050, 2075, 2100, 2125, 2150].forEach(function (year) {
      axisLabel(svg, X(year), Ht - B + 22, year);
    });
    el("line", { x1: L, x2: Wd - Rm, y1: Y(0), y2: Y(0), class: "ax-line" }, svg);

    /* the extension band and dashed median, drawn under the solid history */
    var ext = STORY.extension;
    var anchors = [
      { year: 2100, lo: ext.at2100, mid: ext.at2100, hi: ext.at2100 },
      { year: 2125, lo: ext.at2125[0], mid: ext.at2125[1], hi: ext.at2125[2] },
      { year: 2150, lo: ext.at2150[0], mid: ext.at2150[1], hi: ext.at2150[2] }
    ];
    var band = anchors.map(function (a) { return X(a.year) + "," + Y(a.hi); })
      .concat(anchors.slice().reverse().map(function (a) { return X(a.year) + "," + Y(a.lo); }));
    el("polygon", { points: band.join(" "), fill: VIOLET, "fill-opacity": 0.3 }, svg);
    el("polyline", {
      points: anchors.map(function (a) { return X(a.year) + "," + Y(a.mid); }).join(" "),
      class: "series-line", stroke: VIOLET, "stroke-dasharray": "7 6"
    }, svg);
    anchors.forEach(function (a) {
      el("circle", { cx: X(a.year), cy: Y(a.mid), r: 4, fill: VIOLET, stroke: "#0a0f18", "stroke-width": 2 }, svg);
    });

    /* history and projection */
    function segment(fromYear, toYear, colour) {
      var pts = [];
      for (var year = fromYear; year <= toYear; year++) {
        pts.push(X(year) + "," + Y(GLOBE.world[year - GLOBE.firstYear]));
      }
      el("polyline", { points: pts.join(" "), class: "series-line", stroke: colour }, svg);
    }
    segment(1950, GLOBE.estimatesTo, LAMPC);
    segment(GLOBE.estimatesTo, 2100, CYAN);

    /* the two boundaries that matter */
    [[2024, "projection begins"], [2100, "UN assumptions stop"]].forEach(function (mark) {
      el("line", {
        x1: X(mark[0]), x2: X(mark[0]), y1: T - 4, y2: Y(0),
        stroke: "#2c3a4d", "stroke-width": 1, "stroke-dasharray": "3 5"
      }, svg);
      var label = axisLabel(svg, X(mark[0]) + 6, T + 8, mark[1], "ax-text", "start");
      label.setAttribute("fill", "#7d8ca6");
    });

    /* the peak of the drawn curve, read off the curve itself */
    var peak = 0, peakYear = 0;
    for (var i = 0; i <= 2100 - GLOBE.firstYear; i++) {
      if (GLOBE.world[i] > peak) { peak = GLOBE.world[i]; peakYear = GLOBE.firstYear + i; }
    }
    el("circle", { cx: X(peakYear), cy: Y(peak), r: 3.5, fill: CYAN }, svg);
    var peakText = axisLabel(svg, X(peakYear), Y(peak) - 14, fmt(peak, 2) + " bn, " + peakYear, "mark-label");
    peakText.setAttribute("text-anchor", "middle");

    var endLabel = axisLabel(svg, X(2150), Y(ext.at2150[1]) + 26,
      fmt(ext.at2150[1], 2) + " bn", "mark-label", "end");
    endLabel.setAttribute("fill", VIOLET);
    var endRange = axisLabel(svg, X(2150), Y(ext.at2150[1]) + 42,
      "5th–95th " + fmt(ext.at2150[0], 2) + "–" + fmt(ext.at2150[2], 2), "ax-text", "end");
    endRange.setAttribute("font-size", "11.5");

    /* crosshair */
    var hitLine = el("line", { y1: T - 6, y2: Y(0), stroke: "#4a5b73", "stroke-width": 1, opacity: 0 }, svg);
    var hitDot = el("circle", { r: 4.5, fill: "#fff", opacity: 0 }, svg);
    var hit = el("rect", { x: L, y: T - 6, width: Wd - L - Rm, height: Ht - T - B + 6, fill: "transparent" }, svg);
    hit.style.cursor = "crosshair";
    hit.addEventListener("mousemove", function (event) {
      var box = svg.getBoundingClientRect();
      var px = (event.clientX - box.left) / box.width * Wd;
      var year = Math.round(clamp(x0 + (px - L) / (Wd - L - Rm) * (x1 - x0), x0, x1));
      var value, basis;
      if (year <= 2100) {
        value = GLOBE.world[year - GLOBE.firstYear];
        basis = year <= GLOBE.estimatesTo ? "UN estimate" : "UN medium projection, run here";
      } else {
        var nearest = anchors.reduce(function (best, a) {
          return Math.abs(a.year - year) < Math.abs(best.year - year) ? a : best;
        });
        year = nearest.year;
        value = nearest.mid;
        basis = "project extension &middot; 5th&ndash;95th " + fmt(nearest.lo, 2) + "&ndash;" + fmt(nearest.hi, 2);
      }
      hitLine.setAttribute("x1", X(year));
      hitLine.setAttribute("x2", X(year));
      hitLine.setAttribute("opacity", 1);
      hitDot.setAttribute("cx", X(year));
      hitDot.setAttribute("cy", Y(value));
      hitDot.setAttribute("opacity", 1);
      showTip(event, "<b>" + year + "</b> &middot; " + fmt(value, 2) +
        " billion<br><span class='k'>" + basis + "</span>");
    });
    hit.addEventListener("mouseleave", function () {
      hitLine.setAttribute("opacity", 0);
      hitDot.setAttribute("opacity", 0);
      hideTip();
    });

    /* table */
    var rows = [];
    for (var year = 1950; year <= 2100; year += 25) {
      rows.push([year, fmt(GLOBE.world[year - GLOBE.firstYear], 2),
        year <= GLOBE.estimatesTo ? "UN estimate" : "UN medium, run here"]);
    }
    rows.push([2125, fmt(ext.at2125[1], 2) + " (" + fmt(ext.at2125[0], 2) + "–" + fmt(ext.at2125[2], 2) + ")", "project extension"]);
    rows.push([2150, fmt(ext.at2150[1], 2) + " (" + fmt(ext.at2150[0], 2) + "–" + fmt(ext.at2150[2], 2) + ")", "project extension"]);
    table("tbl-world", ["Year", "World population, billions", "Basis"], rows, [0, 1]);
  })();

  /* --- dispersion of completed family size ----------------------------- */
  (function dispersionFigure() {
    var svg = document.getElementById("fig-cv");
    if (!svg) return;
    var d = STORY.dispersion;
    var Wd = 960, Ht = 250, L = 26, Rm = 26, T = 54, B = 52;
    svg.setAttribute("viewBox", "0 0 " + Wd + " " + Ht);
    var lo = 0.40, hi = 0.84;
    var X = function (v) { return L + (v - lo) / (hi - lo) * (Wd - L - Rm); };
    var mid = (T + Ht - B) / 2;

    /* the range the model carries through every result */
    el("rect", {
      x: X(d.cvLow), y: T - 16, width: X(d.cvHigh) - X(d.cvLow), height: (Ht - B) - (T - 16),
      fill: "#ffffff", "fill-opacity": 0.028, stroke: "#243141", "stroke-dasharray": "4 5"
    }, svg);
    var rangeLabel = axisLabel(svg, X((d.cvLow + d.cvHigh) / 2), T - 24,
      "range carried through every result: " + fmt(d.cvLow, 2) + " to " + fmt(d.cvHigh, 2));
    rangeLabel.setAttribute("fill", "#7d8ca6");

    for (var t = 0.40; t <= 0.841; t += 0.05) {
      var tx = X(t);
      el("line", { x1: tx, x2: tx, y1: Ht - B, y2: Ht - B + 6, class: "ax-line" }, svg);
      axisLabel(svg, tx, Ht - B + 22, fmt(t, 2));
    }
    el("line", { x1: L, x2: Wd - Rm, y1: Ht - B, y2: Ht - B, class: "ax-line" }, svg);
    axisLabel(svg, (L + Wd - Rm) / 2, Ht - 12,
      "coefficient of variation of completed family size", "ax-text big");

    /* deterministic jitter so the strip reads as a distribution */
    var seed = 11;
    function rand() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }
    d.rows.forEach(function (row) {
      var low = row.mean <= 2.2;
      var y = mid + (rand() - 0.5) * 58;
      var dot = el("circle", {
        cx: X(row.cv), cy: y, r: 5.4, fill: low ? LAMPC : CYAN,
        "fill-opacity": low ? 0.95 : 0.62, stroke: "#0a0f18", "stroke-width": 1.4,
        role: "img",
        "aria-label": row.country + ", coefficient of variation " + fmt(row.cv, 2)
      }, svg);
      hoverable(dot, "<b>" + row.country + "</b><br>CV " + fmt(row.cv, 3) +
        " &middot; mean " + fmt(row.mean, 2) + " children<br><span class='k'>" +
        row.source + " &middot; " + Math.round(row.women / 1000).toLocaleString("en-US") +
        "k women</span>");
    });

    /* the United States, from an independent source */
    var us = el("circle", {
      cx: X(d.usCheck), cy: mid + 36, r: 6.2, fill: ROSE, stroke: "#0a0f18", "stroke-width": 1.6,
      tabindex: "0", role: "img", "aria-label": "United States, CDC cohort tables, 0.69"
    }, svg);
    hoverable(us, "<b>United States</b><br>CV " + fmt(d.usCheck, 3) + " &middot; mean " +
      fmt(d.usMean, 2) + " children<br><span class='k'>CDC/NCHS cohort tables, an independent check</span>");
    var usLabel = axisLabel(svg, X(d.usCheck), mid + 60, "United States", "mark-label sm");
    usLabel.setAttribute("fill", ROSE);

    /* the median the model uses */
    el("line", { x1: X(d.median), x2: X(d.median), y1: T - 10, y2: Ht - B, stroke: LAMPC, "stroke-width": 2 }, svg);
    var medianLabel = axisLabel(svg, X(d.median), T - 2, "median " + fmt(d.median, 2), "mark-label");
    medianLabel.setAttribute("fill", LAMPC);

    table("tbl-cv", ["Country", "CV", "Mean children", "Women", "Source"],
      d.rows.map(function (r) {
        return [r.country, fmt(r.cv, 3), fmt(r.mean, 2), r.women.toLocaleString("en-US"), r.source];
      }), [1, 2, 3]);
  })();

  /* --- why the next generation is not a random sample ------------------ */
  (function samplingFigure() {
    var svg = document.getElementById("fig-sampling");
    if (!svg) return;
    var Wd = 960, Ht = 330;
    svg.setAttribute("viewBox", "0 0 " + Wd + " " + Ht);

    /* One hundred women, family sizes drawn to match the measured mean and
       spread. Deterministic, and labelled in the caption as an illustration. */
    var seed = 4;
    function rand() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }
    var sizes = [], mean = 1.8;
    var shares = [0.19, 0.20, 0.36, 0.15, 0.07, 0.03];
    shares.forEach(function (share, kids) {
      var n = Math.round(share * 100);
      for (var i = 0; i < n; i++) sizes.push(kids);
    });
    while (sizes.length < 100) sizes.push(2);
    sizes.length = 100;
    for (var i = sizes.length - 1; i > 0; i--) {
      var j = Math.floor(rand() * (i + 1)); var tmp = sizes[i]; sizes[i] = sizes[j]; sizes[j] = tmp;
    }

    var cols = 20, cell = 26, x0 = 40, yTop = 54, yBottom = 214;
    var born = sizes.reduce(function (a, b) { return a + b; }, 0);
    var motherMean = born / 100;
    /* Mean family size of the mother a randomly chosen child was born to. */
    var childWeighted = sizes.reduce(function (a, n) { return a + n * n; }, 0) / born;

    function row(y, label, sub) {
      var t = axisLabel(svg, x0, y - 20, label, "mark-label", "start");
      t.setAttribute("font-size", "14");
      var s = axisLabel(svg, x0, y - 4, sub, "ax-text", "start");
      s.setAttribute("fill", "#7d8ca6");
    }
    row(yTop, "One hundred women, with their completed families",
      "mean " + fmt(motherMean, 2) + " children each");
    sizes.forEach(function (n, index) {
      var cxp = x0 + (index % cols) * cell + 8;
      var cyp = yTop + Math.floor(index / cols) * cell + 10;
      var shade = n === 0 ? 0.18 : 0.30 + Math.min(n, 5) * 0.14;
      var mark = el("circle", {
        cx: cxp, cy: cyp, r: 7.4, fill: LAMPC, "fill-opacity": shade,
        stroke: n === 0 ? "#33415a" : LAMPC, "stroke-opacity": n === 0 ? 1 : 0.55, "stroke-width": 1.2
      }, svg);
      hoverable(mark, "<b>" + n + (n === 1 ? " child" : " children") + "</b>");
      var num = axisLabel(svg, cxp, cyp + 4, String(n), "ax-text");
      num.setAttribute("font-size", "10.5");
      num.setAttribute("fill", n === 0 ? "#63728c" : "#0b1119");
      num.setAttribute("font-weight", "600");
    });

    row(yBottom + 34, "The generation they produced, one mark per child",
      "each child's mother had " + fmt(childWeighted, 2) + " children on average");
    var perRow = 46, k = 0;
    for (var w = 0; w < sizes.length; w++) {
      for (var c = 0; c < sizes[w]; c++) {
        var cxp2 = x0 + (k % perRow) * 19 + 6;
        var cyp2 = yBottom + 54 + Math.floor(k / perRow) * 19;
        el("circle", {
          cx: cxp2, cy: cyp2, r: 5.2, fill: LAMPC,
          "fill-opacity": 0.22 + Math.min(sizes[w], 5) * 0.13, stroke: "none"
        }, svg);
        k++;
      }
    }

    var arrow = el("text", { x: Wd - 40, y: yBottom + 8, class: "mark-label", "text-anchor": "end" }, svg);
    arrow.textContent = fmt(motherMean, 2) + "  →  " + fmt(childWeighted, 2) + " children";
    arrow.setAttribute("font-size", "17");
    arrow.setAttribute("fill", LAMPC);
    var arrowSub = el("text", { x: Wd - 40, y: yBottom + 28, class: "ax-text", "text-anchor": "end" }, svg);
    arrowSub.textContent = "the shift a national average cannot represent";
  })();

  /* --- the ladder ------------------------------------------------------ */
  (function ladderFigure() {
    var svg = document.getElementById("fig-ladder");
    if (!svg) return;
    var steps = STORY.ladder;
    var Wd = 960, Ht = 400, L = 56, Rm = 24, T = 40, B = 76;
    svg.setAttribute("viewBox", "0 0 " + Wd + " " + Ht);
    var top = 11.2;
    var Y = function (v) { return Ht - B - v / top * (Ht - T - B); };

    for (var v = 0; v <= 10; v += 2) {
      el("line", { x1: L, x2: Wd - Rm, y1: Y(v), y2: Y(v), class: "grid-line" }, svg);
      axisLabel(svg, L - 10, Y(v) + 4, v === 10 ? "10 bn" : String(v), "ax-text", "end");
    }
    el("line", { x1: L, x2: Wd - Rm, y1: Y(0), y2: Y(0), class: "ax-line" }, svg);

    var bars = [
      { label: "Benchmark", sub: "stable-low,|no selection", from: 0, to: steps[0].value, kind: "level", basis: steps[0].basis },
      { label: "+ selection", sub: "measured spread|and persistence", from: steps[0].value, to: steps[1].value, kind: "up", basis: steps[1].basis },
      { label: "+ named groups", sub: "Haredi, Amish|and the rest", from: steps[1].value, to: steps[2].value, kind: "up", basis: steps[2].basis },
      { label: "− pressure", sub: "illustrative 4%|per decade", from: steps[2].value, to: steps[3].value, kind: "down", basis: steps[3].basis },
      { label: "Result", sub: "world population|in 2150", from: 0, to: steps[3].value, kind: "level", basis: "the end of the ladder" }
    ];
    var slot = (Wd - L - Rm) / bars.length;
    var bw = Math.min(slot * 0.56, 96);

    bars.forEach(function (bar, i) {
      var cx = L + slot * (i + 0.5);
      var hiV = Math.max(bar.from, bar.to), loV = Math.min(bar.from, bar.to);
      var colour = bar.kind === "up" ? GOLD : bar.kind === "down" ? ROSE : "#5b6b85";
      var y = Y(hiV), h = Math.max(Y(loV) - Y(hiV), 3);
      var rect = el("rect", {
        x: cx - bw / 2, y: y, width: bw, height: h, rx: 4, fill: colour,
        "fill-opacity": bar.kind === "level" ? 0.85 : 1,
        tabindex: "0", role: "img",
        "aria-label": bar.label + ", " + fmt(bar.to, 2) + " billion"
      }, svg);
      hoverable(rect, "<b>" + bar.label + "</b><br>" +
        (bar.kind === "level" ? fmt(bar.to, 2) + " billion in 2150"
          : (bar.to > bar.from ? "+" : "−") + fmt(Math.abs(bar.to - bar.from), 2) +
            " billion, to " + fmt(bar.to, 2)) +
        "<br><span class='k'>" + bar.basis + "</span>");

      if (i > 0) {
        el("line", {
          x1: cx - slot + bw / 2, x2: cx - bw / 2, y1: Y(bar.from), y2: Y(bar.from),
          stroke: "#33415a", "stroke-width": 1, "stroke-dasharray": "3 4"
        }, svg);
      }
      var value = bar.kind === "level" ? fmt(bar.to, 2)
        : (bar.to > bar.from ? "+" : "−") + fmt(Math.abs(bar.to - bar.from), 2);
      var label = axisLabel(svg, cx, y - 12, value, "mark-label");
      label.setAttribute("fill", bar.kind === "down" ? ROSE : bar.kind === "up" ? css("--seq-5") : "#c3cede");
      var name = axisLabel(svg, cx, Ht - B + 24, bar.label, "ax-text big");
      name.setAttribute("fill", "#c3cede");
      bar.sub.split("|").forEach(function (line, n) {
        var sub = axisLabel(svg, cx, Ht - B + 42 + n * 14, line, "ax-text");
        sub.setAttribute("font-size", "11.5");
      });
    });

    table("tbl-ladder", ["Step", "World 2150, billions", "Change", "What it rests on"],
      steps.map(function (s) {
        return [s.label, fmt(s.value, 3), s.change === null ? "—" :
          (s.change > 0 ? "+" : "−") + fmt(Math.abs(s.change), 3), s.basis];
      }), [1, 2]);
  })();

  /* --- the break-even grid --------------------------------------------- */
  (function gridFigure() {
    var svg = document.getElementById("fig-grid");
    if (!svg) return;
    var b = STORY.boundary;
    var cvs = [], pers = [];
    b.grid.forEach(function (cell) {
      if (cvs.indexOf(cell.cv) < 0) cvs.push(cell.cv);
      if (pers.indexOf(cell.persistence) < 0) pers.push(cell.persistence);
    });
    cvs.sort(function (a, c) { return a - c; });
    pers.sort(function (a, c) { return a - c; });

    var Wd = 960, Ht = 340, L = 96, Rm = 30, T = 76, B = 96;
    svg.setAttribute("viewBox", "0 0 " + Wd + " " + Ht);
    var cw = (Wd - L - Rm) / pers.length, ch = (Ht - T - B) / cvs.length;
    var max = 0, min = Infinity;
    b.grid.forEach(function (cell) {
      if (cell.breakEven > max) max = cell.breakEven;
      if (cell.breakEven < min) min = cell.breakEven;
    });

    function mix(a, c, t) {
      function part(hex, i) { return parseInt(hex.substr(1 + i * 2, 2), 16); }
      var out = "#";
      for (var i = 0; i < 3; i++) {
        var v = Math.round(part(a, i) + (part(c, i) - part(a, i)) * t);
        out += ("0" + v.toString(16)).slice(-2);
      }
      return out;
    }
    /* Linear in the value, so the gradient legend means what it says. */
    function rampAt(value) {
      var t = clamp((value - min) / (max - min), 0, 1) * (SEQ.length - 1);
      var i = Math.min(Math.floor(t), SEQ.length - 2);
      return { colour: mix(SEQ[i], SEQ[i + 1], t - i), step: t };
    }

    b.grid.forEach(function (cell) {
      var col = pers.indexOf(cell.persistence), row = cvs.indexOf(cell.cv);
      var x = L + col * cw, y = T + row * ch;
      var isBenchmark = Math.abs(cell.cv - STORY.dispersion.cv) < 1e-6 &&
        Math.abs(cell.persistence - STORY.dispersion.persistence) < 1e-6;
      var ramp = rampAt(cell.breakEven);
      var rect = el("rect", {
        x: x + 1, y: y + 1, width: cw - 2, height: ch - 2, rx: 3,
        fill: ramp.colour,
        stroke: isBenchmark ? "#ffffff" : "none", "stroke-width": isBenchmark ? 2 : 0,
        tabindex: isBenchmark ? "0" : null, role: "img",
        "aria-label": "spread " + fmt(cell.cv, 2) + ", persistence " + fmt(cell.persistence, 3) +
          ": break-even " + fmt(cell.breakEven, 2) + " percent per decade"
      }, svg);
      hoverable(rect, "<b>" + fmt(cell.breakEven, 2) + "% per decade</b><br>" +
        "cancels a selection effect of &times;" + fmt(cell.effect, 3) +
        "<br><span class='k'>spread " + fmt(cell.cv, 2) + " &middot; persistence " +
        fmt(cell.persistence, 3) + (isBenchmark ? " &middot; the benchmark" : "") + "</span>");
      /* No number inside every cell: a gold ramp's midtones carry neither dark
         nor light text well. The benchmark is labelled outside the grid, the
         ends are on the legend, and hover or the table gives the rest. */
      if (isBenchmark) {
        el("line", {
          x1: x + cw / 2, x2: x + cw / 2, y1: y - 6, y2: T - 12,
          stroke: "#ffffff", "stroke-width": 1, "stroke-opacity": 0.55
        }, svg);
        var mark = axisLabel(svg, x + cw / 2, T - 18,
          "benchmark: " + fmt(cell.breakEven, 2) + "% per decade", "mark-label");
        mark.setAttribute("font-size", "12.5");
      }
    });

    cvs.forEach(function (cv, row) {
      var label = axisLabel(svg, L - 12, T + row * ch + ch / 2 + 4, fmt(cv, 2), "ax-text big", "end");
      label.setAttribute("fill", cv === STORY.dispersion.cv ? LAMPC : "#8794ab");
    });
    pers.forEach(function (p, col) {
      if (col % 2 !== 0 && pers.length > 6) return;
      axisLabel(svg, L + col * cw + cw / 2, Ht - B + 22, fmt(p, 3));
    });
    var yTitle = axisLabel(svg, 4, T - 8, "spread of\u00a0family size", "ax-text", "start");
    yTitle.setAttribute("fill", "#7d8ca6");
    axisLabel(svg, L + (Wd - L - Rm) / 2, Ht - B + 46,
      "parent–child correlation in completed family size", "ax-text big");
    var note = axisLabel(svg, L + (Wd - L - Rm) / 2, Ht - B + 68,
      "cell colour: additional decline per decade that exactly cancels selection", "ax-text");
    note.setAttribute("fill", "#7d8ca6");

    /* ramp legend */
    var lx = L, ly = 20, lw = 210, lh = 9;
    var gradId = "ramp";
    var defs = el("defs", {}, svg);
    var grad = el("linearGradient", { id: gradId, x1: "0", x2: "1" }, defs);
    SEQ.forEach(function (colour, i) {
      el("stop", { offset: (i / (SEQ.length - 1) * 100) + "%", "stop-color": colour }, grad);
    });
    el("rect", { x: lx, y: ly, width: lw, height: lh, rx: 2, fill: "url(#" + gradId + ")" }, svg);
    var lo = axisLabel(svg, lx, ly - 6, fmt(min, 2) + "%", "ax-text", "start");
    lo.setAttribute("fill", "#7d8ca6");
    var hi = axisLabel(svg, lx + lw, ly - 6, fmt(max, 2) + "%", "ax-text", "end");
    hi.setAttribute("fill", "#7d8ca6");

    table("tbl-grid", ["Spread (CV)", "Persistence", "Selection effect", "Break-even, % per decade"],
      b.grid.map(function (cell) {
        return [fmt(cell.cv, 2), fmt(cell.persistence, 3), "×" + fmt(cell.effect, 3), fmt(cell.breakEven, 2)];
      }), [0, 1, 2, 3]);
  })();

  /* --- what is uncertain ------------------------------------------------ */
  (function widthFigure() {
    var svg = document.getElementById("fig-width");
    if (!svg) return;
    var u = STORY.uncertainty;
    var rows = [
      { label: "Fertility path", value: u.fertility },
      { label: "Mechanism parameters", value: u.mechanism },
      { label: "Mortality", value: u.mortality },
      { label: "Migration", value: u.migration }
    ];
    var Wd = 960, Ht = 260, L = 190, Rm = 90, T = 40, B = 46;
    svg.setAttribute("viewBox", "0 0 " + Wd + " " + Ht);
    var max = 8;
    var X = function (v) { return L + v / max * (Wd - L - Rm); };
    var rowH = (Ht - T - B) / rows.length;

    for (var v = 0; v <= 8; v += 2) {
      el("line", { x1: X(v), x2: X(v), y1: T - 8, y2: Ht - B, class: "grid-line" }, svg);
      axisLabel(svg, X(v), Ht - B + 20, v === 8 ? "8 bn" : String(v));
    }
    rows.forEach(function (row, i) {
      var y = T + i * rowH + rowH * 0.5;
      var h = Math.min(rowH * 0.52, 26);
      var rect = el("rect", {
        x: L, y: y - h / 2, width: Math.max(X(row.value) - L, 3), height: h, rx: 4, fill: GOLD,
        tabindex: "0", role: "img",
        "aria-label": row.label + ": " + fmt(row.value, 2) + " billion"
      }, svg);
      hoverable(rect, "<b>" + row.label + "</b><br>" + fmt(row.value, 2) +
        " billion wide at 2150<br><span class='k'>5th to 95th percentile of " +
        u.draws + " draws</span>");
      var name = axisLabel(svg, L - 14, y + 5, row.label, "ax-text big", "end");
      name.setAttribute("fill", "#c3cede");
      var value = axisLabel(svg, X(row.value) + 12, y + 5, fmt(row.value, 2) + " bn", "mark-label", "start");
      value.setAttribute("fill", css("--seq-5"));
    });

    /* everything at once, as a reference rule rather than a fifth bar */
    el("line", {
      x1: X(u.everything), x2: X(u.everything), y1: T - 18, y2: Ht - B + 2,
      stroke: "#8794ab", "stroke-width": 1.5, "stroke-dasharray": "5 4"
    }, svg);
    var ref = axisLabel(svg, X(u.everything), T - 24, "everything at once: " + fmt(u.everything, 2) + " bn", "ax-text big");
    ref.setAttribute("fill", "#c3cede");

    table("tbl-width", ["What varies", "Width of the 2150 distribution, billions"],
      rows.map(function (r) { return [r.label, fmt(r.value, 2)]; })
        .concat([["Everything at once", fmt(u.everything, 2)]]), [1]);
  })();

  /* --- where the parameters come from ---------------------------------- */
  (function parameterFigure() {
    var svg = document.getElementById("fig-params");
    if (!svg) return;
    var p = STORY.parameters;
    var Wd = 960, Ht = 130;
    svg.setAttribute("viewBox", "0 0 " + Wd + " " + Ht);
    var gap = 46, x0 = 30, y = 58;
    for (var i = 0; i < p.total; i++) {
      var sourced = i < p.sourced;
      var cxp = x0 + i * gap + 16;
      var mark = el("circle", {
        cx: cxp, cy: y, r: 13,
        fill: sourced ? GOLD : "none", "fill-opacity": sourced ? 0.9 : 0,
        stroke: sourced ? "none" : "#5b6b85", "stroke-width": 1.6, "stroke-dasharray": sourced ? null : "3 3"
      }, svg);
      hoverable(mark, sourced
        ? "<b>Sourced</b><br><span class='k'>checked against the literature recorded in the parameter audit</span>"
        : "<b>Scenario knob</b><br><span class='k'>no independent support exists; carried openly, never fitted</span>");
    }
    var a = axisLabel(svg, x0 + 16, y + 40, p.sourced + " sourced and checked", "ax-text big", "start");
    a.setAttribute("fill", css("--seq-5"));
    var bLabel = axisLabel(svg, x0 + p.sourced * gap + 16, y + 40, p.knobs + " scenario knobs", "ax-text big", "start");
    bLabel.setAttribute("fill", "#8794ab");
  })();

  /* ---------------------------------------------------------------- table */

  function table(id, headers, rows, numeric) {
    var node = document.getElementById(id);
    if (!node) return;
    var thead = document.createElement("thead");
    var tr = document.createElement("tr");
    headers.forEach(function (h, i) {
      var th = document.createElement("th");
      th.textContent = h;
      if (numeric && numeric.indexOf(i) >= 0) th.className = "n";
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    node.appendChild(thead);
    var tbody = document.createElement("tbody");
    rows.forEach(function (row) {
      var line = document.createElement("tr");
      row.forEach(function (cell, i) {
        var td = document.createElement("td");
        td.textContent = cell;
        if (numeric && numeric.indexOf(i) >= 0) td.className = "n";
        line.appendChild(td);
      });
      tbody.appendChild(line);
    });
    node.appendChild(tbody);
  }
})();
