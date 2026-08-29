/* Stormy-Pulse WebUI player logic.
 * The browser <audio> element owns the playback clock; the backend renders
 * deterministic frames for the current timestamp on demand. */

const $ = (id) => document.getElementById(id);
const audio = $("player");
const stage = $("stage");

const state = {
  ready: false,
  analyzing: false,
  duration: 0,
  system: null,
  lastAudioFile: null,
  inflight: false,
  scrubbing: false,
  audioRetried: false,
  fps: { n: 0, t: performance.now(), label: "" },
  paramTimer: null,
  pollTimer: null,
  objectUrl: null,
};

const FAMILY_LABELS = {
  auto: "自动（跟随曲目 DNA）",
  amber_ignition: "琥珀余烬 Amber",
  royal_amethyst: "皇家紫晶 Amethyst",
  emerald_dusk: "翡翠暮色 Emerald",
  rose_nebula: "玫瑰星云 Rose",
  obsidian_gold: "黑曜鎏金 Obsidian",
  midnight_depth: "午夜深海 Midnight",
  aurora_teal: "极光青 Aurora",
  cyberpunk_neon: "赛博霓虹 Cyberpunk",
};

const PRESET_MAP = {
  amf: [["quality", "quality"], ["balanced", "balanced"], ["speed", "speed"]],
  av1_amf: [["high_quality", "high_quality"], ["quality", "quality"], ["balanced", "balanced"], ["speed", "speed"]],
  nvenc: [["p1", "p1"], ["p2", "p2"], ["p3", "p3"], ["p4", "p4"], ["p5", "p5"], ["p6", "p6 (推荐)"], ["p7", "p7"]],
  qsv: [["veryfast", "veryfast"], ["faster", "faster"], ["fast", "fast"], ["medium", "medium (推荐)"], ["slow", "slow"], ["slower", "slower"], ["veryslow", "veryslow"]],
  cpu: [["high_quality", "high_quality (极慢)"], ["quality", "quality (推荐)"], ["balanced", "balanced"], ["speed", "speed (快)"]],
};

function presetListFor(codec) {
  if (codec === "av1_amf") return PRESET_MAP.av1_amf;
  if (codec.endsWith("_amf")) return PRESET_MAP.amf;
  if (codec.endsWith("_nvenc")) return PRESET_MAP.nvenc;
  if (codec.endsWith("_qsv")) return PRESET_MAP.qsv;
  return PRESET_MAP.cpu;
}

/* ------------------------------------------------------------------ */
/* UI helpers                                                          */
/* ------------------------------------------------------------------ */
function fmtTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function showError(msg) {
  const box = $("errorBox");
  box.textContent = msg;
  box.classList.toggle("hidden", !msg);
}

function setHint(msg) {
  $("stageHint").textContent = msg;
  $("stageHint").classList.toggle("hidden", !msg);
}

function fillSelect(sel, pairs, value) {
  sel.innerHTML = "";
  for (const [val, label] of pairs) {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = label;
    sel.appendChild(opt);
  }
  if (value !== undefined) sel.value = value;
}

/* ------------------------------------------------------------------ */
/* Params: collect from controls / push to server                      */
/* ------------------------------------------------------------------ */
const PARAM_IDS = [
  "structure", "palette_family", "hue_shift", "energy", "chaos", "brightness",
  "aspect", "frame_height",
  "custom_title", "custom_artist",
  "show_title", "show_artist", "title_scale", "title_x", "title_y",
  "artist_scale", "artist_x", "artist_y",
  "show_lyrics", "lyrics_scale", "lyrics_x", "lyrics_y",
  "show_left_hud", "show_right_hud", "hud_scale", "effect_scale",
];

const NUMERIC_PARAMS = new Set([
  "frame_height", "hue_shift", "energy", "chaos", "brightness",
  "title_scale", "title_x", "title_y", "artist_scale", "artist_x", "artist_y",
  "lyrics_scale", "lyrics_x", "lyrics_y", "hud_scale", "effect_scale",
]);

