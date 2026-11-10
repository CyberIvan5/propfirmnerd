// Site-wide behaviour: menu, affiliate click tracking, copy-code buttons, sortable tables, mobile visit bar.
(function () {
  var b = document.querySelector('.menu-btn'), n = document.getElementById('nav');
  if (b && n) b.addEventListener('click', function () {
    var o = n.classList.toggle('open'); b.setAttribute('aria-expanded', o);
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var a = e.target.closest('a[href^="/go/"]');
    if (a && window.gtag) {
      gtag('event', 'affiliate_click', { firm: a.getAttribute('href').split('/')[2], page: location.pathname,
        place: a.getAttribute('data-place') || '' });
    }
    var c = e.target.closest('[data-copy]');
    if (!c) return;
    var code = c.getAttribute('data-copy');
    var label = c.getAttribute('data-label') || c.textContent;
    c.setAttribute('data-label', label);
    if (window.gtag) gtag('event', 'code_copy', { code: code, page: location.pathname });
    function done(ok) {
      c.textContent = ok ? 'Copied' : code; c.classList.add('done');
      setTimeout(function () { c.textContent = label; c.classList.remove('done'); }, 1600);
    }
    (navigator.clipboard ? navigator.clipboard.writeText(code) : Promise.reject())
      .then(function () { done(true); }, function () { done(false); });
  });

  // Click a column heading to sort; click again to reverse. Empty values always go last.
  document.querySelectorAll('table.cmp').forEach(function (t) {
    if (!t.tHead) return;
    var ths = Array.prototype.slice.call(t.tHead.rows[0].cells);
    ths.forEach(function (th, i) {
      var btn = th.querySelector('button.sort');
      if (!btn) return;
      btn.addEventListener('click', function () {
        var dir = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
        ths.forEach(function (x) { x.removeAttribute('aria-sort'); });
        th.setAttribute('aria-sort', dir);
        var num = th.getAttribute('data-sort') === 'num', tb = t.tBodies[0];
        function val(r) {
          var c = r.cells[i], v = c.getAttribute('data-v');
          if (v === null) v = c.textContent.trim();
          if (num) { v = parseFloat(v); return isNaN(v) ? null : v; }
          return v === '' ? null : v.toLowerCase();
        }
        Array.prototype.slice.call(tb.rows).sort(function (a, b) {
          var x = val(a), y = val(b);
          if (x === null || y === null) return x === y ? 0 : (x === null ? 1 : -1);
          var r = x < y ? -1 : x > y ? 1 : 0;
          return dir === 'ascending' ? r : -r;
        }).forEach(function (r) { tb.appendChild(r); });
      });
    });
  });

  // Phone: keep a Visit button in reach once the one in the page header scrolls away.
  var bar = document.querySelector('.sticky-cta'), head = document.querySelector('.firm-head .btn');
  if (bar && head && 'IntersectionObserver' in window) {
    document.body.classList.add('has-sticky');
    new IntersectionObserver(function (en) {
      bar.classList.toggle('on', !en[0].isIntersecting && en[0].boundingClientRect.top < 0);
    }).observe(head);
  }
})();
