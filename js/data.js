/* NoFunLeague — snapshot loader and shared render helpers.

   Every page reads the committed data/*.json files written by
   tools/snapshot.py + tools/analyze.py and refreshed by
   .github/workflows/snapshot.yml. There is no runtime API key and no model
   call anywhere: if a file is missing the page says so instead of inventing
   numbers. */
window.NFL = window.NFL || {};
(function (N) {
  var cache = {};

  N.load = function (name) {
    if (name in cache) return cache[name];
    return (cache[name] = fetch("data/" + name + ".json", { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .catch(function (e) {
        console.warn("snapshot " + name + " unavailable", e);
        return null;
      }));
  };

  N.all = function (names) {
    return Promise.all(names.map(N.load)).then(function (vals) {
      var out = {};
      names.forEach(function (n, i) { out[n] = vals[i]; });
      return out;
    });
  };

  /* ---------------------------------------------------------- formatting */

  N.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  N.num = function (v, dp) {
    if (v == null || isNaN(v)) return "—";
    return Number(v).toFixed(dp == null ? 2 : dp);
  };

  N.pct = function (v) {
    if (v == null || isNaN(v)) return "—";
    return (Number(v) * 100).toFixed(1) + "%";
  };

  N.signed = function (v, dp) {
    if (v == null || isNaN(v) || Number(v) === 0) return "0";
    var n = Number(v);
    return (n > 0 ? "+" : "−") + Math.abs(n).toFixed(dp == null ? 0 : dp);
  };

  N.record = function (r) {
    return r.wins + "-" + r.losses + (r.ties ? "-" + r.ties : "");
  };

  N.ordinal = function (n) {
    var s = (n % 100 >= 11 && n % 100 <= 13) ? "th"
          : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th");
    return n + s;
  };

  N.stamp = function (meta, extra) {
    var el = document.getElementById("site-stamp");
    if (!el || !meta) return;
    var when = (meta.generated || "").replace("T", " ").replace("+00:00", " UTC");
    el.textContent = "Sleeper snapshot · " + (extra ? extra + " · " : "") +
                     "updated " + when;
  };

  N.fill = function (id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
  };

  N.oops = function (id, what) {
    N.fill(id, '<div class="error">' + N.esc(what) +
               " snapshot is missing. The next scheduled run will rebuild it.</div>");
  };

  /* ------------------------------------------------------------- widgets */

  /* rows: [[cell, ...], ...]; cols: [{label, num?, cls?}] */
  N.table = function (cols, rows, opts) {
    opts = opts || {};
    var head = cols.map(function (c) {
      return "<th" + (c.num ? ' class="num"' : "") + ">" + N.esc(c.label) + "</th>";
    }).join("");
    var body = rows.map(function (r, i) {
      var cls = opts.rowClass ? opts.rowClass(i) : "";
      return "<tr" + (cls ? ' class="' + cls + '"' : "") + ">" + r.map(function (cell, j) {
        var c = cols[j] || {};
        var klass = [c.num ? "num" : "", c.cls || ""].filter(Boolean).join(" ");
        return "<td" + (klass ? ' class="' + klass + '"' : "") + ">" + cell + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return '<div class="table-scroll"><table class="data"><thead><tr>' + head +
           "</tr></thead><tbody>" + body + "</tbody></table></div>";
  };

  /* rows: [{label, value, raw}] drawn as proportional bars */
  N.bars = function (rows, opts) {
    opts = opts || {};
    var vals = rows.map(function (r) { return Math.abs(r.raw || 0); });
    var max = opts.max != null ? opts.max : Math.max.apply(null, vals.concat([1]));
    return rows.map(function (r) {
      var w = max ? Math.max(1, (Math.abs(r.raw || 0) / max) * 100) : 0;
      var neg = (r.raw || 0) < 0;
      return '<div class="bar-row"><span class="label">' + N.esc(r.label) + "</span>" +
             '<span class="bar-track"><span class="bar-fill' + (neg ? " neg" : "") +
             '" style="width:' + w.toFixed(1) + '%"></span></span>' +
             '<span class="bar-val">' + r.value + "</span></div>";
    }).join("");
  };

  N.teamCell = function (team, sub) {
    return '<span class="team-cell">' + N.esc(team) +
           (sub ? "<small>" + N.esc(sub) + "</small>" : "") + "</span>";
  };

  /* One matchup line, used by the home page and the schedule page. */
  N.matchup = function (g) {
    var aw = g.winner && g.winner === g.a.team;
    var bw = g.winner && g.winner === g.b.team;
    var mid = g.played
      ? '<span class="vs">' + (g.margin != null ? "by " + N.num(g.margin, 1) : "final") + "</span>"
      : '<span class="vs">vs</span>';
    return '<div class="matchup">' +
      '<div class="side' + (aw ? " win" : "") + '">' +
        '<div class="name">' + N.esc(g.a.team) + "</div>" +
        (g.played ? '<div class="score">' + N.num(g.a.points) + "</div>" : "") +
      "</div>" + mid +
      '<div class="side right' + (bw ? " win" : "") + '">' +
        '<div class="name">' + N.esc(g.b.team) + "</div>" +
        (g.played ? '<div class="score">' + N.num(g.b.points) + "</div>" : "") +
      "</div></div>";
  };
})(window.NFL);