function readParamControl(id) {
  const el = $("p_" + id);
  if (!el) return undefined;
  if (el.type === "checkbox") return el.checked;
  if (el.tagName === "SELECT") {
    return NUMERIC_PARAMS.has(id) ? parseFloat(el.value) : el.value;
  }
  if (el.type === "range" || el.type === "number") return parseFloat(el.value);
  return el.value;
}

function writeParamControl(id, value) {
  const el = $("p_" + id);
  if (!el || value === undefined || value === null) return;
  if (el.type === "checkbox") el.checked = !!value;
  else el.value = value;
}

function collectParams() {
  const out = {};
  for (const id of PARAM_IDS) out[id] = readParamControl(id);
  return out;
}

function pushParams(immediate = false) {
  clearTimeout(state.paramTimer);
  const send = async () => {
    const body = collectParams();
    try {
      await fetch("/api/params", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      updateHueLabel();
      if (!state.analyzing && state.ready && audio.paused) grabFrame(audio.currentTime);
    } catch (e) { /* transient network hiccup; next edit retries */ }
  };
  if (immediate) send();
  else state.paramTimer = setTimeout(send, 160);
}

function updateHueLabel() {
  $("v_hue_shift").textContent = `${Math.round($("p_hue_shift").value)}°`;
}

function syncParamsFromServer(params) {
  for (const id of PARAM_IDS) writeParamControl(id, params[id]);
  updateHueLabel();
  $("p_palette_family").value = params.palette_family;
}

/* ------------------------------------------------------------------ */
/* Frame pump                                                          */
/* ------------------------------------------------------------------ */
async function grabFrame(t, extra = {}) {
  try {
    const qs = new URLSearchParams({ t: t.toFixed(3), ...extra });
    const res = await fetch(`/api/frame?${qs}`, { cache: "no-store" });
    if (res.status === 409 || res.status === 503) return false;
    if (!res.ok) {
      $("fpsInfo").textContent = "⚠ 渲染出错";
      return false;
    }
    const at = audio.currentTime;
    // Drop only badly stale responses (single in-flight request keeps ordering).
    if (Math.abs(parseFloat(res.headers.get("X-Frame-Time") || t) - at) > 2.5 && !audio.paused) {
      return false;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const prev = state.objectUrl;
    stage.src = url;
    state.objectUrl = url;
    if (prev) URL.revokeObjectURL(prev);
    setHint("");
    const f = state.fps;
    f.n += 1;
    const now = performance.now();
    if (now - f.t >= 1000) {
      f.label = `${Math.round((f.n * 1000) / (now - f.t))} fps`;
      f.n = 0;
      f.t = now;
      $("fpsInfo").textContent = f.label;
    }
  } catch (e) {
    return false;
  }
  return true;
}

/* setTimeout chain instead of requestAnimationFrame: rAF freezes entirely in
 * background tabs, which would stall the video while audio keeps playing.
 *
 * Playback uses the continuous "live" mode where the persistent scene evolves
 * frame-by-frame exactly like the desktop player (particles accumulate, beat
 * bursts fire, the vortex keeps spinning). Paused falls into the desktop-style
 * idle drift; dragging the seek bar uses deterministic "still" scrub frames. */
function pump() {
  if (!state.ready || state.inflight || state.analyzing) { setTimeout(pump, 80); return; }
  state.inflight = true;
  const params = state.scrubbing
    ? { mode: "still" }
    : { mode: "live", playing: audio.paused ? 0 : 1 };
  grabFrame(audio.currentTime, params).then((ok) => {
    state.inflight = false;
    const idle = audio.paused && !state.scrubbing;
    // On server errors ease off instead of hammering it.
    setTimeout(pump, ok ? (idle ? 120 : 15) : 300);
  });
}
setTimeout(pump, 100);

/* ------------------------------------------------------------------ */
/* State polling (analysis + export)                                   */
/* ------------------------------------------------------------------ */
async function pollState() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    const s = await r.json();

    if (s.analyzing && !state.analyzing) beginAnalysisUI();
    if (s.analyzing) {
      $("analysisBar").style.width = `${s.progress}%`;
      $("analysisMsg").textContent = `${s.message || "分析中..."} (${s.progress}%)`;
    }
    if (s.phase === "ready" && state.analyzing) onAnalysisDone(s);
    if (s.phase === "error" && state.analyzing) onAnalysisError(s.error || "分析失败");

    syncExportUI(s.export || {});
  } catch (e) { /* server briefly unavailable */ }
}
setInterval(pollState, 700);

