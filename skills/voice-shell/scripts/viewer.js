// Make the failures that never reach the screen visible (a load failure just leaves the buttons doing nothing)
window.addEventListener('error', e => {
  const box = document.getElementById('hint');
  if (box) box.textContent = 'Script error. ' + e.message;
});


/* The languages listed in the dropdown. Each name is written in that
   language's own script. A name written in letters you cannot read is a name
   you cannot pick, so this is the one place we do not translate.
   Only languages recognition can handle (ASR_LANGS below) are listed. Translate
   the screen and then offer a language your voice cannot get through in, and it
   looks usable when it is not. */
const UI_LANGS = [
  ['en', 'English'], ['ja', '日本語'], ['es', 'Español'], ['fr', 'Français'],
  ['de', 'Deutsch'], ['zh', '中文（简体）'], ['ko', '한국어'],
];

/* How the time is written. We pass hour12:false, so all of them come out on a 24 hour clock. */
const TIME_LOCALE = {en:'en-GB', ja:'ja-JP', es:'es-ES', fr:'fr-FR',
                     de:'de-DE', zh:'zh-CN', ko:'ko-KR'};
const timeLocale = () => TIME_LOCALE[lang] || 'en-GB';

const store = {
  get(k, d) { try { return localStorage.getItem('vs.' + k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem('vs.' + k, v); } catch {} },
};

/* While it floats in front, the contents of the screen have been moved into
   the floating window's document. Theme, language and color all have to be
   written to that :root or they do nothing. Copying once at the moment it opens
   means anything switched afterwards never reaches the small window, and it
   stays stale until you come back. A window on its way out is still there
   inside 'pagehide', so rather than looking at documentPictureInPicture every
   time, we remember it ourselves and clear it ourselves.
   (Nothing touches the identifier directly, so a browser without this feature
   does not fall over) */
let pipDoc = null;
const uiDoc = () => (pipDoc && pipDoc.defaultView) ? pipDoc : document;

let langPref = store.get('lang', 'auto');
let lang = 'en';
/* The browser announces itself with the region attached, like ja-JP or zh-TW.
   Match the whole thing first, then match again on just the front half, and if
   both miss, fall back to English. zh-TW ends up on a simplified Chinese
   screen, which is still closer than falling back to English. */
function pickLang(tag) {
  const want = (tag || '').toLowerCase();
  if (I18N[want]) return want;
  const head = want.split('-')[0];
  return I18N[head] ? head : 'en';
}
function resolveLang() {
  lang = langPref !== 'auto' ? langPref : pickLang(navigator.language);
  if (!I18N[lang]) lang = 'en';
  // While it floats, write it to the small window too. Without also leaving it
  // on the original document, coming back rewinds to the language it opened in.
  for (const d of new Set([document, uiDoc()])) d.documentElement.lang = lang;
}
// Fill-ins like {name} are handled here as well
const t = (key, vars) => {
  let s = (I18N[lang] && I18N[lang][key]) ?? I18N.en[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll('{' + k + '}', v);
  return s;
};

// The default target is whichever document the contents are living in right
// now. Search document while it floats and not a single [data-i18n] turns up,
// so changing the language changes no text at all.
function applyI18n(root = uiDoc()) {
  for (const n of root.querySelectorAll('[data-i18n]')) {
    // For an element holding an icon, replace only the text part (do not wipe out the svg)
    const svg = n.querySelector(':scope > svg');
    if (svg) {
      const last = n.lastChild;
      if (last && last.nodeType === 3) last.nodeValue = t(n.dataset.i18n);
      else n.append(t(n.dataset.i18n));
    } else {
      n.textContent = t(n.dataset.i18n);
    }
  }
  for (const n of root.querySelectorAll('[data-i18n-ph]')) n.placeholder = t(n.dataset.i18nPh);
  // The text shown when the live transcript box is empty (CSS reads it through content)
  for (const n of root.querySelectorAll('[data-i18n-quiet]')) n.dataset.quiet = t(n.dataset.i18nQuiet);
  for (const n of root.querySelectorAll('[data-i18n-title]')) {
    n.title = t(n.dataset.i18nTitle);
    n.setAttribute('aria-label', t(n.dataset.i18nTitle));
  }
  // Wording that changes with the state cannot ride on data-i18n, so it gets repainted here
  if (typeof paintPower === 'function' && el.powerLabel) paintPower();
  // silenceNote is the same story: which of the two wordings belongs there
  // depends on asrChosen, so a plain data-i18n sweep would undo the swap and
  // leave the note claiming the setting works again while the slider stays
  // disabled.
  if (typeof paintBrowserAsr === 'function' && el.silenceNote) paintBrowserAsr();
}

const $ = id => document.getElementById(id);
const el = {};
for (const id of ['beacon','stateText','modes','segLive','segHold','segOff',
                  'power','powerLabel','powerRow','powerNote','openSettings','sheet','closeSettings','floatBtn','page',
                  'miniMic','miniViz','navRow','pageHead','sheetHead','helpHead','openDict','sheetTitle',
                  'routes','routeChips','routePick','routePickLabel','viz','meter','meterHit','meterFill','meterMark','logoMark',
                  'tray','stream','draft','draftTime','send','discard',
                  'editOnce','dropOne','sendOne','cancelOnce','draftMark',
                  'hint','note','log','none','count','fresh','floatAsk','taken','takeBack',
                  'mic','recogLang','recogLangField','thresh','threshVal','gaugeFill','gaugeMark',
                  'silence','silenceVal','silenceNote','minChars','minCharsVal','clean',
                  'engineGroup','enginePick','engineNote','whisperModel','whisperModelField','whisperModelNote',
                  'browserAsrWarn','asrConflict','browserMic','micSettingsLink','asrLang','asrLangField',
                  'idleMute','idleMuteVal','idleMuteField','idleMinsField','idleMuteOn','idleMuteNote',
                  'browserGestureField','browserGestureOn','browserGesturePeaks','browserGesturePeaksVal',
                  'browserGestureWindow','browserGestureWindowVal','browserGestureThreshold','browserGestureThresholdVal',
                  'themeRow','langPick','multiOn','machineName','machineNameField','machineTag',
                  'tabReplace','tabIgnore',
                  'paneReplace','paneIgnore','replaceRows','ignoreRows',
                  'addReplace','addIgnore','newFrom','newTo','newIgnore','filterReplace',
                  'builtinChips','builtinCount',
                  'dictNote','dictExport','dictImport','dictFile',
                  'paneBasic','paneDict',
                  'openHelp','helpSheet','closeHelp','helpMini','helpMiniViz',
                  'cmdGroups','cmdNote','floatStand','floatStandBack'])
  el[id] = $(id);

const post = (path, body) =>
  fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
               body: JSON.stringify(body || {})});

const putJSON = (path, body) =>
  fetch(path, {method:'PUT', headers:{'Content-Type':'application/json'},
               body: JSON.stringify(body || {})});


// Build an svg holding both the outline and the fill. CSS decides which one shows.
function iconSvg(name, size = 18) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 -960 960 960');
  svg.setAttribute('fill', 'currentColor');
  svg.setAttribute('aria-hidden', 'true');
  svg.style.width = svg.style.height = size + 'px';
  svg.style.flex = 'none';
  const pair = ICON[name] || ICON.auto_awesome;
  for (const [i, cls] of [[0, 'line'], [1, 'solid']]) {
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', pair[i]);
    path.setAttribute('class', cls);
    svg.appendChild(path);
  }
  return svg;
}

// Put a drawing at the head of every element carrying data-icon. Do not leave the screen all words.
function decorateIcons(root = document) {
  for (const n of root.querySelectorAll('[data-icon]:not([data-iconed])')) {
    n.dataset.iconed = '1';
    n.prepend(iconSvg(n.dataset.icon, Number(n.dataset.iconSize) || 18));
  }
}

/* Cleaning up the text is the daemon's job. Fixing only the look here does
   nothing to the body that reaches Claude (we once believed 「えーと」 was being
   stripped when it was not). The screen shows exactly what was written to the
   log. */
const format = raw => raw;

/* ── Visualizer ─────────────────────────
   The browser opens the same microphone, reads the frequencies, and draws the
   real shape of your voice. It is a separate path from the daemon (ffmpeg), so
   if permission is refused we run on nothing but the level that comes over the
   WebSocket (level.txt). */
const MARK_BASE_HEIGHTS = [23, 36, 18, 31, 20];
const MARK_MIN_HEIGHT = 12;
const MARK_GAIN = 24;
let audioCtx = null, analyser = null, micStream = null, freq = null;
let daemonLevel = 0, daemonSpeaking = false;
let vizFailed = false;
let vizGeneration = 0, vizStarting = false;
// How many times in a row opening it has failed with the device simply busy
// (see the catch block in startViz for why that one alone gets retried).
let vizBusyRetries = 0;
const VIZ_BUSY_RETRY_MAX = 5;

const canvas = el.viz, cx = canvas.getContext('2d');
let cw = 0, ch = 0;

function fitCanvas() {
  const r = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  cw = Math.max(1, Math.round(r.width));
  ch = Math.max(1, Math.round(r.height));
  canvas.width = cw * dpr;
  canvas.height = ch * dpr;
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  // Writing width or height wipes out the contents of a canvas. ResizeObserver
  // runs **after** requestAnimationFrame, so waiting for the next frame paints
  // one empty frame. While you have the window in your hand that repeats every
  // frame, and the mic looks like it is blinking as it shrinks. Redraw here.
  try { paintFrame(performance.now()); } catch {}
}
new ResizeObserver(fitCanvas).observe(canvas);

/* The small mic that sits in a sheet heading. Same drawing as the main screen,
   drawn from the same values. While hidden it has no measurable size (it is
   display:none, so everything reads 0), so it gets measured again the moment
   the sheet opens. Add any new sheet here. Skip that and, for as long as that
   screen is open, there is no way to see whether you are being heard. */
const minis = [[el.miniViz, el.sheet, el.miniMic],
               [el.helpMiniViz, el.helpSheet, el.helpMini]]
  .map(([canvas, sheet, box]) => ({canvas, sheet, box, cx: canvas.getContext('2d'), w: 0, h: 0}));
function fitMini() {
  const dpr = window.devicePixelRatio || 1;
  for (const m of minis) {
    const r = m.canvas.getBoundingClientRect();
    if (!r.width || !r.height) { m.w = m.h = 0; continue; }
    m.w = Math.round(r.width);
    m.h = Math.round(r.height);
    m.canvas.width = m.w * dpr;
    m.canvas.height = m.h * dpr;
    m.cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}
for (const m of minis) new ResizeObserver(fitMini).observe(m.canvas);

// Colors are read from whichever document the contents are living in too. Read
// them from the original document and, when the theme is switched while it
// floats, only the mic on the canvas takes the new color while the HTML around
// it keeps the old one.
const cssVar = n => {
  const d = uiDoc();
  return d.defaultView.getComputedStyle(d.documentElement).getPropertyValue(n).trim();
};
// Fade a theme color as it is (assumes #rrggbb. Anything else comes back untouched)
const color = (hex, alpha) => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16 & 255}, ${n >> 8 & 255}, ${n & 255}, ${alpha})`;
};

// Loudness is handled on a log scale (dB). With raw amplitude, the small
// differences down in the quiet get crushed and only the loud end stretches.
// The 0 to 255 out of getByteFrequencyData is an even scale between
// minDecibels and maxDecibels, so it converts straight back to dB.
const DB_MIN = -85, DB_MAX = -25;
const DB_SPAN = DB_MAX - DB_MIN;
const toDb = byte => DB_MIN + (byte / 255) * DB_SPAN;
const GATE_DB = 7, RANGE_DB = 26;

// The room's noise floor (dB). It drifts slowly toward what it reads when
// things are quiet. With a fixed threshold, a quiet room reacts to the air
// conditioning and the fans, and a noisy room sits pinned the other way.
let floorDb = -60;

// The height of the streaming waveform. This one also uses the amount over the sensitivity as it stands.

// The level measured by the browser's own microphone (0 to 1). It still works with the daemon down.
function browserLevel() {
  let db;
  if (analyser && !vizFailed) {
    // Look at the RMS across every band and the hiss of a sibilant alone (the
    // さ row in Japanese) pins the meter. That hiss comes out strongly above
    // 4kHz, so we look only at 120 to 2600Hz, where the fundamental and the
    // formants of the voice sit. getByteFrequencyData is already on a dB scale,
    // so averaging it directly does not crush the loud parts too far.
    const hz = (audioCtx.sampleRate / 2) / freq.length;
    const lo = Math.max(1, Math.round(120 / hz));
    const hi = Math.max(lo + 1, Math.min(freq.length, Math.round(2600 / hz)));
    let sum = 0;
    for (let k = lo; k < hi; k++) sum += freq[k];
    db = toDb(sum / (hi - lo));
  } else {
    // What the daemon puts out is an RMS amplitude, so this side converts it to dB itself
    db = 20 * Math.log10(Math.max(daemonLevel, 1e-5));
  }

  // Follow it fast on the way down and very gently on the way up
  // (so the noise floor estimate is not dragged up while you are talking)
  floorDb = db < floorDb ? floorDb * 0.92 + db * 0.08
                         : floorDb * 0.9995 + db * 0.0005;

  // How many dB it came out above the noise floor. Anything below this never gets drawn.
  return Math.min(1, Math.max(0, (db - floorDb - GATE_DB) / RANGE_DB));
}

// With the daemon down, the waveform runs on the browser's microphone too
function amplitudeFallback() {
  return (analyser && !vizFailed) ? browserLevel() : 0;
}



// Loudness is read in dB. On top of that, anything under the threshold drops
// away sharply (an expander). It never reaches zero, so it never reads as
// "maybe it stopped recording", and it still does not wander around when
// things are quiet.
//
//   above the threshold, left as it is
//   below the threshold, the amount it fell is multiplied by EXPAND
//
// Joining the two straight leaves a visible step, so KNEE_DB smooths the bend.
const EXPAND = 5;        // how many times faster it falls below the threshold
const KNEE_DB = 6;       // the width that smooths the bend
const BELOW_DB = 4;      // how many dB under the threshold counts as the floor
const SPAN_DB = 18;      // how many dB above the threshold pins it

function expand(db, kneeDb) {
  const d = db - kneeDb;
  if (d >= KNEE_DB / 2) return db;                       // above, left as it is
  if (d <= -KNEE_DB / 2) return kneeDb + d * EXPAND;     // below, dropped sharply
  return db - (EXPAND - 1) * Math.pow(d - KNEE_DB / 2, 2) / (2 * KNEE_DB);
}

// The scale is taken from the threshold. Change the sensitivity and the whole
// mapping moves with it, so a normal voice lands around 70 percent in any room.
//   noise floor and stray sounds → 0% (the bars stay at their thinnest, so it never looks gone)
//   exactly at the threshold     → around 5%
//   a normal voice               → around 65%
//   a loud voice                 → 100%
const levelToUnit = v => {
  const db = 20 * Math.log10(Math.max(v, 1e-5));
  const knee = 20 * Math.log10(Math.max(tuning.silence_threshold, 1e-5));
  const out = expand(db, knee);
  return Math.min(1, Math.max(0, (out - (knee - BELOW_DB)) / (SPAN_DB + BELOW_DB)));
};
// When the daemon is not the one recognizing, run on the level measured by
// this microphone. Otherwise the waveform looks frozen the whole time you are
// running on browser recognition alone.
const amplitudeNow = () =>
  (engine === 'off' || asrActive()) ? amplitudeFallback() : levelToUnit(daemonLevel);

/* A second reading off the same analyser, kept apart from browserLevel() on
   purpose. browserLevel() is a self-calibrating fill (it tracks its own
   floor and answers "how far above the room's own quiet"), which is right
   for the glow inside the mic but cannot be compared against the trigger
   mark, a fixed number the room's floor keeps drifting under. What the
   trigger mark and the meter bar need is the same physical quantity
   silence_threshold already is, plain RMS of the raw waveform, the same sum
   asr_mic.py takes (block.dot(block) / block.size, square-rooted) so a
   position on this bar means the same amplitude a position on the daemon's
   own bar would. Time domain, not the frequency-domain bytes browserLevel()
   reads, an FFT bucket average is not a waveform amplitude. */
let timeDomainBuf = null;
function computeBrowserRms() {
  if (!analyser || vizFailed) return 0;
  if (!timeDomainBuf || timeDomainBuf.length !== analyser.fftSize) {
    timeDomainBuf = new Float32Array(analyser.fftSize);
  }
  analyser.getFloatTimeDomainData(timeDomainBuf);
  let sum = 0;
  for (let i = 0; i < timeDomainBuf.length; i++) { const v = timeDomainBuf[i]; sum += v * v; }
  return Math.sqrt(sum / timeDomainBuf.length);
}
let browserRmsNow = 0;

/* The fill inside the mic gets the same easing. The raw value only changes
   every 0.1 seconds (asr_mic.py measures 0.1 seconds at a time and viewer.py
   pushes every 0.1 seconds) while we draw every frame, so one value sits for 6
   frames and jumps on the 7th. With the bars, 48 of them average each other out
   and the step disappears, but there is only one mic, so the jump shows up as a
   stutter.
   The rise is 0.045 seconds. By the time the next value arrives it is about 90
   percent of the way there, so the 0.1 second step turns into one slope. The
   start of a sentence never looks sluggish.
   The fall is 0.15 seconds. Same as the bars, only the fall is slowed.
   It is held in seconds rather than as a coefficient so that a 120Hz screen
   does not follow at twice the speed. */
const MIC_RISE = 0.045, MIC_FALL = 0.15;
let micLevel = 0, micAt = 0;
function stepMicLevel(now) {
  const raw = amplitudeNow();
  // No frames arrive while it sits in the background. Using that whole gap as
  // it stands makes it jump all at once the instant you come back, so cap it.
  // fitCanvas calls this too and the clock ticks can come out of order, so keep
  // it off negative as well (the sign flips and it runs away).
  const dt = micAt ? Math.min(Math.max((now - micAt) / 1000, 0), 0.1) : 0.1;
  micAt = now;
  micLevel += (raw - micLevel) * (1 - Math.exp(-dt / (raw > micLevel ? MIC_RISE : MIC_FALL)));
  return micLevel;
}
// Fill the Material Symbols path as it is. It goes on a canvas, so make it a
// Path2D and reuse it (rebuilding one every frame gets heavy on allocation and
// disposal alone).
const _micPaths = {};
function micPath2D(name) {
  if (!_micPaths[name]) _micPaths[name] = new Path2D(ICON[name][1]);   // the filled one
  return _micPaths[name];
}
function paintGlyph(ctx, name, midX, midY, size, color) {
  ctx.save();
  ctx.translate(midX, midY);
  const k = size / 960;                 // viewBox is 0 -960 960 960
  ctx.scale(k, k);
  ctx.translate(-480, 480);
  ctx.fillStyle = color;
  ctx.fill(micPath2D(name));
  ctx.restore();
}

/* The same drawing goes in two places, the big one on the main screen and the
   small one in the settings heading. It takes the target and the size as
   arguments because giving the small one the same ring thickness fills a 30px
   circle with nothing but ring and buries the mic inside it.
   tone is the color that fills up with the level. It carries the mode (instant
   / review) straight through. */
function drawMic(ctx, w, h, tone) {
  const midX = w / 2, midY = h / 2;
  const size = h * 0.62;            // height of the mic drawing
  const ring = h * 0.40;            // radius of the ring around it
  const lw = Math.max(1.6, Math.min(3, h * 0.05));   // the main one stays at 3px
  const lv = micLevel;               // the eased value. The raw one moves in steps
  const off = route === 'off';

  if (off) {
    ctx.strokeStyle = cssVar('--danger');
    ctx.lineWidth = lw;
    ctx.beginPath();
    ctx.arc(midX, midY, ring, 0, Math.PI * 2);
    ctx.stroke();
    paintGlyph(ctx, 'mic_off', midX, midY, size, cssVar('--danger'));
    return;
  }

  // The ring around it never changes. If its color moved with your voice, how
  // far the pressable area reaches would blur every time. Only the inside of
  // the mic moves.
  ctx.strokeStyle = color(cssVar('--faint'), 0.55);
  ctx.lineWidth = lw;
  ctx.beginPath();
  ctx.arc(midX, midY, ring, 0, Math.PI * 2);
  ctx.stroke();

  // The mic in its sunken state
  paintGlyph(ctx, 'mic', midX, midY, size, cssVar('--faint'));

  // The inside lights up from below. Clip to the level and repaint that much in the bright color.
  if (lv > 0.01) {
    const top = midY + size / 2 - size * lv;
    ctx.save();
    ctx.beginPath();
    ctx.rect(midX - size, top, size * 2, size);
    ctx.clip();
    paintGlyph(ctx, 'mic', midX, midY, size, tone);
    ctx.restore();
  }
}
let frameFailed = false;
function frame(now) {
  requestAnimationFrame(frame);
  // Even when the drawing cannot happen (no measurable box size and so on), still show it building toward being sent
  paintSendCue(now);
  if (!cw || !ch) return;
  try { paintFrame(now); } catch (err) {
    // One failed frame does not stop it. The next frame redraws.
    // It only goes quiet from the second one on. Swallow it and, even with
    // every single frame failing, all you know is that no picture shows (which
    // is exactly how it once went unnoticed).
    if (!frameFailed) { frameFailed = true; console.error('paintFrame:', err); }
    cx.setTransform(window.devicePixelRatio || 1, 0, 0, window.devicePixelRatio || 1, 0, 0);
    cx.globalAlpha = 1;
    cx.globalCompositeOperation = 'source-over';
  }
}

function paintFrame(now) {
  cx.clearRect(0, 0, cw, ch);

  // The mic drawing shows being switched off through its shape too, so it keeps drawing
  if (analyser && !vizFailed) analyser.getByteFrequencyData(freq);

  stepMicLevel(now);
  drawMic(cx, cw, ch, cssVar('--accent'));

  // While a sheet is open the main screen is hidden entirely. Draw the same
  // picture next to the heading so that at least whether you are being heard
  // stays visible. Nothing is drawn while it is closed (that would only be
  // painting something invisible every frame).
  for (const m of minis) {
    if (m.sheet.hidden || !m.w || !m.h) continue;
    m.cx.clearRect(0, 0, m.w, m.h);
    drawMic(m.cx, m.w, m.h, cssVar(shownMode === 'hold' ? '--accent-2' : '--accent'));
  }

  const marks = el.logoMark.querySelectorAll('rect');
  const markLevel = route === 'off' ? 0 : micLevel;
  for (let i = 0; i < marks.length; i++) {
    const h = route === 'off'
      ? MARK_MIN_HEIGHT
      : Math.min(60, MARK_BASE_HEIGHTS[i] + markLevel * MARK_GAIN);
    marks[i].setAttribute('y', ((66 - h) / 2).toFixed(2));
    marks[i].setAttribute('height', h.toFixed(2));
  }
}
requestAnimationFrame(frame);

// We want the browser on the same microphone the daemon picked.
// ffmpeg and Chrome write their labels differently, so we match on containment.
async function matchDeviceId(label) {
  if (!label) return null;
  try {
    const list = await navigator.mediaDevices.enumerateDevices();
    const ins = list.filter(d => d.kind === 'audioinput' && d.label);
    const norm = s => s.toLowerCase().replace(/[^a-z0-9]/g, '');
    const want = norm(label);
    const hit = ins.find(d => norm(d.label).includes(want) || want.includes(norm(d.label)));
    return hit ? hit.deviceId : null;
  } catch { return null; }
}

// The mic dropdown picks which device asr_mic.py (the daemon) opens, not
// which one Chrome's own recognition listens through (browserMicNote says as
// much: Chrome always uses its own default there, the dropdown does nothing
// under browser recognition). This analyser exists to gate "pause to send"
// on real quiet, and asking it to open whatever device the dropdown names
// measures a different microphone than the one actually hearing you the
// moment that device is not Chrome's default, so the gate reads quiet no
// matter what you say and sends the instant a clause finalizes regardless of
// silence_duration. Naming no device at all here, under browser recognition,
// is what keeps the two listening to the same one.
const vizDeviceLabel = () => asrChosen ? '' : (el.mic.value || '');

async function startViz(label) {
  const generation = ++vizGeneration;
  vizStarting = true;
  const outdated = () => generation !== vizGeneration;
  let stream = null;
  try {
    if (micStream) micStream.getTracks().forEach(tr => tr.stop());
    micStream = null;
    analyser = null;
    const id = await matchDeviceId(label);
    if (outdated()) return;
    stream = await navigator.mediaDevices.getUserMedia({
      audio: id ? {deviceId: {ideal: id}} : true,
    });
    if (outdated()) {
      stream.getTracks().forEach(tr => tr.stop());
      return;
    }
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') await audioCtx.resume();
    if (outdated()) {
      stream.getTracks().forEach(tr => tr.stop());
      return;
    }
    const nextAnalyser = audioCtx.createAnalyser();
    nextAnalyser.fftSize = 512;
    nextAnalyser.smoothingTimeConstant = 0.7;
    nextAnalyser.minDecibels = -85;
    nextAnalyser.maxDecibels = -25;
    audioCtx.createMediaStreamSource(stream).connect(nextAnalyser);
    micStream = stream;
    analyser = nextAnalyser;
    freq = new Uint8Array(nextAnalyser.frequencyBinCount);
    vizFailed = false;
    vizBusyRetries = 0;
  } catch (err) {
    if (outdated()) return;
    if (stream && micStream !== stream) stream.getTracks().forEach(tr => tr.stop());
    // The screen still has to hold together where permission is refused (it runs on the level alone)
    vizFailed = true;
    analyser = null;
    // Swallowed before this, so there was no trace anywhere of why the pause
    // to send gate had nothing to measure quiet with (browserGateTick reads
    // 0 for the level whenever this failed, which the gate itself treats as
    // silence, not as "unknown", the daemon-driven ring's own account of the
    // same thing (see the comment on sendCountdownOn)).
    console.warn('voice-shell: could not open the analyser mic stream', err);
    if (el.hint.textContent === '') el.hint.textContent = t('hintNoMic');
    // NotReadableError means the device itself refused to open, not that
    // permission was denied, and the common way that happens is something
    // else holding it exclusively right at this instant, the browser's own
    // recognition among them, having just grabbed the same microphone a
    // moment earlier for the same start. Windows in particular tends not to
    // let two callers open one input device at once. That contention is
    // usually gone within a second, but nothing was retrying, so a stream
    // that lost this race at startup stayed lost for the rest of the
    // session. NotAllowedError and the rest are left alone; hammering a
    // refusal helps nobody.
    if (err?.name === 'NotReadableError' && vizBusyRetries < VIZ_BUSY_RETRY_MAX) {
      vizBusyRetries++;
      const delay = Math.min(8000, 500 * Math.pow(2, vizBusyRetries - 1));
      setTimeout(() => { if (!outdated()) syncVizCapture(); }, delay);
    }
  } finally {
    if (!outdated()) vizStarting = false;
  }
}

function stopViz() {
  vizGeneration++;
  vizStarting = false;
  if (micStream) micStream.getTracks().forEach(tr => tr.stop());
  micStream = null; analyser = null; freq = null;
}

// Autoplay is restricted, so we go and get the audio the first time anything is touched
let vizArmed = false;
function armViz() {
  if (vizArmed) return;
  vizArmed = true;
  syncVizCapture();
}
addEventListener('pointerdown', armViz, {once:true});
addEventListener('keydown', armViz, {once:true});

/* ── Painting ───────────────────────────── */
function setState(kind, text) {
  el.beacon.className = 'beacon ' + kind;
  el.stateText.textContent = text;
  /* While a sheet is open this one line is hidden. The small mic is the only
     cue left, so the same sentence goes on its label and its tooltip too.
     It presses now, so what pressing does has to come first. A screen reader
     announcing nothing but the state would leave a button whose name never says
     what it is for. The two are split by a newline rather than any punctuation,
     because the mark between two sentences is not the same in all seven
     languages and there is nothing here that has to be spelled. */
  for (const m of minis) {
    const s = t(route === 'off' ? 'resumeTitle' : 'pauseTitle') + '\n' + text;
    m.box.title = s;
    m.box.setAttribute('aria-label', s);
  }
}

function retally() {
  const n = el.log.children.length;
  el.count.textContent = n;
  el.none.hidden = n > 0;
}

function addEntry(rec) {
  const row = document.createElement('div');
  row.className = 'entry';
  row.dataset.kind = rec.resent ? 'resent' : rec.edited ? 'edited' : 'sent';

  const gutter = document.createElement('div');
  gutter.className = 'gutter';
  const mark = document.createElement('span');
  mark.className = 'mark ' + row.dataset.kind;
  const markWord = rec.resent ? t('resent') : rec.edited ? t('edited') : t('sent');
  // Carried here too, so a narrow window that hides the word (below) still
  // says it on hover/to a screen reader, the checkmark alone means nothing
  // read out loud.
  mark.title = markWord;
  // The word sits in its own span so a narrow window can hide just this and
  // keep the checkmark (mark::before in the stylesheet), rather than the
  // whole label being left to wrap the way CJK text does with no spaces to
  // break on, one character deep per line, inside a row that has no room
  // to spare for it.
  const markLabel = document.createElement('span');
  markLabel.className = 'mark-label';
  markLabel.textContent = markWord;
  mark.append(markLabel);
  const stamp = document.createElement('span');
  // The log carries no timestamp, so we show the time it arrived
  stamp.textContent = rec.time ||
    new Date().toLocaleTimeString(timeLocale(), {hour12:false});
  gutter.append(mark, stamp);

  row.dataset.to = rec.to ? String(rec.to) : '';
  const text = document.createElement('div');
  text.className = 'text';
  text.dataset.raw = rec.text;
  text.textContent = format(rec.text);
  gutter.append(buildToControl(row.dataset.to));

  row.append(gutter, text);
  el.log.prepend(row);          // newest on top (same order as the mock)
  retally();
}

/* The destination chip doubles as the resend control, rather than a second,
   separate arrow sitting off at the row's own edge (an earlier build did
   that, and it read as two unrelated controls that happened to share a
   row). Picking a different name from the same chip that already names
   where it went is what "resend elsewhere" reads as one motion instead of
   two (#79).

   Rebuilt from scratch on every call rather than patched in place, off
   both addEntry and relabelEntries's five second poll, since who is
   listening drifts the whole time a card sits in the log and a list built
   once at send time would go stale. */
function buildToControl(to) {
  const wrap = document.createElement('span');
  wrap.className = 'to';
  // Only one (or nobody) listening right now, so there is nothing to switch
  // between. Say where it went, same as always, and stop there. With no
  // destination on record either (working alone the whole time), there is
  // nothing worth a chip over at all.
  if (knownListeners.length < 2) {
    if (!to) return wrap;
    wrap.append(iconSvg('terminal', 11), document.createTextNode(routeNames.get(to) || `#${to}`));
    return wrap;
  }
  const knownIdx = knownListeners.findIndex(l => String(l.pid) === to);
  const label = knownIdx >= 0 ? `${knownIdx + 1}. ${knownListeners[knownIdx].label}`
              : to ? (routeNames.get(to) || `#${to}`)
              : t('resendPick');
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'to-btn';
  btn.title = t('resendTitle');
  const labelSpan = document.createElement('span');
  labelSpan.className = 'to-label';
  labelSpan.textContent = label;
  const caret = document.createElement('span');
  caret.className = 'to-caret';
  caret.textContent = '▾';
  caret.setAttribute('aria-hidden', 'true');
  btn.append(labelSpan, caret);
  btn.onclick = () => openToMenu(btn, to);
  wrap.append(iconSvg('terminal', 11), btn);
  return wrap;
}

