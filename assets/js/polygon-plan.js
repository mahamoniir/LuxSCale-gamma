/**
 * LuxScale — polygon floor-plan helpers for result.html
 * Draws CAD polygons (geometry_version 2) with orientation-aware
 * fixture clipping matching luxscale/uniformity_calculator.py.
 */
(function (global) {
  "use strict";

  function getPolygonMeta(meta) {
    if (!meta || typeof meta !== "object") return null;
    const poly = meta.polygon;
    if (!poly || typeof poly !== "object") return null;
    const verts = poly.vertices;
    if (!Array.isArray(verts) || verts.length < 3) return null;
    return poly;
  }

  function engineDimsFromPayload(request, meta) {
    const eq = meta && meta.equivalent_rectangle;
    if (eq && Array.isArray(eq.sides_used) && eq.sides_used.length === 4) {
      const a = Number(eq.sides_used[0]), b = Number(eq.sides_used[1]);
      const c = Number(eq.sides_used[2]), d = Number(eq.sides_used[3]);
      return { lengthX: Math.max(a, c), widthY: Math.max(b, d) };
    }
    if (eq && eq.width_m != null && eq.length_m != null) {
      return { lengthX: Number(eq.width_m), widthY: Number(eq.length_m) };
    }
    // /cad_calc returns length=length_eq, width=width_eq → engine x = width_eq
    if (request && request.width != null && request.length != null) {
      return { lengthX: Number(request.width), widthY: Number(request.length) };
    }
    const sides = request && request.sides;
    if (Array.isArray(sides) && sides.length >= 4) {
      return {
        lengthX: Math.max(Number(sides[0]), Number(sides[2])),
        widthY: Math.max(Number(sides[1]), Number(sides[3])),
      };
    }
    if (Array.isArray(sides) && sides.length >= 2) {
      return { lengthX: Number(sides[0]) || 6, widthY: Number(sides[1]) || 4 };
    }
    return { lengthX: 6, widthY: 4 };
  }

  function orientationRad(poly, meta) {
    const eq = meta && meta.equivalent_rectangle;
    if (eq && eq.orientation_deg != null) return (Number(eq.orientation_deg) * Math.PI) / 180;
    if (poly && poly.orientation_deg != null) return (Number(poly.orientation_deg) * Math.PI) / 180;
    return 0;
  }

  function pointInPolygon(x, y, verts) {
    let inside = false;
    const n = verts.length;
    for (let i = 0, j = n - 1; i < n; j = i++) {
      const xi = verts[i][0], yi = verts[i][1];
      const xj = verts[j][0], yj = verts[j][1];
      const denom = yj - yi || 1e-15;
      const intersect =
        yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / denom + xi;
      if (intersect) inside = !inside;
    }
    return inside;
  }

  function polygonInEngineFrame(worldVerts, lengthX, widthY, theta) {
    const c = Math.cos(-theta), s = Math.sin(-theta);
    const rotated = worldVerts.map(([x, y]) => [c * x - s * y, s * x + c * y]);
    const xs = rotated.map((p) => p[0]);
    const ys = rotated.map((p) => p[1]);
    const xmin = Math.min(...xs), xmax = Math.max(...xs);
    const ymin = Math.min(...ys), ymax = Math.max(...ys);
    const bw = Math.max(xmax - xmin, 1e-12);
    const bl = Math.max(ymax - ymin, 1e-12);
    return rotated.map(([x, y]) => [
      ((x - xmin) / bw) * lengthX,
      ((y - ymin) / bl) * widthY,
    ]);
  }

  function farthestPointSubset(candidates, k) {
    if (k <= 0 || !candidates.length) return [];
    if (k >= candidates.length) return candidates.slice();
    const cx = candidates.reduce((s, p) => s + p[0], 0) / candidates.length;
    const cy = candidates.reduce((s, p) => s + p[1], 0) / candidates.length;
    let seedI = 0, bestD = Infinity;
    candidates.forEach((p, i) => {
      const d = (p[0] - cx) ** 2 + (p[1] - cy) ** 2;
      if (d < bestD) { bestD = d; seedI = i; }
    });
    const chosen = [candidates[seedI]];
    const remaining = candidates.filter((_, i) => i !== seedI);
    const minD2 = remaining.map(
      (p) => (p[0] - chosen[0][0]) ** 2 + (p[1] - chosen[0][1]) ** 2
    );
    while (chosen.length < k && remaining.length) {
      let bestJ = 0;
      for (let j = 1; j < remaining.length; j++) {
        if (minD2[j] > minD2[bestJ]) bestJ = j;
      }
      const pick = remaining.splice(bestJ, 1)[0];
      minD2.splice(bestJ, 1);
      chosen.push(pick);
      remaining.forEach((p, j) => {
        const d2 = (p[0] - pick[0]) ** 2 + (p[1] - pick[1]) ** 2;
        if (d2 < minD2[j]) minD2[j] = d2;
      });
    }
    return chosen;
  }

  function fixturePositionsPolygon(worldVerts, lengthX, widthY, nx, ny, theta, target) {
    nx = Math.max(1, nx | 0);
    ny = Math.max(1, ny | 0);
    target = Math.max(1, target | 0);
    const proxy = polygonInEngineFrame(worldVerts, lengthX, widthY, theta);
    let inside = [];
    for (let scale = 1; scale <= 8; scale++) {
      const sx = nx * scale, sy = ny * scale;
      const candidates = [];
      for (let i = 0; i < sx; i++) {
        for (let j = 0; j < sy; j++) {
          candidates.push([((i + 0.5) * lengthX) / sx, ((j + 0.5) * widthY) / sy]);
        }
      }
      inside = candidates.filter(([x, y]) => pointInPolygon(x, y, proxy));
      if (inside.length >= target) break;
    }
    if (!inside.length) {
      const fallback = [];
      for (let i = 0; i < nx; i++) {
        for (let j = 0; j < ny; j++) {
          fallback.push([((i + 0.5) * lengthX) / nx, ((j + 0.5) * widthY) / ny]);
        }
      }
      return fallback.slice(0, target);
    }
    if (inside.length <= target) return inside;
    return farthestPointSubset(inside, target);
  }

  function engineToWorld(enginePts, worldVerts, lengthX, widthY, theta) {
    const c = Math.cos(-theta), s = Math.sin(-theta);
    const rotated = worldVerts.map(([x, y]) => [c * x - s * y, s * x + c * y]);
    const xs = rotated.map((p) => p[0]);
    const ys = rotated.map((p) => p[1]);
    const xmin = Math.min(...xs), xmax = Math.max(...xs);
    const ymin = Math.min(...ys), ymax = Math.max(...ys);
    const bw = Math.max(xmax - xmin, 1e-12);
    const bl = Math.max(ymax - ymin, 1e-12);
    return enginePts.map(([ex, ey]) => {
      const xr = xmin + (ex / Math.max(lengthX, 1e-12)) * bw;
      const yr = ymin + (ey / Math.max(widthY, 1e-12)) * bl;
      return [c * xr + s * yr, -s * xr + c * yr];
    });
  }

  function layoutNxNy(result, fixtures) {
    let nx = parseInt(result.layout_nx, 10) || 0;
    let ny = parseInt(result.layout_ny, 10) || 0;
    if ((!nx || !ny) && result["Layout grid"]) {
      const parts = String(result["Layout grid"]).split(/[x×X]/);
      nx = parseInt(parts[0], 10) || 0;
      ny = parseInt(parts[1], 10) || 0;
    }
    if (!nx || !ny) {
      nx = Math.max(1, Math.ceil(Math.sqrt(fixtures)));
      ny = Math.max(1, Math.ceil(fixtures / nx));
    }
    return { nx, ny };
  }

  function fixturesForResult(result, request, meta) {
    const poly = getPolygonMeta(meta);
    const { lengthX, widthY } = engineDimsFromPayload(request, meta);
    const fixtures = Math.max(
      1,
      Math.floor(Number(result.Fixtures ?? result.fixtures ?? 1)) || 1
    );
    const { nx, ny } = layoutNxNy(result, fixtures);
    if (!poly) {
      const sx =
        Number(result["Spacing X (m)"] ?? result.spacing_x) || lengthX / nx;
      const sy =
        Number(result["Spacing Y (m)"] ?? result.spacing_y) || widthY / ny;
      const ox = (lengthX - sx * (nx - 1)) / 2;
      const oy = (widthY - sy * (ny - 1)) / 2;
      const pts = [];
      for (let i = 0; i < nx; i++) {
        for (let j = 0; j < ny; j++) {
          if (pts.length >= fixtures) break;
          pts.push([ox + i * sx, oy + j * sy]);
        }
      }
      return { world: pts, lengthX, widthY, isPolygon: false, verts: null, orientDeg: 0 };
    }
    const verts = poly.vertices.map((v) => [Number(v[0]), Number(v[1])]);
    const theta = orientationRad(poly, meta);
    const enginePts = fixturePositionsPolygon(
      verts, lengthX, widthY, nx, ny, theta, fixtures
    );
    const world = engineToWorld(enginePts, verts, lengthX, widthY, theta);
    return {
      world,
      lengthX,
      widthY,
      isPolygon: true,
      verts,
      orientDeg: (theta * 180) / Math.PI,
      area: Number(poly.area_m2) || null,
      fillRatio: poly.fill_ratio != null ? Number(poly.fill_ratio) : null,
    };
  }

  /**
   * Draw floor plan onto a canvas. For polygons, vertices are in CAD/world
   * coordinates (orientation preserved). For rectangles, engine-frame grid.
   */
  function drawFloorPlan(canvas, result, request, meta, opts) {
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth || opts?.width || 320;
    const cssH = canvas.clientHeight || opts?.height || 220;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const layout = fixturesForResult(result || {}, request || {}, meta || {});
    const pad = 28;
    let xmin, xmax, ymin, ymax;
    if (layout.isPolygon && layout.verts) {
      xmin = Math.min(...layout.verts.map((v) => v[0]));
      xmax = Math.max(...layout.verts.map((v) => v[0]));
      ymin = Math.min(...layout.verts.map((v) => v[1]));
      ymax = Math.max(...layout.verts.map((v) => v[1]));
    } else {
      xmin = 0; xmax = layout.lengthX; ymin = 0; ymax = layout.widthY;
    }
    const spanX = Math.max(xmax - xmin, 1e-6);
    const spanY = Math.max(ymax - ymin, 1e-6);
    const scale = Math.min((cssW - 2 * pad) / spanX, (cssH - 2 * pad) / spanY);
    const ox = (cssW - spanX * scale) / 2 - xmin * scale;
    const oy = (cssH - spanY * scale) / 2 + ymax * scale; // flip Y for screen

    const toScreen = (x, y) => [ox + x * scale, oy - y * scale];

    ctx.clearRect(0, 0, cssW, cssH);
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.fillRect(0, 0, cssW, cssH);

    // Room outline
    ctx.beginPath();
    if (layout.isPolygon && layout.verts) {
      layout.verts.forEach((v, i) => {
        const [sx, sy] = toScreen(v[0], v[1]);
        if (i === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
      });
      ctx.closePath();
    } else {
      const [x0, y0] = toScreen(0, 0);
      const [x1, y1] = toScreen(layout.lengthX, layout.widthY);
      ctx.rect(x0, y1, x1 - x0, y0 - y1);
    }
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.fill();
    ctx.strokeStyle = "#1a1a1a";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Fixtures
    layout.world.forEach(([fx, fy]) => {
      const [sx, sy] = toScreen(fx, fy);
      ctx.fillStyle = "#EB1B26";
      ctx.fillRect(sx - 4, sy - 4, 8, 8);
      ctx.strokeStyle = "#1a1a1a";
      ctx.lineWidth = 1;
      ctx.strokeRect(sx - 4, sy - 4, 8, 8);
    });

    // Labels
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.font = "11px IBM Plex Sans Arabic, sans-serif";
    let label = `${layout.world.length} fixtures`;
    if (layout.isPolygon) {
      const parts = [`N-gon`, label];
      if (layout.area != null) parts.push(`A=${layout.area.toFixed(1)} m²`);
      if (layout.fillRatio != null) parts.push(`α=${layout.fillRatio.toFixed(2)}`);
      if (Math.abs(layout.orientDeg) > 0.5) parts.push(`θ=${layout.orientDeg.toFixed(0)}°`);
      label = parts.join(" · ");
    }
    ctx.fillText(label, 10, cssH - 10);

    // North arrow (screen up = +Y CAD)
    ctx.strokeStyle = "#EB1B26";
    ctx.fillStyle = "#EB1B26";
    ctx.beginPath();
    ctx.moveTo(cssW - 18, 28);
    ctx.lineTo(cssW - 18, 12);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cssW - 18, 12);
    ctx.lineTo(cssW - 22, 18);
    ctx.lineTo(cssW - 14, 18);
    ctx.closePath();
    ctx.fill();
    ctx.font = "bold 10px sans-serif";
    ctx.fillText("N", cssW - 22, 10);
  }

  function roomSizeLabel(request, meta) {
    const poly = getPolygonMeta(meta);
    if (poly) {
      const n = poly.vertex_count || (poly.vertices && poly.vertices.length) || "?";
      const a = poly.area_m2 != null ? Number(poly.area_m2).toFixed(1) : "?";
      const th = poly.orientation_deg != null ? Number(poly.orientation_deg).toFixed(0) : "0";
      return `Polygon · ${n} verts · ${a} m² · θ=${th}°`;
    }
    const { lengthX, widthY } = engineDimsFromPayload(request, meta);
    return `${lengthX.toFixed(2)} × ${widthY.toFixed(2)} m`;
  }

  global.LuxPolygonPlan = {
    getPolygonMeta,
    engineDimsFromPayload,
    fixturesForResult,
    drawFloorPlan,
    roomSizeLabel,
  };
})(typeof window !== "undefined" ? window : globalThis);