function beginAnalysisUI() {
  state.analyzing = true;
  state.ready = false;
  $("playBtn").disabled = true;
  $("analysisBox").classList.remove("hidden");
  $("analysisBar").style.width = "0%";
  showError("");
}

function onAnalysisDone(s) {
  state.analyzing = false;
  state.ready = true;
  $("analysisMsg").textContent = "分析完成 ✓";
  setTimeout(() => $("analysisBox").classList.add("hidden"), 1200);

  const t = s.track || {};
  $("tTitle").textContent = t.title || "未知曲目";
  $("tArtist").textContent = t.artist || "";
  $("tMeta").innerHTML = [
    `⏱ ${t.duration_str}`, `🎼 ${t.bpm} BPM`, `🎨 ${t.dna_family}`,
    `🧬 ${t.dna_structure}`, t.has_lyrics ? "📝 歌词已加载" : "",
  ].filter(Boolean).map((x) => `<span>${x}</span>`).join("");
  $("trackCard").classList.remove("hidden");

  syncParamsFromServer(s.params || {});
  fillSelect($("p_palette_family"),
    [["auto", FAMILY_LABELS.auto], ...Object.entries(FAMILY_LABELS).filter(([k]) => k !== "auto")],
    s.params?.palette_family || "auto");

  setAudioSource();
  $("playBtn").disabled = false;
  $("seekBar").disabled = false;
  $("clipBtn").disabled = false;
  $("exportBtn").disabled = false;
  setHint("点击 ▶ 开始实时播放渲染");
  grabFrame(0);
}

function onAnalysisError(err) {
  state.analyzing = false;
  $("analysisBox").classList.add("hidden");
  showError(`❌ ${err}`);
  setHint("上传音频后将自动分析，点击 ▶ 开始实时播放");
}

/* ------------------------------------------------------------------ */
/* Export                                                              */
/* ------------------------------------------------------------------ */
function syncExportUI(exp) {
  if (!exp || !exp.phase) return;
  const box = $("exportBox");
  if (exp.phase === "idle") { box.classList.add("hidden"); $("cancelExportBtn").classList.add("hidden"); return; }
  box.classList.remove("hidden");
  $("exportBar").style.width = `${exp.progress || 0}%`;
  $("exportMsg").textContent = `${exp.message || ""} ${exp.progress ? "(" + exp.progress + "%)" : ""}`;
  const link = $("exportLink");
  const cancelBtn = $("cancelExportBtn");
  if (exp.phase === "done" && exp.file) {
    link.href = "/api/export/file";
    link.classList.remove("hidden");
    cancelBtn.classList.add("hidden");
    $("exportBtn").disabled = false;
    $("exportBtn").textContent = "🚀 开始全量导出视频";
  } else if (exp.phase === "error") {
    $("exportMsg").textContent = `❌ ${exp.error || "导出失败"}`;
    cancelBtn.classList.add("hidden");
    $("exportBtn").disabled = false;
    $("exportBtn").textContent = "🚀 开始全量导出视频";
  } else if (exp.phase === "cancelled") {
    $("exportMsg").textContent = `⛔ 已取消导出`;
    link.classList.add("hidden");
    cancelBtn.classList.add("hidden");
    $("exportBtn").disabled = false;
    $("exportBtn").textContent = "🚀 开始全量导出视频";
  } else if (exp.phase === "running") {
    link.classList.add("hidden");
    cancelBtn.classList.remove("hidden");
    $("exportBtn").disabled = true;
    $("exportBtn").textContent = "⏳ 正在后台导出...";
  }
}

/* ------------------------------------------------------------------ */
/* Events                                                              */
/* ------------------------------------------------------------------ */
$("audioFile").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  state.lastAudioFile = file;
  await uploadAndAnalyze(file, $("lrcFile").files[0] || null);
  ev.target.value = "";
});