// Only one open at a time, and relabelEntries (the five second poll) checks
// this to leave that one row alone rather than rebuild the chip out from
// under whoever has it open.
let openToMenuBtn = null;
let closeToMenu = null;

/* A plain <select> was tried first, styled down to look like the chip. The
   closed-state box takes CSS fine, but the opened list is the browser's own
   native popup regardless, on its own theme rather than this page's dark
   one (#79 feedback: "not the native dropdown as it is, a hand-built one").
   Built by hand instead, in the same vein as the destination bubble's own
   floating panel elsewhere on this page.

   Both places that pick a destination come through here: the chip on a sent
   card (resend it somewhere else) and the roll-up picker above the draft card
   (where the next thing you say lands). Those two looked alike while closed
   and came apart the moment either one opened, which is the single thing a
   picker cannot afford to do.

   `items` is [{key, label}]. onPick runs only for a key that is not the one
   already chosen, so neither caller has to guard against re-picking. A
   `heading` line, when given, sits above the list as a plain caption (not a
   pickable row) rather than living on the chip itself the whole time, in
   the way, whether it was ever going to be opened or not (#79 feedback:
   said outright once opened is enough, said every time it sits closed is
   noise). */
function openPickMenu(anchor, items, currentKey, onPick, heading) {
  // A second press on the same anchor is a close, not a rebuild-and-reopen.
  if (openToMenuBtn === anchor) { closeToMenu(); return; }
  if (closeToMenu) closeToMenu();
  // While it floats in front, the screen has been moved into the small
  // window's own document. A panel appended to this one would be built into
  // a window nobody is looking at, and measured against the wrong width.
  const doc = anchor.ownerDocument;
  const win = doc.defaultView;
  // The nearest ancestor that actually clips its own content (the history
  // list scrolls inside one of these; the roll-up picker above the draft
  // card is not inside one at all). Used below to close the panel once its
  // anchor scrolls out of that container's own visible area, rather than
  // letting a position:fixed panel go on floating over whatever sits
  // above or below that container (#79 feedback: it was reaching up over
  // the unsent card and the mic button once scrolled).
  let clip = anchor.parentElement;
  while (clip && clip !== doc.body) {
    if (/(auto|scroll)/.test(win.getComputedStyle(clip).overflowY)) break;
    clip = clip.parentElement;
  }
  if (clip === doc.body) clip = null;
  const menu = doc.createElement('div');
  menu.className = 'to-menu';
  menu.setAttribute('role', 'listbox');
  if (heading) {
    const h = doc.createElement('div');
    h.className = 'to-menu-heading';
    h.textContent = heading;
    menu.append(h);
  }
  for (const it of items) {
    const item = doc.createElement('button');
    item.type = 'button';
    item.className = 'to-menu-item' + (it.key === currentKey ? ' on' : '');
    item.textContent = it.label;
    item.onclick = () => {
      close();
      if (it.key === currentKey) return;
      onPick(it.key);
    };
    menu.append(item);
  }
  doc.body.append(menu);
  // Placed off the anchor's own live position (same reasoning as
  // positionFloatAsk), then nudged left if that would run the panel off
  // the right edge of a narrow window. Re-run on scroll (the history list
  // this chip sits in scrolls on its own, position:fixed does not follow
  // that by itself) and on resize, the same two triggers positionFloatAsk
  // already re-measures on.
  function place() {
    const r = anchor.getBoundingClientRect();
    // The roll-up picker collapses to nothing the moment the last listener
    // drops (paintRoutes hides el.routes entirely). Nothing left to anchor
    // against, so close rather than pin the panel at a stale 0x0 corner.
    if (!r.width) { close(); return; }
    // Scrolled out of the list's own visible band. Reaching for a position
    // here would mean floating the panel over the fixed controls above or
    // below that list instead of over the row it belongs to, so close
    // instead of chasing it somewhere that no longer makes sense.
    if (clip) {
      const cr = clip.getBoundingClientRect();
      if (r.bottom < cr.top || r.top > cr.bottom) { close(); return; }
    }
    menu.style.top = Math.round(r.bottom + 4) + 'px';
    menu.style.left = Math.round(r.left) + 'px';
    const overflowRight = menu.getBoundingClientRect().right - (win.innerWidth - 8);
    if (overflowRight > 0) menu.style.left = Math.round(r.left - overflowRight) + 'px';
  }
  place();

  function close() {
    menu.remove();
    doc.removeEventListener('click', onDocClick, true);
    doc.removeEventListener('keydown', onKey);
    doc.removeEventListener('scroll', place, true);
    win.removeEventListener('resize', place);
    if (closeToMenu === close) { closeToMenu = null; openToMenuBtn = null; }
  }
  function onDocClick(e) {
    if (!menu.contains(e.target) && !anchor.contains(e.target)) close();
  }
  function onKey(e) { if (e.key === 'Escape') close(); }
  // Deferred so the very click that opened this menu, still bubbling up to
  // document, does not also count as the outside click that shuts it.
  setTimeout(() => doc.addEventListener('click', onDocClick, true), 0);
  doc.addEventListener('keydown', onKey);
  // capture:true so a scroll on the history list (or any other nested
  // scroller) is caught too, not only a scroll of the document itself.
  doc.addEventListener('scroll', place, true);
  win.addEventListener('resize', place);
  closeToMenu = close;
  openToMenuBtn = anchor;
}

/* The numbers are the ones said out loud (「2番に切り替え」). The chips, the
   chip menu and the roll-up picker all have to count them the same way. */
const listenerItems = () =>
  knownListeners.map((l, i) => ({key: String(l.pid), label: `${i + 1}. ${l.label}`}));

// The chip on a sent card. Picking another name sends the same text there.
// The chip is rebuilt right away rather than left for the five second poll,
// since its own onclick closes over `to` at build time (buildToControl) and
// a stale one reads the wrong destination as "already selected" until then.
function openToMenu(btn, to) {
  openPickMenu(btn, listenerItems(), to, async pid => {
    const row = btn.closest('.entry');
    const prevTo = row.dataset.to;
    row.dataset.to = pid;
    row.querySelector('.to')?.replaceWith(buildToControl(pid));
    try {
      await post('/api/resend', {text: row.querySelector('.text').dataset.raw, to: pid});
    } catch (err) {
      row.dataset.to = prevTo;
      row.querySelector('.to')?.replaceWith(buildToControl(prevTo));
      el.hint.textContent = t('resendFailed', {err: err.message});
    }
  }, t('resendLabel'));
}

/* Look up a name from the destination PID. Names of finished sessions are kept
   as well. If the entry survives but the destination alone turns into #42101,
   you still cannot tell which one it was. */
const routeNames = new Map();

function relabelEntries() {
  for (const row of el.log.children) {
    const node = row.querySelector('.to');
    // Left alone rather than rebuilt while its own menu is open, so nobody
    // mid-pick has the chip (and the button the open menu is anchored to)
    // swapped out from under them by this same five second poll.
    if (node && node.contains(openToMenuBtn)) continue;
    node?.replaceWith(buildToControl(row.dataset.to || ''));
  }
}

function reformatAll() {
  for (const row of el.log.children) {
    const n = row.querySelector('.text');
    n.textContent = format(n.dataset.raw);
  }
}

/* ── Modes ──────────────────────────────
   Three of them, instant, review and paused. The daemon never gets as far as
   the hold decision while muted, so there is no such thing as off and
   collecting. */
const ROUTE = {
  live: {muted:false, paused:false},
  hold: {muted:false, paused:true},
  off:  {muted:true,  paused:false},
};

let route = 'live';
let lastMode = 'live';   // coming off pause goes back to the mode just before it
let oneShot = false;     // whether just this one utterance is being routed to review
/* Whether a person laid hands on the current draft. It rides along on send, and
   the server reads it to stamp "edited". It is not decided by whether the text
   went through the edit box. That would stamp sentences that came out of
   recognition clean and went out untouched, and Claude would read them as
   deliberately worded and hold back on rereading them. A recognition result
   arrives by assignment to value, which fires no 'input', so this only goes up
   when a person types, pastes or cuts.
   Editing and then putting the original sentence back still counts as edited
   (an act took place either way).
   It comes down only on send and on discard. */
let draftTouched = false;
let shownMode = 'live';  // the mode shown on screen. The small mic takes its color from this
let asrPausedByRoute = false;   // whether browser recognition was stopped for the pause
let inFlight = false;    // keeps polling from rewinding things mid-switch
let routeRevision = 0;
let routeQueue = Promise.resolve();
let wsMessageQueue = Promise.resolve();
let discardInProgress = 0;
let wsMessageNumber = 0;
let discardResultCutoff = 0;
let discardQueue = Promise.resolve();
const dropBarriers = new Set();

function paint() {
  // While Edit this one is on, keep showing instant. Inside it is holding, but
  // the mode itself was never switched, so changing the display too would make
  // it look like something else. While muted, route is 'off', which would leave
  // neither one looking selected. Show the mode you come back to as the
  // selected one (CSS pulls the color out).
  const shown = oneShot ? 'live' : (route === 'off' ? lastMode : route);
  shownMode = shown;

  for (const [k, b] of [['live', el.segLive], ['hold', el.segHold]]) {
    b.classList.toggle('on', shown === k);
    b.setAttribute('aria-checked', String(shown === k));
  }
  const off = route === 'off';
  el.modes.classList.toggle('muted', off);
  // The small mics in the sheet headings press the same thing, so they carry
  // the same state. Their wording is written in setState instead, which runs
  // last of all and has the status line to fold in with it.
  for (const b of [el.segOff, el.miniMic, el.helpMini])
    b.setAttribute('aria-pressed', String(off));
  el.segOff.title = t(off ? 'resumeTitle' : 'pauseTitle');
  el.segOff.setAttribute('aria-label', el.segOff.title);

  // The beacon color puts being switched off first (shown points at where you come back to)
  setState(off ? 'off' : shown,
           t(off ? 'statusOff' : shown === 'hold' ? 'statusHold' : 'statusLive'));
  if (!oneShot && performance.now() > hintHoldUntil) {
    el.hint.textContent = armPending ? t('hintArm')
      : t(off ? 'hintOff' : shown === 'hold' ? 'hintHold' : 'hintLive');
  }
  // While you are working elsewhere, the tab title is the only cue left
  setTitle(t(off ? 'titleOff' : shown === 'hold' ? 'titleHold' : 'titleLive') + ' · Voice Shell');

  el.tray.classList.toggle('holding', route === 'hold');
  el.tray.classList.toggle('editing', oneShot);
  el.draftMark.textContent = t(oneShot ? 'editingOne' : 'unsent');
  paintTinyButtons();
  el.tray.classList.toggle('idle', off);
  if (off) el.stream.textContent = '';
  paintDraft();
}

/* Edit, discard and send stay put at all times outside of editing just this
   one, and only whether they can be pressed changes. Showing and hiding them
   moves the target, and in a hurry you hit the one next to it. Send is
   settled every frame in paintSendCue instead, because what it turns on goes
   empty on its own once an utterance settles and nothing calls back here to
   say so.
   Editing just this one is the one exception. The pencil can only ever show
   disabled there, since you are already inside what it opens, and the trash
   next to it reads as a second copy of the discard already sitting in the
   edit box below. Neither is doing a job worth the seat, so the two of them
   swap for cancelOnce, the one thing missing: a plain way back out. */
function paintTinyButtons() {
  // Discard can always be pressed. Press it with nothing to discard and
  // nothing happens, because there is simply nothing being said right now.
  // Raising and sinking it is worse to live with, since you then have to check
  // every time whether it can be pressed when you want to press it.
  // Review mode is the same situation as a one-shot edit, standing rather
  // than momentary: the box below is already open, so the pencil can only
  // ever show disabled — it opens what you are inside — and the trash reads
  // as a second copy of the discard sitting right under it. Two bins on one
  // card and neither says which one you want. Both step aside.
  // Switching back to live with unsent text still in the box is the same
  // situation once more, even though route itself already reads live.
  const editingHere = oneShot || route === 'hold' || !!el.draft.value.trim();
  el.editOnce.disabled = route !== 'live' || oneShot;
  el.editOnce.hidden = editingHere;
  el.dropOne.hidden = editingHere;
  // The way out belongs to the momentary case only. Review mode is not
  // something you back out of from here — it is a setting, and the control
  // that turns it off is the one that turned it on.
  el.cancelOnce.hidden = !oneShot;
}

/* The setting for using several machines. It changes what it takes for a
   signal to be accepted, so while it is on, the machine name shows on the main
   screen too (buried in settings, you could be talking to the wrong machine and
   never notice). */
function paintMachine() {
  const on = el.multiOn.checked;
  const all = el.machineName.value.split(/[,、]/).map(v => v.trim()).filter(Boolean);
  el.machineNameField.hidden = !on;      // a setting that is not in use is not shown
  el.machineTag.hidden = !(on && all.length);
  el.machineTag.textContent = all[0] || '';
  el.machineTag.title = t('multiOn');
}
/* While you are typing, never overwrite with the server's value. The refetch
   every 3 seconds would wipe out what you were part way through writing. It is
   held as a flag rather than read off focus so that it keeps protecting you
   when the write fails. Focus goes the moment you leave the field, but it has
   not reached the server yet, so watching focus alone loses what you wrote on
   the next refetch. */
let machineDirty = false;

function saveMachine() {
  machineDirty = false;
  paintMachine();
  putJSON('/api/machine', {multi: el.multiOn.checked, name: el.machineName.value.trim()})
    .catch(() => { machineDirty = true; });   // if the write failed, keep protecting what was typed
}
el.multiOn.onchange = saveMachine;
el.machineName.onchange = saveMachine;       // read it the moment you leave the field
el.machineName.onblur = saveMachine;         // for the paths where change never fires
el.machineName.oninput = () => { machineDirty = true; paintMachine(); };

// The edit box shows only in review mode, or when something is part way
// written. In instant mode all you need to see is the live transcript.
function paintDraft() {
  const want = route === 'hold' || !!el.draft.value.trim();
  el.draft.hidden = !want;
  el.discard.hidden = el.send.hidden = !want;
}

/* ── The wait before it goes out ─────────
   The daemon breaks an utterance where the time spent under the reference level
   reaches the pause to send (asr_mic.stream_utterances). It counts that in
   seconds of the audio it has actually taken in, sends the running count out
   with every level, and the paper plane in the corner of the card is filled
   from that number.

   Running the same count here off this machine's clock is what used to make the
   drawing finish 1.0 to 1.9 seconds before the card moved. Audio reaches the
   daemon at 0.78 to 0.89 times real time, so a second of wall clock here was
   never a second of the silence being measured over there, and the shortfall
   moved from one utterance to the next, which is why no fixed offset would have
   covered it (#53).

   The clock is kept as the fallback, for a daemon old enough that its level
   carries the volume and nothing else. */
let voiceSeen = false;   // whether this utterance has picked up voice past the reference
let silentAt = 0;        // when the voice broke off, by this machine's clock. The fallback alone reads it
let livePartial = '';    // what is being recognized, raw, before the dictionary touches it

/* The daemon's own count, in seconds of audio. cueOn says whether the last
   level carried one at all, and it is settled per message rather than latched,
   so a daemon swapped underneath us is followed in both directions. It is
   deliberately not cleared along with the count below, because it answers what
   the daemon sends, not where this utterance stands. */
let cueOn = false, cueRun = 0;
function takeSilenceRun(m) {
  cueOn = 'silence_run' in m;
  if (cueOn) cueRun = m.silence_run;
}

/* One count lands per block, which is 0.1 seconds of audio and about 0.12 of
   wall clock, while the ring is drawn every frame. Taken whole it would sit
   still for 6 frames and step on the 7th, the same stutter #19 found in the
   fill inside the mic, and it is smoothed the same way and with that fix's time
   constant. By the time the next count lands the drawing is about 90 percent of
   the way to the last one, so the step becomes one slope and nothing trails by
   more than a block. Held in seconds, not as a coefficient, so a 120Hz screen
   does not run it at twice the speed. */
const CUE_EASE = 0.045;
let cueShown = 0, cueShownAt = 0;

/* Full, and staying that way until the utterance really lands. The daemon still
   has to run the whole thing through recognition once more to settle it, which
   measured 0.13 to 0.47 seconds here and runs longer on whisper, and the line
   then takes up to 0.25 more to reach this page. Snapping the ring back to
   empty in that gap was the old reading, and it said the opposite of what was
   happening. Holding adds no movement. It takes one away.
   The cap is a backstop for the case where nothing ever comes to end the hold,
   an utterance the daemon threw out for a reason this page cannot see. Long
   enough to cover the slowest settle measured, short enough not to sit there
   looking stuck. */
const CUE_HOLD_MAX = 2500;
let cueFull = false, cueFullDrop = false, cueFullAt = 0;

/* Nothing shows for the first stretch of the silence. A breath, or the gap
   between two words, drops under the reference level constantly, and starting
   to fill on every one of them puts movement in the corner of your eye while
   you are still in the middle of a sentence. The shortest pause to send anyone
   can choose is 0.5s, so holding back 0.4s means those gaps show nothing at all
   and only a real stop is ever drawn. */
const SEND_CUE_DEAD = 400;

/* Counting is allowed only on the side that goes straight through, and only
   while the daemon is listening. In review and under Edit this one, going quiet
   sends nothing, and while paused nothing is picked up at all. Browser
   recognition decides its own breaks, so it has nothing to do with the pause to
   send here. */
const sendCountdownOn = () =>
  route === 'live' && !oneShot && engineOnish() && !asrActive();

function clearSendCountdown() {
  voiceSeen = false; silentAt = 0; livePartial = '';
  cueRun = 0; cueShown = 0; cueFull = false;
  clearTimeout(tailMarkTimer); tailMarkTimer = null; tailMarkKey = null; tailMarkPending = null;
}

/* The same test voice_daemon.py runs (is_noise and is_allowed_short). Compare
   with the punctuation taken off, and count a word merely said twice
   (「了解、了解」) as that word on its own. Reading it differently from the
   daemon is what would make the drawing promise a send that never comes. */
const CUE_TRIM = /^[。、．，！？!?.…・\s　]+|[。、．，！？!?.…・\s　]+$/g;
const cueCore = s => s.replace(CUE_TRIM, '').toLowerCase();
function isBackchannel(text, words) {
  if (!words.size) return false;
  const core = cueCore(text);
  if (!core) return false;
  if (words.has(core)) return true;
  const parts = core.split(/[、。,.\s]+/).map(cueCore).filter(Boolean);
  return parts.length > 0 && parts.every(p => words.has(p));
}

/* The signals that close a sentence (「〜、キャンセル」 and 「〜、手直し」). One of
   these on the end means the utterance is thrown away or handed to the draft, so
   it never goes out.

   The wordings are read from the daemon's own table through /api/commands. A copy
   written here would go stale the day a wording changes over there, and the
   drawing would fill for words that get thrown away. That endpoint lays out one
   language at a time, because it feeds the "?" list, which answers "what do I say"
   in the reader's language. Matching follows no language at all (voice_daemon.py
   says why at the head of COMMAND_WORDS), so every screen language is asked and
   the answers are joined.

   The built-in table is read once and never changes while the screen is up.
   Wordings added by hand can, from any tab, so loadTailWords is called again
   after every save (saveCmds), the same refresh cmdOff already got. What the
   user switched off is held apart in cmdOff for the same reason. */
/* mute rides along here too (#76 follow-up), so the drawing can show the same
   "about to happen" preview for it that cancel_tail/hold_tail already get. Unlike
   those two, mute only counts with a short noise prefix ahead of the word, not a
   whole clause ahead of it, so TAIL_NOISE_MAX below keeps that ceiling in step
   with MUTE_TAIL_NOISE_MAX in voice_daemon.py. unmute is left out, nothing is on
   screen to highlight while the mic is off. */
const TAIL_IDS = ['cancel_tail', 'hold_tail', 'mute'];
let tailWords = {cancel_tail: new Set(), hold_tail: new Set(), mute: new Set()};
const TAIL_NOISE_MAX = {mute: 7};
async function loadTailWords() {
  try {
    const all = await Promise.all(UI_LANGS.map(
      ([code]) => fetch('/api/commands?lang=' + code).then(r => r.json())));
    const out = {cancel_tail: new Set(), hold_tail: new Set(), mute: new Set()};
    for (const d of all) {
      for (const g of d.groups || [])
        if (out[g.id])
          // An empty wording would end every sentence and leave the drawing
          // permanently dark, so it is dropped rather than trusted.
          for (const w of g.phrases || []) if (w) out[g.id].add(w.toLowerCase());
      // Wordings added by hand, not just the built-in table. The same list
      // regardless of which language this pass is for (what you typed is not
      // translated), so adding it again on every pass through this loop only
      // repeats work, it does not double anything up (a Set).
      for (const id of TAIL_IDS)
        for (const w of (d.user || {})[id] || []) if (w) out[id].add(w.toLowerCase());
      takeCmdOff(d);
    }
    tailWords = out;
  } catch { /* an older server has no such endpoint. Leave the drawing as it was */ }
}

