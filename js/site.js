/* NoFunLeague — shared site chrome (nav + footer + icon sprite).
   Every page carries <div id="site-nav"></div> and <div id="site-footer"></div>
   plus <script src="js/site.js"></script>; this fills them in so the nav lives
   in one place. Active state comes from the current filename.
   Icons: <svg class="icon"><use href="#i-trophy"></use></svg>  */
(function () {
  var PAGE = (location.pathname.split("/").pop() || "index.html").toLowerCase();

  var SPRITE =
    '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute" aria-hidden="true">' +
    '<symbol id="i-trophy" viewBox="0 0 24 24"><path d="M7 4h10v5a5 5 0 0 1-10 0V4Z"/><path d="M7 6H4v2a3 3 0 0 0 3 3M17 6h3v2a3 3 0 0 1-3 3M12 14v4M8 20h8M9 20l.5-2h5l.5 2"/></symbol>' +
    '<symbol id="i-crown" viewBox="0 0 24 24"><path d="M4 18h16M4 18 3 8l5 4 4-6 4 6 5-4-1 10"/></symbol>' +
    '<symbol id="i-flame" viewBox="0 0 24 24"><path d="M12 3c1 3 4 5 4 9a4 4 0 0 1-8 0c0-1 .5-2 1-3 .5 2 2 2 2 2 .5-3-1-6 1-9Z"/></symbol>' +
    '<symbol id="i-skull" viewBox="0 0 24 24"><path d="M12 3a8 8 0 0 0-5 14v2a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-2a8 8 0 0 0-5-14Z"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><path d="M11 17h2"/></symbol>' +
    '<symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 5v15h16M8 16v-4M12 16V8M16 16v-6"/></symbol>' +
    '<symbol id="i-swords" viewBox="0 0 24 24"><path d="M14 3h5v5M19 3l-8 8M5 21l3-3M8.5 15.5 4 20l-1-1 4.5-4.5M10 3H5v5M5 3l8 8M19 21l-3-3M15.5 15.5 20 20l1-1-4.5-4.5"/></symbol>' +
    '<symbol id="i-list" viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M4 6h.01M4 12h.01M4 18h.01"/></symbol>' +
    '<symbol id="i-trend-up" viewBox="0 0 24 24"><path d="M3 17 9 11l4 4 8-8M16 7h5v5"/></symbol>' +
    '<symbol id="i-trend-down" viewBox="0 0 24 24"><path d="M3 7 9 13l4-4 8 8M16 17h5v-5"/></symbol>' +
    '<symbol id="i-target" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></symbol>' +
    '<symbol id="i-calendar" viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></symbol>' +
    '<symbol id="i-clipboard" viewBox="0 0 24 24"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 10h6M9 14h6M9 18h3"/></symbol>' +
    '<symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/></symbol>' +
    '</svg>';
  document.body.insertAdjacentHTML("afterbegin", SPRITE);

  var NAV = [
    { href: "index.html",     label: "Home" },
    { href: "standings.html", label: "Standings" },
    { href: "rankings.html",  label: "Power" },
    { href: "schedule.html",  label: "Schedule" },
    { href: "burns.html",     label: "Burns" },
    { label: "More", menu: [
      { href: "stats.html",   label: "Stats & Analytics" },
      { href: "draft.html",   label: "Draft History" },
      { href: "history.html", label: "League History" }
    ] }
  ];
  var UNDER_MORE = ["stats.html", "draft.html", "history.html"];

  function frag(html) {
    var t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstChild;
  }
  function isActive(href) { return href.split("#")[0] === PAGE; }

  var links = NAV.map(function (item) {
    if (item.menu) {
      var here = UNDER_MORE.indexOf(PAGE) >= 0;
      var sub = item.menu.map(function (m) {
        return '<a href="' + m.href + '"' + (isActive(m.href) ? ' class="active"' : "") +
               ">" + m.label + "</a>";
      }).join("");
      return '<div class="nav-dropdown"><span class="nav-dropdown-toggle' +
             (here ? " active" : "") + '" role="button" tabindex="0">' + item.label +
             ' <span aria-hidden="true">▾</span></span>' +
             '<div class="nav-dropdown-menu">' + sub + "</div></div>";
    }
    return '<a href="' + item.href + '"' + (isActive(item.href) ? ' class="active"' : "") +
           ">" + item.label + "</a>";
  }).join("");

  var nav = frag(
    '<nav class="nav" aria-label="Primary">' +
      '<div class="nav-inner">' +
        '<a href="index.html" class="nav-logo">' +
          '<span><span class="no">No</span><span class="fun">Fun</span><span class="no">League</span></span>' +
          '<span class="sub">Fantasy Football</span>' +
        "</a>" +
        '<span class="nav-toggle" role="button" tabindex="0" aria-label="Menu" aria-expanded="false">' +
          "<span></span><span></span><span></span></span>" +
        '<div class="nav-links">' + links + "</div>" +
      "</div>" +
    "</nav>");

  var mount = document.getElementById("site-nav");
  if (mount) mount.replaceWith(nav);
  else document.body.insertBefore(nav, document.body.firstChild);

  var toggle = nav.querySelector(".nav-toggle");
  var linkbox = nav.querySelector(".nav-links");
  toggle.addEventListener("click", function () {
    var open = linkbox.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });

  nav.querySelectorAll(".nav-dropdown").forEach(function (dd) {
    var dt = dd.querySelector(".nav-dropdown-toggle");
    if (!dt) return;
    var setOpen = function (v) {
      dd.classList.toggle("open", v);
      dt.setAttribute("aria-expanded", String(v));
    };
    dt.addEventListener("click", function () { setOpen(!dd.classList.contains("open")); });
    dt.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(!dd.classList.contains("open")); }
      if (e.key === "Escape") { setOpen(false); dt.focus(); }
    });
    dd.addEventListener("mouseleave", function () { setOpen(false); });
    dd.querySelectorAll(".nav-dropdown-menu a").forEach(function (a) {
      a.addEventListener("click", function () { setOpen(false); });
    });
  });

  var footer = frag(
    '<footer class="footer">' +
      '<span class="wordmark">NO<span class="fun">FUN</span>LEAGUE</span>' +
      '<span id="site-stamp">Data from the Sleeper public API.</span>' +
    "</footer>");
  var fm = document.getElementById("site-footer");
  if (fm) fm.replaceWith(footer);
  else document.body.appendChild(footer);
})();