$("lrcFile").addEventListener("change", async (ev) => {
  const lrc = ev.target.files[0];
  if (lrc && state.lastAudioFile) {
    await uploadAndAnalyze(state.lastAudioFile, lrc);  // re-analyze with lyrics
  }
});

async function uploadAndAnalyze(audioFile, lrcFile) {
  const fd = new FormData();
  fd.append("audio", audioFile, audioFile.name);
  if (lrcFile) fd.append("lrc", lrcFile, lrcFile.name);
  setHint("上传中...");
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    if (!r.ok) {
      const detail = (await r.json().catch(() => ({}))).detail || `上传失败 (${r.status})`;
      showError(`❌ ${detail}`);
      setHint("");
      return;
    }
    setHint("分析中，请稍候...");
    beginAnalysisUI();
  } catch (e) {
    showError(`❌ 上传失败: ${e}`);
    setHint("");
  }
}

$("playBtn").addEventListener("click", async () => {
  if (!state.ready) return;
  if (audio.paused) {
    try { await audio.play(); } catch (e) { showError(`播放失败: ${e}`); }
  } else {
    audio.pause();
  }
});

audio.addEventListener("play", () => { $("playBtn").textContent = "⏸"; });
audio.addEventListener("pause", () => {
  $("playBtn").textContent = "▶";
  grabFrame(audio.currentTime);
});
audio.addEventListener("timeupdate", () => {
  if (!state.duration) return;
  if (!seekDragging) $("seekBar").value = Math.round((audio.currentTime / state.duration) * 1000);
  $("curTime").textContent = fmtTime(audio.currentTime);
});
audio.addEventListener("durationchanged", () => {});
audio.addEventListener("loadedmetadata", () => {
  state.duration = audio.duration || 0;
  $("durTime").textContent = fmtTime(state.duration);
});
function setAudioSource(search = "") {
  state.audioRetried = search.includes("recode");
  audio.src = "/api/audio" + search;
  audio.load();
}

audio.addEventListener("error", () => {
  if (!state.ready) return;
  if (!state.audioRetried) {
    // Browser cannot decode this container/codec: ask the server for a
    // transcoded AAC sidecar once, then resume playback at the same position.
    const at = audio.currentTime;
    setAudioSource("?recode=1");
    audio.addEventListener("loadedmetadata", () => { audio.currentTime = at; }, { once: true });
    audio.play().catch(() => {});
    return;
  }
  showError("浏览器无法解码该音频格式，且自动转码失败。建议改用 mp3 / flac / wav。");
});

let seekDragging = false;
$("seekBar").addEventListener("input", () => {
  seekDragging = true;
  state.scrubbing = true;   // deterministic still frames while dragging
  $("curTime").textContent = fmtTime(($("seekBar").value / 1000) * state.duration);
});
$("seekBar").addEventListener("change", () => {
  seekDragging = false;
  state.scrubbing = false;
  if (state.duration) {
    audio.currentTime = ($("seekBar").value / 1000) * state.duration;
    grabFrame(audio.currentTime, { mode: "still" });
  }
});

$("volBar").addEventListener("input", () => { audio.volume = $("volBar").value / 100; });

/* Any param control change → push (debounced) */
for (const id of PARAM_IDS) {
  const el = $("p_" + id);
  if (el) el.addEventListener("input", () => pushParams());
}
$("p_aspect").addEventListener("change", () => pushParams(true));

/* Export panel */
$("e_codec").addEventListener("change", () => {
  const codec = $("e_codec").value;
  fillSelect($("e_preset"), presetListFor(codec), presetListFor(codec)[1][0]);
  // Desktop parity: AMF hardware encoders pair with OpenGL frame rendering.
  if (codec.endsWith("_amf") && !$("e_gpu").disabled) {
    $("e_gpu").checked = true;
  }
});

$("cancelExportBtn").addEventListener("click", async () => {
  try {
    await fetch("/api/export/cancel", { method: "POST" });
    $("cancelExportBtn").disabled = true;
    setTimeout(() => { $("cancelExportBtn").disabled = false; }, 3000);
  } catch (e) { /* transient */ }
});

