/* ArchivioFoto webapp: suggerimenti, tutorial, guida con ricerca e assistente. Nessuna dipendenza esterna. */
(function () {
  "use strict";
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem("af:" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem("af:" + k, JSON.stringify(v)); } catch (e) {} }
  };
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function md(s) {  // markdown minimo: grassetto, codice, liste, paragrafi
    var out = [], lista = null;
    esc(s).split("\n").forEach(function (r) {
      r = r.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>");
      var m = r.match(/^\s*(\d+\.|-)\s+(.*)$/);
      if (m) {
        var tipo = m[1] === "-" ? "ul" : "ol";
        if (lista !== tipo) { if (lista) out.push("</" + lista + ">"); out.push("<" + tipo + ">"); lista = tipo; }
        out.push("<li>" + m[2] + "</li>");
      } else {
        if (lista) { out.push("</" + lista + ">"); lista = null; }
        if (r.trim()) out.push("<p>" + r + "</p>");
      }
    });
    if (lista) out.push("</" + lista + ">");
    return out.join("");
  }
  var TOKEN = (document.querySelector('meta[name="token"]') || {}).content || "";
  function api(percorso, dati) {
    return fetch(percorso, {method: "POST", headers: {"Content-Type": "application/json", "X-Token": TOKEN}, body: JSON.stringify(dati || {})})
      .then(function (r) { return r.json(); });
  }
  function norm(s) { return String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); }

  /* ---------- Suggerimenti (finestre a comparsa, disattivabili) ---------- */
  var aiutiOn = store.get("aiuti", true);
  var popup = document.createElement("div");
  popup.className = "popup"; popup.setAttribute("role", "tooltip"); popup.id = "popup-aiuto";
  document.body.appendChild(popup);
  function applicaAiuti() {
    document.body.classList.toggle("aiuti-on", aiutiOn);
    var b = $("#btn-aiuti"); if (b) { b.setAttribute("aria-pressed", String(aiutiOn)); b.textContent = aiutiOn ? "Suggerimenti: sì" : "Suggerimenti: no"; }
    if (!aiutiOn) nascondi();
  }
  function mostra(el) {
    if (!aiutiOn) return;
    popup.textContent = el.getAttribute("data-aiuto");
    popup.classList.remove("sopra");
    var r = el.getBoundingClientRect(), w = Math.min(300, window.innerWidth - 24);
    var left = Math.max(12, Math.min(r.left, window.innerWidth - w - 12));
    popup.style.left = left + "px"; popup.style.maxWidth = w + "px";
    popup.style.setProperty("--freccia", Math.max(10, Math.min(r.left - left + 12, w - 20)) + "px");
    popup.style.top = (r.bottom + 10) + "px";
    popup.classList.add("on");
    var h = popup.offsetHeight;
    if (r.bottom + 10 + h > window.innerHeight && r.top - h - 10 > 0) { popup.style.top = (r.top - h - 10) + "px"; popup.classList.add("sopra"); }
  }
  function nascondi() { popup.classList.remove("on"); }
  function bersaglio(e) {
    var el = e.target.closest && e.target.closest("[data-aiuto]");
    if (!el && e.target.closest) {  // un campo eredita il suggerimento dalla sua etichetta
      var campo = e.target.closest("input,select,textarea");
      if (campo && campo.previousElementSibling && campo.previousElementSibling.hasAttribute("data-aiuto")) el = campo.previousElementSibling;
    }
    return el;
  }
  document.addEventListener("mouseover", function (e) { var el = bersaglio(e); if (el) mostra(el); });
  document.addEventListener("mouseout", function (e) { if (bersaglio(e)) nascondi(); });
  document.addEventListener("focusin", function (e) { var el = bersaglio(e); if (el) mostra(el); else nascondi(); });
  window.addEventListener("scroll", nascondi, {passive: true});

  /* ---------- Tutorial guidato ---------- */
  var tour = {i: 0, passi: [], evid: null, box: null};
  function passiPagina() {
    return $$("[data-tour]").filter(function (el) { return el.offsetParent !== null || el.tagName === "HEADER"; })
      .sort(function (a, b) { return (+a.dataset.tourOrdine || 0) - (+b.dataset.tourOrdine || 0); });
  }
  function avviaTour() {
    nascondi(); chiudiPannello();
    tour.passi = passiPagina();
    if (!tour.passi.length) return;
    tour.i = 0;
    tour.evid = document.createElement("div"); tour.evid.className = "tour-evidenza";
    tour.box = document.createElement("div"); tour.box.className = "tour-box"; tour.box.setAttribute("role", "dialog"); tour.box.setAttribute("aria-modal", "true");
    document.body.appendChild(tour.evid); document.body.appendChild(tour.box);
    passoTour();
  }
  function passoTour() {
    var el = tour.passi[tour.i], n = tour.passi.length;
    el.scrollIntoView({block: "center", behavior: "auto"});
    var r = el.getBoundingClientRect(), pad = 6;
    Object.assign(tour.evid.style, {left: (r.left - pad) + "px", top: (r.top - pad) + "px", width: (r.width + 2 * pad) + "px", height: (r.height + 2 * pad) + "px"});
    var auto = store.get("tour-auto", true);
    tour.box.innerHTML = "<h3>" + esc(el.dataset.tourTitolo || "") + "</h3><p>" + esc(el.dataset.tour) + "</p>" +
      '<div class="riga"><span class="mut">' + (tour.i + 1) + " di " + n + "</span><span>" +
      (tour.i ? '<button class="sec" data-t="indietro">Indietro</button> ' : "") +
      '<button data-t="avanti">' + (tour.i === n - 1 ? "Fine" : "Avanti") + '</button> <button class="sec" data-t="chiudi" aria-label="Chiudi">✕</button></span></div>' +
      '<label><input type="checkbox" data-t="auto"' + (auto ? " checked" : "") + "> Mostra il tutorial alla prima visita delle pagine</label>";
    var bw = tour.box.offsetWidth, bh = tour.box.offsetHeight;
    var top = r.bottom + 14 + bh < window.innerHeight ? r.bottom + 14 : Math.max(12, r.top - bh - 14);
    tour.box.style.top = top + "px";
    tour.box.style.left = Math.max(12, Math.min(r.left, window.innerWidth - bw - 12)) + "px";
    $('[data-t="avanti"]', tour.box).focus();
  }
  function chiudiTour() {
    if (tour.evid) { tour.evid.remove(); tour.box.remove(); tour.evid = tour.box = null; }
  }
  document.addEventListener("click", function (e) {
    var t = e.target.getAttribute && e.target.getAttribute("data-t");
    if (!t || !tour.box) return;
    if (t === "avanti") { if (tour.i < tour.passi.length - 1) { tour.i++; passoTour(); } else chiudiTour(); }
    if (t === "indietro") { tour.i--; passoTour(); }
    if (t === "chiudi") chiudiTour();
    if (t === "auto") store.set("tour-auto", e.target.checked);
  });
  window.addEventListener("resize", function () { if (tour.box) passoTour(); });

  /* ---------- Guida: ricerca e assistente ---------- */
  var guida = [], chat = store.get("chat", []);
  var pan = $("#pannello"), corpo = $("#pannello .corpo"), q = $("#q");
  fetch("/static/guida.json").then(function (r) { return r.json(); }).then(function (g) { guida = g; mostraElenco(); });

  function cercaGuida(testo) {
    var parole = norm(testo).match(/\w{3,}/g) || [];
    return guida.map(function (a) {
      var t = norm(a.titolo), k = norm(a.chiavi), x = norm(a.testo), s = 0;
      parole.forEach(function (w) {
        var rad = w.slice(0, Math.max(4, w.length - 2));
        if (t.indexOf(rad) >= 0) s += 5; if (k.indexOf(rad) >= 0) s += 3; if (x.indexOf(rad) >= 0) s += 1;
      });
      return {a: a, s: s};
    }).filter(function (r) { return r.s > 0; }).sort(function (a, b) { return b.s - a.s; }).map(function (r) { return r.a; });
  }
  function mostraElenco(testo) {
    var lista = testo ? cercaGuida(testo) : guida;
    var h = "";
    if (chat.length) h += '<div class="mut">Conversazione</div>' + chat.map(msgHtml).join("") + '<button class="chip" data-g="pulisci">Cancella conversazione</button><hr>';
    if (testo && !lista.length) h += '<p class="mut">Nessun articolo trovato. Premi <strong>Chiedi</strong> per domandarlo all\'assistente.</p>';
    h += lista.slice(0, testo ? 6 : 99).map(function (a) {
      return '<button class="risultato" data-art="' + a.id + '">' + esc(a.titolo) + "<small>" + esc(a.categoria) + "</small></button>";
    }).join("");
    corpo.innerHTML = h;
  }
  function mostraArticolo(id) {
    var a = guida.filter(function (x) { return x.id === id; })[0];
    if (!a) return;
    corpo.innerHTML = '<button class="chip" data-g="indietro">← Tutti gli articoli</button><div class="articolo"><h3>' + esc(a.titolo) + "</h3>" + md(a.testo) + "</div>";
    corpo.scrollTop = 0;
  }
  function msgHtml(m) {
    var fonti = (m.fonti || []).map(function (f) { return '<button class="chip" data-art="' + f.id + '">' + esc(f.titolo) + "</button>"; }).join("");
    return '<div class="msg ' + m.ruolo + (m.errore ? " errore" : "") + '">' + (m.ruolo === "assistente" ? md(m.testo) : esc(m.testo)) + (fonti ? "<div>" + fonti + "</div>" : "") + "</div>";
  }
  function chiedi(domanda) {
    var storia = chat.slice(-6);
    chat.push({ruolo: "utente", testo: domanda});
    mostraElenco(); corpo.insertAdjacentHTML("beforeend", '<p class="mut" id="attesa">L\'assistente sta rispondendo…</p>');
    corpo.scrollTop = 0;
    api("/api/chiedi", {domanda: domanda, storia: storia})
      .then(function (d) {
        if (d.errore) {
          var art = cercaGuida(domanda).slice(0, 3).map(function (a) { return {id: a.id, titolo: a.titolo}; });
          chat.push({ruolo: "assistente", errore: true, testo: "Assistente non disponibile: " + d.errore + "\n\nArticoli della guida che possono aiutarti:", fonti: art});
        } else chat.push({ruolo: "assistente", testo: d.risposta, fonti: d.fonti});
      })
      .catch(function (e) { chat.push({ruolo: "assistente", errore: true, testo: "Errore di rete: " + e}); })
      .then(function () { chat = chat.slice(-20); store.set("chat", chat); mostraElenco(); });
  }
  function apriPannello(testo) {
    pan.classList.add("aperto"); pan.setAttribute("aria-hidden", "false");
    if (typeof testo === "string") { q.value = testo; mostraElenco(testo); }
    q.focus();
  }
  function chiudiPannello() { pan.classList.remove("aperto"); pan.setAttribute("aria-hidden", "true"); }

  q.addEventListener("input", function () { mostraElenco(q.value.trim()); });
  $("#form-chiedi").addEventListener("submit", function (e) {
    e.preventDefault(); var d = q.value.trim(); if (d) { chiedi(d); q.value = ""; }
  });
  pan.addEventListener("click", function (e) {
    var b = e.target.closest("[data-art],[data-g]"); if (!b) return;
    if (b.dataset.art) mostraArticolo(b.dataset.art);
    if (b.dataset.g === "indietro") mostraElenco(q.value.trim());
    if (b.dataset.g === "pulisci") { chat = []; store.set("chat", chat); mostraElenco(); }
  });
  document.addEventListener("click", function (e) {
    var g = e.target.closest && e.target.closest("[data-guida]");
    if (g) { e.preventDefault(); apriPannello(); mostraArticolo(g.dataset.guida); }
  });

  /* ---------- Barra superiore e scorciatoie ---------- */
  $("#btn-aiuti").addEventListener("click", function () { aiutiOn = !aiutiOn; store.set("aiuti", aiutiOn); applicaAiuti(); });
  $("#btn-tour").addEventListener("click", avviaTour);
  $("#btn-guida").addEventListener("click", function () { pan.classList.contains("aperto") ? chiudiPannello() : apriPannello(); });
  $("#btn-chiudi-guida").addEventListener("click", chiudiPannello);
  document.addEventListener("keydown", function (e) {
    var inCampo = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (e.key === "Escape") { chiudiTour(); chiudiPannello(); nascondi(); }
    else if (e.key === "/" && !inCampo) { e.preventDefault(); apriPannello(); }
  });
  applicaAiuti();

  /* ---------- Esci ---------- */
  $("#btn-esci").addEventListener("click", function () {
    if (!confirm("Chiudere ArchivioFoto? Un lavoro in corso verrebbe interrotto.")) return;
    api("/api/esci").then(function () {
      document.body.innerHTML = '<main><h2>ArchivioFoto è chiuso</h2><p>Puoi chiudere questa scheda. Per riaprirlo, avvia di nuovo il programma.</p></main>';
    });
  });

  /* ---------- Impostazioni: elenco e prova dei motori ---------- */
  var esitoMotori = $("#esito-motori");
  function prova(ruolo) {
    esitoMotori.textContent = "Prova " + ruolo + " in corso… (può richiedere fino a un minuto)";
    api("/api/prova", {ruolo: ruolo}).then(function (e) {
      esitoMotori.innerHTML = '<span class="' + (e.ok ? "ok" : "errore") + '">' + (e.ok ? "✔ Funziona" : "✖ Non funziona") + "</span> · " +
        esc(e.modello) + " · " + e.secondi + " s<br>" + esc(e.dettaglio);
    }).catch(function (x) { esitoMotori.textContent = "Errore: " + x; });
  }
  if (esitoMotori) {
    $("#btn-prova-visione").addEventListener("click", function () { prova("visione"); });
    $("#btn-prova-testo").addEventListener("click", function () { prova("testo"); });
    $("#btn-modelli").addEventListener("click", function () {
      var out = $("#elenco-modelli"); out.textContent = "Carico l'elenco…";
      api("/api/modelli").then(function (d) {
        if (d.errore) { out.innerHTML = '<span class="errore">' + esc(d.errore) + "</span>"; return; }
        $("#modelli").innerHTML = d.modelli.map(function (m) { return '<option value="' + esc(m.id) + '">' + (m.visione ? "visione" : "testo") + "</option>"; }).join("");
        var vis = d.modelli.filter(function (m) { return m.visione; });
        out.innerHTML = d.modelli.length + " modelli disponibili, " + vis.length + " probabilmente di visione. Ora i campi «modello» propongono l'elenco mentre scrivi.<br>" +
          vis.slice(0, 12).map(function (m) { return "<code>" + esc(m.id) + "</code>"; }).join(" ");
      });
    });
  }

  /* ---------- Lavori: avanzamento in tempo reale ---------- */
  var log = $("#lav-log");
  if (log) {
    var sfoglia = $("#btn-sfoglia");
    if (sfoglia) sfoglia.addEventListener("click", function () {
      sfoglia.disabled = true;
      api("/api/sfoglia").then(function (d) { if (d.cartella) $("#cartella").value = d.cartella; }).then(function () { sfoglia.disabled = false; });
    });
    var aggiorna = function () {
      fetch("/api/lavoro").then(function (r) { return r.json(); }).then(function (s) {
        var fine = s.codice === null ? "" : (s.codice === 0 ? " — completato ✔" : " — terminato con errori ✖ (vedi Note)");
        $("#lav-titolo").textContent = s.titolo ? (s.attivo ? "In corso: " : "Ultimo lavoro: ") + s.titolo + fine : "Nessun lavoro in corso";
        var barra = $("#lav-barra");
        if (s.totale) { barra.max = s.totale; barra.value = Math.min(s.fatti, s.totale); } else if (s.attivo) { barra.removeAttribute("value"); } else { barra.max = 1; barra.value = s.titolo ? 1 : 0; }
        var giu = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
        log.textContent = s.righe.join("\n");
        if (giu) log.scrollTop = log.scrollHeight;
        $$("#lavori-schede button, form[action='/lavori/avvia'] button").forEach(function (b) { if (b.type !== "button") b.disabled = s.attivo; });
        if (s.attivo) setTimeout(aggiorna, 1000);
      });
    };
    aggiorna();
    document.addEventListener("submit", function () { setTimeout(aggiorna, 800); });
  }

  var pagina = document.body.dataset.pagina || "pagina";
  var visti = store.get("tour-visti", {});
  if (store.get("tour-auto", true) && !visti[pagina] && passiPagina().length) {
    visti[pagina] = true; store.set("tour-visti", visti);
    setTimeout(avviaTour, 400);
  }
})();
