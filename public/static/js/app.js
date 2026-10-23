(() => {
  "use strict";

  const STORAGE_VIEW = "tahminLigi.view";
  const AUTO_REFRESH_MS = 60_000;
  const VALID_VIEWS = new Set(["matches", "standings", "predictions", "results"]);
  const ICON = {
    chevron: '<svg class="icon"><use href="#i-chevron"/></svg>',
    users: '<svg class="icon"><use href="#i-users"/></svg>',
    lock: '<svg class="icon"><use href="#i-lock"/></svg>',
    bolt: '<svg class="icon"><use href="#i-bolt"/></svg>',
    target: '<svg class="icon"><use href="#i-target"/></svg>',
    trophy: '<svg class="icon"><use href="#i-trophy"/></svg>',
    clock: '<svg class="icon"><use href="#i-clock"/></svg>',
    ball: '<svg class="icon"><use href="#i-ball"/></svg>',
  };

  const state = {
    data: null,
    loading: false,
    selectedDate: null,
    status: "all",
    competition: "all",
    selectedPlayer: "",
    identityPrompt: false,
    view: "matches",
    timezone: "Europe/Istanbul",
    lastLoadAt: 0,
    lastFocus: null,
    toastTimer: null,
    requestSeq: 0,
  };

  const el = {
    refreshBtn: document.getElementById("refreshBtn"),
    shareBtn: document.getElementById("shareBtn"),
    globalLive: document.getElementById("globalLive"),
    demoBadge: document.getElementById("demoBadge"),
    globalNotice: document.getElementById("globalNotice"),
    updateMeta: document.getElementById("updateMeta"),
    dateStrip: document.getElementById("dateStrip"),
    statusFilters: document.getElementById("statusFilters"),
    competitionFilter: document.getElementById("competitionFilter"),
    fixtureList: document.getElementById("fixtureList"),
    miniStandings: document.getElementById("miniStandings"),
    liveCard: document.getElementById("liveCard"),
    standingsMeta: document.getElementById("standingsMeta"),
    standingsContent: document.getElementById("standingsContent"),
    predictionsMeta: document.getElementById("predictionsMeta"),
    predictionsContent: document.getElementById("predictionsContent"),
    resultsMeta: document.getElementById("resultsMeta"),
    resultsContent: document.getElementById("resultsContent"),
    sourceLabel: document.getElementById("sourceLabel"),
    sheetLayer: document.getElementById("sheetLayer"),
    sheetContent: document.getElementById("sheetContent"),
    identityLayer: document.getElementById("identityLayer"),
    identityOptions: document.getElementById("identityOptions"),
    toast: document.getElementById("toast"),
    tabbar: document.getElementById("tabbar"),
  };

  const fmtCache = new Map();

  function formatter(options) {
    const key = JSON.stringify(options);
    if (!fmtCache.has(key)) {
      fmtCache.set(
        key,
        new Intl.DateTimeFormat("tr-TR", { timeZone: state.timezone, ...options })
      );
    }
    return fmtCache.get(key);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function safeColor(value) {
    return /^#[0-9a-f]{6}$/i.test(String(value || "")) ? value : "#b8f34a";
  }

  function safeUrl(value) {
    if (!value) return "";
    try {
      const url = new URL(value, window.location.origin);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
    } catch {
      return "";
    }
  }

  function parseDate(iso) {
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function dateKey(iso) {
    const date = parseDate(iso);
    if (!date) return "";
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: state.timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }

  function clock(iso) {
    const date = parseDate(iso);
    if (!date) return "--:--";
    return formatter({ hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  }

  function fullDate(iso) {
    const date = parseDate(iso);
    if (!date) return "";
    return formatter({
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(date);
  }

  function shortDate(iso) {
    const date = parseDate(iso);
    if (!date) return "";
    return formatter({ day: "numeric", month: "short" }).format(date);
  }

  function dateParts(key) {
    const [year, month, day] = key.split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day, 12));
    return {
      date,
      day: String(day),
      month: formatter({ month: "short" }).format(date),
      weekday: formatter({ weekday: "short" }).format(date),
      long: formatter({ weekday: "long", day: "numeric", month: "long" }).format(date),
    };
  }

  function todayKey() {
    return state.data?.meta?.today || dateKey(new Date().toISOString());
  }

  function relativeDayLabel(key) {
    const today = new Date(`${todayKey()}T12:00:00Z`);
    const target = new Date(`${key}T12:00:00Z`);
    const diff = Math.round((target - today) / 86_400_000);
    if (diff === 0) return "Bugün";
    if (diff === -1) return "Dün";
    if (diff === 1) return "Yarın";
    return dateParts(key).long;
  }

  function matchDate(match) {
    return dateKey(match.kickoff);
  }

  function statusLabel(match) {
    if (match.status === "POSTPONED") return "Ertelendi";
    if (match.status === "CANCELLED") return "İptal";
    if (match.status === "SUSPENDED") return "Askıda";
    if (match.is_live) return match.minute ? `${match.minute}'` : "Canlı";
    if (match.is_finished) return "Bitti";
    return "Yaklaşan";
  }

  function statusWord(match) {
    if (match.status === "POSTPONED") return "ERT";
    if (match.status === "CANCELLED") return "İPTAL";
    if (match.status === "SUSPENDED") return "ASKIDA";
    if (match.is_live) return "CANLI";
    if (match.is_finished) return "BİTTİ";
    return "";
  }

  function scoreText(match) {
    if (match.score.home === null || match.score.away === null) return "–";
    return `${match.score.home} - ${match.score.away}`;
  }

  function crest(team) {
    const fallback = escapeHtml(team.tla || team.short || team.name || "?");
    const url = safeUrl(team.crest);
    if (!url) {
      return `<span class="crest"><span class="crest-fallback">${fallback}</span></span>`;
    }
    return `<span class="crest"><span class="crest-fallback">${fallback}</span><img src="${escapeHtml(
      url
    )}" alt="" loading="lazy" referrerpolicy="no-referrer"></span>`;
  }

  function compColor(code) {
    const palette = {
      PL: "#b8f34a",
      PD: "#ff8b5e",
      BL1: "#ff5d70",
      SA: "#6db6ff",
      FL1: "#c7a4ff",
      CL: "#5ce1e6",
      EL: "#ffb347",
      DED: "#ff9f43",
      PPL: "#4ade80",
      TSL: "#ff647c",
    };
    return palette[code] || "#b8f34a";
  }

  function compBadge(competition, sizeClass = "") {
    const code = escapeHtml(competition?.code || "?");
    const color = compColor(competition?.code);
    return `<span class="comp-badge ${sizeClass}" style="--comp-color:${color}">${code}</span>`;
  }

  function avatar(player, extraClass = "") {
    return `<span class="avatar ${extraClass}" style="--avatar-color:${safeColor(
      player.color
    )}">${escapeHtml(player.initials || "?")}</span>`;
  }

  function teamForm(team) {
    if (!team.form || !team.form.length) return "";
    const labels = { G: "G", B: "B", M: "M" };
    return `<span class="team-form">${team.form
      .map((result) => {
        const cls =
          result === "G" ? "is-win" : result === "B" ? "is-draw" : "is-loss";
        return `<span class="${cls}" title="${escapeHtml(
          result === "G" ? "Galibiyet" : result === "B" ? "Beraberlik" : "Mağlubiyet"
        )}">${labels[result] || "?"}</span>`;
      })
      .join("")}</span>`;
  }

  function selectedPlayer() {
    if (!state.data || !state.selectedPlayer) return null;
    return (
      state.data.players.find(
        (player) => String(player.id) === String(state.selectedPlayer)
      ) || null
    );
  }

  function standingFor(playerId) {
    return state.data?.standings?.find((row) => String(row.id) === String(playerId));
  }

  function predictionFor(match, playerId) {
    return (match.predictions || []).find(
      (prediction) => String(prediction.player_id) === String(playerId)
    );
  }

  function setView(view, { updateHash = true, scroll = true } = {}) {
    if (!VALID_VIEWS.has(view)) view = "matches";
    const previousView = state.view;
    state.view = view;
    localStorage.setItem(STORAGE_VIEW, view);

    document.querySelectorAll("[data-view-panel]").forEach((panel) => {
      panel.classList.toggle("is-hidden", panel.dataset.viewPanel !== view);
    });
    document.querySelectorAll(".tab[data-view]").forEach((tab) => {
      const active = tab.dataset.view === view;
      tab.classList.toggle("is-active", active);
      if (active) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    });

    if (updateHash && window.location.hash !== `#${view}`) {
      history.replaceState(null, "", `#${view}`);
    }
    if (scroll) window.scrollTo({ top: 0, behavior: "smooth" });

    if (view === "predictions") {
      state.identityPrompt = true;
      renderPredictions();
      syncIdentityGate();
      return;
    }

    if (previousView === "predictions" && view !== "predictions") {
      state.selectedPlayer = "";
      renderStandings();
      renderPredictions();
      renderResults();
    }

    state.identityPrompt = false;
    closeIdentityGate();
    renderPredictions();
  }

  function routeFromHash() {
    const hash = window.location.hash.replace("#", "");
    if (VALID_VIEWS.has(hash)) return hash;
    const stored = localStorage.getItem(STORAGE_VIEW);
    return VALID_VIEWS.has(stored) ? stored : "matches";
  }

  function showToast(message, duration = 2600) {
    el.toast.textContent = message;
    el.toast.classList.add("is-visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      el.toast.classList.remove("is-visible");
    }, duration);
  }

  function setRefreshBusy(busy) {
    el.refreshBtn.classList.toggle("is-spinning", busy);
    el.refreshBtn.disabled = busy;
  }

  async function loadData({ silent = false } = {}) {
    if (state.loading) return;
    state.loading = true;
    const seq = ++state.requestSeq;
    if (!silent || !state.data) setRefreshBusy(true);

    try {
      const response = await fetch("/api/league", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (seq !== state.requestSeq) return;
      state.data = data;
      state.timezone = data.meta?.timezone || "Europe/Istanbul";
      state.lastLoadAt = Date.now();
      fmtCache.clear();
      hydrate();
    } catch (error) {
      console.error("Lig verisi alınamadı", error);
      if (!state.data) {
        el.fixtureList.innerHTML = errorState(
          "Veriler yüklenemedi",
          "Bağlantıyı kontrol edip tekrar deneyin.",
          true
        );
        showNotice("Veri kaynağına şu anda ulaşılamıyor.", true);
      } else if (!silent) {
        showToast("Yenileme başarısız. Mevcut veriler gösteriliyor.");
      }
    } finally {
      state.loading = false;
      setRefreshBusy(false);
    }
  }

  function hydrate() {
    if (!state.data) return;
    const dates = allDates();
    if (!state.selectedDate || !dates.includes(state.selectedDate)) {
      state.selectedDate = defaultDate();
    }
    if (
      state.selectedPlayer &&
      !state.data.players.some(
        (player) => String(player.id) === String(state.selectedPlayer)
      )
    ) {
      state.selectedPlayer = "";
    }

    renderHeader();
    renderNotice();
    renderUpdateMeta();
    renderDateStrip();
    renderCompetitionFilter();
    renderStatusFilters();
    renderFixtures();
    renderMiniStandings();
    renderLiveCard();
    renderStandings();
    renderPredictions();
    renderResults();
    renderSource();
    syncIdentityGate();
  }

  function allDates() {
    const dates = new Set((state.data?.matches || []).map(matchDate));
    dates.add(todayKey());
    return [...dates].filter(Boolean).sort();
  }

  function defaultDate() {
    const today = todayKey();
    const matches = state.data.matches;
    if (matches.some((match) => matchDate(match) === today)) return today;
    const future = matches
      .filter((match) => matchDate(match) > today)
      .sort((a, b) => a.kickoff.localeCompare(b.kickoff));
    if (future.length) return matchDate(future[0]);
    const past = matches
      .filter((match) => matchDate(match) < today)
      .sort((a, b) => b.kickoff.localeCompare(a.kickoff));
    return past.length ? matchDate(past[0]) : today;
  }

  function renderHeader() {
    const meta = state.data.meta;
    el.globalLive.classList.toggle("is-hidden", meta.counts.live === 0);
    el.demoBadge.classList.toggle("is-hidden", !meta.demo);
    document.title = `${meta.league_name} · Avrupa Futbolu Tahmin Ligi`;
  }

  function renderIdentityOptions() {
    if (!el.identityOptions || !state.data) return;
    const current = String(state.selectedPlayer || "");
    el.identityOptions.innerHTML = state.data.players
      .map((item) => {
        const isCurrent = current && String(item.id) === current;
        return `<button class="player-chip${isCurrent ? " is-selected" : ""}" type="button" data-open-player="${escapeHtml(
          item.id
        )}">${avatar(item)}${escapeHtml(item.name)}</button>`;
      })
      .join("");
  }

  function openIdentityGate() {
    if (!el.identityLayer || !state.data?.players.length) return;
    renderIdentityOptions();
    el.identityLayer.classList.remove("is-hidden");
    el.identityLayer.setAttribute("aria-hidden", "false");
    document.body.classList.add("has-identity");
    requestAnimationFrame(() => {
      const first =
        el.identityOptions.querySelector(".player-chip.is-selected") ||
        el.identityOptions.querySelector(".player-chip");
      first?.focus();
    });
  }

  function closeIdentityGate() {
    if (!el.identityLayer) return;
    el.identityLayer.classList.add("is-hidden");
    el.identityLayer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("has-identity");
  }

  function syncIdentityGate() {
    if (!state.data) return;
    if (state.identityPrompt && state.view === "predictions") {
      openIdentityGate();
      return;
    }
    if (!state.identityPrompt) {
      closeIdentityGate();
      return;
    }
    if (state.view !== "predictions") {
      state.identityPrompt = false;
      closeIdentityGate();
    }
  }

  function renderNotice() {
    const { meta } = state.data;
    if (meta.sync?.error) {
      showNotice(
        `Canlı veri alınamadı. Son başarılı güncelleme: ${
          meta.sync.last_success_at
            ? clock(meta.sync.last_success_at)
            : "henüz yok"
        }. Mevcut veriler gösteriliyor.`,
        true
      );
      return;
    }
    if (meta.demo) {
      showNotice(
        "Demo modu: fikstür, sonuçlar ve tahminler örnek veridir. Canlı veri için README’deki kurulumu izleyin.",
        false
      );
      return;
    }
    el.globalNotice.classList.add("is-hidden");
  }

  function showNotice(message, isError) {
    el.globalNotice.textContent = message;
    el.globalNotice.classList.remove("is-hidden");
    el.globalNotice.classList.toggle("is-error", Boolean(isError));
  }

  function renderUpdateMeta() {
    const { meta } = state.data;
    const stamp = meta.sync?.last_success_at || meta.generated_at;
    el.updateMeta.innerHTML = `<span>${ICON.clock}</span><span>Güncelleme ${clock(
      stamp
    )}</span><span class="meta-sep"></span><span>${escapeHtml(
      meta.source
    )}</span>`;
  }

  function renderSource() {
    const { meta } = state.data;
    if (meta.source_url && !meta.demo) {
      el.sourceLabel.innerHTML = `Veri: <a href="${escapeHtml(
        meta.source_url
      )}" target="_blank" rel="noopener">${escapeHtml(meta.source)}</a>`;
    } else {
      el.sourceLabel.textContent = `Veri: ${meta.source}`;
    }
  }

  function renderDateStrip() {
    const dates = allDates();
    const liveDates = new Set(
      state.data.matches.filter((match) => match.is_live).map(matchDate)
    );
    const counts = state.data.matches.reduce((map, match) => {
      const key = matchDate(match);
      map[key] = (map[key] || 0) + 1;
      return map;
    }, {});
    const today = todayKey();

    el.dateStrip.innerHTML = dates
      .map((key) => {
        const parts = dateParts(key);
        const active = key === state.selectedDate;
        const isToday = key === today;
        return `<button class="date-chip${active ? " is-active" : ""}${
          isToday ? " is-today" : ""
        }" type="button" role="tab" aria-selected="${active}" data-date="${key}">
          <span class="dow">${escapeHtml(parts.weekday)}</span>
          <span class="day">${parts.day}</span>
          <span class="month">${escapeHtml(parts.month)}</span>
          ${
            liveDates.has(key)
              ? '<span class="date-live" title="Canlı maç var"></span>'
              : counts[key]
              ? `<span class="date-count">${counts[key]}</span>`
              : ""
          }
        </button>`;
      })
      .join("");

    const active = el.dateStrip.querySelector(".date-chip.is-active");
    if (active) {
      requestAnimationFrame(() =>
        active.scrollIntoView({ block: "nearest", inline: "center" })
      );
    }
  }

  function renderCompetitionFilter() {
    const current = state.competition;
    el.competitionFilter.innerHTML =
      '<option value="all">Tüm ligler</option>' +
      state.data.competitions
        .map(
          (competition) =>
            `<option value="${escapeHtml(competition.code)}">${escapeHtml(
              competition.name
            )}</option>`
        )
        .join("");
    el.competitionFilter.value = [
      ...el.competitionFilter.options,
    ].some((option) => option.value === current)
      ? current
      : "all";
    state.competition = el.competitionFilter.value;
  }

  function renderStatusFilters() {
    el.statusFilters.querySelectorAll(".segment").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.status === state.status);
    });
  }

  function matchesForCurrentFilters({ ignoreDate = false } = {}) {
    return state.data.matches.filter((match) => {
      if (!ignoreDate && matchDate(match) !== state.selectedDate) return false;
      if (state.competition !== "all" && match.competition_code !== state.competition) {
        return false;
      }
      if (state.status === "live") return match.is_live;
      if (state.status === "finished") return match.is_finished;
      if (state.status === "upcoming") {
        return match.status_group === "upcoming" && !match.is_started;
      }
      return true;
    });
  }

  function renderFixtures() {
    const matches = matchesForCurrentFilters().sort((a, b) =>
      a.kickoff.localeCompare(b.kickoff)
    );
    if (!matches.length) {
      const alternative = nextInterestingDate();
      const action = alternative
        ? `<button class="primary-button" type="button" data-goto-date="${alternative}">${escapeHtml(
            relativeDayLabel(alternative)
          )} maçlarına git</button>`
        : "";
      el.fixtureList.innerHTML = errorState(
        "Bu filtrede maç yok",
        state.status === "live"
          ? "Şu anda seçili tarihte canlı maç bulunmuyor."
          : "Başka bir tarih veya lig filtresi deneyin.",
        false,
        action
      );
      return;
    }

    const order = new Map(
      state.data.competitions.map((competition, index) => [competition.code, index])
    );
    const groups = new Map();
    for (const match of matches) {
      const code = match.competition_code;
      if (!groups.has(code)) groups.set(code, []);
      groups.get(code).push(match);
    }
    const sortedGroups = [...groups.entries()].sort(
      (a, b) => (order.get(a[0]) ?? 999) - (order.get(b[0]) ?? 999)
    );

    el.fixtureList.innerHTML = sortedGroups
      .map(([code, groupMatches]) => {
        const competition = groupMatches[0].competition || { code, name: code };
        const liveCount = groupMatches.filter((match) => match.is_live).length;
        return `<section class="competition-group" aria-label="${escapeHtml(
          competition.name
        )}">
          <header class="competition-head">
            ${compBadge(competition)}
            <div class="competition-name">
              <strong>${escapeHtml(competition.name)}</strong>
              <small>${escapeHtml(competition.country || "Avrupa")}</small>
            </div>
            <span class="group-count">${
              liveCount ? `${liveCount} canlı · ` : ""
            }${groupMatches.length} maç</span>
          </header>
          ${groupMatches.map(matchRow).join("")}
        </section>`;
      })
      .join("");
  }

  function matchRow(match) {
    const homeWin =
      match.is_finished && Number(match.score.home) > Number(match.score.away);
    const awayWin =
      match.is_finished && Number(match.score.away) > Number(match.score.home);
    const rowClass = [
      "match-row",
      match.is_live ? "is-live" : "",
      match.is_finished ? "is-finished" : "",
      match.status_group === "upcoming" ? "is-scheduled" : "",
    ]
      .filter(Boolean)
      .join(" ");
    const leftPrimary = match.is_live
      ? match.minute
        ? `${match.minute}'`
        : "CANLI"
      : match.is_finished
      ? "BİTTİ"
      : clock(match.kickoff);
    const leftSecondary = match.is_live
      ? "CANLI"
      : match.is_finished
      ? "MS"
      : statusWord(match);
    return `<button class="${rowClass}" type="button" data-match-id="${match.id}" aria-label="${escapeHtml(
      `${match.home.name} - ${match.away.name}, ${statusLabel(match)}`
    )}">
      <span class="match-clock">
        <strong>${escapeHtml(leftPrimary)}</strong>
        <small>${escapeHtml(leftSecondary)}</small>
      </span>
      <span class="match-teams">
        <span class="team-line${homeWin ? " is-winner" : ""}">
          ${crest(match.home)}
          <span class="team-name">${escapeHtml(match.home.name)}</span>
          <span class="team-score">${
            match.score.home === null ? "–" : escapeHtml(match.score.home)
          }</span>
        </span>
        <span class="team-line${awayWin ? " is-winner" : ""}">
          ${crest(match.away)}
          <span class="team-name">${escapeHtml(match.away.name)}</span>
          <span class="team-score">${
            match.score.away === null ? "–" : escapeHtml(match.score.away)
          }</span>
        </span>
      </span>
      <span class="match-meta">
        <span class="pred-icon">${ICON.users}${match.prediction_count}</span>
        <span>tahmin</span>
      </span>
      <span class="match-chevron">${ICON.chevron}</span>
    </button>`;
  }

  function nextInterestingDate() {
    const dates = allDates();
    const current = state.selectedDate || todayKey();
    return (
      dates.find((date) => date > current && state.data.matches.some((m) => matchDate(m) === date)) ||
      dates.find((date) => date < current && state.data.matches.some((m) => matchDate(m) === date)) ||
      null
    );
  }

  function renderMiniStandings() {
    const rows = state.data.standings.slice(0, 5);
    if (!rows.length) {
      el.miniStandings.innerHTML = `<div class="side-card-head"><div><p class="eyebrow">Klasman</p><h2>Puan tablosu</h2></div></div><p class="fine-print">Henüz puan oluşmadı.</p>`;
      return;
    }
    el.miniStandings.innerHTML = `
      <div class="side-card-head">
        <div><p class="eyebrow">Klasman</p><h2>Puan tablosu</h2></div>
      </div>
      ${rows
        .map(
          (row) => `<div class="mini-standing-row">
            <span class="mini-rank">${row.rank}</span>
            <span class="mini-player">${avatar(row, "is-sm")}<span class="mini-player-name">${escapeHtml(
            row.name
          )}</span></span>
            <span class="mini-points">${row.points}<small>P</small></span>
          </div>`
        )
        .join("")}
      <a class="side-link" href="#standings">Tüm sıralamayı gör</a>
    `;
  }

  function renderLiveCard() {
    const live = state.data.matches
      .filter((match) => match.is_live)
      .sort((a, b) => a.kickoff.localeCompare(b.kickoff));
    if (!live.length) {
      el.liveCard.innerHTML = `<div class="side-card-head"><span class="side-icon">${ICON.bolt}</span><div><p class="eyebrow">Şimdi</p><h2>Canlı maç yok</h2></div></div><p class="fine-print">Maçlar başladığında skorlar burada görünür.</p>`;
      return;
    }
    el.liveCard.innerHTML = `
      <div class="side-card-head">
        <span class="side-icon">${ICON.bolt}</span>
        <div><p class="eyebrow">Şimdi</p><h2>${live.length} maç canlı</h2></div>
      </div>
      <div class="live-mini">
        ${live
          .map(
            (match) => `<button class="live-mini-row" type="button" data-match-id="${
              match.id
            }">
              <span class="live-mini-teams">
                <span>${escapeHtml(match.home.short)}</span>
                <span>${escapeHtml(match.away.short)}</span>
              </span>
              <span class="live-mini-score">
                <span>${match.score.home ?? "–"}</span>
                <span>${match.score.away ?? "–"}</span>
                <span class="live-mini-minute">${
                  match.minute ? `${match.minute}'` : "CANLI"
                }</span>
              </span>
            </button>`
          )
          .join("")}
      </div>
    `;
  }

  function renderStandings() {
    const rows = state.data.standings;
    const finished = state.data.meta.counts.finished;
    el.standingsMeta.innerHTML = `<span>${rows.length} oyuncu</span><span class="meta-sep"></span><span>${finished} biten maç</span>`;

    if (!rows.length) {
      el.standingsContent.innerHTML = errorState(
        "Henüz oyuncu yok",
        "Yönetici oyuncu eklediğinde puan tablosu burada oluşur."
      );
      return;
    }

    const totalPoints = rows.reduce((sum, row) => sum + row.points, 0);
    const totalOutcomes = rows.reduce((sum, row) => sum + row.correct_outcomes, 0);
    const leader = rows[0];
    const podiumColors = ["#ffd05c", "#c6d4e3", "#dc9b65"];
    const podium = rows.slice(0, 3);

    el.standingsContent.innerHTML = `
      <div class="summary-grid">
        <div class="stat-card"><span>Lider</span><strong>${escapeHtml(
          leader.name
        )}</strong><small>${leader.points} puan</small></div>
        <div class="stat-card"><span>Katılımcı</span><strong>${rows.length}</strong><small>oyuncu</small></div>
        <div class="stat-card"><span>Doğru sonuç</span><strong>${totalOutcomes}</strong><small>toplam isabet</small></div>
        <div class="stat-card"><span>Ortalama</span><strong>${Math.round(
          totalPoints / rows.length
        )}</strong><small>puan / oyuncu</small></div>
      </div>
      <div class="podium">
        ${podium
          .map(
            (row, index) => `<article class="podium-card ${
              index === 0 ? "is-first" : ""
            }" style="--podium-color:${podiumColors[index]}">
              <span class="podium-rank">${
                index === 0 ? ICON.trophy : ""
              } ${row.rank}. sıra</span>
              ${avatar(row, "is-lg")}
              <span class="podium-name">${escapeHtml(row.name)}</span>
              <span class="podium-points">${row.points}<small> P</small></span>
              <span class="podium-sub">${row.correct_outcomes} doğru sonuç · ${row.played} maç</span>
            </article>`
          )
          .join("")}
      </div>
      <div class="standings-card">
        <div class="table-scroll">
          <table class="standings-table">
            <thead><tr>
              <th>#</th><th>Oyuncu</th><th>O</th>
              <th title="Fenerbahçe">FB</th><th title="Galatasaray">GS</th>
              <th title="Beşiktaş">BJK</th><th title="Trabzonspor">TS</th>
              <th>P</th>
            </tr></thead>
            <tbody>
              ${rows
                .map((row) => {
                  const isMe = String(row.id) === String(state.selectedPlayer);
                  const teams = row.team_correct || {};
                  return `<tr class="${isMe ? "is-me" : ""}">
                    <td class="standings-rank ${row.rank <= 3 ? "is-top" : ""}">${row.rank}</td>
                    <td><div class="standings-player">${avatar(
                      row,
                      "is-sm"
                    )}<strong>${escapeHtml(row.name)}</strong>${
                    isMe ? '<span class="me-tag">SEN</span>' : ""
                  }</div></td>
                    <td>${row.played}</td>
                    <td class="team-points">${teams.FB || 0}</td>
                    <td class="team-points">${teams.GS || 0}</td>
                    <td class="team-points">${teams.BJK || 0}</td>
                    <td class="team-points">${teams.TS || 0}</td>
                    <td class="standing-points">${row.points}</td>
                  </tr>`;
                })
                .join("")}
            </tbody>
          </table>
        </div>
        <div class="standings-note">
          <span>O: oynanan maç · FB: Fenerbahçe · GS: Galatasaray · BJK: Beşiktaş · TS: Trabzonspor · P: puan</span>
        </div>
      </div>
    `;
  }

  function predictionBadge(match, prediction) {
    if (!match.is_finished) {
      return `<span class="prediction-points is-pending">${ICON.clock} Bekliyor</span>`;
    }
    const points = prediction.points ?? 0;
    const cls = prediction.correct_outcome ? "is-hit" : "is-miss";
    const label = prediction.correct_outcome ? "Doğru sonuç" : "Isabet yok";
    return `<span class="prediction-points ${cls}" title="${label} · ${
      prediction.joker ? `Joker ×${prediction.multiplier}` : "Normal"
    }">${points > 0 ? "+" : ""}${points} P</span>`;
  }

  function renderPredictions() {
    if (!state.data) return;
    if (!state.data.players.length) {
      el.predictionsMeta.textContent = "";
      el.predictionsContent.innerHTML = errorState(
        "Henüz oyuncu yok",
        "Yönetici oyuncu eklediğinde tahmin karneleri burada görünür."
      );
      return;
    }

    const player = selectedPlayer();
    if (!player) {
      el.predictionsMeta.textContent = "";
      if (state.identityPrompt) {
        el.predictionsContent.innerHTML = "";
        return;
      }
      el.predictionsContent.innerHTML = `
        <div class="player-prompt">
          <span class="prompt-icon">${ICON.target}</span>
          <h2>Kendi karneni gör</h2>
          <p>Tahminlerini görmek için adını seç.</p>
          <div class="player-chips">
            ${state.data.players
              .map(
                (item) =>
                  `<button class="player-chip" type="button" data-open-player="${
                    item.id
                  }">${avatar(item)}${escapeHtml(item.name)}</button>`
              )
              .join("")}
          </div>
        </div>`;
      return;
    }

    const standing = standingFor(player.id);
    const started = state.data.matches
      .filter((match) => match.predictions_visible && predictionFor(match, player.id))
      .sort((a, b) => {
        const fa = a.is_finished ? 1 : 0;
        const fb = b.is_finished ? 1 : 0;
        if (fa !== fb) return fb - fa;
        if (fa === 1) return b.kickoff.localeCompare(a.kickoff);
        return a.kickoff.localeCompare(b.kickoff);
      });
    const visibleCount = started.length;

    el.predictionsMeta.innerHTML = `<span>${visibleCount} tahmin</span><span class="meta-sep"></span><span>Henüz oynanmamış maçlar da gösteriliyor</span>`;
    el.predictionsContent.innerHTML = `
      <div class="player-hero">
        <div class="player-identity">
          ${avatar({ ...player, initials: player.initials }, "is-lg")}
          <div>
            <h2>${escapeHtml(player.name)}</h2>
            <p>${standing ? `${standing.rank}. sıradasın · ${standing.played} maçta tahmin` : "Henüz sıralamada değil"}</p>
          </div>
        </div>
        <div class="player-hero-stats">
          <div class="hero-stat"><span>Puan</span><strong>${standing?.points ?? 0}</strong></div>
          <div class="hero-stat"><span>Doğru sonuç</span><strong>${standing?.correct_outcomes ?? 0}</strong></div>
          <div class="hero-stat"><span>Yanlış sonuç</span><strong>${standing ? (standing.played - standing.correct_outcomes) : 0}</strong></div>
          <div class="hero-stat"><span>İsabet</span><strong>${standing?.accuracy ?? 0}<small>%</small></strong></div>
        </div>
      </div>
      ${
        started.length
          ? `<div class="prediction-grid">${started
              .map((match) => {
                const prediction = predictionFor(match, player.id);
                const awayWins =
                  match.is_finished &&
                  match.score.home !== null &&
                  match.score.away !== null &&
                  match.score.away > match.score.home;
                const leftTeam = awayWins ? match.away : match.home;
                const rightTeam = awayWins ? match.home : match.away;
                const leftScore = awayWins ? match.score.away : match.score.home;
                const rightScore = awayWins ? match.score.home : match.score.away;
                return `<button class="prediction-card" type="button" data-match-id="${
                  match.id
                }">
                  <div class="prediction-card-head">
                    ${compBadge(match.competition)}
                    <span>${escapeHtml(match.competition.name)}</span>
                    <span class="pred-date">${escapeHtml(shortDate(match.kickoff))}</span>
                  </div>
                  <div class="prediction-teams">
                    <div class="prediction-teams-row prediction-teams-row--dual">
                      <div class="prediction-team">
                        ${crest(leftTeam)}
                        <span>${escapeHtml(leftTeam.short || leftTeam.name)}</span>
                      </div>
                      <div class="prediction-team">
                        ${crest(rightTeam)}
                        <span>${escapeHtml(rightTeam.short || rightTeam.name)}</span>
                      </div>
                    </div>
                    ${
                      match.is_finished
                        ? `<div class="prediction-score-row">
                    <span class="prediction-score">${leftScore ?? "–"}</span>
                    <span class="prediction-score">${rightScore ?? "–"}</span>
                  </div>`
                        : ""
                    }
                  </div>
                  <div class="prediction-result-line">
                    <span class="prediction-my">Tahminin <strong>${escapeHtml(
                      prediction.label
                    )}</strong>${prediction.joker ? '<span class="joker-flag">⚡ JOKER</span>' : ""}</span>
                    ${
                      match.is_finished
                        ? predictionBadge(match, prediction)
                        : `<span class="prediction-points is-pending">${ICON.clock} Bekliyor</span>`
                    }
                  </div>
                </button>`;
              })
              .join("")}</div>`
          : errorState(
              "Henüz görünür tahmin yok",
              "Henüz bu oyuncuya ait tahmin görünmüyor."
            )
      }
      <p class="fine-print" style="margin-top:14px">Henüz oynanmamış maçlar da gösteriliyor.</p>
    `;
  }

  function renderResults() {
    const finished = state.data.matches
      .filter((match) => match.is_finished)
      .sort((a, b) => b.kickoff.localeCompare(a.kickoff));
    el.resultsMeta.innerHTML = `<span>${finished.length} biten maç</span>`;
    if (!finished.length) {
      el.resultsContent.innerHTML = errorState(
        "Henüz biten maç yok",
        "Maçlar tamamlandıkça sonuçlar burada listelenir."
      );
      return;
    }

    const groups = new Map();
    for (const match of finished) {
      const key = matchDate(match);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(match);
    }
    const player = selectedPlayer();

    el.resultsContent.innerHTML = `<div class="results-list">${[...groups.entries()]
      .map(
        ([key, matches]) => `<section class="result-day">
          <header class="result-day-head"><strong>${escapeHtml(
            relativeDayLabel(key)
          )}</strong><span>${matches.length} maç</span></header>
          ${matches
            .map((match) => {
              const prediction = player ? predictionFor(match, player.id) : null;
              let pointsHtml = '<span class="fine-print">–</span>';
              if (prediction) {
                pointsHtml = predictionBadge(match, prediction);
              } else if (player) {
                pointsHtml = '<span class="prediction-points is-miss">Tahmin yok</span>';
              }
              return `<button class="result-row" type="button" data-match-id="${
                match.id
              }">
                <span class="result-comp">
                  ${compBadge(match.competition)}
                  <span class="result-teams">
                    <span class="team-name">${escapeHtml(match.home.short)}</span>
                    <span class="score">${match.score.home}–${match.score.away}</span>
                    <span class="team-name">${escapeHtml(match.away.short)}</span>
                  </span>
                </span>
                <span class="result-time">${clock(match.kickoff)}<br>${escapeHtml(
                match.competition.code
              )}</span>
                <span class="result-points">${pointsHtml}</span>
                <span class="match-chevron">${ICON.chevron}</span>
              </button>`;
            })
            .join("")}
        </section>`
      )
      .join("")}</div>`;
  }

  function errorState(title, description, retry = false, actionHtml = "") {
    return `<div class="empty-state">
      <span class="empty-icon">${ICON.ball}</span>
      <h2>${escapeHtml(title)}</h2>
      <p>${escapeHtml(description)}</p>
      ${
        retry
          ? '<button class="primary-button" type="button" id="retryLoadBtn">Tekrar dene</button>'
          : actionHtml
      }
    </div>`;
  }

  function openMatch(matchId) {
    const match = state.data?.matches.find(
      (item) => String(item.id) === String(matchId)
    );
    if (!match) return;
    const player = selectedPlayer();
    const statusText = match.is_live
      ? `CANLI${match.minute ? ` · ${match.minute}'` : ""}`
      : match.is_finished
      ? "BİTTİ"
      : match.status === "POSTPONED"
      ? "ERTELENDİ"
      : match.status === "CANCELLED"
      ? "İPTAL"
      : formatSheetDate(match.kickoff);
    const scoreHome = match.score.home ?? "–";
    const scoreAway = match.score.away ?? "–";

    let predictionsHtml = "";
    if (match.predictions_visible) {
      if (match.predictions.length) {
        predictionsHtml = `<div class="sheet-predictions">${match.predictions
          .map((prediction) => {
            const isMe = String(prediction.player_id) === String(state.selectedPlayer);
            let points = "";
            if (match.is_finished) {
              const pointsValue = prediction.points ?? 0;
              const cls = prediction.correct_outcome
                ? "is-hit"
                : "is-miss";
              points = `<span class="prediction-points ${cls} sheet-pred-points">${
                pointsValue > 0 ? "+" : ""
              }${pointsValue}</span>`;
            } else {
              points = `<span class="prediction-points is-pending sheet-pred-points">CANLI</span>`;
            }
            return `<div class="sheet-prediction-row${isMe ? " is-me" : ""}">
              ${avatar(
                { color: prediction.color, initials: prediction.initials },
                "is-sm"
              )}
              <span class="sheet-player"><span>${escapeHtml(prediction.name)}</span>${
              isMe ? '<span class="me-tag">SEN</span>' : ""
            }</span>
              <span class="sheet-pred-score${prediction.joker ? " is-joker" : ""}">${escapeHtml(
              prediction.label
            )}${prediction.joker ? " ⚡" : ""}</span>
              ${points}
            </div>`;
          })
          .join("")}</div>`;
        if (match.is_finished) {
          predictionsHtml += `<div class="sheet-legend">
            <span><i class="legend-dot is-hit"></i> Doğru sonuç</span>
            <span><i class="legend-dot is-zero"></i> Isabet yok</span>
            <span>⚡ Joker</span>
          </div>`;
        }
      } else {
        predictionsHtml = `<div class="card-empty"><strong>Henüz tahmin yok</strong>Bu maça tahmin girilmemiş.</div>`;
      }
    } else {
      predictionsHtml = `<div class="sheet-locked">${ICON.lock}<span>Tahminler maç başlayınca açılır. Şu ana kadar <strong>${
        match.prediction_count
      }</strong> tahmin girildi.</span></div>`;
    }

    el.sheetContent.innerHTML = `
      <h2 id="sheetTitle" class="sr-only">${escapeHtml(match.home.name)} - ${escapeHtml(
      match.away.name
    )}</h2>
      <div class="sheet-comp">${compBadge(match.competition)}<span>${escapeHtml(
      match.competition.name
    )}</span><span>·</span><span>${escapeHtml(fullDate(match.kickoff))} · ${clock(
      match.kickoff
    )}</span></div>
      <div class="sheet-scoreboard">
        <div class="sheet-team">
          ${crest(match.home)}
          <span class="sheet-team-name">${escapeHtml(match.home.name)}</span>
          ${teamForm(match.home)}
        </div>
        <div class="sheet-score">
          <strong class="${match.is_live ? "is-live" : ""}">${scoreHome}–${scoreAway}</strong>
          <span class="sheet-status ${match.is_live ? "is-live" : ""} ${
      match.is_finished ? "is-finished" : ""
    }">${escapeHtml(statusText)}</span>
        </div>
        <div class="sheet-team">
          ${crest(match.away)}
          <span class="sheet-team-name">${escapeHtml(match.away.name)}</span>
          ${teamForm(match.away)}
        </div>
      </div>
      <div class="sheet-section-title">
        <h3>Tahminler</h3>
        <span>${match.prediction_count} oyuncu tahmin verdi</span>
      </div>
      ${predictionsHtml}
    `;

    state.lastFocus = document.activeElement;
    el.sheetLayer.classList.remove("is-hidden");
    el.sheetLayer.setAttribute("aria-hidden", "false");
    document.body.classList.add("has-sheet");
    requestAnimationFrame(() => {
      const sheet = el.sheetLayer.querySelector(".match-sheet");
      sheet?.focus();
      sheet?.scrollTo({ top: 0 });
    });
  }

  function formatSheetDate(iso) {
    const date = parseDate(iso);
    if (!date) return "";
    return formatter({
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }

  function closeSheet() {
    el.sheetLayer.classList.add("is-hidden");
    el.sheetLayer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("has-sheet");
    if (state.lastFocus && typeof state.lastFocus.focus === "function") {
      state.lastFocus.focus();
    }
    state.lastFocus = null;
  }

  function setSelectedPlayer(playerId, { notify = true } = {}) {
    const player = state.data?.players.find(
      (item) => String(item.id) === String(playerId)
    );
    if (!player) return;
    state.selectedPlayer = String(player.id);
    state.identityPrompt = false;
    closeIdentityGate();
    renderStandings();
    renderPredictions();
    renderResults();
    if (notify) showToast(`${player.name} olarak görüntülüyorsun.`);
  }

  async function sharePage() {
    const shareData = {
      title: document.title,
      text: "Tahmin Ligi — fikstür, tahminler ve puan tablosu",
      url: window.location.href,
    };
    try {
      if (navigator.share) {
        await navigator.share(shareData);
        return;
      }
      await navigator.clipboard.writeText(window.location.href);
      showToast("Bağlantı kopyalandı.");
    } catch (error) {
      if (error?.name === "AbortError") return;
      window.prompt("Bağlantıyı kopyalayın:", window.location.href);
    }
  }

  el.refreshBtn.addEventListener("click", () => {
    loadData().then(() => showToast("Veriler yenilendi."));
  });

  el.shareBtn.addEventListener("click", sharePage);

  el.statusFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-status]");
    if (!button) return;
    state.status = button.dataset.status;
    renderStatusFilters();
    renderFixtures();
  });

  el.competitionFilter.addEventListener("change", () => {
    state.competition = el.competitionFilter.value;
    renderFixtures();
  });

  el.dateStrip.addEventListener("click", (event) => {
    const button = event.target.closest("[data-date]");
    if (!button) return;
    state.selectedDate = button.dataset.date;
    renderDateStrip();
    renderFixtures();
  });

  document.addEventListener("click", (event) => {
    const matchTarget = event.target.closest("[data-match-id]");
    if (matchTarget) {
      openMatch(matchTarget.dataset.matchId);
      return;
    }
    const playerTarget = event.target.closest("[data-open-player]");
    if (playerTarget) {
      setSelectedPlayer(playerTarget.dataset.openPlayer);
      return;
    }
    const dateTarget = event.target.closest("[data-goto-date]");
    if (dateTarget) {
      state.selectedDate = dateTarget.dataset.gotoDate;
      renderDateStrip();
      renderFixtures();
      return;
    }
    if (event.target.closest("#retryLoadBtn")) {
      loadData();
      return;
    }
    if (event.target.closest("[data-close-sheet]")) {
      closeSheet();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !el.sheetLayer.classList.contains("is-hidden")) {
      closeSheet();
    }
  });

  window.addEventListener("hashchange", () => {
    setView(routeFromHash(), { updateHash: false });
  });

  document.addEventListener("visibilitychange", () => {
    if (
      document.visibilityState === "visible" &&
      Date.now() - state.lastLoadAt > AUTO_REFRESH_MS - 10_000
    ) {
      loadData({ silent: true });
    }
  });

  window.setInterval(() => {
    if (document.visibilityState === "visible") loadData({ silent: true });
  }, AUTO_REFRESH_MS);

  state.view = routeFromHash();
  setView(state.view, { updateHash: false, scroll: false });
  renderStatusFilters();
  loadData();
})();