/* GPU rendering parallelizes too: each worker owns its own GL context. */
$("e_gpu").addEventListener("change", () => {
  const gpu = $("e_gpu").checked;
  $("e_workers").title = gpu
    ? "GPU 并行渲染进程数：每个进程持有独立 OpenGL 上下文，同时渲染不同分段"
    : "0 为自动选择；手动指定更高进程数会提高 CPU 占用";
  $("v_workers").textContent = $("e_workers").value;
});

$("exportBtn").addEventListener("click", async () => {
  const [w, h] = $("e_res").value.split("x").map(Number);
  const body = {
    width: w, height: h,
    fps: parseInt($("e_fps").value),
    video_codec: $("e_codec").value,
    preset: $("e_preset").value,
    video_bitrate: $("e_bitrate").value,
    audio_bitrate: $("e_abitrate").value,
    cpu_render_workers: parseInt($("e_workers").value),
    use_gpu_renderer: $("e_gpu").checked,
  };
  try {
    const r = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const detail = (await r.json().catch(() => ({}))).detail || "导出启动失败";
      showError(`❌ ${detail}`);
    }
  } catch (e) { showError(`❌ 导出启动失败: ${e}`); }
});

$("clipBtn").addEventListener("click", async () => {
  if (!state.ready) return;
  $("clipBtn").disabled = true;
  $("clipBtn").textContent = "⏳ 正在渲染片段...";
  try {
    const r = await fetch("/api/clip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start: audio.currentTime, duration: 5.0, fps: 30 }),
    });
    if (r.ok) {
      const { url } = await r.json();
      $("clipVideo").src = url;
      $("clipBox").classList.remove("hidden");
      $("clipVideo").play();
    } else {
      const detail = (await r.json().catch(() => ({}))).detail || "片段生成失败";
      showError(`❌ ${detail}`);
    }
  } finally {
    $("clipBtn").disabled = false;
    $("clipBtn").textContent = "🎬 生成当前时间 5s 试看片段";
  }
});

/* ------------------------------------------------------------------ */
/* Boot                                                                */
/* ------------------------------------------------------------------ */
async function boot() {
  try {
    const r = await fetch("/api/system");
    state.system = await r.json();
    const sys = state.system.system;
    $("sysBadges").innerHTML = [
      `🖥️ ${sys.os} (${sys.architecture})`,
      `⚡ ${sys.cpu_cores} 核`,
      `💾 ${sys.ram_total_gb} GB`,
      `🎬 FFmpeg ${sys.ffmpeg_available ? "✅" : "❌"}`,
    ].map((x) => `<span class="badge">${x}</span>`).join("");

    fillSelect($("e_codec"),
      state.system.encoder_choices.map(([label, codec]) => [codec, label]),
      state.system.default_encoder);
    fillSelect($("e_preset"), presetListFor(state.system.default_encoder));

    // GPU frame-render probe (isolated child process server-side)
    fetch("/api/gpu").then(r => r.json()).then(g => {
      const box = $("e_gpu");
      if (!g.gpu_render_available) {
        box.disabled = true;
        box.checked = false;
        const reason = g.probe_detail || "未检测到可用的 OpenGL 环境";
        $("gpuRenderWrap").title = reason;
        $("gpuRenderWrap").style.opacity = ".5";
        const hint = $("gpuHint");
        hint.textContent = `GPU 渲染不可用：${reason}（服务器上可运行 uv run python -m app.webui --check-gpu 查看详情）`;
        hint.classList.remove("hidden");
      }
    }).catch(() => { /* probe failure: keep default CPU path */ });
  } catch (e) { /* badges are cosmetic */ }

  fillSelect($("p_palette_family"),
    [["auto", FAMILY_LABELS.auto], ...Object.entries(FAMILY_LABELS).filter(([k]) => k !== "auto")],
    "auto");
  updateHueLabel();

  try {
    const r = await fetch("/api/state");
    const s = await r.json();
    syncParamsFromServer(s.params || {});
    if (s.phase === "ready" && s.has_audio) onAnalysisDone(s);
    else if (s.phase === "analyzing") beginAnalysisUI();
  } catch (e) { /* first boot */ }
}
boot();
