(() => {
  "use strict";

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const VIEW_TITLES = {
    predictions: "Tahminler",
    players: "Oyuncular",
    scoring: "Puanlama",
    data: "Veri kaynağı",
  };
  const STATUS_LABELS = {
    POSTPONED: "Ertelendi",
    CANCELLED: "İptal",
    SUSPENDED: "Askıda",
  };

  const state = {
    data: null,
    playerId: null,
    filter: "open",
    view: "predictions",
    saving: false,
    toastTimer: null,
  };

  const el = {
    title: document.getElementById("adminTitle"),
    updated: document.getElementById("adminUpdated"),
    sourceBadge: document.getElementById("adminSourceBadge"),
    playerSelect: document.getElementById("adminPlayerSelect"),
    matchFilter: document.getElementById("adminMatchFilter"),
    openMatchCount: document.getElementById("openMatchCount"),
    editor: document.getElementById("predictionEditor"),
    form: document.getElementById("predictionForm"),
    saveBtn: document.getElementById("savePredictionsBtn"),
    dirtyCount: document.getElementById("dirtyCount"),
    playerList: document.getElementById("playerList"),
    playerCount: document.getElementById("playerCount"),
    addPlayerForm: document.getElementById("addPlayerForm"),
    newPlayerName: document.getElementById("newPlayerName"),
    newPlayerColor: document.getElementById("newPlayerColor"),
    scoringForm: document.getElementById("scoringForm"),
    scoringStatus: document.getElementById("scoringStatus"),
    scoringLabel: document.getElementById("scoringLabel"),
    exactScore: document.getElementById("exactScore"),
    correctOutcome: document.getElementById("correctOutcome"),
    goalDifference: document.getElementById("goalDifference"),
    jokerMultiplier: document.getElementById("jokerMultiplier"),
    scoringStatusBadge: document.getElementById("scoringStatusBadge"),
    syncStatus: document.getElementById("syncStatus"),
    syncNowBtn: document.getElementById("syncNowBtn"),
    toast: document.getElementById("adminToast"),
  };

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

  function timezone() {
    return state.data?.meta?.timezone || "Europe/Istanbul";
  }

  function dateParser(iso) {
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function fmt(iso, options) {
    const date = dateParser(iso);
    if (!date) return "";
    return new Intl.DateTimeFormat("tr-TR", {
      timeZone: timezone(),
      ...options,
    }).format(date);
  }

  function clock(iso) {
    return fmt(iso, { hour: "2-digit", minute: "2-digit", hour12: false }) || "--:--";
  }

  function dayKey(iso) {
    const date = dateParser(iso);
    if (!date) return "";
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone(),
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }

  function dayLabel(key) {
    const [year, month, day] = key.split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day, 12));
    const today = new Date();
    const todayKey = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone(),
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(today);
    if (key === todayKey) return "Bugün";
    return new Intl.DateTimeFormat("tr-TR", {
      timeZone: "UTC",
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(date);
  }

  function showToast(message, isError = false) {
    el.toast.textContent = message;
    el.toast.classList.toggle("is-error", isError);
    el.toast.classList.add("is-visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      el.toast.classList.remove("is-visible");
    }, isError ? 4200 : 2600);
  }

  async function api(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.body) headers["Content-Type"] = "application/json";
    if (method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = csrfToken;

    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      method,
      headers,
    });

    if (response.status === 401) {
      window.location.href = "/admin/login";
      throw new Error("Oturum sona erdi.");
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      throw new Error(payload?.error || `İşlem başarısız (HTTP ${response.status}).`);
    }
    if (payload && payload.ok === false) {
      throw new Error(payload.error || "İşlem başarısız.");
    }
    return payload;
  }

  async function load({ silent = false } = {}) {
    if (!silent) {
      el.editor.innerHTML = '<div class="card"><p class="fine-print">Yükleniyor…</p></div>';
    }
    try {
      const data = await api("/admin/api/bootstrap");
      state.data = data;
      if (
        !state.playerId ||
        !data.players.some((player) => String(player.id) === String(state.playerId))
      ) {
        const active = data.players.find((player) => player.active);
        state.playerId = active ? String(active.id) : data.players[0] ? String(data.players[0].id) : null;
      }
      hydrate();
    } catch (error) {
      showToast(error.message, true);
      throw error;
    }
  }

  function hydrate() {
    if (!state.data) return;
    const { meta } = state.data;

    el.updated.textContent = meta.generated_at
      ? `Güncelleme ${clock(meta.generated_at)}`
      : "";
    el.sourceBadge.textContent = meta.demo ? "DEMO VERİ" : "CANLI VERİ";
    el.sourceBadge.classList.toggle("is-live", !meta.demo);

    renderPlayerSelect();
    renderScoring();
    renderPlayers();
    renderEditor();
    renderSync();
  }

  function renderPlayerSelect() {
    const players = state.data.players;
    el.playerSelect.innerHTML = players.length
      ? players
          .map(
            (player) =>
              `<option value="${escapeHtml(player.id)}">${escapeHtml(player.name)}${
                player.active ? "" : " (pasif)"
              }</option>`
          )
          .join("")
      : '<option value="">Oyuncu yok</option>';
    el.playerSelect.value = state.playerId || "";
    el.playerSelect.disabled = players.length === 0;
  }

  function currentPlayer() {
    return state.data?.players.find((player) => String(player.id) === String(state.playerId)) || null;
  }

  function baselineFor(match) {
    return state.data.predictions[`${state.playerId}:${match.id}`] || null;
  }

  function visibleMatches() {
    const matches = state.data.matches || [];
    const filtered =
      state.filter === "open" ? matches.filter((match) => !match.locked) : matches;
    return [...filtered].sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  }

  function statusShort(match) {
    if (STATUS_LABELS[match.status]) return STATUS_LABELS[match.status];
    if (match.is_live) return match.minute ? `${match.minute}' CANLI` : "CANLI";
    if (match.is_finished) {
      const home = match.score.home ?? "–";
      const away = match.score.away ?? "–";
      return `MS ${home}-${away}`;
    }
    return "Yaklaşan";
  }

  function renderEditor() {
    const player = currentPlayer();
    const matches = visibleMatches();
    const openCount = state.data.matches.filter((match) => !match.locked).length;
    el.openMatchCount.textContent = String(openCount);

    if (!player) {
      el.editor.innerHTML = emptyState(
        "Önce oyuncu ekleyin",
        "Tahmin girmek için yönetici panelinden bir oyuncu oluşturun."
      );
      updateDirtyState();
      return;
    }

    if (!matches.length) {
      el.editor.innerHTML = emptyState(
        state.filter === "open" ? "Tahmine açık maç yok" : "Maç bulunamadı",
        state.filter === "open"
          ? "Tüm maçlar başlamış olabilir. “Tüm maçlar” görünümünden geçmiş tahminleri inceleyebilirsiniz."
          : "Veri kaynağından maç gelmesini bekleyin veya senkronizasyonu çalıştırın."
      );
      updateDirtyState();
      return;
    }

    const groups = new Map();
    for (const match of matches) {
      const key = dayKey(match.kickoff);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(match);
    }

    el.editor.innerHTML = [...groups.entries()]
      .map(([key, groupMatches]) => {
        const lockedCount = groupMatches.filter((match) => match.locked).length;
        return `<section class="editor-day">
          <header class="editor-day-head">
            <strong>${escapeHtml(dayLabel(key))}</strong>
            <span>${groupMatches.length} maç${lockedCount ? ` · ${lockedCount} kilitli` : ""}</span>
          </header>
          ${groupMatches.map(editorRow).join("")}
        </section>`;
      })
      .join("");

    updateDirtyState();
  }

  function editorRow(match) {
    const baseline = baselineFor(match);
    const outcomeValue = baseline?.outcome ? String(baseline.outcome) : "";
    const joker = Boolean(baseline?.joker);
    const disabled = match.locked ? " disabled" : "";
    const classes = [
      "editor-row",
      match.locked ? "is-locked" : "",
      match.is_live ? "is-live" : "",
    ]
      .filter(Boolean)
      .join(" ");
    const options = [
      ["", "–"],
      ["H", `${match.home.short} yener`],
      ["D", "Beraberlik"],
      ["A", `${match.away.short} yener`],
    ]
      .map(
        ([value, label]) =>
          `<option value="${value}"${
            value === outcomeValue ? " selected" : ""
          }>${escapeHtml(label)}</option>`
      )
      .join("");

    return `<div class="${classes}" data-editor-match="${match.id}"
        data-baseline-outcome="${escapeHtml(outcomeValue)}"
        data-baseline-joker="${joker ? "1" : "0"}">
      <span class="editor-time">
        <strong>${clock(match.kickoff)}</strong>
        <small>${escapeHtml(statusShort(match))}</small>
      </span>
      <span class="editor-comp">${escapeHtml(match.competition_code)}</span>
      <span class="editor-teams">
        <span title="${escapeHtml(match.home.name)}">${escapeHtml(match.home.short)}</span>
        <span title="${escapeHtml(match.away.name)}">${escapeHtml(match.away.short)}</span>
      </span>
      <span class="score-inputs">
        <select data-outcome aria-label="Tahmin"${disabled}>
          ${options}
        </select>
      </span>
      <label class="joker-toggle${joker ? " is-checked" : ""}" title="Joker (puan ×${escapeHtml(
        state.data.meta.scoring.joker_multiplier
      )})">
        <span aria-hidden="true">⚡</span>
        <input type="checkbox" data-joker${joker ? " checked" : ""}${disabled}
          aria-label="Joker işaretle">
      </label>
    </div>`;
  }

  function emptyState(title, description) {
    return `<div class="card"><div class="card-heading"><div><p class="eyebrow">Tahmin editörü</p><h2>${escapeHtml(
      title
    )}</h2></div></div><p class="fine-print">${escapeHtml(description)}</p></div>`;
  }

  function rowIsDirty(row) {
    const outcome = row.querySelector("[data-outcome]");
    const joker = row.querySelector("[data-joker]");
    const base = {
      outcome: row.dataset.baselineOutcome || "",
      joker: row.dataset.baselineJoker === "1",
    };
    return (
      outcome.value.trim() !== base.outcome ||
      Boolean(joker.checked) !== base.joker
    );
  }

  function dirtyRows() {
    return [...el.editor.querySelectorAll("[data-editor-match]")].filter(rowIsDirty);
  }

  function updateDirtyState() {
    const rows = [...el.editor.querySelectorAll("[data-editor-match]")];
    let dirty = 0;
    for (const row of rows) {
      const isDirty = rowIsDirty(row);
      row.classList.toggle("is-dirty", isDirty);
      if (isDirty) dirty += 1;
      const toggle = row.querySelector(".joker-toggle");
      const checkbox = row.querySelector("[data-joker]");
      if (toggle && checkbox) toggle.classList.toggle("is-checked", checkbox.checked);
    }

    const saveBar = el.saveBtn.closest(".save-bar");
    saveBar?.classList.toggle("is-dirty", dirty > 0);
    el.dirtyCount.textContent = dirty
      ? `${dirty} maçta kaydedilmemiş değişiklik`
      : "Değişiklik yok";
    el.saveBtn.disabled = dirty === 0 || state.saving;
    el.saveBtn.textContent = state.saving ? "Kaydediliyor…" : "Değişiklikleri kaydet";
  }

  async function savePredictions(event) {
    event.preventDefault();
    if (state.saving) return;
    const player = currentPlayer();
    if (!player) {
      showToast("Önce bir oyuncu seçin.", true);
      return;
    }

    const items = [];
    for (const row of dirtyRows()) {
      const matchId = Number(row.dataset.editorMatch);
      const outcome = row.querySelector("[data-outcome]").value.trim();
      const joker = row.querySelector("[data-joker]").checked;

      if (!outcome) {
        items.push({ match_id: matchId });
        continue;
      }
      items.push({ match_id: matchId, outcome, joker });
    }

    if (!items.length) {
      showToast("Kaydedilecek değişiklik yok.");
      return;
    }

    state.saving = true;
    updateDirtyState();
    try {
      const result = await api("/admin/api/predictions", {
        method: "PUT",
        body: JSON.stringify({ player_id: Number(player.id), items }),
      });
      showToast(`${result.saved || items.length} tahmin kaydedildi.`);
      await load({ silent: true });
    } catch (error) {
      showToast(error.message, true);
    } finally {
      state.saving = false;
      updateDirtyState();
    }
  }

  function renderPlayers() {
    const players = state.data.players;
    el.playerCount.textContent = `${players.length} oyuncu`;
    if (!players.length) {
      el.playerList.innerHTML = '<p class="fine-print">Henüz oyuncu eklenmedi.</p>';
      return;
    }
    el.playerList.innerHTML = players
      .map((player) => {
        const initials = (player.name || "?")
          .trim()
          .split(/\s+/)
          .map((part) => part[0])
          .slice(0, 2)
          .join("")
          .toUpperCase();
        return `<div class="player-admin-row${player.active ? "" : " is-inactive"}">
          <span class="player-swatch" style="--swatch:${safeColor(player.color)}">${escapeHtml(
            initials
          )}</span>
          <span class="player-admin-name">
            <strong>${escapeHtml(player.name)}</strong>
            <small>${player.active ? "Aktif" : "Pasif"} · ${player.id}</small>
          </span>
          <button class="ghost-button${player.active ? " is-danger" : ""}" type="button"
            data-toggle-player="${player.id}" data-active="${player.active ? "1" : "0"}">
            ${player.active ? "Pasif yap" : "Aktifleştir"}
          </button>
        </div>`;
      })
      .join("");
  }

  async function togglePlayer(button) {
    const playerId = Number(button.dataset.togglePlayer);
    const active = button.dataset.active === "1";
    button.disabled = true;
    try {
      await api(`/admin/api/players/${playerId}`, {
        method: "PATCH",
        body: JSON.stringify({ active: !active }),
      });
      showToast(active ? "Oyuncu pasifleştirildi." : "Oyuncu aktifleştirildi.");
      await load({ silent: true });
    } catch (error) {
      showToast(error.message, true);
      button.disabled = false;
    }
  }

  async function addPlayer(event) {
    event.preventDefault();
    const name = el.newPlayerName.value.trim();
    if (name.length < 2) {
      showToast("Oyuncu adı en az 2 karakter olmalı.", true);
      return;
    }
    const submit = el.addPlayerForm.querySelector("button[type=submit]");
    submit.disabled = true;
    try {
      const result = await api("/admin/api/players", {
        method: "POST",
        body: JSON.stringify({ name, color: el.newPlayerColor.value }),
      });
      showToast(`${result.player.name} eklendi.`);
      el.addPlayerForm.reset();
      el.newPlayerColor.value = "#b8f34a";
      await load({ silent: true });
      state.playerId = String(result.player.id);
      renderPlayerSelect();
      renderEditor();
    } catch (error) {
      showToast(error.message, true);
    } finally {
      submit.disabled = false;
    }
  }

  function renderScoring() {
    const scoring = state.data.meta.scoring;
    el.scoringStatus.value = scoring.status;
    el.scoringLabel.value = scoring.label;
    el.exactScore.value = scoring.exact_score;
    el.correctOutcome.value = scoring.correct_outcome;
    el.goalDifference.value = scoring.goal_difference_bonus;
    el.jokerMultiplier.value = scoring.joker_multiplier;
    el.scoringStatusBadge.textContent =
      scoring.status === "final" ? "Kesinleşti" : "Geçici";
    el.scoringStatusBadge.classList.toggle("is-live", scoring.status === "final");
  }

  async function saveScoring(event) {
    event.preventDefault();
    const body = {
      status: el.scoringStatus.value,
      label: el.scoringLabel.value.trim() || "Geçici puanlama",
      exact_score: Number(el.exactScore.value),
      correct_outcome: Number(el.correctOutcome.value),
      goal_difference_bonus: Number(el.goalDifference.value),
      joker_multiplier: Number(el.jokerMultiplier.value),
    };
    const values = [
      body.exact_score,
      body.correct_outcome,
      body.goal_difference_bonus,
      body.joker_multiplier,
    ];
    if (values.some((value) => !Number.isInteger(value) || value < 0 || value > 100)) {
      showToast("Puan değerleri 0 ile 100 arasında tam sayı olmalı.", true);
      return;
    }
    const submit = el.scoringForm.querySelector("button[type=submit]");
    submit.disabled = true;
    try {
      await api("/admin/api/scoring", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      showToast("Puanlama güncellendi. Puan tablosu yeniden hesaplandı.");
      await load({ silent: true });
    } catch (error) {
      showToast(error.message, true);
    } finally {
      submit.disabled = false;
    }
  }

  function renderSync() {
    const sync = state.data.meta.sync || {};
    const demo = state.data.meta.demo;
    el.syncStatus.innerHTML = `
      <div class="sync-stat"><span>Sağlayıcı</span><strong>${escapeHtml(
        demo ? "Demo" : sync.provider || "Bilinmiyor"
      )}</strong></div>
      <div class="sync-stat"><span>Son deneme</span><strong>${
        sync.last_attempt_at ? escapeHtml(clock(sync.last_attempt_at)) : "—"
      }</strong></div>
      <div class="sync-stat"><span>Son başarılı</span><strong>${
        sync.last_success_at ? escapeHtml(clock(sync.last_success_at)) : "—"
      }</strong></div>
      <div class="sync-stat"><span>Maç sayısı</span><strong>${escapeHtml(
        sync.matches_seen ?? 0
      )}</strong></div>
    `;
    if (sync.last_error) {
      el.syncStatus.innerHTML += `<div class="sync-error">Son hata: ${escapeHtml(
        sync.last_error
      )}</div>`;
    }
  }

  async function syncNow() {
    el.syncNowBtn.disabled = true;
    el.syncNowBtn.textContent = "Senkronize ediliyor…";
    try {
      const result = await api("/admin/api/sync", { method: "POST" });
      if (result.demo) {
        showToast("Demo verisi hazır.");
      } else {
        showToast(
          `Senkronizasyon tamam: ${result.matches_seen ?? 0} maç, ${
            result.changed ?? 0
          } değişiklik.`
        );
      }
      await load({ silent: true });
    } catch (error) {
      showToast(error.message, true);
      await load({ silent: true }).catch(() => {});
    } finally {
      el.syncNowBtn.disabled = false;
      el.syncNowBtn.textContent = "Şimdi senkronize et";
    }
  }

  function setView(view) {
    if (!VIEW_TITLES[view]) view = "predictions";
    state.view = view;
    document.querySelectorAll("[data-admin-view]").forEach((button) => {
      const active = button.dataset.adminView === view;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    document.querySelectorAll("[data-admin-panel]").forEach((panel) => {
      panel.classList.toggle("is-hidden", panel.dataset.adminPanel !== view);
    });
    el.title.textContent = VIEW_TITLES[view];
    if (window.location.hash !== `#${view}`) {
      history.replaceState(null, "", `#${view}`);
    }
  }

  function switchPlayer(playerId) {
    if (!playerId) return;
    if (dirtyRows().length) {
      const confirmed = window.confirm(
        "Kaydedilmemiş tahmin değişiklikleri var. Oyuncu değiştirilsin mi?"
      );
      if (!confirmed) {
        el.playerSelect.value = state.playerId || "";
        return;
      }
    }
    state.playerId = playerId;
    renderEditor();
  }

  el.playerSelect.addEventListener("change", () => switchPlayer(el.playerSelect.value));

  el.matchFilter.addEventListener("change", () => {
    if (dirtyRows().length) {
      const confirmed = window.confirm(
        "Kaydedilmemiş tahmin değişiklikleri var. Görünüm değiştirilsin mi?"
      );
      if (!confirmed) {
        el.matchFilter.value = state.filter;
        return;
      }
    }
    state.filter = el.matchFilter.value;
    renderEditor();
  });

  el.form.addEventListener("submit", savePredictions);

  el.editor.addEventListener("input", (event) => {
    if (event.target.closest("[data-editor-match]")) updateDirtyState();
  });

  el.editor.addEventListener("change", (event) => {
    if (event.target.closest("[data-editor-match]")) updateDirtyState();
  });

  el.addPlayerForm.addEventListener("submit", addPlayer);

  el.playerList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-toggle-player]");
    if (button) togglePlayer(button);
  });

  el.scoringForm.addEventListener("submit", saveScoring);

  el.syncNowBtn.addEventListener("click", syncNow);

  document.querySelectorAll("[data-admin-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.adminView));
  });

  window.addEventListener("hashchange", () => {
    const view = window.location.hash.replace("#", "");
    setView(view in VIEW_TITLES ? view : "predictions");
  });

  window.addEventListener("beforeunload", (event) => {
    if (dirtyRows().length) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  const initialView = window.location.hash.replace("#", "");
  setView(initialView in VIEW_TITLES ? initialView : "predictions");

  load().catch(() => {
    el.editor.innerHTML = emptyState(
      "Veriler yüklenemedi",
      "Sayfayı yenileyin. Sorun sürerse oturumu kapatıp tekrar giriş yapın."
    );
  });
})();