/* What the user switched off, kept beside the tables above rather than folded
   into them. The tables answer "what wordings exist", which is the same on every
   screen, and this answers "which of them does this machine still listen for",
   which the user moves while the screen is up.

   Kinds and single wordings both live here. **The wordings arrive whole, every
   language, not just the one being laid out**, because the tables above are
   gathered across all seven languages and a wording struck while the screen was
   in Japanese still has to stop filling the drawing when the screen is English. */
let cmdOff = {kinds: new Set(), words: {}};
function takeCmdOff(d) {
  if (!d || typeof d !== 'object') return;
  const words = {};
  for (const id of TAIL_IDS)
    words[id] = new Set(((d.off_words || {})[id] || []).map(w => w.toLowerCase()));
  cmdOff = {kinds: new Set(d.off || []), words};
}

/* The same test voice_daemon.take_tail runs, against the same wordings
   voice_daemon.active_tail hands it. All that is wanted here is whether the tail
   matched, so the body it hands back is not rebuilt. The 「コマンド」 lead-in that
   one strips only shortens that body, it never decides the match, so leaving it
   out cannot read the utterance differently.
   Both ways of switching off are asked about, because both change what the daemon
   will do with the utterance. Miss either one and the drawing goes dark for a
   wording that is going to be sent after all, which is the promise this drawing
   exists to keep. */
const TAIL_TRIM = /[ \t　。、．，・！？!?.,]+$/;

/* The longest wording that matches at the tail, and which kind it belongs to,
   or null. Longest first across every id together, the same reason
   voice_daemon.py sorts MUTE_TAIL by length, a long phrasing must not be eaten
   by a short one that sits inside it. mute's ceiling (TAIL_NOISE_MAX) is
   checked here too, so a sentence that only happens to end in the word after a
   real clause is not read as "about to fire" when the daemon would not read it
   that way either. */
function matchingTailWord(text) {
  const body = text.trim().replace(TAIL_TRIM, '').toLowerCase();
  if (!body) return null;
  let best = null;
  for (const id of TAIL_IDS) {
    if (cmdOff.kinds.has(id)) continue;
    const off = cmdOff.words[id] || new Set();
    const ceiling = TAIL_NOISE_MAX[id];
    for (const w of tailWords[id]) {
      if (off.has(w) || !body.endsWith(w)) continue;
      if (ceiling !== undefined && body.length - w.length > ceiling) continue;
      if (!best || w.length > best.word.length) best = {id, word: w};
    }
  }
  return best;
}
function endsWithTailCmd(text) {
  return matchingTailWord(text) !== null;
}

/* Whether what has been heard so far is something the daemon would send on its
   own. It picks which way the ring fills and in what color, out toward the
   plane in the accent for going, back the other way in red for being dropped.
   It has nothing to say about whether send can be pressed. Narrowing is there
   to decide what leaves without being asked, and a press is being asked.
   The order matches the daemon and viewer.py (minimum length, then ignored
   words, and the dictionary rewrites only after both), so the count here is of
   the raw characters, the same ones the floor is measured against. */
function worthSending(text = livePartial) {
  if (!text) return false;                    // nothing heard yet, so nothing to promise
  // Asked before the floor, the same place the daemon asks it. 「認証まわりを直
  // して、手直し」 goes to the draft and 「テストを実行してキャンセル」 is dropped
  // whole, and a short one closing on 手直し clears the floor yet still never
  // goes out. Only the very end counts. 「キャンセルの画面を直して」 is an
  // ordinary instruction and does get sent.
  if (endsWithTailCmd(text)) return false;
  const min = Number(tuning.min_chars) || 0;
  // Words taken off the built in ignore list get through however short they
  // are, which is the whole point of being able to take them off. Staying dark
  // for 「わかった」 would be the same lie the other way round.
  if (text.length < min && !isBackchannel(text, dictUnignore)) return false;
  // Words the person put on the ignore list themselves are dropped whatever
  // their length. The built in list is not checked here. Every word on it is
  // far under any usable minimum length, so the line above has already caught
  // them, and carrying a copy of that list into the page would leave two
  // versions of the same rule to keep in step.
  return !isBackchannel(text, dictIgnore);
}

/* Browser recognition has its own account of the same wait, kept in
   pendingBrowserSends/lastLoudAt (browserGateTick) rather than in livePartial/
   silentAt/the daemon's silence_run, so it needs its own drawing rather than
   forcing sendCountdownOn's daemon-shaped question ("is the thing we are
   still hearing worth keeping") onto a queue of clauses browser recognition
   already finished hearing. Same button, same custom property, same classes,
   read from the other side of the fork. */
function paintBrowserSendCue(now) {
  el.sendOne.classList.toggle('on', el.send.hidden);
  const item = pendingBrowserSends[0];
  if (!item) {
    el.sendOne.classList.remove('drop');
    if (el.sendOne.disabled !== true) el.sendOne.disabled = true;
    el.sendOne.style.setProperty('--r', '0');
    return;
  }
  const wait = (Number(tuning.silence_duration) || 0) * 1000;
  const dead = wait > SEND_CUE_DEAD ? SEND_CUE_DEAD : 0;
  const quietFor = now - lastLoudAt;
  const target = wait > dead ? Math.max(0, Math.min(1, (quietFor - dead) / (wait - dead))) : 1;
  el.sendOne.classList.toggle('drop', !worthSending(item.text));
  if (el.sendOne.disabled !== false) el.sendOne.disabled = false;
  el.sendOne.style.setProperty('--r', String(target));
}

function paintSendCue(now) {
  if (asrActive()) { paintBrowserSendCue(now); return; }
  const on = sendCountdownOn();
  if (!on) clearSendCountdown();          // once the conditions drop, it resets itself every frame
  // The other send button comes up whenever something is part way written
  // (text carried over from review, for one). Two paper planes on one row,
  // each sending a different thing, leave you working out which is which, so
  // the small one steps aside while the other is up. Every other time it stays
  // where it is and says by being dim that there is nothing to send. Raising
  // and sinking a target is what this screen refuses to do.
  // Shown and hidden by a class, never by the hidden attribute. Hidden takes the
  // seat away with it, and the two buttons beside it would slide every time this
  // comes and goes.
  el.sendOne.classList.toggle('on', el.send.hidden);
  const wait = (Number(tuning.silence_duration) || 0) * 1000;
  /* The pause to send goes as low as 0.3s, under the held back stretch, and
     subtracting it there leaves nothing to divide by. At those settings the
     holding back has nothing left to protect either, because every dip that
     short really is where the utterance gets cut, so filling across the whole
     wait is the honest reading. */
  const dead = wait > SEND_CUE_DEAD ? SEND_CUE_DEAD : 0;
  // Clamped at the bottom as well. All through the held back stretch the top of
  // this comes out negative, and a negative height is thrown out by the style,
  // which would leave whatever the drawing was showing before stuck there.
  /* The count runs on anything heard at all, not only on what is going out.
     An utterance that will be dropped runs the same clock and fills the same
     way, and only the direction and the color say which of the two is coming.
     Showing nothing for the dropped ones was the old reading, and it left the
     case you most need to catch looking like a screen that had gone deaf.
     The daemon's own count when it sends one, this machine's clock when it does
     not. Both are milliseconds of silence, so only where the number comes from
     changes and the reading built on it stays put. Note that the held back
     stretch now lands in audio time rather than wall clock, which lets it cover
     slightly more of a breath than before. That is the direction it was always
     meant to work in. */
  const ran = cueOn ? cueRun * 1000 : (silentAt ? now - silentAt : 0);
  const target = (ran > 0 && wait > 0 && livePartial)
    ? Math.max(0, Math.min(1, (ran - dead) / (wait - dead)))
    : 0;
  /* Eased only on the daemon's side of the fork. The clock on the other side
     already moves every frame and has nothing in it to smooth away. */
  let r = cueOn ? stepCue(now, target) : target;
  /* Landed the instant the count that actually arrived reaches the wait, not
     when the eased drawing catches up to it. That instant is the one the settle
     is made on, and easing into it would leave the ring at 0.97 as the card
     moves, which is the very miss this is here to close. */
  if (target >= 1) r = cueShown = 1;
  /* Which face it wears. Set only once the fill is actually moving, so nothing
     changes color while you are still talking or across the breath the held
     back stretch is there to absorb. Under the fill both faces look the same
     anyway, an empty ring.
     Frozen at the moment it fills. What comes in after that belongs to whatever
     is said next, and letting it still reach here would flip a finished drawing
     over to the other face while it waits to be replaced. */
  if (r >= 1 && !cueFull) { cueFull = true; cueFullDrop = !worthSending(); cueFullAt = now; }
  if (cueFull) {
    r = 1;
    /* What ends the hold is the utterance landing, and the two faces land
       differently. The one going out lands as a line in the log, and that path
       runs clearSendCountdown where the socket reads it. The one going away
       never produces a line at all, so what marks it is the live text going
       empty underneath, which is the daemon clearing what it just threw out. */
    if ((cueFullDrop && !livePartial) || now - cueFullAt > CUE_HOLD_MAX) {
      clearSendCountdown();
      r = 0;
    }
  }
  el.sendOne.classList.toggle('drop', cueFull ? cueFullDrop : (r > 0 && !worthSending()));
  /* Whether it can be pressed asks a different question from whether the ring
     fills. The fill says what happens if you say nothing, so every narrowing
     the daemon applies counts toward it. A press says you meant this one, and
     then the only thing that matters is that there is something to send.
     「スタート」 at four characters never clears a fifteen character floor, so
     the ring runs red on it, and it still goes out the moment you press.
     Ending on the word that cancels is the same. Left alone it is thrown away,
     but reaching for send is the opposite of meaning to throw it away, so the
     press wins.
     It goes dim across the hold. The daemon settled this one already, so a
     press lands on an utterance that no longer exists and nothing happens,
     and a button that does nothing is exactly what this screen refuses to
     show. Dimming there is also what it did before the hold existed, when the
     whole count was thrown away the moment the ring filled. */
  const canSend = on && livePartial !== '' && !cueFull;
  if (el.sendOne.disabled === canSend) el.sendOne.disabled = !canSend;
  /* Handed over as a bare fraction, not rounded to a step. The stylesheet turns
     it into where the gradient's edge sits. Rounding it to a hundredth would put
     a floor under how small a move can be, and at three seconds of silence that
     floor is 30ms of travel, which shows as a stutter. What does carry over
     between frames is the easing above, and that is there to take a step out,
     not to put one in. */
  el.sendOne.style.setProperty('--r', String(r));
}

/* Ease toward the count instead of taking it whole, the way stepMicLevel does
   for the fill inside the mic. Same guards for the same reasons. No frames
   arrive while the tab sits in the background, so the whole gap taken as it
   stands would jump the ring the instant you come back, and the clock can tick
   out of order, which flips the sign and runs it away. */
function stepCue(now, target) {
  const dt = cueShownAt ? Math.min(Math.max((now - cueShownAt) / 1000, 0), 0.1) : 0.1;
  cueShownAt = now;
  cueShown += (target - cueShown) * (1 - Math.exp(-dt / CUE_EASE));
  return cueShown;
}

function setRoute(next) {
  const prev = route;
  const revision = ++routeRevision;
  route = next;
  resetBrowserGesture();
  if (next !== 'off') lastMode = next;
  paint();                            // show it the instant it is pressed
  inFlight = true;
  const task = routeQueue.then(() => changeRoute(next, prev, revision, true));
  routeQueue = task.catch(() => {});
  return task;
}

async function changeRoute(next, prev, revision, syncServer) {
  let applied = false;
  try {
    if (revision !== routeRevision) return;
    const w = ROUTE[next];
    if (prev === 'off' && next !== 'off' && engineOnish() && !asrActive()) {
      const discarded = await discardCurrent({announce: false});
      if (!discarded) throw new Error('Could not discard current utterance');
      if (revision !== routeRevision) return;
    }
    if (syncServer) {
      // ROUTE.off carries paused:false as a fixed shape for the table, not as
      // the daemon's real hold/live state. Posting that verbatim on mute would
      // reset the daemon to live under it, and its own echo of that value is
      // what the 'paused' handler above reads lastMode back from while muted,
      // so hold silently became live by the time you unmuted. Muting from hold
      // has to leave the daemon holding, so unmute lands where it left off.
      const paused = next === 'off' ? ROUTE[lastMode].paused : w.paused;
      await post('/api/pause', {paused});
      if (revision !== routeRevision) return;
      await post('/api/mute', {muted: w.muted});
    }
    if (revision !== routeRevision) return;
    applyRouteSideEffects(next);
    applied = true;
  } catch (err) {
    if (revision !== routeRevision) return;
    let rollbackError = null;
    if (!syncServer && prev === 'off' && next !== 'off') {
      try {
        const response = await post('/api/mute', {muted: true});
        if (!response.ok) rollbackError = new Error(`HTTP ${response.status}`);
      } catch (rollbackErr) { rollbackError = rollbackErr; }
    }
    route = prev;
    if (prev !== 'off') lastMode = prev;
    // editThisOne sets this before this call ever starts (always a live ->
    // hold attempt, its own guard rules out any other prev), and nothing else
    // clears it once the attempt it was guarding never actually landed. Left
    // set, route reads 'live' again but oneShot still reads true, and every
    // check gating on both together (el.tray.onclick, editOnce.disabled) goes
    // on refusing a retry until a manual press of live/hold happens to clear
    // it by coincidence, which reads as "it only works after switching by
    // hand once" (a failed one-shot attempt right as the engine was still
    // booting is the case this was caught from).
    //
    // Narrowed to that exact shape (prev live, next hold) so a *different*
    // rollback does not clear it out from under a one-shot edit already in
    // progress. Muting (segOff) does not pass through live/hold's own
    // oneShot=false first the way segLive/segHold do, so pressing mute while
    // mid-edit and having that specific request fail would otherwise erase
    // oneShot too, even though route rolls back to the 'hold' the edit was
    // still legitimately sitting in.
    if (prev === 'live' && next === 'hold') oneShot = false;
    paint();
    applyRouteSideEffects(prev);
    const message = rollbackError ? `${err.message} (${rollbackError.message})` : err.message;
    el.hint.textContent = t('switchFailed', {err: message});
  } finally {
    if (revision === routeRevision) {
      inFlight = false;
      if (applied) refreshState();
    }
  }
}

function setRemoteRoute(next) {
  const prev = route;
  const revision = ++routeRevision;
  route = next;
  resetBrowserGesture();
  if (next !== 'off') lastMode = next;
  paint();
  inFlight = true;
  const task = routeQueue.then(() => changeRoute(next, prev, revision, false));
  routeQueue = task.catch(() => {});
  return task;
}

/* Cleaning up after switching off. A switch made by voice runs through the
   same path. Skip it and the screen says off while the browser's microphone is
   still open, and the recording indicator on the tab stays lit. */
function applyRouteSideEffects(next) {
  // While paused, let go of the browser's microphone as well (leave no sense
  // of recording behind). Stop recognition along with it. Leave it running and
  // the screen says nothing is being recorded while the audio alone keeps going
  // out.
  if (next === 'off') {
    if (recWanted) { asrPausedByRoute = true; stopRecognition(); }
  } else {
    resetBrowserGesture();
    // Coming back from off (by hand or by voice) always counts as a voice just
    // heard. Otherwise the idle-mute clock, still holding the timestamp from
    // before the mute, finds itself already past its own deadline and mutes
    // again within the next 5-second check, sometimes just seconds after the
    // person turned it back on.
    lastVoiceAt = performance.now();
    if (vizArmed) startViz(vizDeviceLabel());
    if (asrPausedByRoute) {
      asrPausedByRoute = false; recWanted = true; startRecognition();
    }
  }
  syncVizCapture();
  paintBrowserAsr();
}

/* The floating window is a separate document, so writing our title never
   reaches it. The small window's title shows not only in Alt+Tab but along the
   top edge of the window itself. Without keeping the two in step, it goes on
   saying it is sending while you are actually paused. */
function setTitle(text) {
  document.title = text;
  const w = floatingWindow();
  if (w) {
    try { w.document.title = text; } catch { /* on its way closed */ }
  }
}

/* The one line that answers a signal. It is held for a while so the paint()
   every 3 seconds does not write over it. You are operating by voice because
   you are not watching the screen, so a line you miss leaves nothing behind. */
let hintHoldUntil = 0;
function say(text, sec = 6) {
  el.hint.textContent = text;
  hintHoldUntil = performance.now() + sec * 1000;
}

// "Say X to come back" is only true where saying it can still be heard. This
// browser's own recognition cuts the mic the instant it mutes (unlike the
// daemon, which keeps listening for the word on purpose), so under it the
// one true way back is the button, not the word the other engines can still
// hear.
const muteHint = () => t(asrChosen ? 'voiceMutedBrowser' : 'voiceMuted');

/* Show the word taken as a signal in the live transcript box, lit up as it is.
   Watching the very word you said take on color tells you what happened at a
   glance, better than a sentence explaining that it was handled as a signal. */
let flashTimer = null;
/* Words in the dictionary are swapped in on the spot, even mid-recognition.
   If 「クロードコード」 sits there and piles up, reading it back before sending
   still tells you nothing about what will arrive.

   **Only the look is swapped.** The body that gets sent is rebuilt by the
   server along the same path the daemon takes. Recognition keeps correcting the
   tail until you finish speaking, so carrying around characters we touched here
   would stop those corrections from landing. Rebuild from the raw text every
   time and it follows along even when you say it over. */
let dictPairs = [];             // [what was heard, what it becomes], longest first
let dictIgnore = new Set();     // said on its own, this one is not sent
let dictUnignore = new Set();   // taken off the built in ignore list, so short but still sent
async function loadDictPairs() {
  try {
    const d = await (await fetch('/api/dictionary?scope=effective')).json();
    dictPairs = Object.entries(d.replace || {})
      .filter(([k, v]) => k && v)
      .sort((a, b) => b[0].length - a[0].length);   // match the longer words first
    // The same read already carries both lists the drawing in the corner needs,
    // so it costs no second request and there is no second thing to keep fresh.
    // The two are tidied differently on purpose, because the daemon tidies them
    // differently. is_noise takes the ignore list as it stands and only lowers
    // the case, so an entry saved as 「はい。」 never matches anything there and
    // the utterance really is sent. Trimming it here would go dark on a word
    // that goes out. is_allowed_short does strip the punctuation off its list,
    // so that one gets the same treatment here.
    dictIgnore = new Set((d.ignore || []).map(w => w.trim().toLowerCase()).filter(Boolean));
    dictUnignore = new Set((d.unignore || []).map(cueCore).filter(Boolean));
  } catch { /* if it cannot be fetched, show the text plain */ }
}
function withDict(text) {
  for (const [from, to] of dictPairs) text = text.split(from).join(to);
  return text;
}

// The color a fired command flashes in (flashCommand below), reused here so the
// preview and the confirmation read as the same signal a beat apart.
const TAIL_PREVIEW_CLASS = {cancel_tail: 'warn', hold_tail: 'hold', mute: 'warn'};

/* Started equal to SEND_CUE_DEAD (the ring's own hold-back), but that read as
   flickery, cancel is often still settling on its own tail right after being
   said, as the recognizer keeps revising. Held longer on purpose, a slower,
   calmer signal than the ring's fill, not tied to it. */
const TAIL_MARK_DELAY = 800;
let tailMarkTimer = null, tailMarkKey = null, tailMarkPending = null;

/* Draws the live partial, lighting up the trigger word once it has held the
   tail for TAIL_MARK_DELAY. Called from both places text arrives, the
   local-engine partial and the browser SpeechRecognition interim result, so
   the two read identically. */
function paintStream(s) {
  const match = s ? matchingTailWord(s) : null;
  const key = match ? match.id + ' ' + match.word : null;
  tailMarkPending = {s, match};
  if (key !== tailMarkKey) {
    tailMarkKey = key;
    clearTimeout(tailMarkTimer);
    tailMarkTimer = match ? setTimeout(showTailMark, TAIL_MARK_DELAY) : null;
  }
  if (match && !tailMarkTimer) { renderTailMark(s, match); return; }
  el.stream.textContent = s;
}

function showTailMark() {
  tailMarkTimer = null;
  // The match this fires for might have moved on by the time the delay is up
  // (someone kept talking past it), tailMarkPending always holds the latest.
  if (tailMarkPending && tailMarkPending.match)
    renderTailMark(tailMarkPending.s, tailMarkPending.match);
}

function renderTailMark(s, match) {
  const trimmed = s.replace(TAIL_TRIM, '');
  const cut = trimmed.length - match.word.length;
  const mark = document.createElement('mark');
  mark.className = 'tailcmd ' + (TAIL_PREVIEW_CLASS[match.id] || 'warn');
  mark.textContent = s.slice(cut, trimmed.length);
  el.stream.replaceChildren(document.createTextNode(s.slice(0, cut)), mark,
    document.createTextNode(s.slice(trimmed.length)));
}

// The live transcript has a cap on its height. Talk long enough and it flows
// upward, so scroll down far enough to keep the tail you are speaking in view.
function streamTail() {
  const box = el.stream.parentElement;      // the .stream frame (#stream is the span inside it)
  if (box) box.scrollTop = box.scrollHeight;
}

function flashCommand(text, kind) {
  if (!text) return;
  // A held-back preview mark (paintStream) might still be waiting out its
  // SEND_CUE_DEAD timer, and firing after this would overwrite the confirmed
  // flash with a stale preview.
  clearTimeout(tailMarkTimer); tailMarkTimer = null; tailMarkKey = null; tailMarkPending = null;
  const mark = document.createElement('mark');
  mark.className = 'cmd ' + (kind || 'live');
  mark.textContent = text;
  el.stream.replaceChildren(mark);
  el.tray.classList.remove('idle');
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    // If the next utterance arrived in the meantime, leave it alone
    if (el.stream.firstChild === mark) {
      el.stream.textContent = '';
      el.tray.classList.add('idle');
      paintTinyButtons();
    }
  }, 2200);
}

/* A short sound, played only when the switch came by voice.
   You are operating by voice because you are not watching the screen, so a
   change you can only see does not tell you it got through. Following the call
   apps, switching off falls in pitch and coming back rises (which way it went
   is clear from the sound alone). */
const CHIME = {
  down: [[680, 440]],              // switched off
  up:   [[440, 680]],              // switched back on
  ok:   [[620, 620], [880, 880]],  // where speech goes changed (two notes to tell it apart)
  err:  [[300, 220]],              // said, and nothing came of it
};
let chimeCtx = null;
function chime(kind) {
  const seq = CHIME[kind];
  if (!seq) return;
  try {
    chimeCtx = chimeCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (chimeCtx.state === 'suspended') chimeCtx.resume();
    seq.forEach(([from, to], i) => {
      const t0 = chimeCtx.currentTime + i * 0.13;
      const osc = chimeCtx.createOscillator();
      const gain = chimeCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(from, t0);
      osc.frequency.exponentialRampToValueAtTime(to, t0 + 0.10);
      // A straight ramp clicks at the cut, so both ends are pinched in
      gain.gain.setValueAtTime(0.0001, t0);
      gain.gain.exponentialRampToValueAtTime(0.10, t0 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.16);
      osc.connect(gain).connect(chimeCtx.destination);
      osc.start(t0);
      osc.stop(t0 + 0.18);
    });
  } catch { /* where no sound can play, give up quietly (the display has already changed) */ }
}

// Choosing a mode yourself clears both Edit this one and the line from Claude
el.segLive.onclick = () => { oneShot = false; el.note.hidden = true; setRoute('live'); };
el.segHold.onclick = () => { oneShot = false; el.note.hidden = true; setRoute('hold'); };
el.segOff.onclick = () => setRoute(route === 'off' ? lastMode : 'off');

/* The small mics in the sheet headings do the same as the big one. While a
   sheet is up it covers the main screen whole, and until now the only way to
   cut the mic off from in there was to leave, cut it, and come back. Asked for
   by the person using it, after settling a setting and wanting to go quiet
   without losing their place.
   They run el.segOff rather than setRoute so the one path stays the one path.
   Everything that follows switching off (letting go of the browser mic,
   stopping recognition) hangs off that click. */
for (const b of [el.miniMic, el.helpMini]) b.onclick = () => el.segOff.click();

/* ── Talking to the server ──────────────── */
function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);

  ws.onopen = () => {
    dropBarriers.clear();
    refreshState();
  };

  ws.onmessage = ev => {
    let message = null;
    try { message = JSON.parse(ev.data); } catch {}
    if (message?.drop_done) dropBarriers.delete(message.drop_done);
    const packet = {ev, message, number: ++wsMessageNumber,
                    discardInProgress: discardInProgress > 0};
    wsMessageQueue = wsMessageQueue
      .then(() => handleWsMessage(packet))
      .catch(() => {});
  };

  ws.onclose = ev => {
    // If the server folded up (voice mode ended), stop recognition too.
    // Only trying to reconnect leaves the microphone open when you thought it
    // was stopped, and the audio keeps going out. 1001 = GOING_AWAY.
    if (ev.code === 1001) {
      dropBarriers.clear();
      stopRecognition();
      setState('off', t('statusEnded'));
      el.hint.textContent = t('hintEnded');
      return;
    }
    dropBarriers.clear();
    setState('down', t('statusDown'));
    setTimeout(connect, 2000);
  };
}

