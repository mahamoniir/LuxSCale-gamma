/**
 * Standards category → task → ref_no picker.
 *
 * Preferred mode (opts.apiBase set):
 *   GET  {apiBase}/api/standards/categories
 *   GET  {apiBase}/api/standards/categories/<category>/tasks
 *   POST {apiBase}/api/standards/resolve-by-task  → row with ref_no
 *
 * Legacy mode (no apiBase): load standards_cleaned.json locally and filter by
 * combined category (category_base [– category_sub]), matching the backend.
 */
(function () {
  var EN_DASH = " \u2013 "; // " – " same as luxscale/standards_lookup.py

  function fillDatalist(datalistEl, values) {
    if (!datalistEl) return;
    datalistEl.innerHTML = "";
    values.forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      datalistEl.appendChild(opt);
    });
  }

  function combinedCategory(row) {
    if (!row || typeof row !== "object") return "";
    if (row.category) return String(row.category).trim();
    var base = (row.category_base || "").trim();
    var sub = row.category_sub != null && String(row.category_sub).trim() !== ""
      ? String(row.category_sub).trim()
      : "";
    return sub ? base + EN_DASH + sub : base;
  }

  function withCombinedCategory(rows) {
    return (rows || []).map(function (r) {
      var copy = Object.assign({}, r);
      copy.category = combinedCategory(r);
      return copy;
    });
  }

  function uniqueSortedCategoriesFromCleaned(rows) {
    var catSet = new Set();
    rows.forEach(function (r) {
      var c = combinedCategory(r);
      if (c) catSet.add(c);
    });
    return Array.from(catSet).sort();
  }

  function mergeCategoryLists(keywordsObj, cleanedRows) {
    var set = new Set();
    if (keywordsObj && typeof keywordsObj === "object") {
      Object.keys(keywordsObj).forEach(function (k) {
        if (k) set.add(k);
      });
    }
    cleanedRows.forEach(function (r) {
      var c = combinedCategory(r);
      if (c) set.add(c);
    });
    return Array.from(set).sort();
  }

  function taskOptionsForCategory(rows, category) {
    var filtered = rows.filter(function (r) {
      return combinedCategory(r) === category;
    });
    var counts = new Map();
    filtered.forEach(function (r) {
      var t = (r.task_or_activity || "").trim();
      if (!t) return;
      counts.set(t, (counts.get(t) || 0) + 1);
    });
    var seen = new Set();
    var out = [];
    filtered.forEach(function (r) {
      var t = (r.task_or_activity || "").trim();
      if (!t) return;
      var value = t;
      if (counts.get(t) > 1) {
        value = t + " (" + (r.ref_no || "") + ")";
      }
      if (seen.has(value)) return;
      seen.add(value);
      out.push({ value: value, row: r });
    });
    return out;
  }

  function taskOptionsFromApiTasks(tasks) {
    var list = Array.isArray(tasks) ? tasks : [];
    var counts = new Map();
    list.forEach(function (t) {
      var name = (t.task_or_activity || "").trim();
      if (!name) return;
      counts.set(name, (counts.get(name) || 0) + 1);
    });
    var seen = new Set();
    var out = [];
    list.forEach(function (t) {
      var name = (t.task_or_activity || "").trim();
      if (!name) return;
      var value = name;
      if (counts.get(name) > 1) {
        value = name + " (" + (t.ref_no || "") + ")";
      }
      if (seen.has(value)) return;
      seen.add(value);
      out.push({ value: value, task: t });
    });
    return out;
  }

  function findRowForTaskValue(rows, category, taskValue) {
    var opts = taskOptionsForCategory(rows, category);
    for (var i = 0; i < opts.length; i++) {
      if (opts[i].value === taskValue) return opts[i].row;
    }
    var trimmed = (taskValue || "").trim();
    for (var j = 0; j < rows.length; j++) {
      var r = rows[j];
      if (combinedCategory(r) !== category) continue;
      if ((r.task_or_activity || "").trim() === trimmed) return r;
    }
    return null;
  }

  function filterCategories(allCategories, categoryKeywords, query) {
    var q = (query || "").trim().toLowerCase();
    if (!q) return allCategories.slice();
    return allCategories.filter(function (cat) {
      if (cat.toLowerCase().indexOf(q) !== -1) return true;
      var kws = categoryKeywords && categoryKeywords[cat];
      if (!Array.isArray(kws)) return false;
      for (var i = 0; i < kws.length; i++) {
        if (String(kws[i]).toLowerCase().indexOf(q) !== -1) return true;
      }
      return false;
    });
  }

  function normalizeApiBase(base) {
    if (!base) return "";
    return String(base).replace(/\/+$/, "");
  }

  function initViaApi(opts) {
    var apiBase = normalizeApiBase(opts.apiBase);
    var categoryInput = opts.categoryInput;
    var categoryDatalist = opts.categoryDatalist;
    var taskInput = opts.taskInput;
    var taskDatalist = opts.taskDatalist;
    var onRowResolved = typeof opts.onRowResolved === "function" ? opts.onRowResolved : function () {};
    var categoryKeywords = opts.categoryKeywords || {};
    var allCategoryLabels = [];
    var currentTaskOptions = [];
    var tasksFetchSeq = 0;
    var resolveSeq = 0;

    function applyCategoryFilter() {
      var q = categoryInput ? categoryInput.value : "";
      var list = filterCategories(allCategoryLabels, categoryKeywords, q);
      if (list.length === 0 && q) list = allCategoryLabels.slice();
      fillDatalist(categoryDatalist, list);
    }

    function clearTasks() {
      currentTaskOptions = [];
      fillDatalist(taskDatalist, []);
      if (taskInput) taskInput.value = "";
      onRowResolved(null, { category: (categoryInput && categoryInput.value) || "", taskValue: "" });
    }

    function refreshTasks() {
      var cat = (categoryInput && categoryInput.value) || "";
      if (!cat || allCategoryLabels.indexOf(cat) === -1) {
        // Allow typed exact match not yet in labels (keywords filter) — still try API.
        if (!cat) {
          clearTasks();
          return Promise.resolve();
        }
      }
      var seq = ++tasksFetchSeq;
      var url = apiBase + "/api/standards/categories/" + encodeURIComponent(cat) + "/tasks";
      return fetch(url, { credentials: "omit" })
        .then(function (res) {
          if (!res.ok) throw new Error("tasks HTTP " + res.status);
          return res.json();
        })
        .then(function (data) {
          if (seq !== tasksFetchSeq) return;
          var tasks = (data && Array.isArray(data.tasks)) ? data.tasks : [];
          currentTaskOptions = taskOptionsFromApiTasks(tasks);
          fillDatalist(
            taskDatalist,
            currentTaskOptions.map(function (o) {
              return o.value;
            })
          );
          if (taskInput && cat) {
            var stillValid = currentTaskOptions.some(function (o) {
              return o.value === taskInput.value;
            });
            if (!stillValid) taskInput.value = "";
          }
        })
        .catch(function (err) {
          if (seq !== tasksFetchSeq) return;
          console.warn("standards-picker tasks:", err);
          clearTasks();
        });
    }

    function resolveSelection() {
      var cat = (categoryInput && categoryInput.value) || "";
      var taskVal = (taskInput && taskInput.value) || "";
      if (!cat || !taskVal) {
        onRowResolved(null, { category: cat, taskValue: taskVal });
        return Promise.resolve(null);
      }
      var seq = ++resolveSeq;
      return fetch(apiBase + "/api/standards/resolve-by-task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "omit",
        body: JSON.stringify({
          category: cat,
          task_or_activity: taskVal
        })
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok, status: res.status, data: data };
          });
        })
        .then(function (pack) {
          if (seq !== resolveSeq) return null;
          if (pack.data && pack.data.status === "success" && pack.data.row) {
            onRowResolved(pack.data.row, { category: cat, taskValue: taskVal });
            return pack.data.row;
          }
          onRowResolved(null, {
            category: cat,
            taskValue: taskVal,
            reason: (pack.data && pack.data.reason) || "not_found"
          });
          return null;
        })
        .catch(function (err) {
          if (seq !== resolveSeq) return null;
          console.warn("standards-picker resolve-by-task:", err);
          onRowResolved(null, { category: cat, taskValue: taskVal, reason: String(err) });
          return null;
        });
    }

    return fetch(apiBase + "/api/standards/categories", { credentials: "omit" })
      .then(function (res) {
        if (!res.ok) throw new Error("categories HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        var cats = (data && Array.isArray(data.categories)) ? data.categories : [];
        allCategoryLabels = cats.map(function (c) {
          return (c && c.category) || "";
        }).filter(Boolean);
        cats.forEach(function (c) {
          if (c && c.category && Array.isArray(c.keywords) && c.keywords.length) {
            categoryKeywords[c.category] = c.keywords;
          }
        });
        if (Array.isArray(opts.categoryLabels) && opts.categoryLabels.length) {
          // Prefer API list; allow extra labels from caller only if not already present.
          opts.categoryLabels.forEach(function (lab) {
            if (lab && allCategoryLabels.indexOf(lab) === -1) allCategoryLabels.push(lab);
          });
          allCategoryLabels.sort();
        }
        fillDatalist(categoryDatalist, allCategoryLabels);

        if (categoryInput) {
          categoryInput.addEventListener("change", function () {
            applyCategoryFilter();
            refreshTasks().then(function () {
              resolveSelection();
            });
          });
          categoryInput.addEventListener("input", function () {
            applyCategoryFilter();
          });
        }
        if (taskInput) {
          taskInput.addEventListener("change", function () {
            resolveSelection();
          });
          taskInput.addEventListener("blur", function () {
            resolveSelection();
          });
        }

        applyCategoryFilter();
        return refreshTasks().then(function () {
          return {
            mode: "api",
            apiBase: apiBase,
            categoryKeywords: categoryKeywords,
            allCategoryLabels: allCategoryLabels,
            refreshTasks: refreshTasks,
            resolveSelection: resolveSelection
          };
        });
      })
      .catch(function (err) {
        console.error("standards-picker API mode failed:", err);
        if (opts.onError) opts.onError(err);
        throw err;
      });
  }

  function initViaLocal(opts) {
    var cleanedUrl = opts.cleanedUrl || opts.jsonUrl || "standards/standards_cleaned.json";
    var keywordsUrl = opts.keywordsUrl || "standards/standards_keywords_upgraded.json";
    var skipKeywordsFetch = Array.isArray(opts.categoryLabels) && opts.categoryLabels.length > 0;
    var categoryInput = opts.categoryInput;
    var categoryDatalist = opts.categoryDatalist;
    var taskInput = opts.taskInput;
    var taskDatalist = opts.taskDatalist;
    var onRowResolved = typeof opts.onRowResolved === "function" ? opts.onRowResolved : function () {};
    var categoryKeywords = opts.categoryKeywords || null;
    var allCategoryLabels = [];
    var rows = [];

    function applyCategoryFilter() {
      var q = categoryInput ? categoryInput.value : "";
      var list = filterCategories(allCategoryLabels, categoryKeywords, q);
      if (list.length === 0 && q) list = allCategoryLabels.slice();
      fillDatalist(categoryDatalist, list);
    }

    var pCleaned =
      opts.cleanedRows && Array.isArray(opts.cleanedRows)
        ? Promise.resolve(opts.cleanedRows)
        : fetch(cleanedUrl).then(function (res) {
            if (!res.ok) throw new Error("Failed to load standards_cleaned: " + res.status);
            return res.json();
          });

    var pKeywords = skipKeywordsFetch
      ? Promise.resolve(null)
      : fetch(keywordsUrl)
          .then(function (res) {
            if (!res.ok) return null;
            return res.json();
          })
          .catch(function () {
            return null;
          });

    return Promise.all([pCleaned, pKeywords])
      .then(function (pair) {
        var data = pair[0];
        var kwDoc = pair[1];
        if (!Array.isArray(data)) throw new Error("standards_cleaned.json must be an array");
        rows = withCombinedCategory(data);

        if (skipKeywordsFetch) {
          allCategoryLabels = opts.categoryLabels.slice().sort();
        } else if (kwDoc && kwDoc.category_keywords) {
          categoryKeywords = kwDoc.category_keywords;
          allCategoryLabels = mergeCategoryLists(categoryKeywords, rows);
        } else {
          allCategoryLabels = uniqueSortedCategoriesFromCleaned(rows);
        }

        fillDatalist(categoryDatalist, allCategoryLabels);

        function refreshTasks() {
          var cat = (categoryInput && categoryInput.value) || "";
          var taskOpts = taskOptionsForCategory(rows, cat);
          fillDatalist(
            taskDatalist,
            taskOpts.map(function (o) {
              return o.value;
            })
          );
          if (taskInput && cat) {
            var stillValid = taskOpts.some(function (o) {
              return o.value === taskInput.value;
            });
            if (!stillValid) taskInput.value = "";
          }
        }

        function resolveSelection() {
          var cat = (categoryInput && categoryInput.value) || "";
          var taskVal = (taskInput && taskInput.value) || "";
          var row = findRowForTaskValue(rows, cat, taskVal);
          onRowResolved(row, { category: cat, taskValue: taskVal });
        }

        if (categoryInput) {
          categoryInput.addEventListener("change", function () {
            applyCategoryFilter();
            refreshTasks();
            resolveSelection();
          });
          categoryInput.addEventListener("input", function () {
            applyCategoryFilter();
            refreshTasks();
          });
        }
        if (taskInput) {
          taskInput.addEventListener("change", resolveSelection);
          taskInput.addEventListener("blur", resolveSelection);
        }

        refreshTasks();
        applyCategoryFilter();

        return {
          mode: "local",
          rows: rows,
          categoryKeywords: categoryKeywords,
          allCategoryLabels: allCategoryLabels,
          refreshTasks: refreshTasks,
          findRowForTaskValue: findRowForTaskValue
        };
      })
      .catch(function (err) {
        console.error(err);
        if (opts.onError) opts.onError(err);
      });
  }

  window.initStandardsPicker = function (opts) {
    opts = opts || {};
    if (opts.apiBase) {
      return initViaApi(opts).catch(function (err) {
        console.warn("Falling back to local standards_cleaned.json after API failure:", err);
        return initViaLocal(opts);
      });
    }
    return initViaLocal(opts);
  };
})();
