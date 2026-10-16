// Filter chips for firm tables: <div class="filters" data-filter-for="tableId">
(function () {
  document.querySelectorAll('.filters[data-filter-for]').forEach(function (bar) {
    var table = document.getElementById(bar.getAttribute('data-filter-for'));
    if (!table) return;
    var rows = Array.prototype.slice.call(table.tBodies[0].rows);
    var state = {};
    var count = bar.querySelector('.count');
    function apply() {
      var shown = 0;
      rows.forEach(function (r) {
        var ok = Object.keys(state).every(function (k) {
          if (!state[k]) return true;
          var v = r.getAttribute('data-' + k);
          if (k === 'market' && v === 'multi') return true;
          if (k === 'dd' && v === 'mixed' && state[k] === 'eod') return true;
          return v === state[k];
        });
        r.hidden = !ok;
        if (ok) shown++;
      });
      if (count) count.textContent = shown + ' of ' + rows.length + ' firms';
    }
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-f]');
      if (!b) return;
      var f = b.getAttribute('data-f');
      state[f] = b.getAttribute('data-v');
      bar.querySelectorAll('button[data-f="' + f + '"]').forEach(function (x) {
        x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
      });
      apply();
    });
    apply();
  });
})();