async function handleWsMessage({ev, message, number, discardInProgress: wasDiscarding}) {
    await routeQueue;
    const m = message || JSON.parse(ev.data);
    if (m.drop_done) return;
    const result = 'partial' in m || 'held' in m || m.text != null;
    if (result && (wasDiscarding || number <= discardResultCutoff || dropBarriers.size)) return;

    if ('level' in m) {
      // Catch only the moments voice starts and breaks off. level is not sent
      // when the value has not changed, but the level still wavers through the
      // silence, so we spot the turning points ourselves.
      if (m.speaking !== daemonSpeaking) {
        if (m.speaking) {
          voiceSeen = sendCountdownOn(); silentAt = 0;
          // Voice again means the ring starts over, whether that is a breath in
          // the middle of a sentence or the next utterance beginning while the
          // last one is still being settled. Not clearSendCountdown, which
          // would take the live text with it and dim send mid-sentence.
          cueFull = false; cueShown = 0;
        } else if (voiceSeen) silentAt = performance.now();
      }
      takeSilenceRun(m);
      daemonLevel = m.level; daemonSpeaking = m.speaking;
      el.meterFill.classList.toggle('on', m.speaking);
      paintGauge();
      return;      // falling through to the else below treats it as an utterance and breaks things
    }
    if ('muted' in m) {
      // This switches by voice as well (the daemon hears 「ミュート」 and
      // writes the file). When you press it yourself, route was updated the
      // instant you pressed, so here it matches and nothing happens, which
      // means it only fires when the change came from outside.
      if (m.muted !== (route === 'off')) {
        await setRemoteRoute(m.muted ? 'off' : lastMode);
      }
      return;
    }
    if ('voice_cmd' in m) {
      // A signal is never sent as an utterance, so this is where we say it got
      // through. Whatever was already sitting there when the page opened
      // (first) is not something that just happened.
      const c = m.voice_cmd || {};
      // A signal settles the utterance it was spoken in, and no line ever
      // reaches the log for it, so this is the only word that the ring holding
      // itself full is going to get.
      clearSendCountdown();
      if (c.kind === 'mute') {
        chime('down'); say(muteHint());             flashCommand(c.said, 'warn');
      } else if (c.kind === 'unmute') {
        chime('up');   say(t('voiceUnmuted'));     flashCommand(c.said, 'live');
      } else if (c.kind === 'route') {
        chime('ok');   say(t('voiceRoute', {name: c.label}));
        flashCommand(c.said, 'live');
        loadListeners();
      } else if (c.kind === 'mode_live') {
        chime('up');   say(t('voiceLive'));        flashCommand(c.said, 'live');
      } else if (c.kind === 'mode_hold') {
        chime('down'); say(t('voiceHold'));        flashCommand(c.said, 'hold');
      } else if (c.kind === 'held') {
        chime('down'); say(t('voiceHeld'));  flashCommand(c.said, 'hold');
      } else if (c.kind === 'cancelled') {
        chime('err');  say(t('voiceCancelled'));  flashCommand(c.said, 'warn');
      } else if (c.kind === 'route_missing') {
        chime('err');  say(t('voiceRouteMissing', {n: c.label}));
        flashCommand(c.said, 'warn');
      }
      return;
    }
    if ('paused' in m) {
      // This switches by voice as well. While muted the display can stay on off, so leave it alone.
      if (route !== 'off') {
        const next = m.paused ? 'hold' : 'live';
        if (next !== route) { route = lastMode = next; oneShot = false; paint(); }
      } else {
        lastMode = m.paused ? 'hold' : 'live';
      }
      return;
    }
    if ('mic_active' in m) {
      // Confirmation that the switch actually completed on the daemon side.
      // Unlike the hopeful display we put up the instant it was pressed, only
      // once this arrives can we say it really switched.
      if (micConfirmDevice && m.mic_active === micConfirmDevice) {
        clearTimeout(micConfirmTimer);
        const opt = [...el.mic.options].find(o => o.value === m.mic_active);
        el.hint.textContent = t('micSwitched', {name: opt ? opt.textContent : m.mic_active});
        micConfirmDevice = null;
        setTimeout(() => paint(), 2500);
      }
      return;
    }
    if ('partial' in m) {
      // Keep the text as it came as well. The minimum length is measured before
      // the dictionary rewrites anything, so counting the rewritten characters
      // here would let the drawing and the daemon disagree over the same words.
      livePartial = m.partial.trim();
      const s = withDict(livePartial);
      paintStream(s);
      el.tray.classList.toggle('idle', !s);
      streamTail();
      paintTinyButtons();

    } else if ('held' in m) {
      // An utterance from while it was holding. It is only appended at the
      // end, so nothing breaks if you are in the middle of editing.
      // On the review side the line below never shows in the first place, so
      // clearing it here is only to be safe.
      clearSendCountdown();
      appendHeld(m.held);

    } else if (m.text != null) {
      clearSendCountdown();   // that is one utterance done. Counting starts again with the next voice
      // Only rows carrying a body go into the log. Every time another control
      // message was added (level / muted / paused / voice_cmd and so on), an
      // older screen would line it up as an utterance and make an empty card.
      // Quietly dropping keys it does not know is the safer way.
      addEntry(m);
      el.stream.textContent = '';
      el.tray.classList.add('idle');
    }
}

// Grow the height to fit the contents (so nothing scrolls inside)
function grow() {
  el.draft.style.height = 'auto';
  el.draft.style.height = el.draft.scrollHeight + 'px';
}

// Append a held utterance at the end. The caret position and your edits are kept.
function appendHeld(text) {
  text = (text || '').trim();
  if (!text) return;
  // Something arriving outside review mode never opens the edit box (that display would have no explanation)
  if (route !== 'hold') return;
  const cur = el.draft.value;
  el.draft.value = cur ? cur.replace(/\s*$/, '') + '\n' + text : text;
  el.draftTime.textContent = new Date().toLocaleTimeString(
    timeLocale(), {hour12:false});
  paintDraft();
  grow();
  // Right after appending, keep the tail in view (unless you are editing)
  if (uiDoc().activeElement !== el.draft) el.draft.scrollTop = el.draft.scrollHeight;
}

/* ── The recognition engine, on and off ──
   Stopping it gives back whatever that engine was holding. Whisper gives back
   the memory the model takes, Apple gives back the microphone itself (it never
   held memory to begin with). How much comes back depends on the model chosen,
   so no number is put on screen.
   Four states, 'on' / 'booting' / 'stopping' / 'off'. Flipping straight between
   on and off the instant it is pressed would change the label before anything
   had finished, so the in-between states sit in the middle. */
let engine = 'on';
const engineOnish = () => engine === 'on';
/* The engine currently selected. Whether the button shows, and what comes back
   when you stop it, are both decided by this. loadEngines() puts the value the
   server remembers in here every 5 seconds. It stays empty until that can be
   read, and while it is empty we say nothing about what comes back (there is no
   way to know). */
let chosenEngine = '';

let startedAt = 0;     // when start was pressed
const BOOT_SEC = 40;   // measured at roughly 40 seconds
let tick = null;

function paintPower() {
  const busy = engine === 'booting' || engine === 'stopping';
  // Back when this sat in the header as a round icon, it got mistaken for
  // muting the microphone (a power drawing reads as switching off). It moved
  // into settings, and what it does is written out in words.
  el.power.classList.toggle('busy', busy);
  el.powerLabel.textContent = t(engine === 'off' ? 'powerStart' : 'powerStop');
  el.power.disabled = busy;

  if (engine === 'booting' && performance.now() > hintHoldUntil) {
    const sec = (Date.now() - startedAt) / 1000;
    const left = Math.max(0, Math.ceil(BOOT_SEC - sec));
    el.hint.textContent = left > 0 ? t('bootingLeft', {n: left}) : t('bootingSoon');
  }

  // With nothing running, choosing a mode means nothing.
  // Unless the browser is doing the recognizing, in which case it still works
  // with the daemon stopped.
  const usable = engineOnish() || asrActive();
  for (const b of [el.segLive, el.segHold, el.segOff, el.mic,
                   el.miniMic, el.helpMini]) b.disabled = !usable;

  /* A button that does nothing when pressed is not shown. With browser
     recognition there is nothing to load, and pressing it just ends with
     engine-start saying 「ブラウザ認識が選ばれています」.
     For Apple and Whisper it always shows. Starting it up again after a stop is
     also the only route left on screen (picking the engine again is no use for
     recovery, since choosing the same one twice fires no onchange). */
  el.powerRow.hidden = chosenEngine === BROWSER_ENGINE;
  el.powerNote.textContent =
      engine === 'off'                   ? t('powerNoteStart')
    : chosenEngine === WHISPER_ENGINE    ? t('powerNoteWhisper')
    : chosenEngine === APPLE_ENGINE      ? t('powerNoteApple')
    : '';
}

el.power.onclick = async () => {
  const start = engine === 'off';
  if (start) {
    engine = 'booting';
    startedAt = Date.now();
    setState('down', t('statusBooting'));
    clearInterval(tick);
    tick = setInterval(() => { if (engine === 'booting') paintPower(); }, 1000);
  } else {
    engine = 'stopping';
    clearInterval(tick);
    setState('down', t('statusStopped'));
    el.hint.textContent = t('hintStopping');
  }
  paintPower();
  await post('/api/engine', {running: start});
  refreshState();
};

let seeded = false;   // restores what had piled up, once, on reload
let uiStamp = 0;      // the mtime of the screen file at the moment it was loaded
let wayland = false;  // whether the daemon's own session is Wayland (floating cannot stay on top there)

el.fresh.onclick = () => {
  const w = floatingWindow();
  if (w) {
    try { w.close(); } catch { disableFloat(); }
  }
  location.reload();
};

async function refreshState() {
  const revision = routeRevision;
  if (inFlight) return;               // never overwrite mid-switch
  try {
    const s = await (await fetch('/api/state')).json();
    if (revision !== routeRevision) return;

    // Say something when the screen file has been replaced. The floating
    // window has no way to reload, so this is where you get back from.
    if (s.ui) {
      if (uiStamp === 0) uiStamp = s.ui;
      else if (s.ui !== uiStamp) el.fresh.hidden = false;
    }
    wayland = !!s.wayland;

    if (typeof s.engine === 'boolean') {
      if (s.engine) {
        if (engine !== 'on') {
          clearInterval(tick);
          if (performance.now() > hintHoldUntil) el.hint.textContent = '';
        }
        engine = 'on';
      } else if (s.loading) {
        // so that starting up is visible even when another tab was the one that pressed
        if (engine !== 'booting') {
          engine = 'booting';
          startedAt = Date.now();
          clearInterval(tick);
          tick = setInterval(() => { if (engine === 'booting') paintPower(); }, 1000);
        }
      } else if (engine === 'booting' && Date.now() - startedAt < 12000) {
        // Right after pressing, the process is sometimes not visible yet.
        // Dropping to 'off' here would send the display back to Stopped.
      } else {
        clearInterval(tick);
        engine = 'off';
      }

      paintPower();
      if (engine === 'booting') { setState('down', t('statusBooting')); return; }
      if (engine === 'off' && !asrActive()) {
        setState('off', t('statusStopped'));
        el.hint.textContent = t('hintStopped');
        return;
      }
    }

    // The setting for using several machines (another screen can change it).
    // Never touched while you are typing.
    if (!machineDirty) {
      el.multiOn.checked = !!s.multiMachine;
      el.machineName.value = s.machineName || '';
      paintMachine();
    }

    // The line for when Claude did the switching. Nothing is attached when you pressed it yourself.
    el.note.textContent = s.note || '';
    el.note.hidden = !s.note;

    if (!armPending) {
      route = s.muted ? 'off' : (s.paused ? 'hold' : 'live');
      if (route !== 'off') lastMode = route;
    }
    paint();

    // Restore what was collected so a reload does not lose it (never touched while you are typing)
    if (!seeded && Array.isArray(s.held) && s.held.length && !el.draft.value.trim()) {
      el.draft.value = s.held.map(r => r.text).join('\n');
      paintDraft();
      grow();
    }
    seeded = true;
    paintDraft();
    if (!el.draft.hidden) grow();
  } catch {
    setState('down', t('statusDown'));
  }
}

/* ── Send and discard ───────────────────── */
el.send.onclick = async () => {
  const text = el.draft.value.trim();
  if (!text) return;
  await post('/api/send', {text, edited: draftTouched});
  el.draft.value = '';
  draftTouched = false;
  grow();
  paintDraft();
  endOneShot();
};

// What you discard can be brought back once (a confirm dialog every time is a nuisance)
let lastDiscarded = '';
// Kept alongside it so bringing it back does not lose the edited stamp too
let lastDiscardedTouched = false;

el.discard.onclick = async () => {
  lastDiscarded = el.draft.value;
  lastDiscardedTouched = draftTouched;
  await post('/api/discard');
  el.draft.value = '';
  draftTouched = false;
  grow();
  paintDraft();
  if (lastDiscarded.trim()) {
    el.hint.textContent = t('discarded');
    const undo = document.createElement('button');
    undo.textContent = t('undo');
    undo.onclick = () => {
      el.draft.value = lastDiscarded;
      draftTouched = lastDiscardedTouched;
      paintDraft();
      grow();
      el.hint.textContent = '';
    };
    el.hint.appendChild(undo);
  }
  endOneShot();
};

/* Stay on instant and route just this one utterance to review.
   For when you spot a word that came out wrong, or want to fix only this one.
   The daemon checks whether it is holding at the moment an utterance settles,
   so pressing while you are still talking catches what you are saying now. */
async function editThisOne() {
  if (route === 'hold') return;          // already in review mode
  oneShot = true;
  await setRoute('hold');
  el.hint.textContent = t('hintOnce');
  // In a small window the opened box and the send button hang off the bottom.
  // 'nearest' moves only as far as it has to, which leaves the send button
  // stuck at the fold.
  el.tray.scrollIntoView({block: 'end'});
}

el.editOnce.onclick = editThisOne;

/* Throw away a misspoken utterance before it goes out.
   When the daemon is doing the recognizing, we hand over the time it was
   pressed and let that side decide. It cuts the audio right there, so you can
   speak the correction straight away and it comes through as a fresh
   utterance. Clearing the screen alone would not do that, since the phrase in
   progress would keep growing and take the correction down with it.
   With browser recognition, we drop the next one that settles ourselves. */
let dropNextLocal = false;
function newDropId() {
  return globalThis.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

function discardCurrent(options) {
  const task = discardQueue.then(() => discardCurrentNow(options));
  discardQueue = task.catch(() => {});
  return task;
}

async function discardCurrentNow({announce = true} = {}) {
  discardResultCutoff = Math.max(discardResultCutoff, wsMessageNumber);
  discardInProgress++;
  try {
    if (asrActive()) {
      el.stream.textContent = '';
      clearSendCountdown();
      el.tray.classList.add('idle');
      // Whatever was already finalized and sitting in the queue, waiting out
      // its own quiet stretch, is exactly what "discard the current one" means
      // too. Left in place it would still go out once the room fell quiet
      // enough, after the person had already asked for it to be thrown away.
      pendingBrowserSends = [];
      // Clearing the screen alone brings it right back. Recognition keeps
      // putting out everything up to that point as an interim result, so we fold
      // up the whole current session and empty what has piled up.
      dropNextLocal = true;
      const r = rec;
      rec = null; recRunning = false;
      if (r) { try { r.abort(); } catch {} }
      if (recWanted) setTimeout(startRecognition, 120);
    } else {
      const id = newDropId();
      dropBarriers.add(id);
      let response;
      try {
        response = await post('/api/drop-current', {id});
        const body = await response.json();
        if (!response.ok || body.ok !== true || body.id !== id) {
          dropBarriers.delete(id);
          return false;
        }
      } catch {
        dropBarriers.delete(id);
        return false;
      }
      discardResultCutoff = Math.max(discardResultCutoff, wsMessageNumber);
      el.stream.textContent = '';
      clearSendCountdown();
      el.tray.classList.add('idle');
    }
    if (announce) say(t('droppedOne'), 4);
    paint();
    return true;
  } finally {
    discardInProgress--;
  }
}

el.dropOne.onclick = () => discardCurrent();

/* Send this one now, without sitting out the rest of the wait.
   We hand over the time it was pressed and let the daemon decide, the mirror of
   what /api/drop-current does for throwing one away. It settles the utterance in
   progress as if the silence had run out, and marks it as one that was asked
   for, which is what carries it past the narrowing built for lines that leave on
   their own (「スタート」 under the floor on length, a word on the ignore list, a
   closing 「キャンセル」). Doing it in the page instead, by sending
   el.stream.textContent, would race the recognizer and post a body that the
   daemon has not finished writing.
   The ring stops here because it is about to be answered, and clearing it takes
   the button dark on the next frame on its own (paintSendCue reads the same
   values). The live line is left alone, since the daemon wipes it the moment the
   utterance settles and the card that appears is the real word on whether it
   went.
   Whether it can be pressed at all is settled in paintSendCue, and it only ever
   comes up on the side that goes straight through, while the daemon is
   listening, with something heard. So there is no second guard to write here. */
async function sendThisOne() {
  // Browser recognition has already decided the words (isFinal already
  // fired), there is nothing left for the daemon to settle, so the press
  // just skips the rest of the wait for whatever is sitting in the queue.
  if (asrActive()) { flushPendingBrowserSends(); return; }
  clearSendCountdown();
  try { await post('/api/send-current'); } catch {}
}
el.sendOne.onclick = sendThisOne;

/* Pressing anywhere on the draft card routes it to review. Make people aim at
   the live transcript and there is nowhere to press while nothing has shown up
   yet (bracing yourself before you misspeak is the real use for this, so it has
   to be pressable precisely when it is empty). */
el.tray.onclick = e => {
  if (route !== 'live' || oneShot) return;
  if (e.target.closest('button, textarea, input, select, a')) return;
  editThisOne();
};

// Once it is sent or discarded, go back to the mode it came from
async function endOneShot() {
  if (!oneShot) return;
  oneShot = false;
  await setRoute('live');
}
// cancelOnce is this same door, just opened by hand instead of by sending or
// discarding. Whatever is sitting in the edit box is left exactly as it was,
// so nothing spoken is lost, only the "editing just this one" framing is.
el.cancelOnce.onclick = endOneShot;

/* After going into review, pressing outside with nothing there counts as
   backing out. Bracing yourself while empty is the real use for this, so we
   only go back when both the draft and the live transcript are empty. With
   anything in either one, pressing outside keeps it held.
   The listener goes on in three places because el.page and el.sheet move
   wholesale into the floating window (the same listener runs in either
   document), while in a wide tab the margin outside the panel only ever reaches
   document. Even if it runs twice, the second pass does nothing once oneShot is
   down. */
function leaveOneShotIfEmpty(e) {
  if (!oneShot) return;
  if (e.target.closest('#tray')) return;      // inside the card does not count as outside
  if (el.draft.value.trim() || el.stream.textContent.trim()) return;
  endOneShot();
  say(t('oneShotOff'), 4);
}
for (const n of [el.page, el.sheet, el.helpSheet, document])
  n.addEventListener('click', leaveOneShotIfEmpty);

el.draft.addEventListener('input', () => { draftTouched = true; grow(); });
// Ctrl+Enter sends
el.draft.addEventListener('keydown', e => {
  if (e.isComposing || e.keyCode === 229) return;   // the input method still has it
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); el.send.click(); }
});

/* ── Moving between the screens ──────────
   Four screens sit behind the one row of buttons, and the row itself never
   leaves. It is a single node, moved into the heading of whichever screen is
   up, so a button never changes seat as you go between them.

   Where you are is painted onto the button (this screen says everything with
   color and fill, never by taking a thing away). The lit one still does
   something when pressed, which is to close and put you back on the main
   screen. A button that does nothing when pressed is not shown here, and that
   goes for a lit one too.

   Settings and the dictionary are two panes of one sheet rather than two
   sheets. Run as one page they go past 1400px and the dictionary ends up
   buried below the fold. Split as panes, the heading and the mic in it are
   built once and the dictionary keeps every last one of its own parts
   untouched. */
let sheetPane = 'basic';                  // which of the two the settings sheet is showing

// Which of the four you are looking at. '' is the main screen.
const navWhere = () => !el.sheet.hidden ? sheetPane
                     : !el.helpSheet.hidden ? 'help' : '';

/* Put the row of buttons in the heading that is showing. Moving the node drops
   focus (the browser takes it off anything leaving the document, even for the
   instant it takes to re-insert), so it is handed back. Without that, moving
   by keyboard lands you on nothing and the next Tab starts over from the top. */
function placeNav() {
  const head = !el.sheet.hidden ? el.sheetHead
             : !el.helpSheet.hidden ? el.helpHead
             : el.pageHead;
  if (el.navRow.parentNode === head) return;
  const d = uiDoc();
  const keep = el.navRow.contains(d.activeElement) ? d.activeElement : null;
  head.append(el.navRow);
  if (keep) keep.focus({preventScroll: true});
}

function paintNav() {
  const where = navWhere();
  for (const [k, b] of [['help', el.openHelp], ['dict', el.openDict],
                        ['basic', el.openSettings]]) {
    b.classList.toggle('on', where === k);
    b.setAttribute('aria-pressed', String(where === k));
  }
}

function showSheetPane(which) {
  const basic = which !== 'dict';
  sheetPane = basic ? 'basic' : 'dict';
  el.paneBasic.hidden = !basic;
  el.paneDict.hidden = basic;
  saveDict();                             // hiding it kills focus. Write before that
  // The heading says which pane this is now that the tabs are gone. It goes
  // through data-i18n rather than textContent alone, so switching the language
  // while it is open repaints it along with everything else.
  el.sheetTitle.dataset.i18n = basic ? 'settings' : 'grpDict';
  el.sheetTitle.textContent = t(el.sheetTitle.dataset.i18n);
  el.sheet.scrollTop = 0;                 // do not carry over where you were looking before
}

async function openSettings(pane) {
  saveCmds();                       // you can arrive here straight from the signals
  el.helpSheet.hidden = true;       // sheets never stack. Only one of them is up
  el.sheet.hidden = false;
  fitMini();                        // while it is hidden there is no size to measure
  showSheetPane(pane);
  placeNav();
  paintNav();
  await Promise.all([loadMics(), loadLangs(), loadTuning(), loadDict(), loadWhisperModel()]);
  el.dictNote.textContent = '';
}
el.closeSettings.onclick = () => {
  saveDict();
  el.sheet.hidden = true;
  placeNav();
  paintNav();
};

/* The list of voice commands. Like settings, opening it swaps out the main screen. */
async function openHelp() {
  saveDict();                       // you can arrive here straight from settings
  el.sheet.hidden = true;
  el.helpSheet.hidden = false;
  el.helpSheet.scrollTop = 0;
  fitMini();
  placeNav();
  paintNav();
  el.cmdNote.textContent = '';
  await loadCommands();
}
el.closeHelp.onclick = () => {
  saveCmds();
  el.helpSheet.hidden = true;
  placeNav();
  paintNav();
};

/* One press of a button in the row. Pressing the one you are already on closes
   it, and that goes out through the same close handler the back arrow uses, so
   the dictionary and the wordings are written the one way whichever route you
   took out. */
function navGo(to) {
  if (navWhere() === to) {
    (to === 'help' ? el.closeHelp : el.closeSettings).click();
    return;
  }
  if (to === 'help') openHelp(); else openSettings(to);
}
el.openSettings.onclick = () => navGo('basic');
el.openDict.onclick = () => navGo('dict');
el.openHelp.onclick = () => navGo('help');

/* ── What the keyboard can do ────────────
   Anything you can say out loud should also be doable with a key when your
   hands are free.

   There are only two rules for the bindings. **A bare key only moves the
   screen** (open settings, open the list, close). **A key with Shift changes
   where your voice goes** (mic on and off, how it is delivered, discard, where
   it lands). Nothing that silently stops your voice getting through sits on a
   bare single letter. If a mistake only changes the screen, you can see it and
   press again.

   Cmd+, is left alone. On macOS that binding belongs to Chrome's settings and a
   page cannot stop it. Even if it could be stopped, doing so would take away
   the one route from this window to Chrome's settings. We look only at Shift
   and do nothing while Cmd, Ctrl or Alt is along for the ride (so browser
   bindings like Cmd+Shift+M are not stolen out from under it).

   While you are typing, everything passes straight through. What we look at is
   where the key landed (e.target), not uiDoc().activeElement. Focus is on that
   element at the moment of the press, so the answer is the same in either
   document.

   The listener goes on both document and the floating window's document. The
   contents move into the small window along with floatParts, but a key pressed
   with focus nowhere lands on the small window's body. body sits outside
   floatParts, so attaching to the elements alone never catches it. */

// Whether you are in the middle of typing. Judged from where the key landed
function typingIn(node) {
  if (!node || !node.tagName) return false;
  if (node.isContentEditable) return true;
  return node.tagName === 'INPUT' || node.tagName === 'TEXTAREA' || node.tagName === 'SELECT';
}

/* Look at both the character (key) and the position (code) so it still works
   on a keyboard laid out differently. With kana input switched on, key comes
   back as a different character. */
const keyIs = (e, ch) => e.key.toUpperCase() === ch || e.code === 'Key' + ch;

