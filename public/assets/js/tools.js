// PropFirmNerd calculators. Each tool is a <form data-tool="name"> on its page.
(function () {
  function $(sel, root) { return (root || document).querySelector(sel); }
  function num(form, name) { var el = form.elements[name]; var v = parseFloat(el && el.value); return isFinite(v) ? v : 0; }
  function usd(v, dec) {
    if (!isFinite(v)) return '—';
    var d = dec === undefined ? (Math.abs(v) < 100 && v % 1 !== 0 ? 2 : 0) : dec;
    return (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function set(form, key, html) { var el = form.querySelector('[data-out="' + key + '"]'); if (el) el.innerHTML = html; }
  var CONTRACTS = window.PFN_CONTRACTS || [];
  function contract(sym) { for (var i = 0; i < CONTRACTS.length; i++) if (CONTRACTS[i].symbol === sym) return CONTRACTS[i]; return null; }
  function fillContracts(sel, preset) {
    if (!sel || sel.options.length) return;
    CONTRACTS.forEach(function (c) {
      var o = document.createElement('option'); o.value = c.symbol; o.textContent = c.symbol + ' — ' + c.name;
      if (c.symbol === preset) o.selected = true; sel.appendChild(o);
    });
  }

  var tools = {
    // ---------------------------------------------------------------- tick value
    tick: function (form) {
      fillContracts(form.elements.symbol, form.getAttribute('data-preset'));
      var c = contract(form.elements.symbol.value); if (!c) return;
      var qty = num(form, 'qty') || 1, ticks = num(form, 'ticks'), points = ticks * c.tick_size;
      set(form, 'tick', usd(c.tick_value_usd, 2));
      set(form, 'point', usd(c.point_value_usd, 2));
      set(form, 'size', (c.tick_size_text || c.tick_size));
      set(form, 'move', usd(ticks * c.tick_value_usd * qty, 2));
      set(form, 'pts', (+points.toFixed(6)).toString() + ' points');
    },
    // ---------------------------------------------------------------- position size
    size: function (form) {
      fillContracts(form.elements.symbol, form.getAttribute('data-preset'));
      var c = contract(form.elements.symbol.value); if (!c) return;
      var risk = num(form, 'risk'), stop = num(form, 'stop'), unit = form.elements.unit.value;
      var stopTicks = unit === 'points' ? stop / c.tick_size : stop;
      var perContract = stopTicks * c.tick_value_usd;
      var n = perContract > 0 ? Math.floor(risk / perContract + 1e-9) : 0;
      set(form, 'per', usd(perContract, 2));
      set(form, 'n', n + (n === 1 ? ' contract' : ' contracts'));
      set(form, 'used', usd(n * perContract, 2));
      var maxloss = num(form, 'maxloss');
      set(form, 'share', maxloss > 0 ? ((n * perContract) / maxloss * 100).toFixed(1) + '% of max loss' : '—');
    },
    // ---------------------------------------------------------------- true cost
    cost: function (form) {
      var fee = num(form, 'fee'), disc = num(form, 'disc') / 100, billing = form.elements.billing.value;
      var months = Math.max(1, num(form, 'months')), act = num(form, 'act'), resets = num(form, 'resets'), resetFee = num(form, 'resetfee');
      var evalCost = billing === 'monthly' ? fee * (1 - disc) * months : fee * (1 - disc);
      var total = evalCost + resets * resetFee + act;
      set(form, 'eval', usd(evalCost));
      set(form, 'resets', usd(resets * resetFee));
      set(form, 'total', usd(total));
      var split = num(form, 'split') / 100;
      set(form, 'breakeven', split > 0 ? usd(total / split) + ' in profit' : '—');
    },
    // ---------------------------------------------------------------- payout
    payout: function (form) {
      var profit = num(form, 'profit'), first = num(form, 'first'), split = num(form, 'split') / 100, fees = num(form, 'fees');
      var full = Math.min(profit, first), rest = Math.max(0, profit - first);
      var gross = full + rest * split;
      set(form, 'gross', usd(gross));
      set(form, 'firm', usd(profit - gross));
      set(form, 'net', usd(gross - fees));
      set(form, 'eff', profit > 0 ? ((gross / profit) * 100).toFixed(1) + '%' : '—');
    },
    // ---------------------------------------------------------------- drawdown simulator
    dd: function (form) {
      var start = num(form, 'start'), limit = num(form, 'limit'), lockAt = form.elements.lock.checked;
      var rows = form.querySelectorAll('[data-day]'), days = [];
      rows.forEach(function (r) {
        var hi = parseFloat(r.querySelector('[name^=hi]').value), lo = parseFloat(r.querySelector('[name^=lo]').value), cl = parseFloat(r.querySelector('[name^=cl]').value);
        if (isFinite(hi) && isFinite(lo) && isFinite(cl)) days.push({ hi: hi, lo: lo, cl: cl });
      });
      var kinds = { static: 'Static', eod: 'End-of-day trailing', intraday: 'Intraday trailing' };
      var res = {}, bal = start;
      var cap = lockAt ? start : Infinity;
      Object.keys(kinds).forEach(function (k) {
        var floor = start - limit, peak = start, bust = null, b = start, path = [];
        days.forEach(function (d, i) {
          var hiBal = b + d.hi, loBal = b + d.lo, clBal = b + d.cl;
          // worst case for intraday trailing: the day's high prints before its low
          if (k === 'intraday') { peak = Math.max(peak, hiBal); floor = Math.max(floor, Math.min(peak - limit, cap)); }
          path.push({ floor: floor, hi: hiBal, lo: loBal, cl: clBal });
          if (bust === null && loBal <= floor) bust = i + 1;
          if (k === 'eod') floor = Math.max(floor, Math.min(clBal - limit, cap));
          b = clBal;
        });
        res[k] = { bust: bust, floor: floor, path: path, end: b };
      });
      var out = '';
      Object.keys(kinds).forEach(function (k) {
        var r = res[k];
        out += '<div class="' + (r.bust ? 'loss' : 'gain') + '">' + kinds[k] + '<b>' + (r.bust ? 'Breached day ' + r.bust : 'Still alive') + '</b>Limit now ' + usd(r.floor) + '</div>';
      });
      set(form, 'res', out);
      // chart
      var svg = form.querySelector('svg[data-chart]'); if (!svg || !days.length) return;
      var W = 640, H = 240, L = 58, R = 12, T = 12, B = 28, n = days.length;
      var all = [start - limit];
      Object.keys(res).forEach(function (k) { res[k].path.forEach(function (p) { all.push(p.floor, p.hi, p.lo); }); });
      var mn = Math.min.apply(null, all), mx = Math.max.apply(null, all);
      var raw = (mx - mn) / 4 || 100, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 2.5, 5, 10].map(function (m) { return m * mag; }).filter(function (v) { return v >= raw; })[0];
      mn = Math.floor(mn / step) * step; mx = Math.ceil(mx / step) * step;
      var x = function (i) { return L + (i + 0.5) * (W - L - R) / n; }, y = function (v) { return T + (mx - v) * (H - T - B) / (mx - mn); };
      var g = '';
      for (var v = mn; v <= mx + 1e-9; v += step) { g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="#DCE1E7"/><text x="' + (L - 6) + '" y="' + (y(v) + 4) + '" font-size="11" text-anchor="end" fill="#6E7A89">' + usd(v) + '</text>'; }
      var bars = '';
      res.static.path.forEach(function (p, i) {
        var bw = Math.min(26, (W - L - R) / n * 0.4);
        bars += '<line x1="' + x(i) + '" x2="' + x(i) + '" y1="' + y(p.hi) + '" y2="' + y(p.lo) + '" stroke="#18212C"/>';
        bars += '<rect x="' + (x(i) - bw / 2) + '" y="' + (y(p.cl) - 1.5) + '" width="' + bw + '" height="3" fill="#18212C"/>';
        bars += '<text x="' + x(i) + '" y="' + (H - 8) + '" font-size="11" text-anchor="middle" fill="#6E7A89">Day ' + (i + 1) + '</text>';
      });
      var cols = { static: '#9AA5B1', eod: '#C2362F', intraday: '#E08A00' }, dash = { static: '6 4', eod: '', intraday: '2 3' }, lines = '';
      Object.keys(res).forEach(function (k) {
        var d = '';
        res[k].path.forEach(function (p, i) {
          var x0 = L + i * (W - L - R) / n, x1 = L + (i + 1) * (W - L - R) / n;
          d += (i ? 'L' : 'M') + x0 + ',' + y(p.floor) + ' L' + x1 + ',' + y(p.floor) + ' ';
        });
        lines += '<path d="' + d + '" fill="none" stroke="' + cols[k] + '" stroke-width="2.2" stroke-dasharray="' + dash[k] + '"/>';
      });
      svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
      svg.innerHTML = g + lines + bars;
    },
    // ---------------------------------------------------------------- pass probability
    pass: function (form) {
      var win = num(form, 'win') / 100, avgW = num(form, 'avgw'), avgL = num(form, 'avgl'), perDay = Math.max(1, Math.round(num(form, 'perday')));
      var target = num(form, 'target'), limit = num(form, 'limit'), trailing = form.elements.trailing.value === 'trail';
      var daily = num(form, 'daily'), maxDays = Math.max(1, Math.round(num(form, 'days'))), sims = 4000;
      var lock = form.elements.lock && form.elements.lock.checked;
      var passN = 0, failN = 0, daysSum = 0;
      for (var s = 0; s < sims; s++) {
        var bal = 0, peak = 0, floor = -limit, done = 0;
        for (var d = 0; d < maxDays && !done; d++) {
          var dayStart = bal;
          for (var t = 0; t < perDay; t++) {
            bal += Math.random() < win ? avgW : -avgL;
            if (trailing && bal > peak) { peak = bal; floor = Math.max(floor, lock ? Math.min(peak - limit, 0) : peak - limit); }
            if (bal <= floor) { failN++; done = 1; break; }
            if (bal >= target) { passN++; daysSum += d + 1; done = 1; break; }
            if (daily > 0 && bal <= dayStart - daily) break;
          }
        }
      }
      var other = sims - passN - failN;
      var ev = win * avgW - (1 - win) * avgL;
      set(form, 'pass', (passN / sims * 100).toFixed(1) + '%');
      set(form, 'fail', (failN / sims * 100).toFixed(1) + '%');
      set(form, 'open', (other / sims * 100).toFixed(1) + '%');
      set(form, 'days', passN ? (daysSum / passN).toFixed(1) + ' days' : '—');
      set(form, 'ev', usd(ev, 2) + ' per trade');
    }
  };

  document.querySelectorAll('form[data-tool]').forEach(function (form) {
    var fn = tools[form.getAttribute('data-tool')]; if (!fn) return;
    var run = function () { try { fn(form); } catch (e) { console.error(e); } };
    form.addEventListener('input', run);
    form.addEventListener('change', run);
    form.addEventListener('submit', function (e) { e.preventDefault(); run(); });
    run();
  });
})();
