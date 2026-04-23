/**
 * LuxSCale AI - Core Logic Integration
 * Handles standards picking, calculations, and study submission.
 */

(function() {
  let lastResolvedStandardRow = null;

  // Configuration
  const RESULT_LINKS_KEY = "luxscale_result_links";
  const RESULT_LINK_TTL_MS = 60 * 60 * 1000; // 1 hour
  const RESULT_PAGE_PATH = "result.html";

  // API Utils
  function getLocalFlaskOrigin() {
    const h = window.location.hostname;
    if (h === "localhost" || h === "127.0.0.1") {
      return "http://" + h + ":5000";
    }
    return null;
  }

  function getCalculateApiUrl() {
    const origin = getLocalFlaskOrigin();
    if (origin) return origin + "/calculate";
    return "https://bkr3800.pythonanywhere.com/calculate";
  }

  function getPlacesApiUrl() {
    const origin = getLocalFlaskOrigin();
    if (origin) return origin + "/places";
    return "https://bkr3800.pythonanywhere.com/places";
  }

  const SUBMIT_ENDPOINTS = (() => {
    const fromCurrentPage = new URL("./api/submit.php", window.location.href).toString();
    const sameOriginRoot = new URL("/api/submit.php", window.location.origin).toString();
    const endpoints = [fromCurrentPage, sameOriginRoot];
    const h = window.location.hostname;
    if (h === "localhost" || h === "127.0.0.1") {
      endpoints.push("http://127.0.0.1:5000/api/submit");
    }
    return [...new Set(endpoints)];
  })();

  // Standards Loading
  async function loadStandardsConfig() {
    let categoryKeywords = {};
    let categoryLabels = null;

    try {
      const response = await fetch(getPlacesApiUrl());
      if (response.ok) {
        const data = await response.json();
        if (data.category_keywords) categoryKeywords = data.category_keywords;
        if (data.standard_categories) categoryLabels = data.standard_categories;
      }
    } catch (err) {
      console.warn("loadStandardsConfig /places failed, using defaults:", err);
    }

    return { categoryLabels, categoryKeywords };
  }

  async function bootStandardsPicker() {
    const cfg = await loadStandardsConfig();
    if (typeof initStandardsPicker !== "function") return;

    const pickerOpts = {
      cleanedUrl: "standards/standards_cleaned.json",
      keywordsUrl: "standards/standards_keywords_upgraded.json",
      categoryInput: document.getElementById("stdCategory"),
      categoryDatalist: document.getElementById("dl-std-categories"),
      taskInput: document.getElementById("stdTask"),
      taskDatalist: document.getElementById("dl-std-tasks"),
      categoryKeywords: cfg.categoryKeywords,
      onRowResolved: (row) => { lastResolvedStandardRow = row; }
    };

    if (cfg.categoryLabels) pickerOpts.categoryLabels = cfg.categoryLabels;
    initStandardsPicker(pickerOpts);
  }

  // Submission Logic
  async function submitStudy(payload) {
    let lastError = "Submit API request failed.";
    for (const endpoint of SUBMIT_ENDPOINTS) {
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const json = await response.json();
        if (response.ok && json.token) return json;
        lastError = json.message || json.error || lastError;
      } catch (e) {
        lastError = e.message;
      }
    }
    throw new Error(lastError);
  }

  function exportStandardLighting(row) {
    return row ? JSON.parse(JSON.stringify(row)) : null;
  }

  // Result Handling
  function createStoredResultLink(token) {
    const linkUrl = new URL(RESULT_PAGE_PATH, window.location.href);
    linkUrl.searchParams.set("token", token);
    linkUrl.searchParams.set("stored_at", String(Date.now()));
    return linkUrl.pathname + linkUrl.search;
  }

  // Exposed Actions
  // ── Reflectance helpers (§5A/B/C + roughness correction) ──────────────
  function _hexToRho(hex) {
    const h = (hex || '').replace('#','');
    if (h.length !== 6) return 0.5;
    const r = parseInt(h.slice(0,2),16)/255;
    const g = parseInt(h.slice(2,4),16)/255;
    const b = parseInt(h.slice(4,6),16)/255;
    return 0.2126*Math.pow(r,2.2) + 0.7152*Math.pow(g,2.2) + 0.0722*Math.pow(b,2.2);
  }

  // Compute ρ from an <img> element via canvas (64×64 downsample, §5A/B/C)
  function _rhoFromImg(imgEl) {
    return new Promise(resolve => {
      try {
        const cv = document.createElement('canvas');
        cv.width = 64; cv.height = 64;
        const ctx = cv.getContext('2d');
        ctx.drawImage(imgEl, 0, 0, 64, 64);
        const d = ctx.getImageData(0, 0, 64, 64).data;
        let sum = 0, n = 0;
        for (let i = 0; i < d.length; i += 4) {
          const rn=d[i]/255, gn=d[i+1]/255, bn=d[i+2]/255;
          sum += 0.2126*Math.pow(rn,2.2) + 0.7152*Math.pow(gn,2.2) + 0.0722*Math.pow(bn,2.2);
          n++;
        }
        resolve(n > 0 ? Math.min(1, Math.max(0, sum/n)) : 0.5);
      } catch(e) { resolve(0.5); }
    });
  }

  // Roughness estimate from material ID name — no CDN, no proxy, no CORS
  function _roughnessFromAcgId(acgId) {
    const name = (acgId || '').toLowerCase();
    if (/concrete|brick|rock|stone|asphalt|gravel|rough|raw/.test(name)) return Promise.resolve(0.85);
    if (/wood|plaster|fabric|carpet|leather|cork|foam/.test(name))       return Promise.resolve(0.70);
    if (/tile|marble|polished/.test(name))                                return Promise.resolve(0.25);
    if (/metal|steel|iron|copper|brass|chrome|mirror/.test(name))        return Promise.resolve(0.15);
    return Promise.resolve(0.55); // neutral default
  }

  // Apply roughness correction: rough surfaces scatter light → lower effective ρ
  // ρ_final = ρ_color × (1 - roughness × 0.30)
  // Metal override: metalness flag drives specular, not diffuse → cap at 0.15
  function _applyRoughnessCorrection(rho, roughness, isMetal) {
    if (isMetal) return Math.min(rho, 0.15 + rho * 0.1); // metals: mostly specular, low diffuse
    return Math.max(0, rho * (1 - roughness * 0.30));
  }

  // Collect physics state from the mat picker (_surfState) if it exists,
  // otherwise fall back to HEX color inputs for backward compat.
  async function _collectMaterialPhysics(width, length, height) {
    // Case A: full mat picker available (draw_v9 engine embedded)
    if (window._surfState) {
      const ws = window._surfState;
      let rho_walls   = ws.walls.rho;
      let rho_ceiling = ws.ceiling.rho;
      let rho_floor   = ws.floor.rho;

      // If material came from AmbientCG, load & apply roughness correction
      const acgRoughnessJobs = [];
      ['walls','ceiling','floor'].forEach(surf => {
        const mat = ws[surf];
        if (mat && mat.key && mat.key.startsWith('acg_')) {
          const acgId = mat.key.replace('acg_','');
          // Infer metal category from material name
          const isMetal = /metal|steel|iron|copper|brass|chrome|mirror/i.test(mat.name || '');
          acgRoughnessJobs.push(
            _roughnessFromAcgId(acgId).then(roughness => {
              ws[surf]._rho_corrected = _applyRoughnessCorrection(mat.rho, roughness, isMetal);
              ws[surf]._roughness = roughness;
            })
          );
        }
      });
      if (acgRoughnessJobs.length) await Promise.all(acgRoughnessJobs);

      // Use corrected rho if available
      rho_walls   = ws.walls._rho_corrected   ?? ws.walls.rho;
      rho_ceiling = ws.ceiling._rho_corrected ?? ws.ceiling.rho;
      rho_floor   = ws.floor._rho_corrected   ?? ws.floor.rho;

      // Geometry-weighted IRF (same method as draw_v9 updateRoomPhysics)
      const A_floor   = width * length;
      const A_ceiling = width * length;
      const A_walls   = 2*width*height + 2*length*height;
      const A_total   = A_floor + A_ceiling + A_walls;
      const rho_bar   = (rho_floor*A_floor + rho_ceiling*A_ceiling + rho_walls*A_walls) / A_total;
      const irf       = Math.max(0, Math.min(0.40, rho_bar * 0.232));

      return {
        rho_walls:   +rho_walls.toFixed(4),
        rho_ceiling: +rho_ceiling.toFixed(4),
        rho_floor:   +rho_floor.toFixed(4),
        rho_bar:     +rho_bar.toFixed(4),
        irf:         +irf.toFixed(4),
        label: `Physics (ρ ceiling=${rho_ceiling.toFixed(2)} / walls=${rho_walls.toFixed(2)} / floor=${rho_floor.toFixed(2)})`,
        mat_walls:   ws.walls.name   || 'unknown',
        mat_ceiling: ws.ceiling.name || 'unknown',
        mat_floor:   ws.floor.name   || 'unknown',
      };
    }

    // Case B: legacy HEX color inputs only
    const hexW = document.getElementById("colorWallA")?.value || '#c2a86a';
    const hexF = document.getElementById("colorFloor")?.value  || '#8b5e2a';
    const rho_walls   = _hexToRho(hexW);
    const rho_ceiling = 0.80; // fallback white ceiling
    const rho_floor   = _hexToRho(hexF);
    const A_floor = width*length, A_ceiling = width*length, A_walls = 2*width*height+2*length*height;
    const rho_bar = (rho_floor*A_floor + rho_ceiling*A_ceiling + rho_walls*A_walls)/(A_floor+A_ceiling+A_walls);
    const irf = Math.max(0, Math.min(0.40, rho_bar * 0.232));
    return {
      rho_walls:+rho_walls.toFixed(4), rho_ceiling:+rho_ceiling.toFixed(4), rho_floor:+rho_floor.toFixed(4),
      rho_bar:+rho_bar.toFixed(4), irf:+irf.toFixed(4),
      label:`HEX fallback (ρ w=${rho_walls.toFixed(2)} f=${rho_floor.toFixed(2)})`,
      mat_walls:'hex', mat_ceiling:'default', mat_floor:'hex',
    };
  }
  // ── End reflectance helpers ────────────────────────────────────────────

  window.handleCreateStudy = async function() {
    const width1 = Number(document.getElementById("dimA").value);
    const length1 = Number(document.getElementById("dimB").value);
    const width2 = Number(document.getElementById("dimC").value);
    const length2 = Number(document.getElementById("dimD").value);
    const height = Number(document.getElementById("dimHeight").value);

    // Get wall/floor colors
    const room_colors = {
      wall_a: document.getElementById("colorWallA").value,
      wall_b: document.getElementById("colorWallB").value,
      wall_c: document.getElementById("colorWallC").value,
      wall_d: document.getElementById("colorWallD").value,
      floor: document.getElementById("colorFloor").value
    };

    if (!lastResolvedStandardRow) {
      alert("Please select a standard category and task.");
      return;
    }

    const sides = [width1, length1, width2, length2];
    const createBtn = document.getElementById("createStudyBtn");
    createBtn.disabled = true;
    createBtn.textContent = "Creating...";

    // Collect physics (roughness-corrected if ACG material, else HEX fallback)
    const avgWidth  = (width1 + (width2 || width1)) / 2;
    const avgLength = (length1 + (length2 || length1)) / 2;
    const matPhysics = await _collectMaterialPhysics(avgWidth, avgLength, height);

    try {
      // 1. Calculate
      const calcResponse = await fetch(getCalculateApiUrl(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sides, height,
          standard_ref_no: String(lastResolvedStandardRow.ref_no),
          // Phase 2 — material reflectance physics
          ceiling_hex: room_colors.wall_a,   // best proxy until ceiling picker added
          walls_hex:   room_colors.wall_a,
          floor_hex:   room_colors.floor,
          material_physics: matPhysics,
          project_info: {
            standard_category: document.getElementById("stdCategory").value,
            standard_task_or_activity: document.getElementById("stdTask").value
          }
        })
      });

      const calcData = await calcResponse.json();
      if (!calcResponse.ok) throw new Error(calcData.message || "Calculation failed");

      // 2. Submit
      const submitData = {
        project_name: "SC-LUXSCALE Study",
        standard_ref_no: String(lastResolvedStandardRow.ref_no),
        standard_category: document.getElementById("stdCategory").value,
        standard_task_or_activity: document.getElementById("stdTask").value,
        standard_lighting: exportStandardLighting(lastResolvedStandardRow),
        sides, height, room_colors,
        material_physics: matPhysics,
        results: calcData.results,
        calculation_meta: calcData.calculation_meta
      };

      const submitJson = await submitStudy(submitData);
      
      // 3. Stash & Redirect
      const token = submitJson.token;
      localStorage.setItem("user_token", token);
      localStorage.setItem("luxscale_result_rows_" + token, JSON.stringify(calcData.results));
      
      window.location.href = createStoredResultLink(token);
    } catch (err) {
      alert("Error: " + err.message);
      console.error(err);
    } finally {
      createBtn.disabled = false;
      createBtn.textContent = "Create Study";
    }
  };

  // Init
  document.addEventListener('DOMContentLoaded', bootStandardsPicker);
})();