function onKey(e) {
  if (e.defaultPrevented || e.repeat || e.isComposing) return;

  // Send the draft. Inside the edit box the box handles it itself, so this is only for when you are outside.
  if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key === 'Enter') {
    if (typingIn(e.target)) return;
    e.preventDefault();
    el.send.click();
    return;
  }
  // From here on we look only at Shift. Keys the browser owns are left alone.
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  /* Close whatever is open. While you are typing, the first press only gets
     you out of the field. Both the dictionary and the wordings save the moment
     focus leaves, so the write happens here too. Press again and it closes. */
  if (e.key === 'Escape') {
    if (typingIn(e.target)) { e.target.blur(); return; }
    if (!el.helpSheet.hidden) { el.closeHelp.click(); return; }
    if (!el.sheet.hidden) { el.closeSettings.click(); return; }
    if (oneShot) { endOneShot(); say(t('oneShotOff'), 4); }
    return;
  }
  if (typingIn(e.target)) return;

  // Depending on the layout, ? may or may not need Shift, so it is checked first
  if (e.key === '?') {
    e.preventDefault();
    navGo('help');
    return;
  }

  if (!e.shiftKey) {
    // A stand-in for Cmd+,. The way you remember opening settings stays, and it does not fight the browser.
    if (e.key === ',') {
      e.preventDefault();
      navGo('basic');
      return;
    }
    /* The dictionary. It sits beside settings in the top bar, so it gets the
       key beside the settings key. The position is read as well as the
       character, the same way keyIs reads the letter bindings. With kana input
       on, the same key comes back as 「。」, and on a French keyboard it comes
       back as 「:」 with the period itself moved onto Shift. Matching the
       character alone would leave it dead in both. */
    if (e.key === '.' || e.code === 'Period') {
      e.preventDefault();
      navGo('dict');
    }
    return;
  }

  /* From here on, where your voice goes changes. You are operating by voice
     because you are not watching the screen, so a press has to come through in
     a sound and a line (it runs the same ones as saying it out loud. Doing the
     same thing and getting a different notice reads as something else having
     happened). */
  if (keyIs(e, 'M')) {                    // mic on and off
    const back = route === 'off';
    e.preventDefault();
    el.segOff.click();
    chime(back ? 'up' : 'down');
    say(back ? t('voiceUnmuted') : muteHint());
    return;
  }
  if (keyIs(e, 'L')) {                    // send it straight through
    e.preventDefault();
    el.segLive.click();
    chime('ok');
    say(t('voiceLive'));
    return;
  }
  if (keyIs(e, 'H')) {                    // route it to review
    e.preventDefault();
    el.segHold.click();
    chime('ok');
    say(t('voiceHold'));
    return;
  }
  if (keyIs(e, 'E')) {                    // route just this one utterance to review
    e.preventDefault();
    if (el.editOnce.disabled) { chime('err'); return; }
    el.editOnce.click();                  // editThisOne is what puts up the line
    chime('ok');
    return;
  }
  if (e.key === 'Backspace') {            // throw away the unsent one
    e.preventDefault();
    const had = el.draft.value.trim();
    el.discard.click();                   // discard is what puts up the line and the undo
    chime(had ? 'down' : 'err');
    return;
  }
  /* Pick where speech goes by number. On some layouts holding Shift changes
     the digit character itself, so here we look at the position (code). The
     numbers are the same ones shown on the chips. */
  const digit = /^Digit([1-9])$/.exec(e.code || '');
  if (digit) {
    e.preventDefault();
    const no = Number(digit[1]);
    const pickTo = knownListeners[no - 1];
    if (!pickTo) { chime('err'); say(t('voiceRouteMissing', {n: no})); return; }
    setRoute2(String(pickTo.pid));
    chime('ok');
    say(t('voiceRoute', {name: pickTo.label}));
  }
}

document.addEventListener('keydown', onKey);

/* The send combination is the one thing called by a different name on
   different machines. So the list never lies, machines with a Cmd key get it
   rewritten. */
if (/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)) {
  for (const n of document.querySelectorAll('.cap.mod')) n.textContent = 'Cmd';
}

// Theme. On auto it follows the OS setting (data-theme is taken off)
// While it floats, write to both the small window and the original document.
// The small window alone snaps back to the old color the instant you return,
// and the original alone never changes the whole time it floats.
function applyTheme(choice) {
  for (const d of new Set([document, uiDoc()])) {
    if (choice === 'auto') d.documentElement.removeAttribute('data-theme');
    else d.documentElement.setAttribute('data-theme', choice);
  }
  for (const b of el.themeRow.children) b.classList.toggle('on', b.dataset.themeChoice === choice);
  store.set('theme', choice);
}
for (const b of el.themeRow.children) b.onclick = () => applyTheme(b.dataset.themeChoice);

function applyLang(choice) {
  langPref = choice;
  store.set('lang', choice);
  resolveLang();
  applyI18n();
  el.langPick.value = choice;   // for when it is called from voice or from another window
  paint();
  reformatAll();
  for (const row of el.log.children) {
    const m = row.querySelector('.mark');
    m.textContent = t(row.dataset.kind);
  }
  // In the command list both the text and the wordings change with the
  // language. It can be switched while open, so we refetch and rebuild
  // (data-i18n never brings the wordings along).
  if (!el.helpSheet.hidden) loadCommands();
  /* Both of these lists are built in JS, so data-i18n never reaches them.
     Repaint them from what was last fetched. Waiting for the five second poll
     instead would leave the two of them sitting in the old language while every
     other word on the screen had already moved. */
  paintEnginePick();
  paintMicPick();
}
el.langPick.onchange = () => applyLang(el.langPick.value);

// The microphone in use. Switching it swaps only the recording process (the model stays)
let micList = [];
let micCurrent = '';
/* The id the recorder hands back for "whatever the OS is set to". It is written
   into the config file, so it stays this string whatever the screen calls it. */
const MIC_SYSTEM_DEFAULT = 'default';
/* Every other entry is a device name the OS handed over. Those are not ours to
   translate, and 「MacBook Pro のマイク」 is already in the reader's language
   anyway. The one at the head is ours, so that one goes through I18N. */
const micLabel = m => m.id === MIC_SYSTEM_DEFAULT ? t('micSystemDefault') : (m.label || m.id);

function paintMicPick() {
  if (!micList.length) { el.mic.hidden = true; return; }
  el.mic.replaceChildren(...micList.map(m => {
    const o = document.createElement('option');
    o.value = m.id; o.textContent = micLabel(m); o.selected = m.id === micCurrent;
    return o;
  }));
  // Show it even when the one selected is not in the list
  if (micCurrent && ![...el.mic.options].some(o => o.value === micCurrent)) {
    const o = document.createElement('option');
    o.value = micCurrent; o.textContent = micCurrent; o.selected = true;
    el.mic.prepend(o);
  }
  el.mic.hidden = false;
}

async function loadMics() {
  try {
    const d = await (await fetch('/api/mics')).json();
    micList = d.mics || [];
    micCurrent = d.current || '';
  } catch {
    micList = [];
  }
  paintMicPick();
}

// Until the switch actually completes on the backend, the display stays
// hopeful. Once mic_active (over on the ws.onmessage side) sends confirmation,
// that is the moment it is swapped for the switched message.
let micConfirmDevice = null;
let micConfirmTimer = null;

el.mic.onchange = async () => {
  const label = el.mic.selectedOptions[0].textContent;
  const dev = el.mic.value;
  el.hint.textContent = t('micSwitching', {name: label});
  micConfirmDevice = dev;
  clearTimeout(micConfirmTimer);
  // A backstop for an older daemon that never sends mic_active. If the real
  // confirmation arrives first, that one wins (the ws.onmessage above has
  // already handled it by then).
  micConfirmTimer = setTimeout(() => {
    if (micConfirmDevice === dev) {
      el.hint.textContent = t('micSwitched', {name: label});
      micConfirmDevice = null;
      setTimeout(() => paint(), 2500);
    }
  }, 3000);
  await putJSON('/api/mics', {device: dev});
  syncVizCapture(true);
};

// The recognition language (shown only for Whisper. The other engines spell
// them differently, so for those the dropdown itself is hidden).
async function loadLangs() {
  try {
    const d = await (await fetch('/api/languages')).json();
    if (!d.languages.length) { el.recogLangField.hidden = true; return; }
    const auto = document.createElement('option');
    auto.value = ''; auto.textContent = t('recogLangAuto');
    auto.selected = !d.current;
    el.recogLang.replaceChildren(auto, ...d.languages.map(l => {
      const o = document.createElement('option');
      o.value = l.code; o.textContent = l.name; o.selected = l.code === d.current;
      return o;
    }));
    el.recogLangField.hidden = false;
  } catch {
    el.recogLangField.hidden = true;
  }
}

el.recogLang.onchange = async () => {
  await putJSON('/api/tuning', {language: el.recogLang.value});
  // Same as the browser's dropdown below. The built-in words follow whichever
  // language is being listened to, and this is Whisper's way of saying it.
  saveDict().then(loadDict);
};

/* The Whisper model. There is no telling whether a name is right until it is
   loaded, so nothing is checked here. The default name shows in faint type (as
   a placeholder), so an empty box reads as leaving the default alone. */
let whisperModelSaved = '';
async function loadWhisperModel() {
  try {
    const d = await (await fetch('/api/whisper-model')).json();
    whisperModelSaved = d.model || '';
    el.whisperModel.placeholder = d.default || '';
    // Never touched while you are typing (the refetch on reopening settings would wipe it)
    if (uiDoc().activeElement !== el.whisperModel) el.whisperModel.value = whisperModelSaved;
  } catch {}
}
function saveWhisperModel() {
  const name = el.whisperModel.value.trim();
  el.whisperModel.value = name;
  if (name === whisperModelSaved) return;   // if it was only touched, do not write
  whisperModelSaved = name;
  putJSON('/api/whisper-model', {model: name});
}
el.whisperModel.onchange = saveWhisperModel;
el.whisperModel.onblur = saveWhisperModel;   // for the paths where change never fires

/* ── Sensitivity and breaks ──────────────
   All three take effect on the daemon the moment they are saved (it re-reads
   every 0.5 seconds). */
let silenceMin = 0.3, silenceMax = 30;      // the range the server allows (overwritten on load)
let tuning = {idle_mute_min: 5, silence_threshold: 0.015, silence_duration: 3.0,
              min_chars: 15, strip_fillers: false, browser_unmute_gesture: false,
              browser_unmute_peaks: 3, browser_unmute_window: 2,
              browser_unmute_threshold: 0.82};

// The threshold slider runs on a log scale. The 0.003 to 0.03 range people
// actually use takes up more than half the slider, so it can be set finely.
let threshLo = 0.003, threshHi = 0.15;
const threshToPos = v =>
  Math.round(1000 * Math.log(Math.max(threshLo, v) / threshLo) / Math.log(threshHi / threshLo));
const posToThresh = p => {
  const v = threshLo * Math.pow(threshHi / threshLo, p / 1000);
  return Math.round(v * 1000) / 1000;
};
/* The slider, the number and the mark all sit on the same loudness scale, so
   they move together. Calling this a trigger level rather than a sensitivity is
   what lets them agree. A sensitivity would have to count the other way round,
   and the knob would then run against the mark right underneath it. */
const threshToSlider = v => Math.max(0, Math.min(1000, threshToPos(v)));

function paintTuning() {
  el.thresh.value = threshToSlider(tuning.silence_threshold);
  el.silence.value = tuning.silence_duration;
  el.minChars.value = tuning.min_chars;
  el.threshVal.textContent = Math.round(threshToSlider(tuning.silence_threshold) / 10);
  if (uiDoc().activeElement !== el.silenceVal) {          // never touched while you are typing
    el.silenceVal.value = Number(tuning.silence_duration).toFixed(1);
  }
  el.minCharsVal.textContent = tuning.min_chars;
  el.clean.checked = !!tuning.strip_fillers;
  paintIdleMute();
  paintBrowserGesture();
  paintGauge();
}

// Show the measured level and the threshold side by side. With nothing but a number there is no way to settle on a value.
function paintGauge() {
  // Under browser recognition there is no daemon pushing a level at all
  // (asr_mic.py never runs, so level.txt never exists), and daemonLevel sits
  // at its startup value of 0 forever. The bar read that literally and stayed
  // flat no matter how loud the room was, right under a mic icon that (on a
  // different measurement) was lighting up fine. Read this machine's own
  // microphone instead whenever the daemon is not the one actually listening
  // (same split amplitudeNow() draws, for the same reason).
  const usingBrowser = engine === 'off' || asrActive();
  const rawLevel = usingBrowser ? browserRmsNow : daemonLevel;
  const speaking = usingBrowser ? rawLevel >= tuning.silence_threshold : daemonSpeaking;
  // The meter runs on the same scale as the slider. If these did not line up,
  // you could not compare the mark against the level you are actually making.
  const lvl = Math.min(100, threshToPos(rawLevel) / 10);
  const mark = Math.min(100, threshToPos(tuning.silence_threshold) / 10);
  el.gaugeFill.style.width = lvl + '%';
  el.gaugeFill.classList.toggle('on', speaking);
  el.gaugeMark.style.left = mark + '%';
  // The WS 'level' handler already does this for the daemon path (its own
  // push carries m.speaking straight from the source). Repeating it here too
  // is what gets it under browser recognition, which has no such push to ride.
  el.meterFill.classList.toggle('on', speaking);
  // The thin meter on the main screen gets the same scale
  el.meterFill.style.width = lvl + '%';
  el.meterMark.style.left = mark + '%';
  // The mic button itself fills from the bottom by the level being picked up.
  // It uses the same eased value as the drawing (taken separately, the same
  // sound would give two different heights).
  el.segOff.style.setProperty('--lv', Math.round(micLevel * 100) + '%');
}

async function loadTuning() {
  try {
    const d = await (await fetch('/api/tuning')).json();
    for (const [k, v] of Object.entries(d.tuning || {})) if (v != null) tuning[k] = v;
    for (const [k, r] of Object.entries(d.range || {})) {
      if (k === 'silence_threshold') { threshLo = r.min; threshHi = r.max; continue; }
      if (k === 'silence_duration') {
        silenceMin = r.min; silenceMax = r.max;
        el.silenceVal.min = r.min; el.silenceVal.max = r.max;
        continue;
      }
      const node = {min_chars: el.minChars, browser_unmute_peaks: el.browserGesturePeaks,
                    browser_unmute_window: el.browserGestureWindow,
                    browser_unmute_threshold: el.browserGestureThreshold}[k];
      if (node) { node.min = r.min; node.max = r.max; }
    }
    const thresholdRange = d.range && d.range.browser_unmute_threshold;
    if (thresholdRange) {
      tuning.browser_unmute_threshold = Math.min(thresholdRange.max,
        Math.max(thresholdRange.min, Number(tuning.browser_unmute_threshold) || thresholdRange.min));
    }
    paintTuning();
  } catch {}
}

// While you drag the slider only the display updates, and it saves once you
// let go (writing on every move would let an extreme value along the way take
// effect on the daemon for a moment)
let saveTimer = null;
function queueTuning() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => putJSON('/api/tuning', tuning), 250);
}

el.thresh.oninput = () => {
  tuning.silence_threshold = posToThresh(Number(el.thresh.value));
  el.threshVal.textContent = Math.round(Number(el.thresh.value) / 10);
  paintGauge();
  queueTuning();
};
el.silence.oninput = () => { tuning.silence_duration = Number(el.silence.value); paintTuning(); queueTuning(); };
/* The slider goes up to 10 seconds, but some people want to wait longer. The
   number can be typed in directly, and the slider covers everything up to
   there. */
function commitSilence() {
  const v = Number(el.silenceVal.value);
  if (!Number.isFinite(v)) { paintTuning(); return; }
  tuning.silence_duration =
    Math.min(silenceMax, Math.max(silenceMin, Math.round(v * 10) / 10));
  paintTuning(); queueTuning();
}
el.silenceVal.onchange = commitSilence;
el.silenceVal.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); el.silenceVal.blur(); }
});
el.minChars.oninput = () => { tuning.min_chars = Number(el.minChars.value); paintTuning(); queueTuning(); };
/* On and off is kept apart from the length. Give 0 the meaning of never
   turning off and someone who dragged the slider to the end cannot tell what
   they just chose. */
function paintIdleMute() {
  const idle = Number(tuning.idle_mute_min) || 0;
  el.idleMuteOn.checked = idle > 0;
  if (idle > 0) el.idleMute.value = idle;
  else if (!el.idleMute.value || el.idleMute.value === '0') el.idleMute.value = 5;
  el.idleMuteVal.textContent = t('minutesShort', {n: el.idleMute.value});
  el.idleMinsField.hidden = el.idleMuteField.hidden || idle <= 0;
}
el.idleMuteOn.onchange = () => {
  tuning.idle_mute_min = el.idleMuteOn.checked ? (Number(el.idleMute.value) || 5) : 0;
  paintIdleMute(); queueTuning();
};
el.idleMute.oninput = () => { tuning.idle_mute_min = Number(el.idleMute.value); paintIdleMute(); queueTuning(); };

function paintBrowserGesture() {
  el.browserGestureOn.checked = !!tuning.browser_unmute_gesture;
  el.browserGesturePeaks.value = tuning.browser_unmute_peaks;
  el.browserGesturePeaksVal.textContent = tuning.browser_unmute_peaks;
  el.browserGestureWindow.value = tuning.browser_unmute_window;
  el.browserGestureWindowVal.textContent = Number(tuning.browser_unmute_window).toFixed(1) + ' s';
  el.browserGestureThreshold.value = tuning.browser_unmute_threshold;
  el.browserGestureThresholdVal.textContent = Math.round(tuning.browser_unmute_threshold * 100) + '%';
}
el.browserGestureOn.onchange = () => {
  tuning.browser_unmute_gesture = el.browserGestureOn.checked;
  resetBrowserGesture();
  syncVizCapture();
  queueTuning();
};
el.browserGesturePeaks.oninput = () => {
  tuning.browser_unmute_peaks = Number(el.browserGesturePeaks.value);
  paintBrowserGesture(); queueTuning();
};
el.browserGestureWindow.oninput = () => {
  tuning.browser_unmute_window = Number(el.browserGestureWindow.value);
  paintBrowserGesture(); queueTuning();
};
el.browserGestureThreshold.oninput = () => {
  tuning.browser_unmute_threshold = Number(el.browserGestureThreshold.value);
  resetBrowserGesture(); paintBrowserGesture(); queueTuning();
};


/* Drag the mark on the meter to change the trigger level.
   Not having to open settings is faster, so it can be reached from the main
   screen too. It reads the same value as the slider in settings, so moving
   either one keeps them in step. */
function threshFromX(clientX) {
  const r = el.meter.getBoundingClientRect();
  if (!r.width || !Number.isFinite(clientX)) return;
  const pos = Math.min(1000, Math.max(0, ((clientX - r.left) / r.width) * 1000));
  const next = posToThresh(pos);
  if (!Number.isFinite(next) || next <= 0) return;   // do not let a strange value break the drawing
  tuning.silence_threshold = next;
  paintTuning();
  // Read back what was actually kept, not where the finger is. Near the quiet
  // end several positions round to one threshold, and a hint taken from the
  // finger would count on while the value stands still, and disagree with the
  // number in settings.
  el.hint.textContent =
    t('sensitivitySet', {n: Math.round(threshToSlider(tuning.silence_threshold) / 10)});
  queueTuning();
}

let draggingThresh = false;

function endThreshDrag() {
  if (!draggingThresh) return;
  draggingThresh = false;
  el.meterHit.classList.remove('dragging');
  setTimeout(() => { if (!draggingThresh) paint(); }, 1500);
}

el.meterHit.addEventListener('pointerdown', e => {
  draggingThresh = true;
  el.meterHit.classList.add('dragging');
  try { el.meterHit.setPointerCapture(e.pointerId); } catch {}
  threshFromX(e.clientX);
});
el.meterHit.addEventListener('pointermove', e => {
  if (draggingThresh) threshFromX(e.clientX);
});
// Letting go outside the screen, moving to another window and so on can lose
// the pointerup. Left holding on, the value would then change from nothing more
// than the cursor passing over, so the catch is kept wide.
el.meterHit.addEventListener('lostpointercapture', endThreshDrag);
for (const ev of ['pointerup', 'pointercancel']) {
  el.meterHit.addEventListener(ev, endThreshDrag);
  addEventListener(ev, endThreshDrag);
}

/* ── Recognizing in the browser (Web Speech API) ──
   Uses the recognition built into Chrome. It loads no model, so it works as it
   is even on a weak machine. But **the audio is sent to Google's servers**, so
   anyone who needs everything to stay on this machine should use one of the
   other engines.

   The awkward part is that the session cuts itself off after 7 to 10 seconds of
   silence. Scrambling to reconnect after it has gone loses the first words of
   what you were starting to say. The Web Speech API has no way to pour in audio
   you had saved up, so there is no getting it back after the fact.

   So we **reconnect ahead of time, while it is quiet**. Reconnecting during
   silence loses nothing. It is never touched while a voice is coming in. */
// The spoken language choices. Chrome takes BCP-47 tags, so the common ones are listed.
const ASR_LANGS = [
  ['ja-JP', '日本語'], ['en-US', 'English (US)'], ['en-GB', 'English (UK)'],
  ['zh-CN', '中文（简体）'], ['zh-TW', '中文（繁體）'], ['ko-KR', '한국어'],
  ['es-ES', 'Español'], ['fr-FR', 'Français'], ['de-DE', 'Deutsch'],
  ['it-IT', 'Italiano'], ['pt-BR', 'Português (BR)'], ['ru-RU', 'Русский'],
  ['hi-IN', 'हिन्दी'], ['id-ID', 'Indonesia'], ['th-TH', 'ไทย'],
  ['vi-VN', 'Tiếng Việt'],
];

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const canBrowserASR = !!SR;

let rec = null;              // the current SpeechRecognition
let recRunning = false;      // start() has been called and end has not come yet
let recWanted = false;       // whether the setting says to use it
let lastVoiceAt = 0;         // when a voice was last coming in
let recStartedAt = 0;        // when the current session was opened
let recFails = 0;            // failures in a row (used to decide when to give up)
let recStarting = false;
let recGeneration = 0;

/* Whether browser recognition is set to be used and whether it is running
   right now are two different things. Treating them as one meant that the
   instant a pause stopped it, it was judged as having no way to recognize at
   all, and even the resume button went unpressable (we really did get stuck
   that way). Whether the screen is live is read off the setting (asrChosen). */
let asrChosen = false;
const asrActive = () => canBrowserASR && asrChosen;
let asrOwnsLease = false;
let asrConflict = null;

function syncVizCapture(force = false) {
  if (shouldKeepVizCapture({
    route, asrChosen: asrActive(), gestureEnabled: tuning.browser_unmute_gesture, vizArmed,
  })) {
    if (force) stopViz();
    if ((!micStream || !analyser) && !vizStarting) startViz(vizDeviceLabel());
  } else {
    stopViz();
  }
}

const MAX_FAILS = 6;         // this many in a row and we give up and say so

// Reconnect on our own before it cuts. Well short of the measured limit (7 to 10 seconds).
const RENEW_AFTER_MS = 4500;

const BROWSER_GESTURE_MIN_GAP_MS = 300;
const BROWSER_GESTURE_MIN_RISE = 0.28;
let browserGestureState = emptyBrowserGestureState();
function resetBrowserGesture() {
  browserGestureState = emptyBrowserGestureState();
}

function watchBrowserGesture(level, now) {
  const result = nextBrowserGesture(browserGestureState, {
    level, now,
    enabled: route === 'off' && asrActive() && !!tuning.browser_unmute_gesture,
    active: asrActive(), inFlight,
    threshold: tuning.browser_unmute_threshold,
    windowMs: (Number(tuning.browser_unmute_window) || 0) * 1000,
    peakCount: tuning.browser_unmute_peaks,
    minGapMs: BROWSER_GESTURE_MIN_GAP_MS,
    minRise: BROWSER_GESTURE_MIN_RISE,
  });
  browserGestureState = result.state;
  if (!result.triggered) return;
  lastVoiceAt = now;
  setRoute(lastMode);
}

function browserLang() {
  // The language to recognize. Not the language the screen is in, the language you speak.
  const saved = store.get('asrLang', '');
  if (saved) return saved;
  // navigator.language sometimes comes back with no region attached, like "ja".
  // As it stands that matches nothing in the list, and the raw code ends up
  // sitting among the choices.
  const want = (navigator.language || 'en-US');
  if (ASR_LANGS.some(([c]) => c === want)) return want;
  const head = want.split('-')[0].toLowerCase();
  const hit = ASR_LANGS.find(([c]) => c.split('-')[0].toLowerCase() === head);
  return hit ? hit[0] : 'en-US';
}

/* Which language is being spoken into this, in the shape the server takes.

   The words ignored out of the box and the connecting words that get stripped
   are matched against what the recognizer wrote down, so they follow the
   language being spoken and never the language the screen is in. Browser
   recognition is the only engine this page drives and its speak language lives
   in this browser, so it is handed over. Every other engine runs inside the
   daemon, which writes down what it is hearing, and an empty string is how we
   say that the server knows better than we do. */
const spokenLang = () => asrActive() ? browserLang() : '';

// The name of a language, written in that language (UI_LANGS is the one place
// we do not translate, for the reason written at the head of this file).
const langName = code => (UI_LANGS.find(([c]) => c === code) || [, code])[1];

function newRecognition(generation) {
  const r = new SR();
  r.lang = browserLang();
  r.continuous = true;
  r.interimResults = true;
  r.maxAlternatives = 1;

  // Check every time whether this is still us, so a signal from an old
  // instance does not break the new state. Without it, an old end can arrive
  // right after a swap and start it up twice over.
  const mine = () => rec === r && generation === recGeneration;

  r.onstart = () => {
    if (!mine()) return;
    recStarting = false;
    recRunning = true; recStartedAt = performance.now(); recFails = 0;
    asrDeniedFlag = false;
  };

  r.onresult = ev => {
    if (!mine()) return;
    let interim = '';
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const res = ev.results[i];
      if (res.isFinal) queueOrSendFinal(res[0].transcript);
      else interim += res[0].transcript;
    }
    // A clause waiting out its quiet stretch keeps its own text on screen
    // (paintPendingBrowserSends), with whatever is being recognized now
    // appended after it. Before the gate actually held anything, a clause
    // barely spent any real time queued, so there was next to never
    // anything here to lose by leaving interim out. Once it holds for the
    // real few seconds, someone still mid-thought watches their own words
    // stop appearing the moment the first clause of it queues.
    if (pendingBrowserSends.length) {
      paintPendingBrowserSends(interim);
    } else {
      paintStream(withDict(interim));
      el.tray.classList.toggle('idle', !interim);
    }
    streamTail();
    paintTinyButtons();
    if (interim.trim()) lastVoiceAt = performance.now();
  };

  r.onerror = ev => {
    if (!mine()) return;
    recStarting = false;
    // A refused microphone needs a person to act. Roll the setting back and say so.
    if (ev.error === 'not-allowed' || ev.error === 'service-not-allowed') {
      asrDeniedFlag = true;
      beat('denied');            // make the refusal visible from outside too
      disableBrowserASR(t('asrDenied'));
      return;
    }
    // no-speech and aborted happen all the time (you were quiet, or we
    // reconnected ourselves). Everything else (network, audio-capture,
    // language-not-supported and so on) gets counted.
    if (ev.error !== 'no-speech' && ev.error !== 'aborted') recFails++;
  };

  r.onend = () => {
    if (!mine()) return;
    recStarting = false;
    recRunning = false;
    rec = null;
    el.stream.textContent = '';
    if (!recWanted) return;
    if (recFails > MAX_FAILS) {
      disableBrowserASR(t('asrFailed'));
      return;
    }
    // Wait only when failures are piling up. When things are going fine there
    // is no waiting (waiting loses whatever you started saying in the meantime).
    const wait = recFails ? Math.min(8000, 250 * Math.pow(2, recFails - 1)) : 0;
    setTimeout(() => { if (recWanted && !rec) startRecognition(); }, wait);
  };
  return r;
}

async function startRecognition() {
  if (!canBrowserASR || !recWanted || rec || recRunning || recStarting) return;
  const generation = recGeneration;
  recStarting = true;
  try {
    if (!await beat('listening') || generation !== recGeneration || !recWanted || route === 'off' || rec) return;
    const r = newRecognition(generation);
    if (generation !== recGeneration || rec) return;
    rec = r;
    try {
      r.start();
    } catch {
      if (rec === r) rec = null;
      if (generation === recGeneration) recStarting = false;
      // Sometimes the previous session has not folded up yet. Wait a little and come back.
      recFails++;
      setTimeout(() => { if (recWanted && !rec) startRecognition(); },
                 Math.min(8000, 250 * Math.pow(2, recFails - 1)));
    }
  } finally {
    if (generation === recGeneration && !rec) recStarting = false;
  }
}

function stopRecognition(keepWanted = false) {
  recGeneration++;
  if (!keepWanted) recWanted = false; // lower it before abort (stops the revival on end)
  const r = rec;
  rec = null; recRunning = false; recStarting = false; recFails = 0;
  if (r) { try { r.abort(); } catch {} }
  el.stream.textContent = '';
}

// When it can no longer be used, bring the setting, what is saved and the
// screen all into line with reality. Lower only the flag and you get a box
// still ticked with nothing running behind it.
function disableBrowserASR(why) {
  stopRecognition();
  store.set('asr', '');
  paintBrowserAsr();
  if (why) el.hint.textContent = why;
  paintPower();
}

/* Whether a voice is coming in is checked on our own interval, not on rAF.
   Drawing stops in a background tab, so riding along with it would mean
   detection dies exactly while you have it floating and are working on
   something else. That is precisely how this tool gets used, so it is kept
   separate. */
setInterval(() => {
  if (!asrActive() || !analyser || vizFailed) return;
  analyser.getByteFrequencyData(freq);
  const now = performance.now();
  const level = browserLevel();
  if (route !== 'off' && level > 0.12) lastVoiceAt = now;
  watchBrowserGesture(level, now);
}, 150);

/* The watch that reconnects ahead of time while it is quiet.
   It is never touched while a voice is coming in (the one return below is what
   guarantees that). */
setInterval(() => {
  if (!recWanted || !recRunning || !rec) return;
  const now = performance.now();
  if (now - lastVoiceAt < RENEW_AFTER_MS) return;   // still talking
  if (now - recStartedAt < RENEW_AFTER_MS) return;  // just reconnected
  // stop() settles the last result and then throws end (abort throws it away)
  try { rec.stop(); } catch {}
}, 1000);

/* If nobody speaks for a while, we switch the microphone off ourselves.

   Browser recognition cuts the session every 7 to 10 seconds by design, and we
   reconnect ahead of time even while it is quiet. Which means that merely
   stepping away keeps reconnecting to Google forever. There is no reason to
   keep that up through time nobody is using.

   The cut is announced with a sound and a line. Cut it silently and you come
   back, talk, and never notice that nothing is getting through (we burned two
   and a half hours on exactly that, today). */
setInterval(() => {
  if (!asrActive() || route === 'off' || inFlight) return;
  const mins = Number(tuning.idle_mute_min) || 0;
  if (!mins) return;
  if (performance.now() - lastVoiceAt < mins * 60000) return;
  setRoute('off').then(() => {
    chime('down');
    say(t('idleMuted', {n: mins}), 30);
  });
}, 5000);

/* Browser recognition decides on its own when a clause is grammatically
   finished (isFinal), but nothing about the pause that comes after belongs
   to it, that call settles the words, not when they go out. Sent the instant
   isFinal fired, "pause to send" had nothing left to act on under this
   engine, which is why the setting sat disabled the whole time (see
   paintBrowserAsr). Held here for a stretch of measured quiet instead, the
   same number governs both engines again, browser or daemon.

   A shared clock rather than one timer per clause: what actually needs
   watching is "how long has the room been quiet", and every clause waiting
   to go out watches the same answer, so lastLoudAt is the only state, not a
   timer per entry. Ticked by setInterval, not the paint loop. A minimized or
   otherwise occluded tab throttles requestAnimationFrame; a send must not
   quietly stop working right when the person stepped away expecting it to
   go out on its own. */
const BROWSER_SEND_GATE_MS = 100;
let lastLoudAt = 0;
let pendingBrowserSends = [];   // [{text, queuedAt}], oldest first

function browserGateTick() {
  browserRmsNow = computeBrowserRms();
  if (engine === 'off' || asrActive()) paintGauge();
  // Tracked on every tick, queue empty or not. Gated behind the early return
  // below, this only ever caught up the instant a clause finalized and got
  // pushed, by which point the room had usually gone quiet already (that is
  // the whole reason a clause just finalized), so quietFor measured all the
  // way back to whenever lastLoudAt was last touched, page load if this was
  // the first utterance. Always past any wait, so it went out on the very
  // first tick after queuing, wait or no wait.
  const now = performance.now();
  if (browserRmsNow >= tuning.silence_threshold) lastLoudAt = now;
  if (!pendingBrowserSends.length) return;
  const quietFor = now - lastLoudAt;
  const waitMs = Math.max(0, (Number(tuning.silence_duration) || 0) * 1000);
  const ready = [], stillWaiting = [];
  for (const item of pendingBrowserSends) {
    // A cap against a rising noise floor. Some machines' getUserMedia runs
    // automatic gain control that climbs through a real pause and never
    // dips back under a fixed mark on its own, and a wait with no ceiling
    // then never ends, the exact "neither a command nor a prompt, gone
    // nowhere" shape #76 exists to rule out, just reached from the sending
    // side instead of the recognizing side this time.
    const cap = Math.max(waitMs * 2, waitMs + 3000);
    (quietFor >= waitMs || now - item.queuedAt >= cap ? ready : stillWaiting).push(item);
  }
  pendingBrowserSends = stillWaiting;
  for (const item of ready) sendUtterance(item.text);
  paintPendingBrowserSends();
}
setInterval(browserGateTick, BROWSER_SEND_GATE_MS);

function flushPendingBrowserSends() {
  const items = pendingBrowserSends;
  pendingBrowserSends = [];
  for (const item of items) sendUtterance(item.text);
  paintPendingBrowserSends();
}

// Nothing is drawn once the queue empties, the interim painting in onresult
// owns the display from that point on (see the `pendingBrowserSends.length`
// branch there).
function paintPendingBrowserSends(interim = '') {
  if (!pendingBrowserSends.length) return;
  const queued = pendingBrowserSends.map(p => p.text).join(' ');
  el.stream.textContent = interim ? `${queued} ${withDict(interim)}` : queued;
  el.tray.classList.remove('idle');
  streamTail();
}

/* Where a finalized clause actually goes, either straight to sendUtterance or
   parked in pendingBrowserSends to wait out a quiet stretch first. Called
   from onresult in place of calling sendUtterance directly. */
function queueOrSendFinal(text) {
  text = (text || '').trim();
  if (!text) return;
  // The one straggler discardCurrentNow warns about, stale content the newly
  // restarted session can still carry right after an abort. Caught here, at
  // the point of queuing, since sendUtterance's own copy of this same check
  // never gets a turn to run until whatever the queue eventually flushes.
  if (dropNextLocal) { dropNextLocal = false; return; }
  // No analyser to measure quiet with (armViz never got its gesture, or the
  // visualization failed outright), so there is nothing to gate on. Sending
  // right away, the way this always worked, beats a wait that could never end.
  if (!analyser || vizFailed) { sendUtterance(text); return; }
  // A closing mute must not sit behind whatever else is already waiting for
  // quiet, or the room stays live for however long that wait runs, exactly
  // the cost #76 exists to avoid. Send everything already finalized ahead of
  // it first (those were always going regardless), then let mute through
  // this instant, ungated.
  if (matchingTailWord(text)?.id === 'mute') {
    flushPendingBrowserSends();
    sendUtterance(text);
    return;
  }
  pendingBrowserSends.push({text, queuedAt: performance.now()});
  paintPendingBrowserSends();
}

/* Settled utterances go to the server. The dictionary, the ignored words, the
   min length and the hold decision all run through the same path the daemon
   takes, on the server side (so the result does not change with how it was
   recognized).

   Fired and forgotten they arrive out of order, so each send is chained onto
   the one before it and they go in series. */
let sendChain = Promise.resolve();
function sendUtterance(text) {
  text = (text || '').trim();
  if (!text) return;
  if (!asrOwnsLease || asrConflict) {
    if (asrConflict) el.hint.textContent = t('asrConflict');
    return;
  }
  if (dropNextLocal) { dropNextLocal = false; return; }   // an utterance that was cleared on screen
  lastVoiceAt = performance.now();
  sendChain = sendChain.then(async () => {
    if (!asrOwnsLease || asrConflict) {
      if (asrConflict) el.hint.textContent = t('asrConflict');
      return;
    }
    try {
      const res = await post('/api/utterance', {text, lang: spokenLang(), tab: tabId});
      // Browser recognition keeps no copy on this side. If it drops, all we can do is tell the person.
      if (res.status === 409) {
        let data = {};
        try { data = await res.json(); } catch {}
        if (data.error === 'asr_owner_conflict') {
          setAsrConflict(data.owner);
          el.hint.textContent = t('asrConflict');
          return;
        }
        // The daemon is recognizing too. The screen has been left behind, so bring it back into line.
        el.hint.textContent = t('asrDoubled');
        loadEngines();
      } else if (!res.ok) {
        el.hint.textContent = t('asrSendFailed', {n: res.status});
      }
    } catch {
      el.hint.textContent = t('asrSendFailed', {n: '?'});
    }
  });
}

/* Tell the server that we really are listening right now.
   Without this there is no way, from outside, to tell the state where no screen
   is open or the microphone was refused from the state where it is properly
   listening. */
const tabId = Math.random().toString(36).slice(2, 10);
let asrDeniedFlag = false;
let standingDown = false;

function setAsrConflict(owner) {
  asrOwnsLease = false;
  asrConflict = owner || {};
  stopRecognition(true);
  paintBrowserAsr();
}

async function beat(state) {
  if (state === 'gone' && navigator.sendBeacon) {
    try {
      if (navigator.sendBeacon('/api/asr-heartbeat',
        new Blob([JSON.stringify({tab: tabId, state})], {type: 'application/json'}))) {
        asrOwnsLease = false;
        asrConflict = null;
        return true;
      }
    } catch {}
  }
  try {
    const response = await post('/api/asr-heartbeat', {tab: tabId, state});
    let data = {};
    try { data = await response.json(); } catch {}
    if (response.status === 409) {
      setAsrConflict(data.owner);
      return false;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    asrOwnsLease = state !== 'gone' && data.owner?.tab === tabId;
    asrConflict = null;
    paintBrowserAsr();
    return state === 'gone' || asrOwnsLease;
  } catch {
    asrOwnsLease = false;
    if (state !== 'gone') {
      stopRecognition(true);
      el.hint.textContent = t('asrLeaseUnavailable');
      paintBrowserAsr();
    }
    return false;
  }
}

setInterval(() => {
  if (!asrChosen || standingDown) return;
  const state = asrDeniedFlag ? 'denied' : (asrConflict ? 'conflict' : (recRunning ? 'listening' : 'idle'));
  beat(state).then(owned => {
    if (owned && recWanted && !recRunning && !recStarting) startRecognition();
  });
}, 5000);

// On close, say that we are gone (left behind, it still looks like someone is there)
addEventListener('pagehide', () => { if (asrChosen) beat('gone'); });

/* ── Where speech goes ───────────────────
   Voice mode gets used on separate jobs at the same time. This picks which one
   it reaches. The daemon decides the names (the folder name at first, and once
   the agent titles the conversation it switches to that). */
let routeTo = '';          // the one chosen. Empty means nothing chosen (the server decides)
let effectiveTo = '';      // where it actually lands (the one the server picked when nothing was chosen)
let knownListeners = [];

/* While a name is being typed, the chips have to hold still. paintRoutes runs
   off the five second poll as well, and rebuilding underneath would take the
   box away along with everything typed into it. */
let renaming = null;     // {pid} while the rename box is open

// Same idea, for the × on a chip asking "sure?". Without this, the plain
// five second poll (setInterval(loadListeners, 5000) below) lands at a
// random offset from the click and can wipe the ask back to the ordinary
// chip well before its own four second patience runs out, reading as the
// confirm reverting the moment you let go of it rather than as a poll that
// happened to fire early.
let disconnectAsking = null;   // pid while a chip's × is asking to confirm

function paintRoutes() {
  if (renaming) {
    // Still there. Leave the row exactly as it is until the box is done with.
    if (knownListeners.some(l => String(l.pid) === renaming.pid)) return;
    renaming = null;     // that session ended while the box was open
  }
  if (disconnectAsking) {
    if (knownListeners.some(l => String(l.pid) === disconnectAsking)) return;
    disconnectAsking = null;   // that session ended while it was asking
  }
  // With nothing listening there is nothing to show at all. One listener
  // still gets its own chip, numbered 1, rather than staying hidden until a
  // second one shows up. The number popping into existence only once you
  // happen to run two sessions is a worse first look at it than just always
  // being there, one chip deep, even though there is nothing yet to choose
  // between. Saying 「2番に切り替え」 still only does anything once a second
  // one is actually listening, that gate lives on the daemon side and is
  // untouched here.
  if (knownListeners.length < 1) { el.routes.hidden = true; return; }
  el.routes.hidden = false;
  // Show the numbers. This is the number you use when you say 「2番に切り替え」
  // out loud. The daemon counts in the same order (earliest registered first),
  // so it matches the number in front of you.
  //
  // There is no send to everyone. Two sessions taking the same instruction and
  // running off separately had no use, and picking it by mistake was only hard
  // to notice.
  const items = knownListeners.map((l, i) => ({...l, no: i + 1}));
  const pick = l => routeTo ? String(l.pid) === routeTo : String(l.pid) === effectiveTo;

  // This is what comes up in a short window. Same numbers and same names as
  // the chips, and the same hand-built menu the chip on a sent card opens.
  paintRoutePick();

  el.routeChips.replaceChildren(...items.map(l => {
    // Light up where it actually lands. With nothing chosen the server settles
    // on whichever started later, so even with no memory of choosing you can
    // see where it goes.
    const on = pick(l);
    const b = document.createElement('button');
    b.className = 'route-chip' + (on ? ' on' : '');
    b.dataset.pid = String(l.pid);
    // The number is the same one used in the spoken signal (「2番」). Even when
    // a narrow window folds the name away, this part always stays.
    const no = document.createElement('b');
    no.className = 'no';
    no.textContent = l.no + '.';
    const nm = document.createElement('span');
    nm.className = 'nm';
    nm.textContent = l.label;
    b.append(no, nm);
    b.title = [`${l.no}. ${l.label}`, l.cwd || '', t('renameHint')]
                .filter(Boolean).join('\n');

    /* Double click the chip to change its name. A long press does the same, for
       screens where a double tap is either awkward or already spoken for by the
       browser's own zoom. */
    let holdFrom = null, holdTimer = null, longFired = false;
    const cancelHold = () => { clearTimeout(holdTimer); holdTimer = null; };
    b.onpointerdown = ev => {
      if (ev.button || ev.target.closest('.x')) return;
      longFired = false;
      holdFrom = {x: ev.clientX, y: ev.clientY};
      holdTimer = setTimeout(() => { longFired = true; openRename(l, b); }, 550);
    };
    // A drag or a scroll is not a long press. 10px of slop, because a finger
    // resting on glass never holds perfectly still.
    b.onpointermove = ev => {
      if (holdTimer && Math.hypot(ev.clientX - holdFrom.x, ev.clientY - holdFrom.y) > 10)
        cancelHold();
    };
    b.onpointerup = cancelHold;
    b.onpointercancel = cancelHold;
    b.onpointerleave = cancelHold;
    // Without this a long press on a touch screen drops the context menu on top
    // of the box that just opened.
    b.oncontextmenu = ev => ev.preventDefault();

    b.onclick = () => {
      if (longFired) { longFired = false; return; }   // the long press already opened it
      // While asking, the whole chip confirms the disconnect, same as
      // pressing × again. Confirming only landed on the ×'s own 15px circle
      // before this, which the label swapping in for the name (below) can
      // shove sideways out from under wherever the mouse still is, reading
      // as the confirm not responding at all.
      if (b.classList.contains('asking')) { confirmDisconnect(); return; }
      setRoute2(String(l.pid));
    };
    b.ondblclick = ev => {
      // The × has a two step press of its own. stopPropagation on its click does
      // nothing to a dblclick listener sitting up here, so it is checked again.
      if (ev.target.closest('.x')) return;
      openRename(l, b);
    };

    // Stop it listening. The session itself does not end.
    const x = document.createElement('span');
    x.className = 'x';
    x.textContent = '×';
    x.title = t('disconnectTitle', {name: l.label});
    const askToConfirm = () => {
      b.classList.add('asking');
      nm.textContent = t('disconnectAsk');
      disconnectAsking = String(l.pid);
      setTimeout(() => {
        if (b.classList.contains('asking')) { disconnectAsking = null; loadListeners(); }
      }, 4000);
    };
    const confirmDisconnect = async () => {
      disconnectAsking = null;
      try { await post('/api/listeners/disconnect', {pid: String(l.pid)}); } catch {}
      say(t('disconnected', {name: l.label}), 5);
      setTimeout(loadListeners, 400);
    };
    x.onclick = ev => {
      ev.stopPropagation();
      if (!b.classList.contains('asking')) { askToConfirm(); return; }
      confirmDisconnect();
    };
    b.append(x);
    return b;
  }));
}

/* Move the fill without rebuilding the row.

   Picking a destination is the busy path here, and a rebuild puts a brand new
   node under the pointer between the two clicks of a double click, which is
   exactly what stops the pair from ever being read as one. */
function markChosen() {
  const on = pid => routeTo ? pid === routeTo : pid === effectiveTo;
  for (const b of el.routeChips.children) b.classList.toggle('on', on(b.dataset.pid || ''));
  paintRoutePick();
}

/* Change a destination's name right where it stands.

   What gets written is the same names.json `voice-shell.sh name` writes, so a
   name given here outlives voice mode going off and on, and nobody has to ask
   an agent for it.

   Every destination on the row can be renamed, not just this session's own.
   They are all in front of you with numbers on, telling them apart is the whole
   reason to rename one, and a name decides nothing about where a word lands.

   The first of the two clicks picks that destination, the way a single click
   always does. Holding that back to wait and see whether a second click follows
   would put a lag on every destination change. Changing destination is the
   common act by a wide margin and renaming is rare, so renaming rides on top
   rather than slowing it down. Where speech goes is filled in, so the move shows. */
function openRename(l, node) {
  if (renaming) return;
  const pid = String(l.pid);
  const box = document.createElement('span');
  box.className = 'route-chip editing' + (node.classList.contains('on') ? ' on' : '');
  box.dataset.pid = pid;
  // The number never moves. It is what the spoken signal points at.
  const no = document.createElement('b');
  no.className = 'no';
  no.textContent = l.no + '.';
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.className = 'nm-edit';
  inp.maxLength = 60;
  inp.autocomplete = 'off';
  inp.spellcheck = false;
  /* Only a name put on by hand goes in the box, and an empty box is what puts
     the automatic title back. Filling it with the automatic title instead would
     mean pressing Enter froze whatever the agent happened to be calling the
     conversation right then, and no later title could ever replace it. */
  inp.value = l.custom || '';
  inp.placeholder = l.auto || l.label;
  inp.setAttribute('aria-label', t('renameLabel'));
  /* The size attribute is the fallback for anything that does not understand
     field-sizing. It counts in average character widths, so a kana or a hanzi
     has to count as two or a Japanese name comes out at half the box it needs. */
  const fitWidth = () => {
    const text = inp.value || inp.placeholder || '';
    let n = 0;
    for (const ch of text) n += /[\u3000-\u9fff\uff00-\uff60\uffe0-\uffe6\uac00-\ud7af]/.test(ch) ? 2 : 1;
    inp.size = Math.max(8, n + 1);
  };
  fitWidth();
  inp.addEventListener('input', fitWidth);
  box.append(no, inp);
  node.replaceWith(box);
  renaming = {pid};
  inp.focus();
  inp.select();

  let done = false;   // Escape blurs the field, and blur on its own would save it back
  const finish = async keep => {
    if (done) return;
    done = true;
    const name = inp.value.trim();
    renaming = null;
    if (keep) {
      try { await putJSON('/api/listeners/name', {pid, name}); } catch {}
      say(name ? t('renamed', {name}) : t('renameCleared'), 4);
    }
    loadListeners();    // build the row back, carrying whatever name it holds now
  };
  /* Escape throws away what was typed. Everywhere else on this screen Escape
     only steps out of the field and the value is kept, but a name typed onto
     the wrong chip has to be escapable, and an inline rename is the one place
     people reach for Escape expecting it to undo. */
  inp.onkeydown = ev => {
    /* While an input method is still building a word, Enter and Escape belong
       to that, not to us. Taking them here meant the Enter that settles 「かいはつ」
       into 「開発」 also closed the box, and the name had to be opened again for
       every single word. isComposing covers it, and keyCode 229 is the same
       thing where isComposing is not reported. */
    if (ev.isComposing || ev.keyCode === 229) return;
    if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
    else if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
  };
  inp.onblur = () => finish(true);
}

/* The roll-up picker, shown instead of the chips once the window is too short
   for a row of them (each chip takes a line of its own down there). It names
   where your voice lands right now, and opens the same menu the chip on a sent
   card does. */
function paintRoutePick() {
  const cur = routeTo || effectiveTo;
  const items = listenerItems();
  const chosen = items.find(i => i.key === cur) || items[0];
  el.routePickLabel.textContent = chosen ? chosen.label : '';
}

el.routePick.onclick = () =>
  openPickMenu(el.routePick, listenerItems(), routeTo || effectiveTo, setRoute2);

async function setRoute2(to) {
  routeTo = to;
  markChosen();
  try { await putJSON('/api/route', {to}); } catch {}
}

async function loadListeners() {
  let d;
  try {
    d = await (await fetch('/api/listeners')).json();
  } catch { return; }

  const before = knownListeners;
  knownListeners = d.listeners || [];
  // Remember them so log destinations can show a name (kept after they have ended)
  knownListeners.forEach(l => routeNames.set(String(l.pid), l.label));
  relabelEntries();
  effectiveTo = d.target || '';
  const live = new Set(knownListeners.map(l => String(l.pid)));

  // If where it was going has ended, move to a session that is still alive and
  // say so. Left hanging silently, you talk and never notice nothing arrives.
  if (routeTo && !live.has(routeTo)) {
    const gone = before.find(l => String(l.pid) === routeTo);
    const next = knownListeners[knownListeners.length - 1];
    routeTo = '';                       // back to nothing chosen, and leave it to the server's default
    await putJSON('/api/route', {to: ''}).catch(() => {});
    el.note.textContent = next
      ? t('routeGone', {gone: gone ? gone.label : '?', next: next.label})
      : t('routeGoneAll', {gone: gone ? gone.label : '?'});
    el.note.hidden = false;
  } else {
    routeTo = d.route || '';
  }
  // The default (whichever started later) is the server's call. Nothing is
  // pinned here, so it behaves the same even with no screen open.
  paintRoutes();
}

/* ── Browser recognition settings ───────── */
function paintAsrLangs() {
  const cur = browserLang();
  const list = ASR_LANGS.some(([c]) => c === cur) ? ASR_LANGS : [[cur, cur], ...ASR_LANGS];
  el.asrLang.replaceChildren(...list.map(([code, name]) => {
    const o = document.createElement('option');
    o.value = code; o.textContent = name; o.selected = code === cur;
    return o;
  }));
}

/* Choosing how recognition is done.

   The browser's recognition (Web Speech API) runs with nothing installed, so
   that is the default. For people who need everything to stay on this machine,
   or who want to choose on accuracy or on language, the dropdown lists only
   what is actually installed.

   Running both at once writes the same utterance to the log twice, so exactly
   one is chosen at any time. */
const BROWSER_ENGINE = 'browser';
// The two that run on this machine. What comes back when you stop them differs, so they are told apart by name.
const APPLE_ENGINE = 'apple';
const WHISPER_ENGINE = 'whisper';
let localEngines = [];

/* What each engine is called on screen.

   The server hands over the id together with an English label, and that label
   stays English because the very same one is what `voice-shell.sh engines`
   prints for an agent to read. On screen the id is looked up here instead, so
   the moment the display language changes the list changes with it.

   An engine added later that nobody has worded yet falls back to the server's
   English label and then to its bare id, so the row is never left blank. */
const ENGINE_KEYS = {browser:'engineBrowser', apple:'engineApple', whisper:'engineWhisper'};
const engineLabel = e => ENGINE_KEYS[e.id] ? t(ENGINE_KEYS[e.id]) : (e.label || e.id);

function paintEnginePick() {
  const opts = [];
  if (canBrowserASR) opts.push([BROWSER_ENGINE, engineLabel({id: BROWSER_ENGINE})]);
  for (const e of localEngines) opts.push([e.id, engineLabel(e)]);
  // There can be machines with no browser recognition and no installed model either
  if (!opts.length) opts.push(['', t('engineNone')]);
  el.enginePick.replaceChildren(...opts.map(([id, label]) => {
    const o = document.createElement('option');
    o.value = id; o.textContent = label; o.selected = id === chosenEngine;
    return o;
  }));
}

function paintBrowserAsr() {
  el.browserAsrWarn.hidden = !asrChosen;
  el.asrConflict.hidden = !asrChosen || !asrConflict;
  el.asrConflict.textContent = t('asrConflict');
  el.browserMic.hidden = !asrChosen;
  el.asrLangField.hidden = !asrChosen;
  el.idleMuteField.hidden = !asrChosen;
  el.idleMuteNote.hidden = !asrChosen;
  el.browserGestureField.hidden = !asrChosen;
  paintIdleMute();
  // Browser recognition decides for itself when a clause is grammatically
  // done, isFinal is not something this setting can move. What it still
  // governs, on both engines now, is how long it waits after that before
  // actually sending it (queueOrSendFinal), so the slider stays live here too.
  el.silenceNote.textContent = t(asrChosen ? 'silenceNoteBrowser' : 'silenceNote');
  el.engineNote.textContent = t(asrChosen ? 'browserAsrNote' : 'localAsrNote');
  // For turning listening on and off, paintPower() decides both whether it
  // shows and what it says (it changes with more than the engine, it changes
  // with whether anything is running).
  paintPower();
  if (el.recogLangField) el.recogLangField.hidden = asrChosen || el.recogLangField.hidden;
  /* The Whisper model field. It shows while stopped as well. You use it by
     swapping the name and then loading again, so if the field vanished the
     moment you stopped, you could never reach it. */
  const whisper = chosenEngine === WHISPER_ENGINE;
  el.whisperModelField.hidden = !whisper;
  el.whisperModelNote.hidden = !whisper;
}

async function loadEngines() {
  let d;
  try {
    d = await (await fetch('/api/engines')).json();
  } catch { return; }
  localEngines = d.engines || [];
  const was = asrChosen;

  // The remembered choice lives on the server. Make localStorage the truth and
  // changing browsers puts it out of step with the branch taken at startup.
  const cur = d.chosen || BROWSER_ENGINE;
  chosenEngine = cur;
  asrChosen = canBrowserASR && cur === BROWSER_ENGINE;
  asrPausedByRoute = asrChosen && route === 'off';
  recWanted = asrChosen && !asrPausedByRoute;

  // If another tab or a command switched it, follow along here too.
  // Without following, recognition runs twice over, our send gets rejected and
  // the text simply disappears.
  if (was && !asrChosen) {
    stopRecognition();
    beat('gone');
  } else if (!was && asrChosen && recWanted && vizArmed) {
    startRecognition();
  } else if (asrChosen && !recWanted) {
    stopRecognition();
  }
  // Forced exactly when asrChosen just flipped (another tab, or a voice
  // command, switched engines), the same case the picker's own change
  // handler further down forces on too. vizDeviceLabel() reads off asrChosen,
  // so a capture already open for the wrong side of that flip would
  // otherwise sit there unrebuilt, measuring a device nothing is actually
  // listening through (see vizDeviceLabel's own comment).
  syncVizCapture(was !== asrChosen);
  paintEnginePick();
  paintBrowserAsr();
}

el.enginePick.onchange = async () => {
  const pick = el.enginePick.value;
  // Do not wait for the loadEngines every 5 seconds. Line up what shows from the moment it is chosen
  chosenEngine = pick;
  el.enginePick.disabled = true;
  try {
    if (pick === BROWSER_ENGINE) {
      asrChosen = true;
      asrPausedByRoute = route === 'off';
      recWanted = !asrPausedByRoute;
      lastVoiceAt = performance.now();
      // Forced: a capture already open from the local engine's own device
      // pick (asr_mic.py's, read off el.mic) has to be rebuilt without one,
      // now that vizDeviceLabel() reads asrChosen as true. Left standing,
      // "pause to send" gates on a microphone Chrome's own recognition was
      // never actually listening through, reads it as quiet no matter what
      // is said, and sends the instant a clause finalizes regardless of the
      // silence_duration setting.
      syncVizCapture(true);
      // Take the model side down first. Connect before it is down and whatever is said in between arrives twice.
      if (engineOnish()) {
        engine = 'stopping';
        paintPower();
      }
      // Sent either way, even with nothing local running to stop, so the pick
      // is written to the server's own config (resolve_engine) rather than
      // just this tab's memory of it. Left out, the next loadEngines poll (up
      // to 5s later) reads the old engine straight off there, snaps the
      // picker back to it, and takes the browser recognition that had just
      // started down with it (was && !asrChosen in loadEngines), leaving
      // neither engine actually listening.
      await post('/api/engine', {running: false, engine: BROWSER_ENGINE});
      if (recWanted) startRecognition();
    } else {
      asrChosen = false;
      recWanted = false;
      asrPausedByRoute = false;
      stopRecognition();
      beat('gone');
      // Forced for the same reason as the browser branch above, mirrored:
      // vizDeviceLabel() now reads asrChosen as false, so a capture left
      // over from browser recognition (opened with no device named on
      // purpose) has to be rebuilt against el.mic's own pick instead.
      syncVizCapture(true);
      engine = 'booting';
      startedAt = Date.now();
      paintPower();
      await post('/api/engine', {running: true, engine: pick});
    }
  } finally {
    el.enginePick.disabled = false;
  }
  paintBrowserAsr();
  refreshState();
  paint();
  // Swapping the engine swaps which of the three holds the language being
  // spoken, so the built-in words are read again from whoever holds it now.
  saveDict().then(loadDict);
};

el.asrLang.onchange = () => {
  store.set('asrLang', el.asrLang.value);
  // The language takes effect on the next reconnect. If it is in use, reconnect right now.
  if (recWanted && rec) { try { rec.stop(); } catch {} }
  // The words ignored out of the box are matched against what the recognizer
  // wrote down, so they follow this dropdown. Write what is on screen out under
  // the old language before reading the new one back, or a chip pressed just
  // now would be weighed against a list it was never drawn from.
  saveDict().then(loadDict);
};

/* ── Floating on top ─────────────────────
   So you never have to line browsers up side by side, it moves into a small
   window that always floats in front. It uses Chrome's Document
   Picture-in-Picture, so nothing extra has to be installed. */
function detectFloatingApi(target = window) {
  try {
    const api = target.documentPictureInPicture;
    return target.isSecureContext === true && api && typeof api.requestWindow === 'function' ? api : null;
  } catch {
    return null;
  }
}

const documentPip = detectFloatingApi();
let canFloat = !!documentPip;

function disableFloat() {
  canFloat = false;
  el.floatBtn.disabled = true;
  el.floatBtn.hidden = true;
  el.floatAsk.hidden = true;
  // floatStand is left alone on purpose. Hiding it here assumed this only
  // ever fires while not actually floating, but floatingWindow()'s own catch
  // calls this too, and that one can fire mid-float (documentPip.window
  // throwing). floatParts never comes back to this document in that case
  // (there is no document to move it back from, canFloat is now false so
  // nothing here can reach in and ask), so hiding the one thing left pointing
  // at where it went would strand the tab it moved out of with no way back
  // and no sign one ever existed. Left showing, its own button still tries
  // the same close path floatBtn itself would.
}

function floatingWindow() {
  if (!canFloat) return null;
  try {
    return documentPip.window || null;
  } catch {
    disableFloat();
    return null;
  }
}

el.floatBtn.hidden = !canFloat;
// The small window is a separate document and inherits none of our styling.
// Cloning the <style> nodes used to carry it over, but the sheet lives in its
// own file now and there is nothing left to clone. So fetch the text once, up
// front, and hand it to the small window as a <style> when it opens. Starting
// it here rather than at open time keeps the wait off the moment of the click,
// and keeps it off the first paint of this page as well.
const pipCss = canFloat
  ? fetch('viewer.css').then(r => r.ok ? r.text() : '').catch(() => '')
  : null;
// What moves into the small window. To add more, add it only here. If the list
// differs between opening and coming back, whatever was added disappears along
// with the small window when you return.
const floatParts = [el.page, el.sheet, el.helpSheet];
paintFloatAsk();

// The drawing and the description swap with whether it is floating.
// Left on the same drawing, there is no reading whether a press floats it or
// brings it back.
function paintFloat(on) {
  if (on === undefined) on = !!floatingWindow();
  const name = on ? 'picture_in_picture_off' : 'pip_exit';
  el.floatBtn.dataset.icon = name;
  const svg = el.floatBtn.querySelector(':scope > svg');
  if (svg) {
    // Replace only the contents of the drawing already there (rebuilding it can leave two)
    const paths = svg.querySelectorAll('path');
    if (paths.length === 2) {
      paths[0].setAttribute('d', ICON[name][0]);
      paths[1].setAttribute('d', ICON[name][1]);
    }
  } else {
    el.floatBtn.replaceChildren(iconSvg(name, 20));
  }
  el.floatBtn.classList.toggle('lit', on);
  el.floatBtn.title = t(on ? 'unfloatBtn' : 'floatBtn');
  el.floatBtn.setAttribute('aria-label', el.floatBtn.title);
  el.floatBtn.setAttribute('aria-pressed', String(on));
}

/* ── Only one screen ─────────────────────
   Open the same screen twice and you see the same thing, only the mic gets
   grabbed twice over. Where speech goes is chosen inside the screen, so there
   is never a reason to see two of them side by side. The one opened later
   becomes the real one and the older one steps aside (it closes the window if
   it can. Some windows the browser will not let a page close, and there the
   contents are hidden and only the way back is shown). */
const soleId = Math.random().toString(36).slice(2);
let soleChannel = null;
try { soleChannel = new BroadcastChannel('voice-shell-viewer'); } catch {}

function standDown() {
  if (standingDown) return;
  standingDown = true;
  el.taken.hidden = false;
  stopViz();
  if (typeof stopRecognition === 'function') stopRecognition();
  recWanted = false;
  if (asrChosen) beat('gone');
  // #taken lives inside .page, which travels wholesale into the small window
  // while floating (floatParts). Unhidden above but left floating, it shows
  // there, in a window nobody is looking at any more, while this document
  // still shows floatStand's own "bring it back", now quietly wrong (there
  // is nothing healthy left to bring back). Closing the small window first
  // runs its own pagehide handler, which moves floatParts (this node
  // included, already unhidden by the line above) back to this document, so
  // #taken lands where it will actually be seen.
  const fw = floatingWindow();
  if (fw) { try { fw.close(); } catch {} }
  try { window.close(); } catch {}
}

function claimSole() {
  standingDown = false;
  el.taken.hidden = true;
  if (soleChannel) soleChannel.postMessage({claim: soleId});
}

if (soleChannel) {
  soleChannel.onmessage = ev => {
    if (ev.data?.claim && ev.data.claim !== soleId) standDown();
  };
}
el.takeBack.onclick = () => { claimSole(); location.reload(); };
claimSole();

/* A window of its own can be opened automatically, but pinning it on top
   cannot start unless a person presses (a browser rule). That leaves it half
   done, a window that never comes forward, so we put something pressable right
   there.

   It now opens in an ordinary tab (voice-shell.sh's open_gui, #75), rather
   than straight into Chrome's --app mode, so this bubble is the one place
   that still says "float it" out loud, where the shape of the window used
   to say it on its own. It used to show only the first time and remember
   that forever, on the reasoning that once used, the button itself was
   enough of a reminder. In practice a button off in the header is exactly
   what goes unnoticed, so this asks again every time you are back on the
   ordinary tab with nothing floating, rather than banking on one look ever
   sticking. */
function paintFloatAsk() {
  el.floatAsk.hidden = !(canFloat && !floatingWindow());
  positionFloatAsk();
}
el.floatAsk.onclick = () => { el.floatAsk.hidden = true; el.floatBtn.click(); };
// A click anywhere outside it counts as having seen it, so it does not sit
// there through the rest of the visit once it has been noticed. It comes
// back on the next load regardless (paintFloatAsk carries no memory of this),
// which is the point: noticed-and-dismissed is not the same as never
// showing it again.
document.addEventListener('click', e => {
  if (el.floatAsk.hidden) return;
  if (e.target.closest('#floatAsk, #floatBtn')) return;
  el.floatAsk.hidden = true;
});

/* Sits under floatBtn with an arrow pointing back up at it, read off the
   button's own live position rather than a guessed offset (the row it sits
   in is not fixed width, a display name beside the logo, or a longer word in
   another language, can push it either way). Run again on resize while it is
   showing, the same reason fitCanvas re-measures on its own ResizeObserver
   rather than trusting a size taken once. */
function positionFloatAsk() {
  if (el.floatAsk.hidden) return;
  const r = el.floatBtn.getBoundingClientRect();
  if (!r.width) return;         // hidden or not yet laid out, nothing to measure against
  el.floatAsk.style.top = Math.round(r.bottom + 6) + 'px';
  // The bubble's own body sits flush against the right edge of the page
  // column itself, not wherever floatBtn happens to be within it. floatBtn
  // is the first of the header's icons (settings stays last on purpose,
  // that seat does not move), so anchoring the whole bubble to floatBtn's
  // edge the way this used to work left it sitting well short of the
  // column's own right edge instead of at it.
  //
  // The page is a centered, width-capped column (.page, max-width:460px),
  // not the full browser window. window.innerWidth is the window's own
  // edge, out past the column entirely on any screen wider than that cap,
  // and pinning the bubble there sent it drifting off past the actual UI.
  // Only the arrow still needs to point at floatBtn, so it is placed
  // independently of the body, off a CSS variable the stylesheet's
  // ::before reads.
  const margin = 8;
  const pageRight = el.page.getBoundingClientRect().right;
  el.floatAsk.style.right = Math.max(margin, Math.round(window.innerWidth - pageRight + margin)) + 'px';
  const bubbleRight = pageRight - margin;
  const bubbleWidth = el.floatAsk.getBoundingClientRect().width;
  const arrowCenter = r.left + r.width / 2;
  const arrowHalf = 6;   // half the 12px triangle in the stylesheet
  const arrowRight = Math.round(bubbleRight - arrowCenter - arrowHalf);
  // Kept inside the bubble's own rounded ends, or the triangle draws off
  // the edge (or past the opposite one) instead of onto the pill itself.
  const clamped = Math.min(Math.max(arrowRight, 16), Math.max(16, bubbleWidth - 26));
  el.floatAsk.style.setProperty('--arrow-right', clamped + 'px');
}
addEventListener('resize', positionFloatAsk);
// The very first measurement, taken the instant `hidden` comes off, can land
// before the browser has actually settled the bubble into its real size (its
// text was just swapped in by paintFloatAsk, and a layout mid-transition
// from 0 width reads back a width that is not the final one). That stale
// width fed the arrow's offset and sent it drifting toward whichever icon
// the wrong number happened to land near (#79 feedback, traced to floatBtn
// reading as pointed at openDict instead). A ResizeObserver fires once on
// its own right after observation starts, once the box has actually
// settled, on top of catching any later resize the window event alone
// would miss (a language swap changing the bubble's text width, say).
new ResizeObserver(positionFloatAsk).observe(el.floatAsk);

// On browser recognition, with the screen not yet touched. It is shown as off,
// but the mute on the server side has not been touched (that only goes on the
// moment something is pressed).
let armPending = false;

let floating = false;      // waiting on requestWindow. Keeps a flurry of presses from opening two

el.floatBtn.onclick = async () => {
  if (!canFloat || floating) return;
  // A toggle. Press it again while it floats and it goes back to the original
  // screen (the code that brings it back on 'pagehide' already exists. Calling
  // window.close() is what runs it).
  const currentWindow = floatingWindow();
  if (currentWindow) {
    try {
      currentWindow.close();
    } catch {
      disableFloat();
    }
    return;
  }
  floating = true;
  let win;
  try {
    // Where it opens is the browser's own call, on purpose (a page is not
    // allowed to place a window that stays in front of everything else
    // wherever it likes, and moveTo on it is silently ignored). Chrome does
    // remember on its own though, so dragging it to the right edge once is
    // enough. It reopens there from then on without anything asked for here.
    win = await documentPip.requestWindow({width: 400, height: 720});
  } catch {
    disableFloat();
    return;
  } finally {
    floating = false;
  }
  // Carry the styles over as they are so it looks the same. This has to stay
  // after requestWindow, because an await before it would spend the user
  // gesture and the request to open would be refused.
  const css = await pipCss;
  if (css) {
    const sheet = win.document.createElement('style');
    sheet.textContent = css;
    win.document.head.appendChild(sheet);
  }
  // From here on the small window is the target. Rather than copying, repaint
  // through the usual path. Auto is the state with no data-theme at all, so
  // copying would leave no way to take it off.
  pipDoc = win.document;
  resolveLang();
  applyTheme(store.get('theme', 'auto'));
  // Move the elements themselves. The references stay live, so no JS has to change.
  win.document.body.append(...floatParts);
  // floatStand lives outside floatParts on purpose, so it is what is left
  // once they are gone. Otherwise the tab they moved out of just sits there
  // empty until someone happens to remember where it went.
  el.floatStand.hidden = false;
  // The small window is a new document every time. The key listener is
  // reattached here (closing it takes the whole document with it, so nothing
  // has to be detached).
  win.document.addEventListener('keydown', onKey);
  el.sheet.hidden = el.helpSheet.hidden = true;   // the small window starts on the main screen
  // The row of buttons is one node living inside whichever screen is up. Both
  // sheets were just put away, so it has to be walked back to the main
  // screen's heading. Skip this and the small window opens with no way through
  // it at all, since the row went into the small window inside a sheet that is
  // now hidden.
  placeNav();
  paintNav();
  fitCanvas();
  paintFloat(true);
  paintFloatAsk();
  paint();                    // put the same title on the small window too
  // Document Picture-in-Picture has no "stay above everything" flag of its
  // own to ask for, it only works because the OS window manager honors a
  // hint Chrome sends along with the request. X11 does, Wayland (GNOME
  // among them) does not expose that to an ordinary browser window, so the
  // small window floats but can still end up behind whatever is clicked
  // next (#88, found on a real Ubuntu GNOME machine). Say so once, here,
  // rather than leaving it to look broken with no explanation.
  if (wayland) say(t('waylandFloatNote'), 12);
  win.addEventListener('pagehide', () => {
    // Put the target back first. A small window on its way closed is still
    // there, so left alone we would go and write the theme and the colors into
    // a document that is about to disappear.
    pipDoc = null;
    document.body.append(...floatParts);
    el.floatStand.hidden = true;
    paintFloat(false);          // mid-close the window is still around
    paintFloatAsk();
    fitCanvas();
    fitMini();                  // it can come back with a sheet left open from the small window
  });
};

// Same toggle a second press of floatBtn itself would run (closes the small
// window if one is open, which is always true while this button shows).
el.floatStandBack.onclick = () => el.floatBtn.onclick();

/* A page cannot open chrome://, so pressing it only copies. */
el.micSettingsLink.onclick = async () => {
  const url = el.micSettingsLink.textContent.trim();
  try { await navigator.clipboard.writeText(url); } catch { return; }
  const was = el.micSettingsLink.textContent;
  el.micSettingsLink.textContent = t('copied');
  setTimeout(() => { el.micSettingsLink.textContent = was; }, 1400);
};

/* ── The user dictionary ─────────────────
   One entry per row of the form. Nobody has to write arrows or JSON by hand. */

/* What sits between the heard word and the word to send. It was the character
   「→」, the last one left on screen after the rest of the arrows on this screen
   became drawings. A character also carries whatever the reader's font decides,
   which on some of them is a thin stroke of a different weight to everything
   around it. This is the same drawing in every font.
   The add row at the top of the pane carries the same drawing, put there with
   data-icon so the markup says what it holds. */
function arrowIcon() { return iconSvg('arrow_right_alt', 16); }

function replaceRow(from = '', to = '') {
  const row = document.createElement('div');
  row.className = 'row';
  const a = document.createElement('input'); a.className = 'from'; a.value = from;
  a.placeholder = t('dictHeard');
  const arrow = document.createElement('span'); arrow.className = 'arrow'; arrow.appendChild(arrowIcon());
  const b = document.createElement('input'); b.className = 'to'; b.value = to;
  b.placeholder = t('dictSendAs');
  const del = document.createElement('button');
  del.className = 'del'; del.title = t('remove');
  del.appendChild(iconSvg('close', 17));
  // Deleting moves no focus, so unless it is called from here there is no chance to save
  del.onclick = () => { row.remove(); saveDict(); };
  row.append(a, arrow, b, del);
  return row;
}

function ignoreRow(word = '') {
  const row = document.createElement('div');
  row.className = 'row';
  const a = document.createElement('input'); a.className = 'word'; a.value = word;
  a.placeholder = t('dictIgnorePh');
  const del = document.createElement('button');
  del.className = 'del'; del.title = t('remove');
  del.appendChild(iconSvg('close', 17));
  del.onclick = () => { row.remove(); saveDict(); };
  row.append(a, del);
  return row;
}

/* Which language the words ignored out of the box belong to, said under them.

   Without it the list looks like it shrank overnight when you change the
   language you speak. The two lists above it, the words you added and the ones
   you pressed off, follow no language and stay where they are.

   viewer.html has no slot for this line, so it is made here the first time and
   kept after that. isConnected covers the small floating window, where the
   contents move into another document and the line has to be made again. */
let builtinLangNote = null;
function paintBuiltinLang(code) {
  if (!code || !el.builtinChips) return;
  if (!builtinLangNote || !builtinLangNote.isConnected) {
    builtinLangNote = document.createElement('p');
    builtinLangNote.className = 'dict-note';
    el.builtinChips.after(builtinLangNote);
  }
  builtinLangNote.textContent = t('dictBuiltinLang', {lang: langName(code)});
}

function renderDict(d) {
  el.replaceRows.replaceChildren(
    ...Object.entries(d.replace || {}).map(([k, v]) => replaceRow(k, v)));
  el.ignoreRows.replaceChildren(...(d.ignore || []).map(w => ignoreRow(w)));

  // The words ignored out of the box cannot be edited, so they line up as something to look at
  if (d.builtin) {
    const off = new Set(d.unignore || []);
    el.builtinChips.replaceChildren(...d.builtin.map(w => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip' + (off.has(w) ? ' off' : '');
      b.dataset.word = w;
      const label = document.createElement('span');
      label.className = 'w'; label.textContent = w;
      const x = document.createElement('span');
      x.className = 'x'; x.textContent = off.has(w) ? '＋' : '×';
      b.append(label, x);
      const paint = () => {
        const gone = b.classList.contains('off');
        x.textContent = gone ? '＋' : '×';
        b.title = t(gone ? 'dictBuiltinBack' : 'dictBuiltinDrop', {w});
      };
      paint();
      // A chip toggles without ever taking focus. Unless it writes the moment
      // it is pressed, the struck-through look and what is actually in effect
      // stay out of step.
      b.onclick = () => { b.classList.toggle('off'); paint(); saveDict(); };
      return b;
    }));
    el.builtinCount.textContent = d.builtin.length;
    paintBuiltinLang(d.lang);
  }
  // If it is empty, put one row there (so you can start typing straight away)
  if (!el.replaceRows.children.length) el.replaceRows.appendChild(replaceRow());
  if (!el.ignoreRows.children.length) el.ignoreRows.appendChild(ignoreRow());
}

// Build the dictionary data out of the input fields on screen
function collectDict() {
  const replace = {};
  for (const row of el.replaceRows.children) {
    const from = row.querySelector('.from').value.trim();
    const to = row.querySelector('.to').value.trim();
    if (from && to) replace[from] = to;
  }
  const ignore = [...el.ignoreRows.children]
    .map(r => r.querySelector('.word').value.trim()).filter(Boolean);
  // Built-in words that were pressed off. They go over to the not ignored side
  const unignore = [...el.builtinChips.children]
    .filter(c => c.classList.contains('off')).map(c => c.dataset.word);
  return {ignore, unignore, replace};
}

/* ── Saving ──────────────────────────────
   It writes the moment focus leaves. The sliders in the top half save silently
   as soon as you move them, while the bottom half alone lost everything unless
   you pressed a button, and that mismatch was where the accidents came from. */
let dictReady = false;                // nothing is written until it has been read once
let dictLast = '';                    // what was written last. If it matches, nothing is sent
let dictLang = '';                    // the language the built-in chips were drawn in
let dictSaving = Promise.resolve();   // keeps the writes in a single line
let noteTimer = null;

// The mark does not stay up. Left there, you lose track of which save it is about.
function flashNote(msg, ms) {
  clearTimeout(noteTimer);
  el.dictNote.textContent = msg;
  noteTimer = setTimeout(() => { el.dictNote.textContent = ''; }, ms);
}

async function saveDict(quiet = false) {
  // Writing before it has loaded overwrites the real dictionary with a still empty screen
  if (!dictReady) return;
  const d = collectDict();
  const body = JSON.stringify(d);
  // It is called every time focus leaves, mid-typing included. If the contents match, do nothing.
  if (body === dictLast) return;
  dictLast = body;
  // The next write goes out only once the one before it has finished. Delete a
  // row and press a chip right away, and the older contents sent alongside it
  // can land afterward and bring the deleted row back.
  // The language goes back exactly as it arrived on the read, so the words
  // pressed off are weighed against the very list the chips were drawn from.
  // Work it out again here and a language switched mid-edit would let a word
  // taken out under the old one fall out of the record.
  const url = '/api/dictionary' + (dictLang ? '?lang=' + encodeURIComponent(dictLang) : '');
  const mine = dictSaving = dictSaving.then(() => putJSON(url, d))
                                      .then(r => r.ok, () => false);
  if (!await mine) { dictLast = ''; return; }   // it gets sent again the next time anything is touched
  loadDictPairs();       // make it take on the mid-recognition display too, from the next utterance
  if (!quiet) flashNote(t('dictSaved'), 1600);
}

function showDictTab(which) {
  const isReplace = which === 'replace';
  el.paneReplace.hidden = !isReplace;
  el.paneIgnore.hidden = isReplace;
  el.tabReplace.classList.toggle('on', isReplace);
  el.tabIgnore.classList.toggle('on', !isReplace);
}
el.tabReplace.onclick = () => showDictTab('replace');
el.tabIgnore.onclick = () => showDictTab('ignore');

async function loadDict() {
  const want = spokenLang();
  const d = await (await fetch(
    '/api/dictionary' + (want ? '?lang=' + encodeURIComponent(want) : ''))).json();
  dictLang = d.lang || '';
  renderDict(d);
  // Note down how it looked right after loading. Skip this and merely opening it writes once.
  dictLast = JSON.stringify(collectDict());
  dictReady = true;
}

// Nothing is written while you type. It writes only when focus leaves.
el.paneDict.addEventListener('focusout', () => saveDict());

// New entries go at the head of the list (no scrolling to the bottom)
function addReplaceEntry() {
  const from = el.newFrom.value.trim(), to = el.newTo.value.trim();
  if (!from || !to) { el.newFrom.focus(); return; }
  el.replaceRows.prepend(replaceRow(from, to));
  el.newFrom.value = el.newTo.value = '';
  el.newFrom.focus();
  // A newly added row never takes focus. Unless it writes here, it is gone the moment you close.
  saveDict();
}

function addIgnoreEntry() {
  const w = el.newIgnore.value.trim();
  if (!w) return;
  el.ignoreRows.prepend(ignoreRow(w));
  el.newIgnore.value = '';
  el.newIgnore.focus();
  saveDict();
}

el.addReplace.onclick = addReplaceEntry;
el.addIgnore.onclick = addIgnoreEntry;

// Enter adds it (so several can go in one after another)
for (const [input, fn] of [[el.newFrom, addReplaceEntry], [el.newTo, addReplaceEntry],
                           [el.newIgnore, addIgnoreEntry]]) {
  input.addEventListener('keydown', e => {
    if (e.isComposing || e.keyCode === 229) return;   // the input method still has it
    if (e.key === 'Enter') { e.preventDefault(); fn(); }
  });
}

// Filtering (find what is already saved)
el.filterReplace.addEventListener('input', () => {
  const q = el.filterReplace.value.trim().toLowerCase();
  for (const row of el.replaceRows.children) {
    const text = row.querySelector('.from').value + ' ' + row.querySelector('.to').value;
    const hit = q && text.toLowerCase().includes(q);
    row.hidden = q && !hit;
    row.classList.toggle('hit', !!hit);
  }
});

/* ── CSV ─────────────────────────────────
   One entry per line. The columns are type,from,to
     replace,クロードコード,Claude Code
     ignore,チャンネル登録,
*/
const csvCell = s => /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;

el.dictExport.onclick = () => {
  const d = collectDict();
  const lines = ['type,from,to'];
  for (const [k, v] of Object.entries(d.replace)) lines.push(`replace,${csvCell(k)},${csvCell(v)}`);
  for (const w of d.ignore) lines.push(`ignore,${csvCell(w)},`);
  // Put a BOM on it so Excel can tell it is UTF-8
  const blob = new Blob(['﻿' + lines.join('\n') + '\n'], {type: 'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'voice-shell-dictionary.csv';
  a.click();
  URL.revokeObjectURL(a.href);
};

// A small parser that also handles quoted cells
function parseCsvLine(line) {
  const out = [];
  let cur = '', quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (c === '"') quoted = false;
      else cur += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { out.push(cur); cur = ''; }
    else cur += c;
  }
  out.push(cur);
  return out.map(s => s.trim());
}

el.dictImport.onclick = () => el.dictFile.click();

el.dictFile.onchange = async ev => {
  const file = ev.target.files[0];
  if (!file) return;
  const text = (await file.text()).replace(/^﻿/, '');

  // Added to what is already on screen. Replace the lot and reading a file
  // with 3 entries wipes out the 43 you had. The import saves the moment it is
  // pressed, so there is no turning back.
  const cur = collectDict();
  const replace = {...cur.replace}, ignore = [...cur.ignore];
  let skipped = 0, added = 0, updated = 0, first = true;
  for (const raw of text.split(/\r?\n/)) {
    if (!raw.trim()) continue;
    const [type, from, to] = parseCsvLine(raw);
    // The header row. Anything exported from a spreadsheet always carries one,
    // so it is skipped whatever the columns are called. Only the first line is
    // checked. Real rows always start with replace or ignore, so none are lost.
    if (first) {
      first = false;
      if (type !== 'replace' && type !== 'ignore') continue;
    }
    if (type === 'replace' && from && to) {
      if (!(from in replace)) added++;
      else if (replace[from] !== to) updated++;
      replace[from] = to;
    }
    else if (type === 'ignore' && from) {
      if (!ignore.includes(from)) { ignore.push(from); added++; }
    }
    else skipped++;
  }

  renderDict({replace, ignore});
  el.dictFile.value = '';                          // so the same file can be picked again
  await saveDict(true);                            // no mark. The counts below say more
  flashNote(t('dictLoaded', {
    a: added, u: updated,
    s: skipped ? t('dictSkipped', {n: skipped}) : '',
  }), 6000);
};

// Whether filler words get dropped is a daemon setting. It takes effect from the next utterance.
el.clean.onchange = () => {
  tuning.strip_fillers = el.clean.checked;
  putJSON('/api/tuning', tuning);
};

/* ── The list of voice commands ───────────────
   The explanation of what happens lives here (i18n), and the wording you say
   out loud lives in the daemon's table. They translate into different things,
   so they are kept in different places. When adding a language, the text on the
   screen goes here and the words actually spoken go in COMMAND_WORDS in
   voice_daemon.py.

   The wordings are never copied over to this side. Copy them and you end up
   with words written on screen that do nothing, and words that work but are
   written nowhere. */
const CMD_ICON = {mute:'mic_off', unmute:'mic', live:'bolt', hold:'edit',
                  route:'swap_horiz', cancel_tail:'delete', hold_tail:'edit'};
// Only the ones that have conditions. For the ones without, we do not go writing that they always work.
const CMD_WHEN = {unmute:'cmdUnmuteWhen', route:'cmdRouteWhen'};
const SAY_MAX = 6;      // how many wordings show at once. Listing them all is more than anyone reads
// mute → cmdMute, cancel_tail → cmdCancelTail
const cmdI18nBase = id =>
  'cmd' + id.replace(/(^|_)([a-z])/g, (_m, _s, c) => c.toUpperCase());

/* Tidied by the same rules the server uses. Rejecting here is so the person
   typing sees it right away. The server is what decides, and it runs through
   again on save.

   Which signals accept an addition is learned from the server's answer, with no
   copy kept on the screen. Keep a copy and, the day the accepted kinds change
   over there, one side is left stale. */
let cmdEditable = new Set();
const CMD_WIDE = '１２３４５６７８９０';
const CMD_DROP = /[ \t　。、．，・…！？!?.,\-~〜"'「」『』()（）]/g;
const cmdNormal = s => s.trim()
  .replace(/[１２３４５６７８９０]/g, c => '1234567890'[CMD_WIDE.indexOf(c)])
  .replace(CMD_DROP, '').toLowerCase();

function cleanPhrase(kind, s) {
  if (!cmdEditable.has(kind)) return '';
  const key = cmdNormal(s);
  const slots = (key.match(/\{n\}/g) || []).length;
  if (kind === 'route' ? slots !== 1 : slots > 0) return '';
  const bare = key.replaceAll('{n}', '');
  return bare.length >= 2 && bare.length <= 24 ? key : '';
}

let cmdNoteTimer = null;
function flashCmdNote(msg, ms) {
  clearTimeout(cmdNoteTimer);
  el.cmdNote.textContent = msg;
  cmdNoteTimer = setTimeout(() => { el.cmdNote.textContent = ''; }, ms);
}

// One row for an added wording. Same shape as a dictionary row (down to how it is deleted).
function cmdRow(kind, phrase = '') {
  const row = document.createElement('div');
  row.className = 'row';
  const a = document.createElement('input');
  a.className = 'phrase';
  a.value = phrase;
  a.placeholder = t(kind === 'route' ? 'cmdAddRoutePh' : 'cmdAddPh');
  // A wording that cannot be used shows as such right there, before it is sent and disappears
  const mark = () => row.classList.toggle(
    'bad', !!a.value.trim() && !cleanPhrase(kind, a.value));
  a.addEventListener('input', mark);
  mark();
  const del = document.createElement('button');
  del.className = 'del';
  del.title = t('remove');
  del.appendChild(iconSvg('close', 17));
  // Deleting moves no focus, so unless it is called from here there is no chance to save
  del.onclick = () => { row.remove(); saveCmds(); };
  row.append(a, del);
  return row;
}

function cmdGroupEl(g, mine, off, offWords) {
  const base = cmdI18nBase(g.id);
  const box = document.createElement('div');
  box.className = 'group';
  box.dataset.kind = g.id;

  const head = document.createElement('h3');
  head.dataset.icon = CMD_ICON[g.id] || 'auto_awesome';
  head.dataset.iconSize = '16';
  head.append(t(base));
  box.append(head);

  /* Whether this signal is listened for at all. All seven get one, including the
     three that take no added wording, so it goes on above the early return below.

     The seven stand alone and none of them pulls another along. Switching off
     「マイクを入れる」 while 「マイクを切る」 stays on does leave the mic cuttable
     by voice and openable only from here, and that is allowed. Someone reaching
     for it is choosing to stay shut over opening by accident, and this tool holds
     that the accidental opening costs more. Turning both off is a use of its own
     as well (some people simply do not want the mic moving by voice), so the
     one-sided case is not worth a rule against.

     What is remembered is this kind's name, never a wording. See OFF_KEY in
     voice_daemon.py for what the other way costs. */
  const use = document.createElement('label');
  use.className = 'switch';
  use.title = t('cmdUse');
  const useBox = document.createElement('input');
  useBox.type = 'checkbox';
  useBox.className = 'use';
  useBox.checked = !off;
  useBox.setAttribute('aria-label', t('cmdUse'));
  const track = document.createElement('span');
  track.className = 'track';
  const knob = document.createElement('span');
  knob.className = 'knob';
  track.append(knob);
  use.append(useBox, track);
  head.append(use);

  // This browser's own recognition cuts the mic the instant it mutes, so the
  // word can never be heard here to begin with, unlike the daemon's mute
  // (mic_command_shape keeps listening for it on purpose). Not the same
  // thing as switched off, that is a choice made here and undone here. This
  // is a fact of the engine currently running, so the switch itself is held
  // still (whatever it was set to keeps its place for the next time an
  // engine that can hear it is running) and only the line under it changes.
  const deadHere = g.id === 'unmute' && asrChosen;
  if (deadHere) useBox.disabled = true;

  const what = document.createElement('p');
  what.className = 'dict-label';
  box.append(what);
  /* Switched off, this line says what happens instead of what the signal does.
     The wordings below stay on screen so they can be read before switching it back
     on, and left with the old sentence above them they would read as still working.
     One line carries it. Nothing new is put up for it. */
  const paintUse = () => {
    what.textContent = deadHere ? t('cmdUnmuteBrowserOff')
                       : useBox.checked ? t(base + 'What') : t('cmdOff');
    box.classList.toggle('off', !useBox.checked);
    box.classList.toggle('unavailable', deadHere);
  };
  paintUse();
  useBox.onchange = () => {
    paintUse();
    saveCmds();     // no field loses focus here, so nothing else would write it
  };

  /* The wordings themselves. Press one and this machine stops listening for that
     one wording, the same press and the same struck-through look the built-in
     ignore words in the dictionary already use. #27 said these were to be read
     and never made to look pressable. That held while they could not be pressed.
     They can now, so the shape follows.

     Kind by kind and wording by wording are kept apart on purpose. Strike every
     wording here and the switch above still reads as on, because it is. The two
     answer different questions, and folding one into the other would mean
     switching the kind off and on again quietly threw away which wordings had
     been struck. Whichever way round, what was struck comes back exactly as it
     was left.

     **What is struck is held here, not read back off the chips.** Only the first
     few wordings are on screen until the list is opened, so gathering from the
     chips would quietly let go of everything struck past the sixth. */
  // An older server says nothing about this. Then nothing is pressable and
  // nothing is sent back, which leaves a machine that never knew about striking
  // doing exactly what it did before.
  const knows = 'strikable' in g;
  const strikable = g.strikable === true;
  const struck = new Set((offWords[g.id] || []).filter(w => g.phrases.includes(w)));
  box._struck = strikable ? struck : null;

  const says = document.createElement('div');
  says.className = 'chips';
  /* Every wording of this kind struck. The signal is not switched off (the
     switch above says what it says), it simply has nothing left to answer to in
     this language. Say so, or the section reads as working while nothing in it
     does. It counts across the whole kind, not the few on screen, so opening the
     list does not change the answer. */
  const allOff = document.createElement('p');
  allOff.className = 'dict-note';
  const paintAllOff = () => {
    const every = strikable && g.phrases.length > 0
      && g.phrases.every(p => struck.has(p));
    allOff.textContent = every ? t('cmdAllOff') : '';
    // Taken out of the flow rather than merely emptied. A note carries a margin
    // above it, and an empty one would hold that gap open under the wordings in
    // all seven sections for a line that is almost never there.
    allOff.hidden = !every;
  };
  const sayEl = (p) => {
    if (!strikable) {
      const s = document.createElement('span');
      s.className = 'say';
      s.textContent = p;
      return s;
    }
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    const label = document.createElement('span');
    label.className = 'w';
    label.textContent = p;
    const x = document.createElement('span');
    x.className = 'x';
    b.append(label, x);
    const paint = () => {
      const gone = struck.has(p);
      b.classList.toggle('off', gone);
      x.textContent = gone ? '＋' : '×';
      b.title = t(gone ? 'cmdWordBack' : 'cmdWordDrop', {w: p});
    };
    paint();
    // A chip takes no focus when pressed, so unless it writes right here the
    // struck look and what the machine listens for drift apart.
    b.onclick = () => {
      if (struck.has(p)) struck.delete(p); else struck.add(p);
      paint();
      paintAllOff();
      saveCmds();
    };
    return b;
  };
  const paintSays = () => {
    const all = box.classList.contains('open');
    says.replaceChildren(...(all ? g.phrases : g.phrases.slice(0, SAY_MAX))
      .map(sayEl));
  };
  paintSays();
  paintAllOff();
  box.append(says, allOff);

  /* Routing matches a pattern, so what is laid out for it are examples rather
     than wordings, and a chip there would look like it took something out and
     take nothing out. Say why the chips are missing. The server decides which
     kinds these are, so no second opinion is kept here. */
  if (knows && !strikable) {
    const ex = document.createElement('p');
    ex.className = 'dict-note';
    ex.textContent = t('cmdExamples');
    box.append(ex);
  }

  /* It used to sit on the heading row, where opening the list left the target
     where it was. The switch that decides whether this signal is heard at all
     lives up there now, and those two must not be neighbours. A finger aiming at
     「すべて見る」 that lands one target over would switch a signal off, and
     nothing on screen moves far enough to notice it happened.

     So it comes down here under the wordings, and opening the list does push it
     down by the rows that appear. That is the price, and it is the cheaper one.
     Reaching for it a second time costs a moment. Cutting a signal without
     noticing costs every utterance that signal was carrying. */
  if (g.phrases.length > SAY_MAX) {
    const more = document.createElement('button');
    more.className = 'more';
    const paintMore = () => {
      more.textContent = t(box.classList.contains('open') ? 'cmdShowLess' : 'cmdShowAll');
    };
    more.onclick = () => { box.classList.toggle('open'); paintMore(); paintSays(); };
    paintMore();
    box.append(more);
  }

  // Where a language has no wording yet, the English one is showing as it is.
  // Put up silently, there is no telling whether you simply cannot read it or
  // there really is none, so we say so. An older server sends no fallback, so
  // when it is absent nothing is shown.
  if (g.fallback) {
    const fb = document.createElement('p');
    fb.className = 'dict-note';
    fb.textContent = t('cmdFallback');
    box.append(fb);
  }

  if (CMD_WHEN[g.id]) {
    const when = document.createElement('p');
    when.className = 'dict-note';
    when.textContent = t(CMD_WHEN[g.id]);
    box.append(when);
  }

  // For a signal that takes no additions, the reason is written out too.
  // Without a readable reason for the missing field, there is no telling
  // whether you overlooked it or it is by design.
  if (!g.editable) {
    const fixed = document.createElement('p');
    fixed.className = 'dict-note';
    fixed.textContent = t('cmdFixed');
    box.append(fixed);
    return box;
  }

  const label = document.createElement('p');
  label.className = 'dict-label builtin-head';
  label.textContent = t('cmdYours');
  box.append(label);

  if (g.id === 'route') {
    const slot = document.createElement('p');
    slot.className = 'dict-note';
    slot.textContent = t('cmdSlotNote');
    box.append(slot);
  }

  const rows = document.createElement('div');
  rows.className = 'rows';
  rows.append(...mine.map(p => cmdRow(g.id, p)));

  const add = document.createElement('div');
  add.className = 'new-row';
  const input = document.createElement('input');
  input.placeholder = t(g.id === 'route' ? 'cmdAddRoutePh' : 'cmdAddPh');
  const btn = document.createElement('button');
  btn.className = 'btn tonal';
  btn.dataset.icon = 'add';
  btn.dataset.iconSize = '17';
  btn.append(t('add'));
  const doAdd = () => {
    const v = input.value.trim();
    if (!v) { input.focus(); return; }
    if (!cleanPhrase(g.id, v)) {
      flashCmdNote(t('cmdBadPhrase'), 6000);
      input.focus();
      return;
    }
    rows.prepend(cmdRow(g.id, v));
    input.value = '';
    input.focus();
    saveCmds();       // a newly added row never takes focus. Unless it writes here, it is gone
  };
  btn.onclick = doAdd;
  input.addEventListener('keydown', e => {
    if (e.isComposing || e.keyCode === 229) return;   // the input method still has it
    if (e.key === 'Enter') { e.preventDefault(); doAdd(); }
  });
  add.append(input, btn);
  box.append(add, rows);
  return box;
}

function renderCommands(d) {
  // Remember it first. cleanPhrase reads this to drop the kinds that take no additions.
  cmdEditable = new Set((d.groups || []).filter(g => g.editable).map(g => g.id));
  // Which ones are switched off. An older server sends no off list, and then
  // nothing is off, which is what a machine that never knew about it was doing.
  const off = new Set(d.off || []);
  // The wordings switched off. Every kind and every language comes back, and each
  // section keeps only the ones it was given chips for. Hand a section a wording
  // it cannot draw and it would send that wording back as "still struck" without
  // ever having shown it, which is a claim it has no standing to make.
  const offWords = d.off_words || {};
  takeCmdOff(d);          // the send drawing reads the same record
  el.cmdGroups.replaceChildren(...(d.groups || []).map(
    g => cmdGroupEl(g, (d.user || {})[g.id] || [], off.has(g.id), offWords)));
  // Wordings outside Japanese and English have not been looked over by anyone
  // who speaks the language. So nobody reads them and assumes they are right,
  // we say so at the end. collectCmds skips children with no .rows, so adding
  // this here does not disturb saving.
  if (lang !== 'ja' && lang !== 'en') {
    const draft = document.createElement('p');
    draft.className = 'dict-note';
    draft.textContent = t('cmdDraft');
    el.cmdGroups.append(draft);
  }
  decorateIcons(el.cmdGroups);    // it can be floating, so the target gets passed in
}

function collectCmds() {
  const out = {};
  /* The kinds switched off, read from the switches rather than from the rows.
     Three of the seven have no rows at all, and gathered off the rows those three
     could never be switched off.

     Nothing is ever taken out of the rows for being switched off, so a wording
     added to a signal survives being switched off and comes back the moment it is
     switched on again. Clear them instead and switching off would quietly delete
     work the user typed. */
  out.off = [...el.cmdGroups.children]
    .filter(b => b.dataset.kind && !b.querySelector('.use').checked)
    .map(b => b.dataset.kind);
  /* The single wordings struck, read from what each section is holding rather
     than off the chips on screen. Only the first few chips are up until the list
     is opened, so the chips are not the record.

     Only the wordings this section actually put up go back. The server folds them
     into everything else it was already holding (keep_off_words in
     voice_daemon.py), so wordings in another language, or ones that have left the
     built-in table, are not touched by a save from here. Sorted, so a save that
     changed nothing else still compares equal and never goes out.

     Left out entirely when no section could strike anything, which is what an
     older server that says nothing about striking looks like. Sending an empty
     set there would read as "none of them are struck". */
  const words = {};
  let anyStrikable = false;
  for (const box of el.cmdGroups.children) {
    if (!box._struck) continue;
    anyStrikable = true;
    if (box._struck.size) words[box.dataset.kind] = [...box._struck].sort();
  }
  if (anyStrikable) out.off_words = words;
  for (const box of el.cmdGroups.children) {
    const rows = box.querySelector('.rows');
    if (!rows) continue;          // a signal that takes no additions has no field
    out[box.dataset.kind] = [...rows.children]
      .map(r => cleanPhrase(box.dataset.kind, r.querySelector('.phrase').value))
      .filter(Boolean);
  }
  return out;
}

/* Same as the dictionary, it writes the moment focus leaves. No save button. */
let cmdsReady = false;                // nothing is written until it has been read once
let cmdsLast = '';                    // what was written last. If it matches, nothing is sent
let cmdsSaving = Promise.resolve();   // keeps the writes in a single line

async function saveCmds(quiet = false) {
  if (!cmdsReady) return;
  const d = collectCmds();
  const body = JSON.stringify(d);
  if (body === cmdsLast) return;
  cmdsLast = body;
  /* The language being laid out rides along. The server works out which wordings
     this screen was able to put a chip on from the same catalog it answered the
     GET with, and folds the answer into what it already holds rather than
     replacing it. Without the language it cannot tell which wordings had a chip,
     and every wording outside this screen's view would switch itself back on. */
  // Nothing below is allowed to leave this chain rejected. Every later save waits
  // on it, so one refusal left as a rejection would stop all of them.
  const mine = cmdsSaving = cmdsSaving
    .then(() => putJSON('/api/commands?lang=' + lang, d))
    .then(r => r.ok ? r.json().then(j => ({ok: true, data: j}),
                                    () => ({ok: true, data: null}))
                    : {ok: false, data: null},
          () => ({ok: false, data: null}));
  const res = await mine;
  if (!res.ok) { cmdsLast = ''; return; }   // it gets sent again the next time anything is touched
  // Read back what the server ended up holding, so the send drawing stops
  // filling for a wording just struck. It carries the ones this screen could not
  // draw as well, which is the only way those reach the drawing at all.
  if (res.data) takeCmdOff(res.data);
  // The send drawing's own "about to be canceled/held" preview (tailWords)
  // reads added cancel_tail/hold_tail/mute wordings too, and otherwise sits
  // on whatever loadTailWords saw at the one call to it on page load, stale
  // for a wording just added or struck until the next reload.
  loadTailWords();
  if (!quiet) flashCmdNote(t('dictSaved'), 1600);
}

async function loadCommands() {
  cmdsReady = false;
  let d;
  try {
    d = await (await fetch('/api/commands?lang=' + lang)).json();
  } catch {
    return;               // an older server has no such endpoint. Just open it and stay quiet
  }
  renderCommands(d);
  // Note down how it looked right after loading. Skip this and merely opening it writes once.
  cmdsLast = JSON.stringify(collectCmds());
  cmdsReady = true;
}

// Nothing is written while you type. It writes only when focus leaves.
el.helpSheet.addEventListener('focusout', () => saveCmds());

/* ── Startup ────────────────────────────── */
resolveLang();
applyI18n();
decorateIcons();
// It starts on the main screen, so nothing in the row is lit. Say so out loud
// anyway, or a screen reader reads four buttons that never mention their state.
paintNav();
// Reflect the state once the drawings are in (do it first and they go in twice)
if (canFloat) paintFloat(false);
// Browser recognition is Chrome only. Where it cannot be used, the setting is not shown at all.
if (canBrowserASR) {
  paintAsrLangs();
  // Which one to use is remembered by the server (loadEngines reads it and
  // applies it). All this does is build the screen.
  paintBrowserAsr();
  // By browser rule the microphone cannot open until something is touched, so
  // it starts the moment it is touched. Some people work from the keyboard
  // alone, so a keypress starts it too.
  const arm = () => {
    vizArmed = true;
    armPending = false;
    if (recWanted) startRecognition();
  };
  addEventListener('pointerdown', arm, {once:true});
  addEventListener('keydown', arm, {once:true});
}
loadEngines().then(() => {
  if (!recWanted) return;
  if (vizArmed) { startRecognition(); return; }
  // By browser rule the microphone cannot open until the screen has been
  // touched once. Instead of asking anyone to please click, we start switched
  // off. Pressing the mic to turn it on, the obvious thing to do, is itself the
  // touch.
  armPending = true;
  route = 'off';
  paint();
});
applyTheme(store.get('theme', 'auto'));
el.langPick.append(...UI_LANGS.map(([code, name]) => {
  const o = document.createElement('option');
  o.value = code; o.textContent = name;
  return o;
}));
// If the remembered choice is not in the list, fall back to auto. No blank option is shown
if (langPref !== 'auto' && !I18N[langPref]) langPref = 'auto';
el.langPick.value = langPref;
fitCanvas();
retally();
paintPower();
paint();
loadTuning();
loadDictPairs();
loadTailWords();
connect();
loadListeners();
setInterval(refreshState, 3000);
setInterval(loadDictPairs, 30000);   // keep up with changes from another screen or a CSV import
// A title changes as the conversation goes on, so it is fetched again on a schedule
setInterval(loadListeners, 5000);
// How recognition is done can change from outside (another tab, a command, another session)
setInterval(loadEngines, 5000);
