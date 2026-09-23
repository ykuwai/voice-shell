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
   looks usable when it is not.
   Chinese comes twice, once per script, and each name is written in its own
   script, so the two can be told apart by whoever reads either one. */
const UI_LANGS = [
  ['en', 'English'], ['ja', '日本語'], ['es', 'Español'], ['fr', 'Français'],
  ['de', 'Deutsch'], ['zh', '简体中文'], ['zh-TW', '繁體中文'], ['ko', '한국어'],
];

/* How the time is written. We pass hour12:false, so all of them come out on a 24 hour clock. */
const TIME_LOCALE = {en:'en-GB', ja:'ja-JP', es:'es-ES', fr:'fr-FR',
                     de:'de-DE', zh:'zh-CN', 'zh-TW':'zh-TW', ko:'ko-KR'};
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
   both miss, fall back to English.
   Chinese is the one language where the front half is not enough, because the
   two scripts are two screens. Taiwan, Hong Kong and Macau write Traditional
   characters, and so does a tag that names Hant outright. Everything else that
   starts with zh (zh-CN, zh-SG, zh-Hans, a bare zh) stays Simplified, and a tag
   that names Hans outright wins over its region. */
const ZH_TRADITIONAL = new Set(['tw', 'hk', 'mo', 'hant']);
function isTraditionalZh(tag) {
  const [head, ...rest] = (tag || '').toLowerCase().replace(/_/g, '-').split('-');
  return head === 'zh' && !rest.includes('hans') && rest.some(p => ZH_TRADITIONAL.has(p));
}
function pickLang(tag) {
  const want = (tag || '').toLowerCase();
  if (isTraditionalZh(want)) return 'zh-TW';
  const hit = Object.keys(I18N).find(k => k.toLowerCase() === want);
  if (hit) return hit;
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
// For an element holding an icon, replace only the text part (do not wipe out
// the svg). Anything repainting such a label goes through here, not
// textContent, which would take the drawing with it.
function setLabel(n, text) {
  const svg = n.querySelector(':scope > svg');
  if (!svg) { n.textContent = text; return; }
  const last = n.lastChild;
  if (last && last.nodeType === 3) last.nodeValue = text;
  else n.append(text);
}

function applyI18n(root = uiDoc()) {
  for (const n of root.querySelectorAll('[data-i18n]')) setLabel(n, t(n.dataset.i18n));
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
                  'editOnce','dropOne','sendOne','draftMark',
                  'hint','note','log','none','fresh','floatAsk','taken','takeBack',
                  'logJumpWrap','logJump',
                  'mic','recogLang','recogLangField','thresh','threshVal','gaugeFill','gaugeMark',
                  'silence','silenceVal','silenceNote','minChars','minCharsVal','clean',
                  'wakeLockField','wakeLockOn','wakeLockNote',
                  'engineGroup','enginePick','engineNote','whisperModel','whisperModelField','whisperModelNote',
                  'browserAsrWarn','asrConflict','browserMic','micSettingsLink','micSettingsSaid',
                  'asrLang','asrLangField',
                  'onDeviceField','onDeviceStatus','onDeviceRow','onDeviceDownload',
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
                  'clearHistory','clearHistoryLabel','clearHistoryDone',
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

// Swap the drawing on one element whose meaning changed under it. Same
// machinery as decorateIcons, only pointed at a single node, and it does
// nothing when the drawing is already the one wanted.
function setIcon(n, name) {
  if (!n || n.dataset.icon === name) return;
  n.dataset.icon = name;
  const svg = n.querySelector(':scope > svg');
  if (svg) svg.remove();
  n.prepend(iconSvg(name, Number(n.dataset.iconSize) || 18));
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
const MARK_GAIN = 28;
/* Each bar used to ride the exact same eased level, just added to a
   different resting height, so all five moved in lockstep and read as one
   mechanical shape rather than five independent ones. Tried a real
   frequency split too (each bar its own FFT band), but a voice's energy
   sits low, so that left the right-hand bars all but still.
   Neither needs real per-band data. Each bar eases the raw level on its own
   clock (so a burst reaches them at different speeds) and rides two sines
   of its own period and phase on top, scaled down toward the outside and
   gated by the level itself so nothing moves once you go quiet. */
const MARK_RISE  = [0.035, 0.025, 0.020, 0.030, 0.045];   // seconds, per bar
const MARK_FALL  = [0.22,  0.15,  0.11,  0.17,  0.26];    // seconds, per bar
const MARK_SHAPE = [0.65,  0.90,  1.00,  0.85,  0.60];    // how much of MARK_GAIN each bar answers to
const MARK_F1    = [1.9,   2.6,   3.1,   2.3,   1.7];     // Hz, the faster of the two sines
const MARK_F2    = [0.31,  0.47,  0.59,  0.41,  0.37];    // Hz, the slower one
const MARK_PHASE = [0.0,   1.3,   2.7,   4.1,   5.5];     // radians
const MARK_WOBBLE_PX = 7;
const markLevels = [0, 0, 0, 0, 0];
let markAt = 0;
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
  // Not the bare global: while floating, this canvas lives inside the small
  // Picture-in-Picture window, a separate top-level window from the one this
  // script itself loaded into, and window.devicePixelRatio would keep
  // reading whichever monitor the *main* tab sits on. Dragging the small
  // window to a second display with a different DPI than that one left the
  // mic drawn at the wrong resolution for where it actually ended up,
  // scaled soft by whichever side over- or under-shot.
  const dpr = (canvas.ownerDocument.defaultView || window).devicePixelRatio || 1;
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
  for (const m of minis) {
    const r = m.canvas.getBoundingClientRect();
    if (!r.width || !r.height) { m.w = m.h = 0; continue; }
    // Per canvas, not hoisted above the loop: same reasoning as fitCanvas,
    // and while floating this one can be measured before or after the
    // window it just moved into settles on its own devicePixelRatio.
    const dpr = (m.canvas.ownerDocument.defaultView || window).devicePixelRatio || 1;
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
    const dpr = (canvas.ownerDocument.defaultView || window).devicePixelRatio || 1;
    cx.setTransform(dpr, 0, 0, dpr, 0, 0);
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
  if (route === 'off') {
    markAt = 0;
    for (let i = 0; i < marks.length; i++) {
      markLevels[i] = 0;
      marks[i].setAttribute('y', ((66 - MARK_MIN_HEIGHT) / 2).toFixed(2));
      marks[i].setAttribute('height', MARK_MIN_HEIGHT.toFixed(2));
    }
  } else {
    // The raw level, not micLevel. That one is already eased once for the
    // mic drawing above, and easing an eased value again flattens the very
    // difference in speed between bars that is the whole point here.
    const raw = amplitudeNow();
    const dt = markAt ? Math.min(Math.max((now - markAt) / 1000, 0), 0.1) : 0.1;
    markAt = now;
    const t = now / 1000;
    for (let i = 0; i < marks.length; i++) {
      const tau = raw > markLevels[i] ? MARK_RISE[i] : MARK_FALL[i];
      markLevels[i] += (raw - markLevels[i]) * (1 - Math.exp(-dt / tau));
      const lv = markLevels[i];
      // Two sines of the bar's own period and phase, never a lookup back
      // into the same frequency data the equalizer attempt already showed
      // does not split evenly for a voice. Scaled by sqrt(lv) rather than
      // lv itself, so a quiet voice still gets a little life in the wobble
      // rather than needing to get loud before it shows at all, and gated
      // by it either way, so silence holds still instead of drifting.
      const wobble = 0.6 * Math.sin(Math.PI * 2 * MARK_F1[i] * t + MARK_PHASE[i])
                   + 0.4 * Math.sin(Math.PI * 2 * MARK_F2[i] * t + MARK_PHASE[i] * 1.7);
      let h = MARK_BASE_HEIGHTS[i] + MARK_GAIN * MARK_SHAPE[i] * lv + MARK_WOBBLE_PX * Math.sqrt(lv) * wobble;
      h = Math.min(60, Math.max(MARK_MIN_HEIGHT, h));
      marks[i].setAttribute('y', ((66 - h) / 2).toFixed(2));
      marks[i].setAttribute('height', h.toFixed(2));
    }
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
    // Swallowed before this, so there was no trace anywhere of why the level
    // meter (browserRmsNow, see computeBrowserRms) sat dead at 0. With the
    // analyser gone, computeBrowserRms reads 0, which never clears
    // silence_threshold, so browserGateTick's lastLoudAt clock stops
    // advancing and the pause to send wait runs out on its own (the queue
    // still goes out; it just never sees the room as loud again). A failure
    // here costs the meter, not whether things get held before sending.
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
     because the mark between two sentences is not the same in every
     language and there is nothing here that has to be spelled. */
  for (const m of minis) {
    const s = t(route === 'off' ? 'resumeTitle' : 'pauseTitle') + '\n' + text;
    m.box.title = s;
    m.box.setAttribute('aria-label', s);
  }
}

/* Clear history takes two presses, the same as the × on a destination chip.
   It cannot be undone, and it sits in settings where a stray click is easy. */
let clearHistoryAsking = 0;
function resetClearHistory() {
  clearTimeout(clearHistoryAsking);
  clearHistoryAsking = 0;
  el.clearHistoryLabel.textContent = t('clearHistory');
}
el.clearHistory.onclick = async () => {
  if (!clearHistoryAsking) {
    el.clearHistoryLabel.textContent = t('clearHistoryAsk');
    clearHistoryAsking = setTimeout(resetClearHistory, 3000);
    return;
  }
  resetClearHistory();
  try { await post('/api/history/clear'); } catch {}
};

/* Say it is done, in the note under the button. The clearing itself is the
   server's answer coming back to every open screen (history_cleared below),
   so this is said there rather than here, and every screen that just lost its
   list says so rather than only the one that was pressed. */
let clearedNoteTimer = 0;
function flashHistoryCleared() {
  clearTimeout(clearedNoteTimer);
  el.clearHistoryDone.textContent = t('historyCleared');
  clearedNoteTimer = setTimeout(() => { el.clearHistoryDone.textContent = ''; }, 2600);
}

function retally() {
  el.none.hidden = el.log.children.length > 0;
}

/* Scrolled away from the top (below, some slack for the odd sub-pixel
   scrollTop scroll anchoring can leave behind) is scrolled away from
   whatever just arrived, since newest lands at the top. */
const logWrap = el.log.parentElement;
function atLogTop() { return logWrap.scrollTop <= 4; }
logWrap.addEventListener('scroll', () => {
  if (atLogTop()) el.logJumpWrap.hidden = true;
});
el.logJump.onclick = () => {
  el.logJumpWrap.hidden = true;
  logWrap.scrollTo({top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
};

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
  // Shown exactly as it was written, and not folded here. The card is the
  // record of what went out, and the fold runs on the server before anything is
  // decided, above the dictionary (to_halfwidth at the top of the loop, then
  // polish). A replacement the dictionary is told to produce keeps the width it
  // was typed in on purpose (apply_replacements), so folding the line again
  // here would show 「ＡＷＳ」 as AWS on a card whose words reached Claude wide.
  // dataset.raw is what /api/resend sends back out, and a resend is meant to be
  // the same utterance a second time, not a narrower one.
  const body = rec.text || '';
  text.dataset.raw = body;
  text.textContent = format(body);
  gutter.append(buildToControl(row.dataset.to));

  row.append(gutter, text);
  /* Nothing was listening when this went out, so it reached nowhere. The line
     the daemon and the viewer write carries a destination whenever any
     listener is known at all (resolve_target names the latest one rather than
     leaving it blank), so a body with none on it is the record of an utterance
     that was written down and read by nothing. Said on the card rather than
     only in the status line, because the status line is gone a few seconds
     later and this is the one place the utterance itself stays. Not built into
     the destination chip beside it, which relabelEntries rebuilds every five
     seconds off who is listening now, while this is a fact about the moment it
     was said and never changes afterwards. */
  if (!row.dataset.to) {
    const nowhere = document.createElement('div');
    nowhere.className = 'nowhere';
    nowhere.textContent = t('sentNowhere');
    row.append(nowhere);
  }
  // Read before the insert below moves it: CSS scroll anchoring already
  // keeps whatever you were reading in the same place on screen when a row
  // lands above it (Chrome, tested), so a reader scrolled away from the top
  // does not need any help from here to avoid a jump. Someone already
  // sitting right at the top gets pulled along instead of anchored in
  // place, the same as scrollTop:0 pinned to the bottom of a normal,
  // newest-last log — the alternative (anchoring holds them a row's height
  // below the true top) would read as the screen quietly drifting off the
  // newest thing without anything having been clicked.
  const wasAtTop = atLogTop();
  el.log.prepend(row);          // newest on top (same order as the mock)
  if (wasAtTop) logWrap.scrollTop = 0;
  else el.logJumpWrap.hidden = false;
  retally();
}

/* Drag-select a misheard word inside a sent entry and land in the dictionary
   with that word already filling the "heard as" side — the correction is
   the only thing left to type. Offered the moment the drag itself finishes
   (mouseup with a non-empty selection), not behind a right click, so the
   right-click menu stays the browser's own (Copy included, wanted often
   enough on its own that overriding the menu outright got in its way).

   doc/win come from the element the mouseup actually landed on rather than
   the bare document/window/getSelection globals, the same reasoning as
   openPickMenu above: while floating, el.page (the log along with it) has
   been moved into the small window's own document (floatParts, further
   down), so a selection, an append, or an innerWidth read against the bare
   globals would all quietly answer for the wrong window instead of the one
   actually on screen. */
let closeSelMenu = null;
function openSelectionMenu(doc, win, x, y, text) {
  if (closeSelMenu) closeSelMenu();
  const menu = doc.createElement('div');
  menu.className = 'to-menu';
  const item = doc.createElement('button');
  item.type = 'button';
  item.className = 'to-menu-item';
  const label = doc.createElement('span');
  label.className = 'to-menu-item-label';
  label.textContent = t('addToDict');
  item.append(label);
  item.onclick = () => { close(); jumpToDictAdd(text); };
  menu.append(item);
  doc.body.append(menu);
  // Clamped the same way openPickMenu's place() clamps a menu that would
  // otherwise run off whichever edge it is closest to, off the click itself
  // rather than an anchor's rect since there is no button here to measure.
  const r = menu.getBoundingClientRect();
  const left = Math.max(8, Math.min(x, win.innerWidth - r.width - 8));
  const top = Math.max(8, Math.min(y, win.innerHeight - r.height - 8));
  menu.style.left = Math.round(left) + 'px';
  menu.style.top = Math.round(top) + 'px';
  function close() {
    menu.remove();
    doc.removeEventListener('click', onDocClick, true);
    doc.removeEventListener('keydown', onKey);
    if (closeSelMenu === close) closeSelMenu = null;
  }
  function onDocClick(e) { if (!menu.contains(e.target)) close(); }
  function onKey(e) { if (e.key === 'Escape') close(); }
  setTimeout(() => doc.addEventListener('click', onDocClick, true), 0);
  doc.addEventListener('keydown', onKey);
  closeSelMenu = close;
}
el.log.addEventListener('mouseup', e => {
  // Left button only. mouseup also fires releasing a right click, and with
  // a selection already sitting there from an earlier drag (unchanged by
  // the right click itself) this would otherwise pop the menu up right
  // alongside the browser's own, which is exactly the clash leaving the
  // right-click menu alone was meant to avoid.
  if (e.button !== 0) return;
  const textEl = e.target.closest('.entry .text');
  if (!textEl) return;
  const doc = textEl.ownerDocument;
  const win = doc.defaultView;
  const sel = win.getSelection();
  const picked = sel && sel.toString().trim();
  // Nothing to offer unless the drag actually left a selection behind, and
  // it is this entry's own — the leftover selection from an entry scrolled
  // away under the pointer is not what this mouseup meant to act on.
  if (!picked || !sel.anchorNode || !textEl.contains(sel.anchorNode)) return;
  openSelectionMenu(doc, win, e.clientX, e.clientY, picked);
});

/* Opens (or switches to) the dictionary's replace tab with the word already
   in place, from openSelectionMenu above. Reopening it wholesale only when
   it was not already showing the dictionary — doing that unconditionally
   would reload the mics, languages and tuning along with it every time,
   and mid-edit elsewhere in the same pane is exactly when this is likely
   to be reached for. */
async function jumpToDictAdd(text) {
  if (navWhere() !== 'dict') await openSettings('dict');
  showDictTab('replace');
  el.newFrom.value = text;
  el.newTo.value = '';
  el.newTo.focus();
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
function openPickMenu(anchor, items, currentKey, onPick, heading, onDisconnect) {
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
    const label = doc.createElement('span');
    label.className = 'to-menu-item-label';
    label.textContent = it.label;
    item.append(label);

    // Ending a session from in here, not just switching to it. Only offered
    // where the caller passes onDisconnect (the roll-up picker that stands
    // in for the chips, each of which already carries its own ×; resending
    // a sent card to a different destination has no such thing to offer).
    // Same two-step ask/confirm as the chip's own ×, kept local to this one
    // row instead of the module-wide flag that guards the chip's version,
    // since this menu is thrown away and rebuilt fresh every time it opens
    // rather than living through the five second poll that flag exists for.
    let confirmDisconnect = null;
    if (onDisconnect) {
      const x = doc.createElement('span');
      x.className = 'x';
      x.textContent = '×';
      x.title = t('disconnectTitle', {name: it.name || it.label});
      let askTimer = null;
      const askToConfirm = () => {
        item.classList.add('asking');
        label.textContent = t('disconnectAsk');
        askTimer = setTimeout(() => {
          item.classList.remove('asking');
          label.textContent = it.label;
        }, 4000);
      };
      confirmDisconnect = async () => {
        clearTimeout(askTimer);
        item.remove();
        await onDisconnect(it.key, it.name || it.label);
      };
      x.onclick = ev => {
        ev.stopPropagation();
        if (!item.classList.contains('asking')) { askToConfirm(); return; }
        confirmDisconnect();
      };
      item.append(x);
    }

    item.onclick = () => {
      if (item.classList.contains('asking')) { confirmDisconnect(); return; }
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
    menu.style.transformOrigin = 'top';
    const overflowRight = menu.getBoundingClientRect().right - (win.innerWidth - 8);
    if (overflowRight > 0) menu.style.left = Math.round(r.left - overflowRight) + 'px';
    // Below the anchor is the default, but a short floated window leaves
    // barely any of that for a row near the bottom, and the list (11rem
    // max, its own scrollbar past that) mostly ran off the edge instead of
    // scrolling into view. Flip above only once below genuinely does not
    // fit and above actually has more room, so a menu that fits either way
    // never jumps for no reason.
    const menuRect = menu.getBoundingClientRect();
    const overflowBottom = menuRect.bottom - (win.innerHeight - 8);
    if (overflowBottom > 0) {
      const roomAbove = r.top - 8;
      const roomBelow = win.innerHeight - 8 - r.bottom;
      if (roomAbove > roomBelow) {
        menu.style.top = Math.max(8, Math.round(r.top - 4 - menuRect.height)) + 'px';
        // Grow from the bottom edge (nearest the anchor now) instead of the
        // top, so the pop-open animation reads as coming from the anchor
        // whichever way it actually opened.
        menu.style.transformOrigin = 'bottom';
      }
    }
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
  knownListeners.map((l, i) => ({key: String(l.pid), label: `${i + 1}. ${l.label}`,
                                 name: l.label, gone: !!l.gone}))
                .filter(i => !i.gone);

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
      // Muted as well, not only while listening. On the on-device entry a model
      // that goes away while the mic is off takes the spoken way back with it,
      // and left saying only that nothing is recorded, the screen keeps the
      // promise muteHint made a moment earlier long after it stopped holding.
      : onDeviceHeld() ? t('onDeviceHold')
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
  syncWakeLock();
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
   edit box below. Neither is doing a job worth the seat, so both step aside
   and leave the box's own discard/send pair as the only thing showing (a
   dedicated way-back-out button, cancelOnce, sat in that seat once, but
   pressing it left whatever was still in the box sitting there hold with no
   visible way to tell — confusing enough in practice that it was dropped
   outright, in favor of discard doing the one thing needed instead: see
   below). */
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
}

/* The setting for using several machines. It changes what it takes for a
   signal to be accepted, so while it is on, the machine name shows on the main
   screen too (buried in settings, you could be talking to the wrong machine and
   never notice). */
// What this machine answers to, as typed (several spellings, comma separated)
const machineNames = () =>
  el.machineName.value.split(/[,、]/).map(v => v.trim()).filter(Boolean);

function paintMachine() {
  const on = el.multiOn.checked;
  const all = machineNames();
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
  // draftTime says when the held text now in the box was appended
  // (appendHeld is the only place that sets it). With nothing held there
  // any more, that stamp is left over from whichever utterance set it last
  // and reads as though it were the current moment (reported live: 23:11
  // still showing at 22:00, long after review mode had been left).
  if (!want) el.draftTime.textContent = '';
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
   screen to highlight while the mic is off.
   Wordings added by hand sit apart in userWords, because the daemon reads them
   differently by kind. The two tail kinds match them at the tail like the
   built-ins, mute only when the whole utterance is that wording
   (voice_daemon.mic_command_match), so 「はい」 ahead of one leaves it as speech. */
// Full-width Latin letters and digits, folded down to half-width.
//
// Chrome's on-device Japanese recognition writes them full-width (「ＰＲ」,
// 「２０２６」), and nobody means that when they say a word of code or a year.
// The server folds the same set the same way (to_halfwidth in voice_daemon.py),
// so the words on screen while you are still speaking are the words that get
// sent. Fold it only there and the card would show 「ＰＲ」 and then flip to PR
// the moment it went out.
//
// Letters, digits and the symbols that only ever mean code when spoken, the
// hyphen-minus － (U+FF0D) among them: a hyphen inside a name like Wi-Fi or
// voice-shell is half-width wherever it is written down, and 「Ｗｉ－Ｆｉ」 came back
// with the letters folded and the hyphen still wide. The long vowel mark ー
// (U+30FC) is a different character and stays, so 「コーヒー」 is untouched.
// Japanese punctuation (、。「」・？！), the full-width parentheses, the full-width
// quotes ＂ and ＇ (prose as often as code, the same reasoning as 〜), kana and the
// full-width space are all left as they are, since each carries meaning at the
// width it is written in. Half-width katakana goes the other way, a whole run at
// a time so ｷﾞ comes back as ギ rather than ｷ + ﾞ.
const FULLWIDTH_CODE_RE = /[Ａ-Ｚａ-ｚ０-９＠＃＆％＋＝／＼＿＜＞＄＊＾｜｀［］｛｝－]/g;
const HALFWIDTH_KANA_RE = /[\uFF61-\uFF9F]+/g;
const toHalfWidth = text => text
  .replace(FULLWIDTH_CODE_RE, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0))
  .replace(HALFWIDTH_KANA_RE, run => run.normalize('NFKC'));

const TAIL_IDS = ['cancel_tail', 'hold_tail', 'mute'];
/* unmute is gathered from the same endpoint but stays out of TAIL_IDS, so the
   sweep above never picks it up on its own. It decides nothing about an
   utterance on its way out, and a sentence that happens to end in
   「ミュート解除」 while the mic is on is ordinary speech, so letting it into
   the sweep would darken the ring for words that really do get sent. The one
   place that wants it asks for it by name (unmuteCommand below). */
const CMD_IDS = [...TAIL_IDS, 'unmute'];
const UNMUTE_IDS = ['unmute'];
const emptyWords = () => Object.fromEntries(CMD_IDS.map(id => [id, new Set()]));
let tailWords = emptyWords();
let userWords = emptyWords();
/* How much may sit ahead of the word and still count as noise rather than a
   real clause. voice_daemon.MUTE_TAIL_NOISE_MAX and UNMUTE_TAIL_NOISE_MAX.
   Unmute's is the tighter of the two there and is the tighter one here: a
   false unmute costs the whole stretch the speaker thought was off, not one
   utterance. */
const TAIL_NOISE_MAX = {mute: 7, unmute: 3};
/* voice_daemon._UNMUTE_TAIL_EXCLUDE. Everyday bare words (「解除」 is said about
   a lock, a hold, anything) still bring the mic back when the whole utterance
   is that and nothing else, but never with a lead-in ahead of them. */
const UNMUTE_TAIL_EXCLUDE = new Set(['解除', 'かいじょ', '解除して', 'かいじょして']);
async function loadTailWords() {
  try {
    const all = await Promise.all(UI_LANGS.map(
      ([code]) => fetch('/api/commands?lang=' + code).then(r => r.json())));
    const out = emptyWords();
    const mine = emptyWords();
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
        for (const w of (d.user || {})[id] || []) if (w) mine[id].add(w.toLowerCase());
      takeCmdOff(d);
    }
    tailWords = out;
    userWords = mine;
  } catch { /* an older server has no such endpoint. Leave the drawing as it was */ }
}

/* What the user switched off, kept beside the tables above rather than folded
   into them. The tables answer "what wordings exist", which is the same on every
   screen, and this answers "which of them does this machine still listen for",
   which the user moves while the screen is up.

   Kinds and single wordings both live here. **The wordings arrive whole, every
   language, not just the one being laid out**, because the tables above are
   gathered across every screen language and a wording struck while the screen was
   in Japanese still has to stop filling the drawing when the screen is English. */
let cmdOff = {kinds: new Set(), words: {}};
function takeCmdOff(d) {
  if (!d || typeof d !== 'object') return;
  const words = {};
  for (const id of CMD_IDS)
    words[id] = new Set(((d.off_words || {})[id] || []).map(cmdKey).filter(Boolean));
  cmdOff = {kinds: new Set(d.off || []), words};
}

/* The same test voice_daemon.take_tail_word runs, against the same wordings
   voice_daemon.active_tail hands it, and then the same strike check
   voice_daemon.take_active_tail and word_enabled make.
   Both ways of switching off are asked about, because both change what the daemon
   will do with the utterance. Miss either one and the drawing goes dark for a
   wording that is going to be sent after all, which is the promise this drawing
   exists to keep. */
const TAIL_TRIM = /[ \t　。、．，・！？!?.,]+$/;
// voice_daemon._TAIL_PREFIX, the 「コマンド」 lead-in in 「〜。コマンド手直し」
const TAIL_PREFIX = ['コマンド', 'こまんど', 'command'];

/* voice_daemon.command_key, one character at a time. Spaces and symbols drop
   out, full-width digits fold to half-width and the rest is lowercased. Each
   folded character keeps where it came from, so once a folded tail matches,
   the text can be cut at the spoken wording even though the two no longer line
   up character for character. */
const FOLD_DROP = new Set(' \t\u3000。、．，・…！？!?.,-~〜"\'「」『』()（）');
function foldChars(s) {
  const chars = [], at = [];
  const cs = [...s];
  let i = 0;
  for (let k = 0; k < cs.length; k++) {
    // toHalfWidth the same as the server's _folded_chars, and folded before the
    // drop test rather than after, so 「｡」 goes out as the 「。」 it means the way
    // it does there. One character at a time, except for the one fold that is
    // not one for one: half-width katakana carries its dakuten as a character of
    // its own, so ｷ and ﾞ are taken together and come back as ギ. Both characters
    // of the pair hang on the base, so cutting there takes the whole pair off.
    let unit = cs[k];
    if (unit >= '｡' && unit <= 'ﾟ'
        && (cs[k + 1] === 'ﾞ' || cs[k + 1] === 'ﾟ')) {
      unit += cs[k + 1];
      k++;
    }
    let f = '';
    for (const x of toHalfWidth(unit)) if (!FOLD_DROP.has(x)) f += x.toLowerCase();
    for (const x of f) { chars.push(x); at.push(i); }
    i += unit.length;
  }
  return {chars, at};
}
const cmdKey = s => foldChars(String(s).trim()).chars.join('');

/* The longest wording that matches at the tail, which kind it belongs to and
   where in text it starts, or null.

   Compared in the command_key shape, the same as the daemon, so spacing does
   not decide it (「음 마이크음소거」 is the table's 「마이크 음소거」, not the
   shorter 「음소거」 inside it). Within a kind the longest wording at the tail
   decides, struck or not, and a struck one then takes the whole kind out for
   this utterance, for every kind alike, the same as voice_daemon.take_tail_word
   followed by take_active_tail (the tails) or word_enabled (mute). Skipping
   struck wordings before choosing would let a shorter one inside it fire
   instead (「静音」 inside a struck 「麦克风静音」). A wording typed back in by
   hand wins over its strike, as it does there. Across kinds the longest wins.

   mute's ceiling (TAIL_NOISE_MAX) is measured the way the daemon measures it,
   on what is left ahead of the word once the 「コマンド」 lead-in is off, so a
   sentence that only happens to end in the word after a real clause is not
   read as "about to fire", and 「えーと、コマンドミュート」 is. Words added
   by hand for mute count only as the whole utterance, as in the daemon. */
function matchingTailWord(text, ids = TAIL_IDS) {
  const body = text.trim().replace(TAIL_TRIM, '');
  if (!body) return null;
  const lead = text.length - text.trimStart().length;
  const {chars, at} = foldChars(body);
  const key = chars.join('');
  if (!key) return null;
  let best = null;
  for (const id of ids) {
    if (cmdOff.kinds.has(id)) continue;
    const off = cmdOff.words[id] || new Set();
    const mine = userWords[id] || new Set();
    const ceiling = TAIL_NOISE_MAX[id];
    let hit = null;
    const consider = (w, wk) => {
      if (!wk || !key.endsWith(wk)) return;
      const n = [...wk].length;
      if (hit && n <= hit.n) return;
      hit = {w, wk, n};
    };
    for (const w of tailWords[id] || []) {
      const wk = cmdKey(w);
      // The everyday words on unmute's list count only as the whole utterance
      // (voice_daemon builds UNMUTE_TAIL without them while UNMUTE_WORDS keeps
      // them), so they are passed over unless nothing at all sits ahead of them.
      if (id === 'unmute' && UNMUTE_TAIL_EXCLUDE.has(w) && wk !== key) continue;
      consider(w, wk);
    }
    if (id === 'mute') {
      for (const w of mine) if (cmdKey(w) === key) consider(w, key);
    } else if (id !== 'unmute') {
      // unmute is the one kind no wording can be added to (USER_COMMAND_KINDS)
      for (const w of mine) consider(w, cmdKey(w));
    }
    if (hit === null) continue;
    const cut = at[chars.length - hit.n];
    if (ceiling !== undefined && hit.wk !== key) {
      let rest = body.slice(0, cut).replace(TAIL_TRIM, '');
      const low = rest.toLowerCase();
      const pre = TAIL_PREFIX.find(p => low.endsWith(p));
      if (pre) rest = rest.slice(0, rest.length - pre.length).replace(TAIL_TRIM, '');
      if ([...rest].length > ceiling) continue;
    }
    if (off.has(hit.wk) && ![...mine].some(w => cmdKey(w) === hit.wk)) continue;
    if (!best || hit.n > best.n)
      best = {id, word: hit.w, start: lead + cut, n: hit.n};
  }
  return best;
}
function endsWithTailCmd(text) {
  return matchingTailWord(text) !== null;
}

/* voice_daemon._NAME_SEP: what may sit between the machine's name and the
   word itself in 「開発用ミュート解除」. */
const NAME_SEP = ' \t\u3000、,。．，:：・のはでをへに';

/* voice_daemon._strip_name. What is left once this machine's name has been
   taken off the head, or null when the head is not one of its names. The name
   is folded the way the recognized text already is, so a name typed as
   「Ｍａｃ」 matches. Longest first, so a machine called both Mac and MacBook
   is not cut at the shorter one. */
function stripMachineName(text, names) {
  const body = text.trim();
  const low = body.toLowerCase();
  for (const name of [...(names || [])].sort((a, b) => b.length - a.length)) {
    const folded = toHalfWidth(name).toLowerCase();
    if (!folded || !low.startsWith(folded)) continue;
    let rest = body.slice(folded.length);
    let i = 0;
    while (i < rest.length && NAME_SEP.includes(rest[i])) i++;
    return rest.slice(i);
  }
  return null;
}

/* The wording that brings the mic back, or null. Asked of an utterance heard
   while the mic is off, and of nothing else.

   The same question voice_daemon.apply_voice_command asks with muted=True, put
   to the tables this page already holds: the built-in wordings of every
   language, the lead-in tolerance, the kind and the single wordings the user
   switched off, and the machine's own name at the front when several machines
   are listening. With names on and none of them at the front, nothing moves,
   the same as there (a command with no name cannot be pinned to a machine).

   The dictionary-rewritten form is asked about as well, the way the daemon
   asks it, so a wording that keeps coming back garbled can be brought back by
   registering it (「ミュート回収 → ミュート解除」). */
function unmuteCommand(text, {multi = false, names = [], fixup = null} = {}) {
  let body = (text || '').trim();
  if (!body) return null;
  if (multi) {
    const named = stripMachineName(body, names);
    if (named === null) return null;
    body = named.trim();
    if (!body) return null;
  }
  const hit = matchingTailWord(body, UNMUTE_IDS)
    || (fixup ? matchingTailWord(fixup(body), UNMUTE_IDS) : null);
  return hit ? hit.word : null;
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
   read from the other side of the fork.
   No dead zone here (SEND_CUE_DEAD is a daemon-only concern): that gap exists
   to tell a real pause from a breath taken mid-sentence, while the words are
   still being decided. A queued item has already been decided, isFinal fired
   for it, so there is nothing left to mistake a breath for. */
function paintBrowserSendCue(now) {
  el.sendOne.classList.toggle('on', el.send.hidden);
  if (!pendingBrowserSends.length) {
    el.sendOne.classList.remove('drop');
    if (el.sendOne.disabled !== true) el.sendOne.disabled = true;
    el.sendOne.style.setProperty('--r', '0');
    return;
  }
  const wait = sendWaitMs();
  let target = wait > 0 ? Math.max(0, Math.min(1, (now - lastLoudAt) / wait)) : 1;
  // Held just short of the end while recognition is still behind, so the ring
  // never sits full with nothing going out (browserGateTick reads the same
  // question). Short of it rather than frozen where it stood, because what is
  // being waited on really is nearly over.
  if (recognizerOwesWords(now, wait)) target = Math.min(target, 0.95);
  // Checked against the whole queue joined together, the shape it actually
  // goes out in (browserGateTick), not just the oldest item alone. A short
  // clause sitting behind more still-accumulating queued content is not the
  // same as a short clause on its own, and reading it that way left the ring
  // showing "about to be dropped" the entire time more was still coming in.
  const whole = pendingBrowserSends.map(i => i.text).join(clauseJoin());
  el.sendOne.classList.toggle('drop', !worthSending(whole));
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
  // Stamped right here, before routeQueue can sit behind anything already
  // pending. Taken instead at the top of changeRoute (once this call's turn
  // in that queue finally comes up), a backlog of earlier route changes
  // delays the stamp by however long they took to clear, and a fresh
  // utterance begun the instant this button was pressed can then look
  // "already running" to the discard below and gets cut along with it (#108).
  const clickedAt = Date.now() / 1000;
  route = next;
  resetBrowserGesture();
  if (next !== 'off') lastMode = next;
  paint();                            // show it the instant it is pressed
  inFlight = true;
  const task = routeQueue.then(() => changeRoute(next, prev, revision, true, clickedAt));
  routeQueue = task.catch(() => {});
  return task;
}

async function changeRoute(next, prev, revision, syncServer, clickedAt) {
  let applied = false;
  // Whether this call is the one that already told the server "not off"
  // (below), separate from syncServer=false calls, which start from a state
  // the server told *us* about, already unmuted before this call began.
  let muteSynced = false;
  try {
    if (revision !== routeRevision) return;
    const w = ROUTE[next];
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
      muteSynced = true;
      if (revision !== routeRevision) return;
    }
    // Run after the server already knows the mic is live again (#108), not
    // before it. Discarding first left the server still muted for as long as
    // the discard's own round trip took, so anything actually said in that
    // stretch was judged against a mute that had not been lifted yet from the
    // daemon's own point of view (voice_daemon.py's separate mute-generation
    // check) and got thrown away there instead, unmoved by this fix.
    if (prev === 'off' && next !== 'off' && engineOnish() && !asrActive()) {
      const discarded = await discardCurrent({announce: false, at: clickedAt});
      if (!discarded) throw new Error('Could not discard current utterance');
      if (revision !== routeRevision) return;
    }
    if (revision !== routeRevision) return;
    applyRouteSideEffects(next);
    applied = true;
  } catch (err) {
    if (revision !== routeRevision) return;
    let rollbackError = null;
    // The server was already told "not off", either by this call just above
    // or by whatever triggered a syncServer=false call in the first place,
    // before the step meant to follow it (the discard) failed. Left alone
    // that shows off on screen while the mic is actually live underneath.
    if (prev === 'off' && next !== 'off' && (muteSynced || !syncServer)) {
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
  const clickedAt = Date.now() / 1000;   // same reasoning as setRoute above
  route = next;
  resetBrowserGesture();
  if (next !== 'off') lastMode = next;
  paint();
  inFlight = true;
  const task = routeQueue.then(() => changeRoute(next, prev, revision, false, clickedAt));
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
    // Except on the on-device entry, where there is no audio going anywhere to
    // let go of and the word that brings it back has to stay audible.
    if (recWanted && !listensWhileMuted()) { asrPausedByRoute = true; stopRecognition(); }
    // The session stays there, so nothing clears what was on screen when the
    // mute landed. Folding the session up was what did it before, and left to
    // itself the last thing heard sits in the box under a screen that says
    // muted. A throttled paint already waiting its turn is dropped with it
    // (paintInterimThrottled), or it would fire a moment later and put those
    // same words back.
    else if (recWanted) {
      if (interimThrottleTimer) { clearTimeout(interimThrottleTimer); interimThrottleTimer = null; }
      latestInterimForPaint = lastInterimHeard = '';
      el.stream.textContent = browserStreamText();
    }
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

// "Say X to come back" is only true where saying it can still be heard. The
// plain browser entry cuts the mic the instant it mutes (unlike the daemon,
// which keeps listening for the word on purpose), so under that one the only
// way back is the button. The on-device entry keeps listening, so it gets the
// same line the local engines get.
// Held off for a model that is not there (onDeviceHeld), the on-device entry
// has no session open either, so the word cannot be heard through it after
// all and the button is the only way back. Said at the moment of muting, this
// line is the one thing the person carries into a stretch they are not
// watching the screen for, so it has to be true of right now, not of the
// entry in the dropdown.
const muteHint = () =>
  t(asrChosen && !(listensWhileMuted() && !onDeviceHeld())
    ? 'voiceMutedBrowser' : 'voiceMuted');

/* The line under the unmute switch in the lightbulb, where it cannot be heard.
   The plain entry is the one that cuts the mic; the entry that recognizes on
   this device keeps listening, so it is offered as the way to have the word
   back, but only where Chrome is new enough to show it (canLocalASR). */
const unmuteDeadLine = () => t('cmdUnmuteBrowserOff')
  + (canLocalASR ? ' ' + t('cmdUnmuteOnDevice', {local: t('engineBrowserLocal')}) : '');

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
    // The side that is matched folds the way the recognized text does, so an
    // entry saved as 「ＡＷＳ」 lights up on the half-width AWS on screen, exactly as
    // apply_replacements does it on the server. What it becomes is left as typed.
    dictPairs = Object.entries(d.replace || {})
      .filter(([k, v]) => k && v)
      .map(([k, v]) => [toHalfWidth(k), v])
      .sort((a, b) => b[0].length - a[0].length);   // match the longer words first
    // The same read already carries both lists the drawing in the corner needs,
    // so it costs no second request and there is no second thing to keep fresh.
    // The two are tidied differently on purpose, because the daemon tidies them
    // differently. is_noise takes the ignore list as it stands and only lowers
    // the case, so an entry saved as 「はい。」 never matches anything there and
    // the utterance really is sent. Trimming it here would go dark on a word
    // that goes out. is_allowed_short does strip the punctuation off its list,
    // so that one gets the same treatment here.
    dictIgnore = new Set((d.ignore || []).map(w => toHalfWidth(w).trim().toLowerCase())
                                        .filter(Boolean));
    dictUnignore = new Set((d.unignore || []).map(w => cueCore(toHalfWidth(w)))
                                             .filter(Boolean));
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
  /* Not folded here. What arrives has already been folded where it came in,
     above the dictionary both times (onresult on the browser road, the partial
     from the daemon), and what this is handed is the text after withDict has
     run. Folding at this point would narrow a replacement the dictionary was
     told to produce wide, and the live line would then disagree with the card
     the same words land on when they go out. Same reasoning as the server's,
     which folds once at the top of the loop and never again after polish. */
  s = s || '';
  const match = s ? matchingTailWord(s) : null;
  const key = match ? match.id + ' ' + match.word : null;
  tailMarkPending = {s, match};
  if (key !== tailMarkKey) {
    tailMarkKey = key;
    clearTimeout(tailMarkTimer);
    tailMarkTimer = match ? setTimeout(showTailMark, TAIL_MARK_DELAY) : null;
  }
  if (match && !tailMarkTimer) { renderTailMark(s, match); return; }
  // Browser recognition fires onresult repeatedly even when nothing about
  // the interim guess actually changed, and a textContent write repaints
  // regardless of whether the value is the same as what is already there.
  // Skipping the no-op write is what tells those apart from a real update.
  if (el.stream.textContent !== s) el.stream.textContent = s;
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
  const cut = match.start;
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

/* Back to instant with text still in the draft box. Left as it was, the box
   sat there unsent while everything said after it went straight out ahead of
   it. Sending it the instant the mode flips was the other way, but a switch
   made by mistake would then send a draft that was not finished. So it rides
   along with the next utterance instead: that one is held like Edit this one,
   lands at the end of the box, and the whole box goes out together, in the
   order it was said. Until then the screen already reads instant. */
let carryDraft = false;
// Whether any voice has started since the switch. A held line that was
// already on its way (a clause still waiting out its quiet, a POST in
// flight, a line the daemon settled a moment before) is only added to the
// box. The one that sends it all is the one begun after the switch.
let voiceSinceCarry = false;
function carryIntoNext() {
  oneShot = true;
  carryDraft = true;
  voiceSinceCarry = false;
  el.note.hidden = true;
  paint();
  el.hint.textContent = t('hintCarry');
  // The daemon caps its quiet wait at 2s while drafting. Carrying is really
  // sending, so it is told to wait the full time again.
  post('/api/pause', {paused: true, carry: true}).catch(() => {});
}

// Choosing a mode yourself clears both Edit this one and the line from Claude
el.segLive.onclick = () => {
  el.note.hidden = true;
  if (route === 'hold' && !carryDraft && el.draft.value.trim()) { carryIntoNext(); return; }
  oneShot = false; carryDraft = false; setRoute('live');
};
el.segHold.onclick = () => { oneShot = false; carryDraft = false; el.note.hidden = true; setRoute('hold'); };
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
    if (m.history_cleared) {
      el.log.replaceChildren();
      el.logJumpWrap.hidden = true;
      retally();
      flashHistoryCleared();
      return;
    }
    const result = 'partial' in m || 'held' in m || m.text != null;
    if (result && (wasDiscarding || number <= discardResultCutoff || dropBarriers.size)) return;

    if ('level' in m) {
      // Catch only the moments voice starts and breaks off. level is not sent
      // when the value has not changed, but the level still wavers through the
      // silence, so we spot the turning points ourselves.
      if (m.speaking !== daemonSpeaking) {
        if (m.speaking) {
          if (carryDraft) voiceSinceCarry = true;
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
        if (next === 'live' && route === 'hold' && !carryDraft && el.draft.value.trim()) {
          // Switched to instant by voice with a draft still in the box: keep
          // holding the next one so the draft rides along with it (carryIntoNext).
          // Every open screen hears this echo and each may send the box; the
          // server lets the same text through only once in a few seconds.
          // Only if nothing else was chosen during the round trip (a press
          // on Draft or mute in the meantime wins).
          const rev = routeRevision + 1;
          setRoute('hold').then(() => {
            if (routeRevision === rev && route === 'hold' && el.draft.value.trim()) carryIntoNext();
          });
        } else if (next !== route) {
          route = lastMode = next; oneShot = false; carryDraft = false; paint();
        }
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
      // Folded on arrival, not only where it is drawn. worthSending and the
      // send cue below read this same string, so leaving it wide here would
      // have them judging text the server would never see in that shape.
      livePartial = toHalfWidth(m.partial).trim();
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
      // It is in the box now, so take it out of the live line above, the same
      // as a sent one is. Left there, it sat in both places until the next
      // repaint came round, a few seconds later. Whatever is being said right
      // now (browser recognition's current interim) stays.
      const still = asrActive() ? browserStreamText() : '';
      el.stream.textContent = still;
      el.tray.classList.toggle('idle', !still);
      // The utterance the draft was waiting to ride along with. Out they go.
      if (carryDraft && voiceSinceCarry) {
        carryDraft = false;
        sendDraft({carry: true});
      }

    } else if (m.text != null) {
      clearSendCountdown();   // that is one utterance done. Counting starts again with the next voice
      // Only rows carrying a body go into the log. Every time another control
      // message was added (level / muted / paused / voice_cmd and so on), an
      // older screen would line it up as an utterance and make an empty card.
      // Quietly dropping keys it does not know is the safer way.
      addEntry(m);
      // Nothing was listening, so say it at the moment it happens as well.
      // The card below keeps the record, but someone talking is watching the
      // line under the mic, not the log. Left out for the history replayed
      // when the page connects (m.replay), or every old card of a session
      // spent working alone would announce itself again on every reload.
      if (!m.to && !m.replay) say(t('sentNowhereHint'), 8);
      el.stream.textContent = '';
      el.tray.classList.add('idle');
    }
}

// Grow the height to fit the contents (so nothing scrolls inside)
function grow() {
  el.draft.style.height = 'auto';
  el.draft.style.height = el.draft.scrollHeight + 'px';
}

/* Append a held utterance at the end. The caret position and your edits are kept.
   Taken as it came, not folded. The held line was folded on the server before
   the dictionary ran and has been through the dictionary since, and what goes
   into this box is what gets posted to /api/send word for word. Folding here
   would quietly narrow a replacement the dictionary was told to produce wide,
   and Claude would receive text nobody asked for. */
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
  syncWakeLock();
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

/* What this tab had going at the moment it was reloaded, handed across the
   reload in its own sessionStorage. A reload used to come back muted with
   everything unsent gone: only the held lines the server keeps (s.held) ever
   made it back, never the instant-mode box, the clauses still waiting out
   their quiet stretch, or the words being recognized (#118). It is written on
   the main window's pagehide, so the "Updated" button and an ordinary F5
   both go through it. The small window closing fires pagehide on its own
   window, never this one, so that is not mistaken for a reload. */
const RESUME_KEY = 'vs.resume';
const RESUME_MAX_AGE_MS = 30000;   // older than this is some other visit, not this reload

/* A box already on its way out (sendDraft waiting on the server) is left
   out. It is emptied only once the send answers, and put back after the
   reload it would go out a second time with the next utterance. A box being
   discarded (discard waiting on the server) is left out the same way, or
   what was just thrown away would come back after the reload. */
function resumeSnapshot() {
  const leaving = sendingDraft || discardingDraft;
  return {
    live: route !== 'off' && recWanted,
    draft: leaving ? '' : el.draft.value,
    touched: leaving ? false : draftTouched,
    pending: browserStreamText(),
    at: Date.now(),
  };
}

// Read once and removed at once, so a later reload never picks up an old one.
function takeResume(storage, now) {
  let raw = null;
  try {
    raw = storage.getItem(RESUME_KEY);
    storage.removeItem(RESUME_KEY);
  } catch { return null; }
  if (!raw) return null;
  let r;
  try { r = JSON.parse(raw); } catch { return null; }
  if (!r || typeof r.at !== 'number' || !(now - r.at <= RESUME_MAX_AGE_MS)) return null;
  return r;
}

/* The box comes back as it was, with whatever had not gone out yet added at
   the end rather than queued again. It may already have reached Claude in the
   instant the page went away, so it waits for a look and a press instead of
   going out twice. */
function restoreDraft(r) {
  // Put back character for character. Most of what is in this box was typed by
  // hand, and a reload is no occasion to rewrite somebody's own words. Someone
  // who wrote 「ＡＢＣ」 on purpose gets it back that way, and it goes out that way.
  const text = [r.draft, r.pending]
    .map(s => (typeof s === 'string' ? s.trim() : ''))
    .filter(Boolean).join('\n');
  if (!text) return;
  el.draft.value = text;
  draftTouched = !!r.touched;
  paintDraft();
  grow();
}

/* The held lines the server keeps, added once on the first look after a
   load. Only the ones the box does not already have go in, so the ones it
   got back from before the reload are not doubled, while the ones held
   during the reload itself still turn up. Left out, they stayed out of
   sight and were wiped along with the list when the box was sent. */
function mergeHeld(held) {
  const have = new Set(el.draft.value.split('\n').map(l => l.trim()).filter(Boolean));
  // Compared as written, on both sides. Everything that reaches this box keeps
  // the width it arrived in (appendHeld and restoreDraft above), so a held line
  // and the copy of it already sitting there are the same string, and nothing
  // has to be narrowed on one side of the comparison to make them meet.
  const add = held.map(r => (r && typeof r.text === 'string' ? r.text.trim() : ''))
    .filter(x => x && !have.has(x));
  if (!add.length) return;
  const cur = el.draft.value.replace(/\s*$/, '');
  el.draft.value = cur ? cur + '\n' + add.join('\n') : add.join('\n');
  paintDraft();
  grow();
}

addEventListener('pagehide', () => {
  try { sessionStorage.setItem(RESUME_KEY, JSON.stringify(resumeSnapshot())); } catch {}
});

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

    const prevRoute = route;
    if (!armPending) {
      route = s.muted ? 'off' : (s.paused ? 'hold' : 'live');
      if (route !== 'off') lastMode = route;
    }
    paint();
    // Coming out of off here, not through a press, still has to bring
    // recognition back. Only the display flipping left the screen saying live
    // while nothing listened, and with the idle clock never started, the
    // idle mute then really muted a few minutes later (#118, after a reload
    // whose first touch was not the mic).
    if (prevRoute === 'off' && route !== 'off') applyRouteSideEffects(route);
    // And into off the same way. Muted from another screen while this one was
    // reloading, the display went to off with recognition still running.
    else if (prevRoute !== 'off' && route === 'off') applyRouteSideEffects('off');

    // Restore what was collected so a reload does not lose it. Only what the
    // box lacks goes in, at the end, so nothing being typed is overwritten.
    if (!seeded && Array.isArray(s.held) && s.held.length) mergeHeld(s.held);
    seeded = true;
    paintDraft();
    if (!el.draft.hidden) grow();
  } catch {
    setState('down', t('statusDown'));
  }
}

/* ── Send and discard ───────────────────── */
// Raised while the box is on its way to the server (resumeSnapshot leaves it out)
let sendingDraft = false;
// Same for a discard waiting on the server
let discardingDraft = false;
async function sendDraft({carry = false} = {}) {
  carryDraft = false;
  const text = el.draft.value.trim();
  if (!text) return;
  sendingDraft = true;
  try {
    await post('/api/send', {text, edited: draftTouched, carry});
  } finally {
    sendingDraft = false;
  }
  el.draft.value = '';
  draftTouched = false;
  grow();
  paintDraft();
  endOneShot();
}
el.send.onclick = () => sendDraft();

// What you discard can be brought back once (a confirm dialog every time is a nuisance)
let lastDiscarded = '';
// Kept alongside it so bringing it back does not lose the edited stamp too
let lastDiscardedTouched = false;

el.discard.onclick = async () => {
  // Nothing left to carry along, so back to plain instant.
  if (carryDraft) { carryDraft = false; endOneShot(); }
  lastDiscarded = el.draft.value;
  lastDiscardedTouched = draftTouched;
  discardingDraft = true;
  try {
    await post('/api/discard');
  } finally {
    discardingDraft = false;
  }
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
  // Editing just this one, unlike send, is left standing rather than closed
  // out here (no endOneShot). Discard used to always end it, and the box
  // it closed down into still had whatever was said sitting in it, held,
  // with nothing on screen marking that it was still there to deal with —
  // confusing enough in practice that this box staying open, empty and
  // ready to type into, replaced it. Clicking outside while it is empty
  // (leaveOneShotIfEmpty, further down) is still the way out for good.
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

function discardCurrent(options = {}) {
  // Stamped here, ahead of discardQueue, for the same reason setRoute stamps
  // clickedAt ahead of routeQueue (#108). A caller that already has a truer
  // moment in mind (changeRoute, handing over when the button was actually
  // pressed) passes its own `at` and this leaves it alone.
  const at = options.at ?? (Date.now() / 1000);
  const task = discardQueue.then(() => discardCurrentNow({...options, at}));
  discardQueue = task.catch(() => {});
  return task;
}

async function discardCurrentNow({announce = true, at} = {}) {
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
        response = await post('/api/drop-current', {id, at});
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

// Once it is sent, or the box empties out and you click away
// (leaveOneShotIfEmpty, below), go back to the mode it came from.
async function endOneShot() {
  carryDraft = false;
  if (!oneShot) return;
  oneShot = false;
  await setRoute('live');
}

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
  el.micSettingsSaid.hidden = true; // what a press said last time is not news now
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
    /* One that is gone keeps its number, so the key is still pressed at it.
       setRoute2 turns it down and says why, and the ack below would paint
       over that with "now going there" for a place nothing can reach (#110).
       So the answer is given here and the ack skipped. */
    if (pickTo.gone) {
      chime('err');
      say(t('listenerGoneHow', {name: pickTo.label}), 9);
      return;
    }
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
  ['zh-CN', '中文（简体）'], ['zh-TW', '中文（台灣）'], ['zh-HK', '粵語（香港）'],
  ['ko-KR', '한국어'],
  ['es-ES', 'Español'], ['fr-FR', 'Français'], ['de-DE', 'Deutsch'],
  ['it-IT', 'Italiano'], ['pt-BR', 'Português (BR)'], ['ru-RU', 'Русский'],
  ['hi-IN', 'हिन्दी'], ['id-ID', 'Indonesia'], ['th-TH', 'ไทย'],
  ['vi-VN', 'Tiếng Việt'],
];

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const canBrowserASR = !!SR;

/* ── Browser recognition that stays on this device ──
   Chrome 139 and later can run the very same Web Speech API recognition on
   this machine instead of sending the audio to Google, once it holds a model
   for the language being spoken (processLocally). The model is a one-time
   download per Chrome profile, shared by every site, and Chrome only lets a
   page start that download from inside a press (SR.install). Chrome also
   keeps from each site whether the model is there until that site has asked
   for it once: a site that never called install() is told downloadable even
   with the model on disk (seen on Chrome 153, so another site cannot learn
   what you have installed). The press is then over in a few seconds with
   nothing fetched, and the answer stays for that site across restarts.

   It is offered as a second browser entry in the engine dropdown. The server
   never hears about it: to the server both entries are 'browser', and which
   of the two it is lives in this browser (localStorage), which is also where
   the model it needs lives. Another browser pointed at the same viewer has
   models of its own, or none. The 5 second loadEngines poll keeps putting the
   server's 'browser' back into chosenEngine, so what the dropdown shows is
   worked out from both (engineShown). Read off chosenEngine alone, it would
   snap back to the plain entry every 5 seconds.

   Nothing here ever falls back to the cloud. Whoever picked this entry picked
   it so their voice stays on the machine. When the model is missing, or
   Chrome refuses, recognition simply does not start, and the settings say why
   and what to do (download it, or pick the plain entry on purpose). A quiet
   fallback would send exactly the audio they chose to keep.

   The pieces with no page in them come first, together, so a test can lift
   them out and run them on their own (tests/test_on_device.py). */
const BROWSER_LOCAL = 'browser-local';
const ON_DEVICE_FLAG = 'asrLocal';

// Through store, which already swallows a storage that throws (a private
// window, blocked site data). Losing it only puts the plain entry back, which
// recognizes nothing until someone presses the mic anyway.
const readOnDeviceFlag = s => s.get(ON_DEVICE_FLAG, '') === '1';
const writeOnDeviceFlag = (s, on) => s.set(ON_DEVICE_FLAG, on ? '1' : '');

// The dropdown's value, from the server's engine and this browser's flag
const engineShown = (chosen, local) => chosen === BROWSER_ENGINE && local ? BROWSER_LOCAL : chosen;
// And back again: what the server is told, and whether it is the local one
const enginePicked = value => value === BROWSER_LOCAL
  ? {engine: BROWSER_ENGINE, local: true}
  : {engine: value, local: false};

/* What our own server saw on the disk (GET /api/ondevice). engine is the
   SODA engine, pack the model for this one language, and either can be null
   when nothing could be told. Only both being there means Chrome really
   holds it, and then downloadable is only this site not having asked yet. */
const onDeviceHasModel = disk => !!disk && disk.engine === true && disk.pack === true;
// What that model weighs, for the line that says so. '' when the server could
// not tell, and the wording falls back to a rough figure per language.
const onDeviceSizeText = disk => {
  const bytes = disk && disk.packBytes > 0 ? disk.packBytes : 0;
  return bytes ? Math.round(bytes / 1048576) + ' MB' : '';
};

/* What the settings say for each answer SR.available() can give. '' is not
   asked yet (or asked for a language no longer chosen), and a refusal from
   Chrome itself outranks whatever available() last said, since it is Chrome
   saying no to the real thing.

   downloadable is the one answer that does not say what it looks like.
   Chrome tells a site downloadable until that site has called install()
   itself, model on disk or not, so that no site can read off what you have.
   With the disk saying the model is right there, nothing is fetched at all,
   it is this page being let at what Chrome already holds, and it is over in
   seconds. Told that, the line says so, and so does the one shown while it
   runs (the "few minutes" of a real download would be wrong there). */
const ON_DEVICE_KEYS = {
  available: 'onDeviceReady', downloadable: 'onDeviceNeedsDownload',
  downloading: 'onDeviceDownloading', unavailable: 'onDeviceUnavailable',
};
const ON_DEVICE_HERE_KEYS = {downloadable: 'onDeviceEnable', downloading: 'onDeviceEnabling'};
const onDeviceStatusKey = (status, refused, disk) =>
  refused ? 'onDeviceRefused'
    : (onDeviceHasModel(disk) && ON_DEVICE_HERE_KEYS[status])
      || ON_DEVICE_KEYS[status] || 'onDeviceChecking';

/* Whether a press anywhere on the page may finish it by itself.
   Chrome only starts install() from inside a press, so nothing here can be
   fully unattended. But when the model is already on the disk there is
   nothing to fetch, and letting the next press of anything at all (mute,
   send, settings) carry the install too costs that press nothing and is over
   in seconds. A real download is not slipped into a press meant for something
   else, so with the model missing, or with the disk unreadable, only the
   button does it. And nothing fires off the local entry, where recognition on
   this device is not what was asked for in the first place. */
const onDeviceMayAutoInstall = (local, chosen, status, refused, installing, disk) =>
  !!local && !!chosen && status === 'downloadable' && !refused && !installing
  && onDeviceHasModel(disk);

// Whether recognition may start at all. Off the local entry nothing is held
// here. On it, only a model Chrome says is on this machine lets it through,
// and every other answer holds it off rather than letting it go to the cloud.
const onDeviceMayStart = (local, status, refused) =>
  !local || (status === 'available' && !refused);

/* Whether recognition keeps running while the mic is off.

   On the plain browser entry it must not: the audio goes to Google, and the
   whole meaning of muting is that it stops. Chrome's microphone is let go the
   instant it mutes, which is also why the word cannot be heard there.

   On the on-device entry nothing leaves this machine, so there is nothing to
   stop. It keeps listening exactly as the local engines do, and for the same
   one reason: so 「ミュート解除」 can still be heard. Everything else heard while
   it is off is thrown away where it is heard (newRecognition's onresult), it
   is never queued, never sent, never written down and never put on screen.
   Chrome goes on showing its recording dot while that runs, the same as it
   does for a local engine's own microphone, and the screen says muted
   throughout so nobody reads that dot as being listened to. */
const listensWhileMuted = () => asrChosen && onDeviceLocal;

/* Whether a session should be open right now, and the pause flag that goes
   with it. Everywhere that used to work this out from route === 'off' comes
   through here, or the 5 second poll would put its own answer back a moment
   later and cut the mic the on-device entry is supposed to keep. */
function syncRecWanted() {
  recWanted = asrChosen && (route !== 'off' || listensWhileMuted());
  asrPausedByRoute = asrChosen && !recWanted;
  return recWanted;
}

/* What Chrome says when processLocally is on and it has no model to use.
   Chromium says language-not-supported, the spec says service-not-allowed.
   Only the second is also what a refused microphone can look like, and only
   while starting on its own after a reload (autoResumed) is that the likelier
   reading, so there it is left to the path that already handles it. */
const onDeviceRefusal = (error, autoResumed) =>
  error === 'language-not-supported' || (error === 'service-not-allowed' && !autoResumed);

// Whether the local entry can be offered here at all. Chrome 139 and later.
const canLocalASR = canBrowserASR && typeof SR.available === 'function'
  && typeof SR.install === 'function';
let onDeviceLocal = canLocalASR && readOnDeviceFlag(store);
/* Whether this browser really keeps the flag. store swallows a storage that
   throws (site data blocked), so a write there can quietly go nowhere and a
   read come back as off. Only where it is kept may the 5 second poll read it
   back: where it is not, the read would say off every time and put the plain
   entry back five seconds after the local one was picked, sending to Google
   exactly the audio that pick was about. There this tab's own memory is the
   only record of the choice there is, and it holds until the page is left. */
let onDeviceFlagKept = true;
let onDeviceStatus = '';      // what available() last said, for onDeviceLang
let onDeviceLang = '';
let onDeviceRefused = false;  // Chrome refused a start after available() said yes
let onDeviceInstalling = false;
let onDeviceInstallId = 0;    // which press the current download belongs to
let onDeviceInstallLang = '';  // and the language it was pressed for
let onDeviceSawDownloading = false;
let onDeviceProblem = '';     // a download that did not go through, until the next try
let onDeviceAsk = null;       // the available() call under way, {lang, promise}
let onDevicePoll = null;
let onDeviceDisk = null;      // what the server saw on the disk, for onDeviceDisk.lang
let onDeviceDiskAsk = '';     // the language a look at the disk is under way for
let onDeviceArmed = null;     // the press listener waiting, while one is armed

// The answer for the language chosen now, or '' if it was for another one
const onDeviceNow = () => onDeviceLang === browserLang() ? onDeviceStatus : '';
// And the same for what the disk said, which is per language as well
const onDeviceDiskNow = () => onDeviceDisk && onDeviceDisk.lang === browserLang() ? onDeviceDisk : null;
// Held off on purpose, and known to be (an answer still on its way is not a hold yet)
const onDeviceHeld = () => asrActive() && onDeviceLocal
  && (onDeviceRefused || (onDeviceNow() !== '' && onDeviceNow() !== 'available'));

/* Ask Chrome whether the chosen language can be recognized here. One call at
   a time per language: the 5 second poll, a start, and the download's own
   polling all end up here and would otherwise pile up. An answer that comes
   back for a language no longer chosen is dropped. */
function askOnDevice() {
  const lang = browserLang();
  if (onDeviceAsk && onDeviceAsk.lang === lang) return onDeviceAsk.promise;
  const promise = (async () => {
    let status;
    try {
      status = await SR.available({langs: [lang], processLocally: true});
    } catch {
      status = 'unavailable';
    }
    if (onDeviceAsk && onDeviceAsk.promise === promise) onDeviceAsk = null;
    if (browserLang() !== lang) return '';
    const was = onDeviceNow();
    onDeviceStatus = status;
    onDeviceLang = lang;
    // Only downloadable is ambiguous, so only it is worth a look at the disk
    if (status === 'downloadable') checkOnDeviceDisk(lang);
    paintOnDevice();
    // No progress events come out of a download, so it is watched by asking again
    if (status === 'downloading' && lang === onDeviceInstallLang) onDeviceSawDownloading = true;
    if (status === 'downloading' || onDeviceInstalling) keepPollingOnDevice();
    // Came in just now (the download finished, here or anywhere else in this
    // Chrome). Start what was being held for it. A start already under way is
    // the one that asked, and carries on by itself.
    if (status === 'available' && was !== 'available') {
      paint();
      if (onDeviceLocal && !onDeviceRefused && recWanted && !rec && !recStarting) startRecognition();
    }
    return status;
  })();
  onDeviceAsk = {lang, promise};
  return promise;
}

/* Ask our own server to look at the disk. Chrome tells every site
   downloadable until that site has called install() itself, model on disk or
   not, so the page alone cannot tell a real download from a switch on that
   takes seconds. The server runs on this machine and can simply look
   (GET /api/ondevice), read only, without touching Chrome.

   Asked once per language: a model does not come and go while the page is
   open, and the one way it does (the download we started) ends in available,
   which never reads the answer again. An answer for a language no longer
   chosen is dropped, the same as available()'s. */
function checkOnDeviceDisk(lang) {
  if (onDeviceDiskAsk === lang || (onDeviceDisk && onDeviceDisk.lang === lang)) return;
  onDeviceDiskAsk = lang;
  fetch('/api/ondevice?lang=' + encodeURIComponent(lang))
    .then(r => r.json())
    .then(d => {
      if (onDeviceDiskAsk !== lang) return;
      onDeviceDiskAsk = '';
      onDeviceDisk = d && d.lang === lang ? d : null;
      paintOnDevice();
    })
    .catch(() => { if (onDeviceDiskAsk === lang) onDeviceDiskAsk = ''; });
}

function keepPollingOnDevice() {
  if (onDevicePoll) return;
  onDevicePoll = setTimeout(() => {
    onDevicePoll = null;
    if (onDeviceLocal && asrChosen) askOnDevice();
  }, 2000);
}

// The status line and the download button, under the spoken language
function paintOnDevice() {
  const show = asrChosen && onDeviceLocal;
  el.onDeviceField.hidden = !show;
  if (!show) { disarmOnDeviceInstall(); return; }
  let status = onDeviceNow();
  // Between the press and Chrome saying downloading, it still says downloadable.
  // Only for the language the press was for: switched to another one while it
  // downloads, that one has not been asked for, and reading it as downloading
  // would grey its button out until the first one is done, minutes later.
  const installing = onDeviceInstalling && onDeviceInstallLang === browserLang();
  if (installing && status !== 'available' && status !== 'unavailable') status = 'downloading';
  const disk = onDeviceDiskNow();
  el.onDeviceStatus.textContent = onDeviceProblem
    ? t(onDeviceProblem, {back: t('unfloatBtn')})
    : t(onDeviceStatusKey(status, onDeviceRefused, disk),
        {plain: t('engineBrowser'), size: onDeviceSizeText(disk) || t('onDeviceSizeGuess')});
  el.onDeviceRow.hidden = onDeviceRefused || status !== 'downloadable';
  // The button says what pressing it really does. Nothing is fetched when
  // Chrome already holds the model, and calling that a download is the very
  // thing this whole look at the disk is here to stop saying. The drawing
  // says it too: a download arrow over something that downloads nothing is
  // the same untruth in a picture.
  const here = onDeviceHasModel(disk);
  setLabel(el.onDeviceDownload, t(here ? 'onDeviceEnableBtn' : 'onDeviceDownload'));
  setIcon(el.onDeviceDownload, here ? 'bolt' : 'download');
  el.onDeviceDownload.disabled = installing;
  // Every path that changes any of this comes through here (the engine
  // dropdown, the language dropdown, another tab's switch, each answer from
  // available(), the answer from the disk), so the arming is worked out here
  // rather than being remembered to at each of them.
  if (onDeviceMayAutoInstall(onDeviceLocal, asrChosen, status, onDeviceRefused, installing, disk)) {
    armOnDeviceInstall();
  } else {
    disarmOnDeviceInstall();
  }
}

// Say on the main screen too why nothing is being listened to. Settings
// carries the detail, the screen you are looking at only has to point there.
function holdOnDevice() {
  paintOnDevice();
  say(t('onDeviceHold'), 10);
  paint();
}

let rec = null;              // the current SpeechRecognition
let recRunning = false;      // start() has been called and end has not come yet
let recWanted = false;       // whether the setting says to use it
let lastVoiceAt = 0;         // when a voice was last coming in
let recStartedAt = 0;        // when the current session was opened
let recFails = 0;            // failures in a row (used to decide when to give up)
let recStarting = false;
let recGeneration = 0;
// When the state the stall watch measures (recWatchdogTick) last began. Set
// where a start really begins rather than only from the watch's own tick, so
// the count is the age of the open session itself and not the gap between two
// ticks. The tick is a plain setInterval and a hidden tab is where this page
// spends most of its life (it is meant to be worked beside), so those gaps
// stretch: read off a tick alone, an ordinary start sampled once and then not
// again for a minute reads as a minute-old stall and gets folded up mid-word.
let recAliveAt = 0;
// Set only while recognition is being started on its own after a reload
// (#118), with nothing touched yet. A refusal then may be Chrome wanting a
// touch first rather than the person saying no, so it falls back to "touch to
// start" instead of switching browser recognition off.
let autoResumed = false;

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

// A browser set to Hong Kong or Macau Chinese, or to Cantonese by name (yue)
function speaksCantonese(tag) {
  const [head, ...rest] = (tag || '').toLowerCase().replace(/_/g, '-').split('-');
  if (head === 'yue') return true;
  return head === 'zh' && !rest.includes('hans') && (rest.includes('hk') || rest.includes('mo'));
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
  // Hong Kong and Macau read the Traditional screen but mostly speak
  // Cantonese, which Chrome hears as zh-HK. Taiwan's Mandarin would turn it
  // into the wrong words.
  if (speaksCantonese(want)) return 'zh-HK';
  // zh-Hant would otherwise land on the first zh in the list, which is the
  // mainland one, and come back written in Simplified characters.
  if (isTraditionalZh(want)) return 'zh-TW';
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

/* Web Speech API does not just add words as it goes, it revises its own
   guess mid-clause, so interim text can shrink back and regrow differently
   several times a second, most visibly right when the person restates
   something. Painting every one of those revisions on screen makes the
   revising itself the thing that is seen, rather than what it settles into.
   Trailing-edge throttled: painted at once if enough time has passed since
   the last real paint, otherwise the newest text waits out the rest of the
   window and is the one that lands, so nothing shown is ever stale by more
   than the window itself. */
const INTERIM_PAINT_THROTTLE_MS = 200;
let lastInterimPaintAt = 0;
let interimThrottleTimer = null;
let latestInterimForPaint = '';

// Joining clauses that were only ever split because Chrome's own
// endpointing decided to, not because the person paused for one, still
// needs something between them, just not a mark nobody said. A language
// that does not write spaces between its own words was never going to want
// one glued between two clauses either, so those get none. Everything else
// keeps the plain space, the same one already sitting inside each clause
// between its own words.
const NO_SPACE_LANGS = new Set(['ja', 'zh', 'th']);
const speakingNoSpaceLang = () => NO_SPACE_LANGS.has(browserLang().split('-')[0].toLowerCase());
const clauseJoin = () => speakingNoSpaceLang() ? '' : ' ';

/* Chrome's own recognizer writes a plain space between words even in
   Japanese, where nothing was said in that gap at all, not for any of the
   reasons clauseJoin exists for. A Latin word it hears inside Japanese comes
   back the same way and worse, spelled out a letter at a time:
   「Ｉ Ｐ ａ ｄ ｉ Ｐ ｈ ｏ ｎ ｅ」 for "iPad iPhone", every single letter with a
   space after it. On this device that is full-width, and from Google's own
   servers the same sentence comes back half-width (I P a d i P h o n e), so
   the width says nothing about it either way. Nobody said any of those gaps.

   What does tell them apart is how many letters stand together. One letter on
   each side is the recognizer spelling a word out and the space goes. Two or
   more on either side is a word it wrote as a word (「ＰＲ ｔｅｓｔ」, "Claude
   Code", 「Ｍａｃ ｍｉｎｉ」) and the space stays, because that one really does
   separate two words. With no Latin on both sides it is the ordinary invented
   space between two characters outside plain ASCII, which goes as it always
   did, while a space against an English word dropped into the sentence stays.

   Run on the raw transcript, before the fold, the way it was before #127.
   Folding first made that impossible for the spelled-out case: the letters
   are ASCII by then, the rule that only looked at non-ASCII neighbours could
   not touch them, and 「ＩＰｈｏｎｅ」 reached the screen as "I P h o n e", which
   is what full-width looks like at a glance. Reading it first without
   counting the letters is the other half of the same mistake, and that is
   what sent 「ＰＲ ｔｅｓｔ」 out as PRtest. */
const INVENTED_SPACE_RE = /[ \t]+/g;
const NON_ASCII_RE = /[^\x00-\x7F\s]/;
const LETTER_RE = /[A-Za-z0-9Ａ-Ｚａ-ｚ０-９]/;
// How many Latin letters stand in a row from i, walking in one direction
const letterRunFrom = (s, i, step) => {
  let n = 0;
  while (i >= 0 && i < s.length && LETTER_RE.test(s[i])) { n++; i += step; }
  return n;
};
const stripInventedSpaces = text =>
  speakingNoSpaceLang()
    ? text.replace(INVENTED_SPACE_RE, (gap, at, whole) => {
        const before = whole[at - 1], after = whole[at + gap.length];
        if (before === undefined || after === undefined) return gap;
        const left = letterRunFrom(whole, at - 1, -1);
        const right = letterRunFrom(whole, at + gap.length, 1);
        if (left === 1 && right === 1) return '';             // spelled out
        if (left && right) return gap;                        // two real words
        return NON_ASCII_RE.test(before) && NON_ASCII_RE.test(after) ? '' : gap;
      })
    : text;

/* The one string both writers to el.stream agree on: whatever is queued,
   with whatever was last recognized after it. Two different callers used to
   build two different strings, browserGateTick's own paintPendingBrowserSends
   wrote the queued text alone, unconditionally, every 100ms, while this path
   wrote queued-plus-interim on its own, slower, throttled schedule. Between
   the two, the interim half got painted on and wiped off several times a
   second purely from the two writers disagreeing, not from the recognizer
   revising anything, "文字がついたり消えたり" even while nothing was
   actually changing underneath. Routing both through the same function,
   reading the same two pieces of live state, is what makes that impossible
   again: there is only one string, so there is nothing left for them to
   disagree about. */
function browserStreamText() {
  const join = clauseJoin();
  const queued = pendingBrowserSends.map(p => p.text).join(join);
  const interim = latestInterimForPaint;
  return queued ? (interim ? `${queued}${join}${withDict(interim)}` : queued) : withDict(interim);
}

function paintInterimNow(interim) {
  lastInterimPaintAt = performance.now();
  latestInterimForPaint = interim;
  const s = browserStreamText();
  paintStream(s);
  el.tray.classList.toggle('idle', !s);
}

function paintInterimThrottled(interim) {
  latestInterimForPaint = interim;
  const elapsed = performance.now() - lastInterimPaintAt;
  if (elapsed >= INTERIM_PAINT_THROTTLE_MS) {
    if (interimThrottleTimer) { clearTimeout(interimThrottleTimer); interimThrottleTimer = null; }
    paintInterimNow(interim);
    return;
  }
  if (interimThrottleTimer) return;
  interimThrottleTimer = setTimeout(() => {
    interimThrottleTimer = null;
    paintInterimNow(latestInterimForPaint);
  }, INTERIM_PAINT_THROTTLE_MS - elapsed);
}

function newRecognition(generation) {
  const r = new SR();
  r.lang = browserLang();
  // Only ever reached with a model Chrome says is here (the hold in
  // startRecognition), so this never asks for one that would have to be
  // fetched. quality is left at its default on purpose: 'command' is the one
  // Chrome 153 has models for, and asking for any other makes it unavailable.
  if (onDeviceLocal) r.processLocally = true;
  r.continuous = true;
  r.interimResults = true;
  r.maxAlternatives = 1;
  // Off by default (Chrome 151+). With it off, nothing about a spoken pause
  // or a falling tone at the end of a clause makes it into the transcript,
  // which reads as flatter than it sounded, especially once several clauses
  // are joined into one line. Checked rather than just set, for whatever
  // browser or older Chrome build has never heard of the property.
  if ('unspokenPunctuation' in r) r.unspokenPunctuation = true;

  // Check every time whether this is still us, so a signal from an old
  // instance does not break the new state. Without it, an old end can arrive
  // right after a swap and start it up twice over.
  const mine = () => rec === r && generation === recGeneration;

  r.onstart = () => {
    if (!mine()) return;
    recStarting = false;
    recRunning = true; recStartedAt = performance.now(); recFails = 0;
    asrDeniedFlag = false;
    autoResumed = false;
  };

  r.onresult = ev => {
    if (!mine()) return;
    /* The mic is off and this session is still open, which only happens on the
       on-device entry (listensWhileMuted). Everything heard here is dropped on
       the spot: no interim painted, no clause queued, nothing sent, nothing
       written and nothing left in the draft box. The settled text is looked at
       once, for the one word that brings the mic back, and then it is gone.

       Read off the session rather than off the setting, so the promise holds
       whatever else moved: a session built for the plain entry cannot be the
       one still listening here, and one that somehow is gets aborted instead
       of heard, rather than quietly sending the audio to Google while the
       screen says muted. */
    if (route === 'off') {
      if (r.processLocally !== true) { try { r.abort(); } catch {} return; }
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const res = ev.results[i];
        if (res.isFinal) heardWhileMuted(toHalfWidth(stripInventedSpaces(res[0].transcript)));
      }
      return;
    }
    let interim = '';
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const res = ev.results[i];
      // The spaces first, then the fold. stripInventedSpaces has to read the
      // transcript while the Latin in it is still full-width: that is what
      // says the letters are the recognizer's own writing and not something
      // anyone spoke, and it is what tells 「Ｉ Ｐ ａ ｄ」 spelled a letter at a
      // time from the two words of 「ＰＲ ｔｅｓｔ」. Folded first, both look like
      // ASCII words with a space between them and neither can be helped.
      const transcript = toHalfWidth(stripInventedSpaces(res[0].transcript));
      if (res.isFinal) queueOrSendFinal(transcript);
      else interim += transcript;
    }
    // A clause waiting out its quiet stretch keeps its own text on screen
    // (paintPendingBrowserSends), with whatever is being recognized now
    // appended after it. Before the gate actually held anything, a clause
    // barely spent any real time queued, so there was next to never
    // anything here to lose by leaving interim out. Once it holds for the
    // real few seconds, someone still mid-thought watches their own words
    // stop appearing the moment the first clause of it queues. Throttled
    // (paintInterimThrottled) since this fires many times a second and each
    // one can be a revision of the last, not just more added to the end.
    paintInterimThrottled(interim);
    streamTail();
    paintTinyButtons();
    if (interim.trim()) lastVoiceAt = performance.now();
    // Words still coming in are talking, whatever the level meter says.
    // The quiet wait (browserGateTick) is timed off the mic level alone, and
    // someone speaking softly, under the trigger mark, read as silent: the
    // clauses already finalized went out while the rest of the sentence was
    // still growing on screen, and it arrived cut in two. A changed interim
    // restarts the wait the same way a loud frame does.
    if (interim.trim() && interim !== lastInterimHeard) {
      lastLoudAt = lastInterimChangeAt = performance.now();
      if (carryDraft) voiceSinceCarry = true;
    }
    lastInterimHeard = interim;
  };

  r.onerror = ev => {
    if (!mine()) return;
    recStarting = false;
    // Kept on this device and Chrome would not do it there. Nothing is
    // counted as a failure, since trying again would only bring the same
    // answer with growing waits in between and end in "check your
    // connection". It is held instead (startRecognition reads
    // onDeviceRefused), and available() is asked again so the settings show
    // what Chrome now says. Read as a refused microphone below, it would
    // switch browser recognition off altogether.
    if (r.processLocally === true && onDeviceRefusal(ev.error, autoResumed)) {
      onDeviceRefused = true;
      onDeviceStatus = '';
      askOnDevice();
      holdOnDevice();
      return;
    }
    // A refused microphone needs a person to act. Roll the setting back and say so.
    if (ev.error === 'not-allowed' || ev.error === 'service-not-allowed') {
      if (autoResumed) {
        autoResumed = false;
        armPending = true;
        route = 'off';
        applyRouteSideEffects('off');
        paint();
        return;
      }
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
    // What was being recognized ended with the session. Keep the clauses
    // still waiting to go out on screen, drop the stale interim.
    latestInterimForPaint = lastInterimHeard = '';
    el.stream.textContent = browserStreamText();
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

/* An utterance settled while the mic is off. Nothing is kept: it is asked the
   one question the daemon asks in the same state (is this 「ミュート解除」), and
   whatever the answer, the text goes no further than this function.

   Coming back sounds and reads exactly as it does under a local engine: the
   same rising chime, the same line, and the word that did it lit up in the
   transcript box, so operating by ear tells you the same thing either way.
   The switch itself goes through setRoute, which posts /api/mute, so the
   daemon and every other screen come back with it. */
function heardWhileMuted(text) {
  if (route !== 'off' || inFlight) return;
  const said = unmuteCommand(text, {multi: el.multiOn.checked,
                                    names: machineNames(), fixup: withDict});
  if (!said) return;
  setRoute(lastMode);
  chime('up');
  say(t('voiceUnmuted'));
  flashCommand(text.trim().slice(0, 60), 'live');
}

async function startRecognition() {
  // A start that gives up before recognition opens also ends the unattended
  // one after a reload (autoResumed). Left raised, a refusal much later, to
  // someone who has since touched the page, would be taken for Chrome wanting
  // a touch and would not say it was refused. A call that bounces off one
  // already under way leaves it alone.
  if (!canBrowserASR || !recWanted || rec || recRunning || recStarting) {
    if (!canBrowserASR || !recWanted) autoResumed = false;
    return;
  }
  const generation = recGeneration;
  recStarting = true;
  // The one way into the state the stall watch counts (rec is assigned
  // nowhere else), so this is the moment it has been open since.
  recAliveAt = performance.now();
  try {
    // On the local entry nothing starts until Chrome says the model is here.
    // Asked before the heartbeat, so a start held off here never claims
    // browser recognition for a tab that is not listening. Nothing is counted
    // as a failure either: no session opens, so no end comes back to retry,
    // and it is the answer turning to available (askOnDevice) that starts it.
    if (onDeviceLocal) {
      if (onDeviceNow() !== 'available') await askOnDevice();
      if (generation !== recGeneration || !recWanted) { autoResumed = false; return; }
      if (!onDeviceMayStart(onDeviceLocal, onDeviceNow(), onDeviceRefused)) {
        autoResumed = false;
        holdOnDevice();
        return;
      }
    }
    // route === 'off' holds a start back, except where the mic is meant to stay
    // open through the mute (listensWhileMuted). Chrome ends a session every 7
    // to 10 seconds, so without that the first end would be the last one.
    if (!await beat('listening') || generation !== recGeneration || !recWanted
        || (route === 'off' && !listensWhileMuted()) || rec) {
      autoResumed = false;
      return;
    }
    const r = newRecognition(generation);
    if (generation !== recGeneration || rec) { autoResumed = false; return; }
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
  latestInterimForPaint = lastInterimHeard = '';
  el.stream.textContent = browserStreamText();
}

/* Build the session again, with the settings as they stand now.

   Moving between the two browser entries changes nothing the server can see
   (both of them are 'browser' to it), and nothing about a session already
   open either: processLocally is fixed when the SpeechRecognition object is
   built, so whichever of the two it was built for goes on being used until
   the object itself is replaced. Asking Chrome to stop() and waiting for the
   end it throws back is not enough on its own, because then the swap rests on
   Chrome answering: a stop() that goes unanswered, or merely takes its time,
   leaves the old session recognizing under the old setting while the
   dropdown, the settings and the status line all say the other one. Coming
   off the local entry that reads as a switch back to Chrome's cloud that
   never happened, and going onto it, as audio still going to Google after the
   entry that keeps it here was picked. Neither may wait on a reply.

   So the old one is dropped through stopRecognition, which aborts it there
   and then and steps the generation, so nothing arriving late from it is
   heard (mine() in newRecognition), and the next one is opened immediately
   after. There is never a moment with both of them open, and the gap with
   neither is the one lease heartbeat startRecognition already takes. The half
   clause still being recognized goes with the session, which is right: it was
   recognized under the setting that has just been left behind. */
function restartRecognition() {
  // The hold line is pinned on the main screen for 10 seconds (holdOnDevice).
  // The entry it was about is gone, so the pin goes with it and the next
  // paint writes what is true now, rather than leaving the screen saying
  // recognition is held here while a cloud session runs.
  if (el.hint.textContent === t('onDeviceHold')) hintHoldUntil = 0;
  stopRecognition(true);
  if (recWanted) startRecognition();
  paint();
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

   Tried a plain per-clause timer first (no room-level reading at all): each
   clause just waits out the setting from its own isFinal, unaffected by
   anything said afterward. Simpler, and it is what the setting's own
   description promises, but trying it live turned up the cost, someone still
   mid-thought watches an already-finalized clause go out from under them
   while they are still talking, because talking is exactly what the timer
   never looked at. So: a shared clock instead. What actually needs watching
   is "how long has the room been quiet", and every clause waiting to go out
   watches the same answer, so lastLoudAt is the only state, not a timer per
   entry. Ticked by setInterval, not the paint loop. A minimized or otherwise
   occluded tab throttles requestAnimationFrame; a send must not quietly stop
   working right when the person stepped away expecting it to go out on its
   own. */
const BROWSER_SEND_GATE_MS = 100;
let lastLoudAt = 0;
let lastInterimHeard = '';      // the interim last seen, so an unchanged repeat is not counted as talking
let lastInterimChangeAt = 0;   // when it last changed (words still coming in)
let pendingBrowserSends = [];   // [{text, queuedAt}], oldest first

/* The two clocks the hold below compares. Both are kept apart from lastLoudAt
   on purpose: lastLoudAt answers "how long has it been quiet" and is nudged by
   things that are not sound at all (a changed interim, a session coming back
   up), which is right for a wait but useless for asking what the microphone
   actually heard. lastMicLoudAt is the microphone alone, nothing else writes
   it. lastFinalAt is the last time recognition handed anything back. */
let lastMicLoudAt = 0;
let lastFinalAt = 0;

/* Whether recognition still owes us words.

   Kept on this device (processLocally), Chrome recognizes behind the speech,
   seconds behind it on a long sentence, and it goes quiet while it catches up.
   The wait above reads that quiet as the end of the thought: the clauses
   already handed over go out, and the rest of the same sentence arrives after
   they have gone and lands as a second prompt. One thought, two prompts, which
   is what this is for.

   The question it answers is not "has anything been said lately" (that is the
   wait) but "is there sound the recognizer has not accounted for yet". Loud
   audio after the last thing recognition said is exactly that: it was heard,
   and nothing has come back for it. Interims cannot stand in for it, because
   going quiet is what the stall looks like from here.

   Sound with nothing said about it is not the only sign, though, and on its
   own it misses the shape this is actually for. A clause handed back while
   the room is already quiet is itself the proof: the audio it covers was
   over before it arrived, so the recognizer is running that far behind, and
   a recognizer that far behind rarely has just the one clause left. Reading
   only the first sign, the catch-up traffic disarmed the hold that was
   waiting for it, so a stall that came back as two events two tenths of a
   second apart went out as two prompts anyway.

   How far behind it is, is the same measure as how much longer to wait: a
   clause that landed a second into the quiet says the recognizer is a second
   behind, so it gets a second past that clause before anything moves. Prompt
   recognition measures near zero there and so waits no longer than it ever
   did, which is what keeps this from costing every on-device sentence a
   second send wait.

   Bounded by twice the wait either way, and this is not the outer limit on
   sending that was turned down before. That one cut people off while they
   were still talking. This one only says how long to keep waiting for a
   recognizer that has gone quiet after the talking stopped, and it is here so
   that a keyboard clack or a door after the last word, loud with no words
   behind it, does not hold the prompt back until the cap. A recognizer
   further behind than that still splits, which is the honest limit of reading
   it from the outside. (The bound is measured from the last sound, and a
   session renewed mid-hold moves the wait itself, so in the worst case the
   real delay is that bound plus one more wait after the session settles.)

   The ordinary browser path is left exactly as it was. It answers within a
   fraction of a second, so it is never behind in the first place. */
const RECOG_OWED_FACTOR = 2;
function recognizerOwesWords(now, waitMs) {
  if (!onDeviceLocal) return false;
  // Never heard anything at all. The analyser can fail to open (startViz, and
  // on Windows it does), and then the level reads 0 forever: with no sound to
  // reason from there is nothing to say the recognizer is behind, so this
  // stays out of the way and the wait alone decides, exactly as before.
  if (!lastMicLoudAt) return false;
  if (now - lastMicLoudAt >= waitMs * RECOG_OWED_FACTOR) return false;
  if (lastMicLoudAt > lastFinalAt) return true;
  const behind = lastFinalAt - lastMicLoudAt;
  return now - lastFinalAt < behind;
}

/* How long to wait for quiet before a finished clause moves on. In draft mode
   it only lands in the box on screen, nothing goes to Claude yet, so a long
   "pause to send" (5 or 10 seconds, set for thinking out loud) would just
   leave the box lagging behind. There the wait is capped at DRAFT_WAIT_MS. */
const DRAFT_WAIT_MS = 2000;
function sendWaitMs() {
  const wait = Math.max(0, (Number(tuning.silence_duration) || 0) * 1000);
  // Carrying a draft along is really sending, so it waits the full time.
  return route === 'hold' && !carryDraft ? Math.min(wait, DRAFT_WAIT_MS) : wait;
}

function browserGateTick() {
  browserRmsNow = computeBrowserRms();
  if (engine === 'off' || asrActive()) paintGauge();
  // Tracked on every tick, queue empty or not, so a stretch of talking before
  // anything has finalized yet still counts. Missing this the first time
  // (only updating it once something was already queued) is what made the
  // very first version of this send everything the instant it queued.
  const now = performance.now();
  if (browserRmsNow >= tuning.silence_threshold) lastMicLoudAt = lastLoudAt = now;
  // Chrome cuts its session every 7 to 10 seconds and the next one takes a
  // moment to come up. Nothing can be heard in that gap, so it must not count
  // as the quiet that sends what was said so far.
  if (recWanted && (!recRunning || recStarting)) lastLoudAt = now;
  if (!pendingBrowserSends.length) return;
  const quietFor = now - lastLoudAt;
  const waitMs = sendWaitMs();
  // A cap against a rising noise floor. Some machines' getUserMedia runs
  // automatic gain control that climbs through a real pause and never dips
  // back under a fixed mark on its own, and a wait with no ceiling then
  // never ends, the exact "neither a command nor a prompt, gone nowhere"
  // shape #76 exists to rule out, just reached from the sending side
  // instead of the recognizing side this time. A genuine noise floor is the
  // one case this is for, and that takes much longer than ordinary
  // conversational pauses (which is exactly the case this used to trip on
  // instead: someone talking continuously in short clauses, each one only
  // ever a couple of seconds from its neighbor, never once from the room
  // itself) to show up as a real problem, so this only has to be short
  // next to "stuck forever," not next to the wait itself.
  const cap = Math.max(waitMs * 10, waitMs + 30000);
  // Not while words are still coming in, though. The cap is for a noise floor
  // the level never drops below, not for someone who simply talks for longer
  // than the cap: cutting them off there split one long thought in two.
  const stillTalking = now - lastInterimChangeAt < waitMs;
  // No outer limit while words keep coming in: people do talk for minutes on
  // end, and cutting them off at any fixed length split the thought. A noisy
  // room keeping recognition busy is not a place anyone dictates from, and
  // the send button is always there.
  const capTripped = !stillTalking &&
    pendingBrowserSends.some(item => now - item.queuedAt >= cap);
  // Tripping the cap, like clearing the wait, releases everything currently
  // pending together, not only the one item old enough to trip it.
  // Releasing that one item alone was fragmentation by another name: three
  // clauses queued a couple of seconds apart during one continuous stretch
  // of talking each aged past the cap on their own staggered schedule, so
  // each went out as its own POST, undoing the joining below entirely on
  // exactly the path continuous speech takes most often.
  // Quiet for long enough, and nothing still on its way in. The cap goes
  // around it, so a hold here can never be the thing that loses a prompt.
  const ready = ((quietFor >= waitMs && !recognizerOwesWords(now, waitMs)) || capTripped)
    ? pendingBrowserSends : [];
  pendingBrowserSends = ready.length ? [] : pendingBrowserSends;
  // Joined into one utterance, not one POST per clause. Chrome's own
  // endpointing is what split a single continuous thought into several
  // isFinal chunks to begin with (nothing this page controls), and clauses
  // that clear the same wait together at the same moment are exactly the
  // ones that were never really separate to the person saying them. Joining
  // is also what lets a tail command land on the right side of the split:
  // 「内容、キャンセル」reunited into one string is what the server's own
  // trailing-キャンセル check (viewer.py, take_tail) was always meant to see.
  if (ready.length) sendUtterance(ready.map(i => i.text).join(clauseJoin()));
  paintPendingBrowserSends();
}
setInterval(browserGateTick, BROWSER_SEND_GATE_MS);

function flushPendingBrowserSends() {
  const items = pendingBrowserSends;
  pendingBrowserSends = [];
  if (items.length) sendUtterance(items.map(i => i.text).join(clauseJoin()));
  paintPendingBrowserSends();
}

// Called right after pendingBrowserSends itself changes (queued or
// flushed), so the queued card(s) show up without waiting on the next
// recognition event. Built through browserStreamText, the same function
// paintInterimNow uses, so this and the next recognition event agree on
// what belongs on screen rather than each painting their own half of it.
function paintPendingBrowserSends() {
  const s = browserStreamText();
  if (!s) return;
  if (el.stream.textContent !== s) el.stream.textContent = s;   // see paintStream
  el.tray.classList.remove('idle');
  streamTail();
}

/* Where a finalized clause actually goes, either straight to sendUtterance or
   parked in pendingBrowserSends to wait out a quiet stretch first. Called
   from onresult in place of calling sendUtterance directly. */
function queueOrSendFinal(text) {
  // Ahead of every way out below. A clause that trims away to nothing, one
  // dropped as stale, and a closing mute are all recognition having said
  // something about what it heard, which is the whole of what lastFinalAt
  // tracks (see recognizerOwesWords).
  lastFinalAt = performance.now();
  text = (text || '').trim();
  if (!text) return;
  // The one straggler discardCurrentNow warns about, stale content the newly
  // restarted session can still carry right after an abort. Caught here, at
  // the point of queuing, since sendUtterance's own copy of this same check
  // never gets a turn to run until whatever the queue eventually flushes.
  if (dropNextLocal) { dropNextLocal = false; return; }
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

/* Why an utterance the server took in went nowhere, in words for the person
   who said it. The reasons a command or a cancel leaves behind are not here:
   those already put their own line up (voice_cmd.json), and one the draft box
   is holding is on screen in the box itself. These four say nothing anywhere
   else, and speech that goes nowhere while the screen carries on as though it
   had arrived is the one thing this must never look like. */
const DROP_REASONS = {too_short: 'dropTooShort', noise: 'dropNoise',
                      muted: 'dropMuted', empty: 'dropEmpty'};

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
      } else {
        // Taken in and let go again, for a reason the server knows and the
        // person cannot see (under the floor on length, a word on the ignore
        // list, a cut microphone, nothing left after the dictionary). It
        // comes back as an ordinary 200, so without this the words simply
        // vanish off the screen and nothing is ever said about them.
        let data = {};
        try { data = await res.json(); } catch {}
        // Held on screen (say), not written straight onto the line: paint()
        // puts the ordinary "listening" wording back every 3 seconds, and the
        // whole point of these four is to reach someone who is talking rather
        // than watching. Written bare, the reason their words went nowhere
        // was gone again before they looked up.
        const why = DROP_REASONS[data.dropped];
        if (why) say(t(why));
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

/* A session that was opened and never came up.

   startRecognition turns away any call made while rec is set or a start is
   still under way, and both are cleared only by something arriving back from
   the recognizer. A session that was start()ed and never reached onstart,
   with no end and no error either, therefore leaves them set for good: the
   page wants to listen, nothing is listening, everything said goes nowhere
   and nothing says so, and only a reload brings it back. Nothing is being
   recognized in that state, so there is nothing to lose by folding the dead
   session up and beginning again.

   Told apart from the ordinary gap between two sessions (Chrome cuts its own
   every 7 to 10 seconds and the next takes a moment) by how long it has run. */
const REC_STALL_MS = 30000;

/* How long a session has been open with nothing running behind it. Every
   other state counts as alive, and none of them are for this to start up
   again behind the person: nothing opened at all (a page nobody has touched
   yet, where the microphone rule holds the start until it is, a local model
   still being waited on, a lease that could not be read), recognition
   genuinely running, the lease held by another tab, a refused microphone. */
function recStalledFor(now, s) {
  if (!s.held || !s.recWanted || s.recRunning || s.conflict || s.denied) return 0;
  return Math.max(0, now - s.aliveAt);
}

function recWatchdogTick(now = performance.now()) {
  const stalled = recStalledFor(now, {held: !!rec || recStarting,
                                      recWanted, recRunning, conflict: !!asrConflict,
                                      denied: asrDeniedFlag, aliveAt: recAliveAt});
  if (stalled < REC_STALL_MS) {
    if (!stalled) recAliveAt = now;
    return false;
  }
  recAliveAt = now;
  // Held (say, not a bare write to the line), since whatever was spoken into
  // the dead session is gone and only the person can say it again. paint()
  // rewrites that line every 3 seconds, and someone operating by voice is by
  // definition not watching the screen, so a line written straight onto it is
  // one nobody ever sees.
  say(t('asrRestarted'), 10);
  stopRecognition(true);
  startRecognition();
  return true;
}
setInterval(() => recWatchdogTick(), 5000);

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

/* scrollHeight alone only ever reports the larger of "what is set" and "what
   the content needs" — with four short chips inside a box already dragged
   tall, that is just the box's own height handed back, not the two rows the
   chips actually take. Asking with the height briefly relaxed to auto (its
   intrinsic size, wrapped rows and all) is what gets the real number, and
   back on the very next line, before the layout this forces ever reaches
   paint. The max-height set by an earlier call has to come off for that same
   moment too, or it clips the auto size right back down to whatever the last
   measurement was, and the box never notices the list growing past it. */
function chipsNaturalHeight() {
  const prevH = el.routeChips.style.height, prevMax = el.routeChips.style.maxHeight;
  el.routeChips.style.height = 'auto';
  el.routeChips.style.maxHeight = 'none';
  const h = el.routeChips.scrollHeight;
  el.routeChips.style.height = prevH;
  el.routeChips.style.maxHeight = prevMax;
  return h;
}

/* Rows are measured off where the chips actually land (offsetTop), not
   counted or guessed at, so it holds regardless of how many fit across the
   current width. */
function chipsRowCount() {
  const tops = new Set();
  for (const b of el.routeChips.children) tops.add(Math.round(b.offsetTop));
  return tops.size;
}

/* How far resize:vertical (below) lets the chip box be dragged. Fixed in the
   stylesheet it would either cap the box below what a long session list
   needs or, sized for that, leave a short list draggable into a stretch of
   empty panel below its own last row. Call after every re-paint and
   whenever the window's own width might have moved where the chips wrap.
   Below four rows the whole list already sits fully in view (that is the
   height the box opens at), so there is nothing yet for a grab handle to
   do — resize itself comes off, not just its corner mark, so a stray drag
   cannot open a gap under a still-short list either. */
function updateChipsSizing() {
  el.routeChips.style.resize = chipsRowCount() >= 4 ? 'vertical' : 'none';
  el.routeChips.style.maxHeight = (chipsNaturalHeight() + 1) + 'px';
}
/* window's own 'resize' event first, same as most everything else on this
   page answers to. Unlike those, this one visibly lagged behind a live drag
   of the window's own edge, catching up only once the drag let go. fitCanvas
   above already settled this same question the other way: it repaints off a
   ResizeObserver instead specifically because that one **does** fire every
   frame while the window is in your hand, not just at the end. Watching
   .routes rather than the element this function itself writes to
   (routeChips) is what keeps that from re-triggering itself: the former's
   width moves only with the window, never with our own height/max-height
   writes below. */
new ResizeObserver(updateChipsSizing).observe(el.routes);

/* Double-click the resize corner itself to snap straight to that same
   content height, instead of dragging by eye. 16px is Chrome's own resizer
   square; a real click a few px short of dead-on the corner still lands
   inside it, so this is generous rather than exact. A chip sitting in that
   same corner keeps its own dblclick (rename) — checked first, so the two
   never both fire off one click. */
function fitChipsHeight(ev) {
  if (ev.target.closest('.route-chip')) return;
  const r = el.routeChips.getBoundingClientRect();
  if (r.right - ev.clientX > 16 || r.bottom - ev.clientY > 16) return;
  el.routeChips.style.height = chipsNaturalHeight() + 'px';
}
el.routeChips.addEventListener('dblclick', fitChipsHeight);

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
    // Between two watches (a Monitor deadline): it keeps its number and its
    // place as destination, shown faded until its next watch picks it up.
    // Away is a session between two watches, faded and coming back on its
    // own. Gone is one whose listen ended and is not coming back by itself:
    // it keeps its place and its number so the row does not shuffle under the
    // person, and says outright that it cannot be used (#110).
    b.className = 'route-chip' + (on ? ' on' : '') + (l.away ? ' away' : '')
                + (l.gone ? ' gone' : '');
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
    b.title = [`${l.no}. ${l.label}`,
               l.gone ? t('listenerGone') : l.away ? t('listenerAway') : '',
               l.cwd || '', t('renameHint')].filter(Boolean).join('\n');
    if (l.gone) b.setAttribute('aria-disabled', 'true');

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
  updateChipsSizing();
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
  openPickMenu(el.routePick, listenerItems(), routeTo || effectiveTo, setRoute2, undefined,
    async (pid, name) => {
      try { await post('/api/listeners/disconnect', {pid}); } catch {}
      say(t('disconnected', {name}), 5);
      setTimeout(loadListeners, 400);
    });

async function setRoute2(to) {
  /* One whose listen is gone stays in the row, numbered, so the person can
     still see it was there. Nothing reads it, so it cannot be where speech
     goes. Say why rather than let the fill move and the words disappear
     (#110). The server refuses this one too. */
  const gone = knownListeners.find(l => String(l.pid) === to && l.gone);
  if (gone) {
    // Pressing it is how someone asks "why can I not use this one". Answer
    // with what to do about it, in the same status line every other notice
    // on this screen uses, and give it longer to be read than a plain ack.
    chime('err');
    say(t('listenerGoneHow', {name: gone.label}), 9);
    return;
  }
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
  // One that is gone is still in the row, so counting it as alive here would
  // let the destination move out from under the person without a word, which
  // is the very thing this notice exists to stop (#110). Only the ones that
  // can actually be reached count.
  const usable = knownListeners.filter(l => !l.gone);
  const live = new Set(usable.map(l => String(l.pid)));

  // If where it was going has ended, move to a session that is still alive and
  // say so. Left hanging silently, you talk and never notice nothing arrives.
  if (routeTo && !live.has(routeTo)) {
    const gone = before.find(l => String(l.pid) === routeTo);
    const next = usable[usable.length - 1];
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
  if (canBrowserASR) opts.push([BROWSER_ENGINE, engineLabel({id: BROWSER_ENGINE}), false]);
  if (canLocalASR) opts.push([BROWSER_LOCAL, t('engineBrowserLocal'), false]);
  /* An engine the server marked not ready is shown, not hidden. It cannot be
     picked yet, so the row carries the one command that makes it pickable
     (`apple` on a Mac without the Command Line Tools is the case this is for).
     Dropping it from the list would leave no way of learning that. */
  for (const e of localEngines) {
    const notYet = e.ready === false && e.need;
    opts.push([e.id,
               notYet ? t('engineNotYet', {label: engineLabel(e), cmd: e.need})
                      : engineLabel(e),
               !!notYet]);
  }
  // There can be machines with no browser recognition and no installed model
  // either. One that is only a command away does not count as having one.
  if (!opts.some(([, , off]) => !off)) opts.push(['', t('engineNone'), false]);
  el.enginePick.replaceChildren(...opts.map(([id, label, off]) => {
    const o = document.createElement('option');
    o.value = id; o.textContent = label;
    o.selected = id === engineShown(chosenEngine, onDeviceLocal);
    o.disabled = off;
    return o;
  }));
}

function paintBrowserAsr() {
  // "Keep this off if everything must stay on this machine" is the wrong
  // thing to say to someone who picked the entry that does exactly that.
  el.browserAsrWarn.hidden = !asrChosen || onDeviceLocal;
  el.asrConflict.hidden = !asrChosen || !asrConflict;
  el.asrConflict.textContent = t('asrConflict');
  el.browserMic.hidden = !asrChosen;
  if (!asrChosen) el.micSettingsSaid.hidden = true;   // no stale answer left behind
  el.asrLangField.hidden = !asrChosen;
  el.idleMuteField.hidden = !asrChosen;
  el.idleMuteNote.hidden = !asrChosen;
  // "Keeps reconnecting to Google" is untrue on the local entry, where the
  // reason to switch off is the same but nothing goes anywhere
  el.idleMuteNote.textContent = t(onDeviceLocal ? 'idleMuteNoteLocal' : 'idleMuteNote');
  el.browserGestureField.hidden = !asrChosen;
  paintIdleMute();
  // Browser recognition decides for itself when a clause is grammatically
  // done, isFinal is not something this setting can move. What it still
  // governs, on both engines now, is how long it waits after that before
  // actually sending it (queueOrSendFinal), so the slider stays live here too.
  el.silenceNote.textContent = t(asrChosen ? 'silenceNoteBrowser' : 'silenceNote');
  el.engineNote.textContent = t(asrChosen && !onDeviceLocal ? 'browserAsrNote' : 'localAsrNote');
  // Asked again with every paint, the 5 second poll included, so a model that
  // arrives some other way (another site, chrome://components) is noticed too
  paintOnDevice();
  if (asrChosen && onDeviceLocal) askOnDevice();
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
  syncRecWanted();

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
  /* The flag itself, read again here as well as on the storage event. The
     event is the only word another tab gives, it is not delivered to the tab
     that wrote it, and a tab that was asleep or had not loaded yet never
     hears it at all. Read off storage every 5 seconds, a tab that missed one
     comes back into line by itself rather than recognizing under a setting
     this browser moved away from minutes ago. */
  followOnDeviceFlag();
  paintEnginePick();
  paintBrowserAsr();
}

el.enginePick.onchange = async () => {
  // Both browser entries are 'browser' to the server. Which one it is stays here.
  const {engine: pick, local} = enginePicked(el.enginePick.value);
  const localChanged = pick === BROWSER_ENGINE && local !== onDeviceLocal;
  if (pick === BROWSER_ENGINE) {
    onDeviceLocal = local && canLocalASR;
    writeOnDeviceFlag(store, onDeviceLocal);
    // Read back rather than assumed. See onDeviceFlagKept.
    onDeviceFlagKept = readOnDeviceFlag(store) === onDeviceLocal;
    // Picking it again is also how a refusal gets another try
    onDeviceRefused = false;
    onDeviceProblem = '';
  }
  // Do not wait for the loadEngines every 5 seconds. Line up what shows from the moment it is chosen
  chosenEngine = pick;
  el.enginePick.disabled = true;
  try {
    if (pick === BROWSER_ENGINE) {
      asrChosen = true;
      // onDeviceLocal has already moved above, so this answers for the entry
      // being picked. Moving off the on-device entry while the mic is off puts
      // recWanted down, and the restart below then only stops.
      syncRecWanted();
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
      // Moving between the two browser entries. The session open now was
      // built for the other one, so it is dropped and the one that follows is
      // built afresh (through the hold, if local). Not conditional on one
      // being open: with none open, this is also what opens the right one.
      if (localChanged) restartRecognition();
      else if (recWanted) startRecognition();
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
  // A model is per language, so what was known is for the old one
  onDeviceRefused = false;
  onDeviceProblem = '';
  if (onDeviceLocal) paintBrowserAsr();
  // The language takes effect on the next reconnect. If it is in use,
  // reconnect right now. Through restartRecognition rather than a stop() and
  // the end it throws back, for the same reason the entry switch goes that
  // way: a model is per language, so on the local entry the new language may
  // have none, and a session left standing because Chrome never answered
  // would go on recognizing the old one on this device.
  if (recWanted) restartRecognition();
  // The words ignored out of the box are matched against what the recognizer
  // wrote down, so they follow this dropdown. Write what is on screen out under
  // the old language before reading the new one back, or a chip pressed just
  // now would be weighed against a list it was never drawn from.
  saveDict().then(loadDict);
};

/* This browser moved between the two browser entries somewhere other than
   here. The flag is shared by every tab of this browser (localStorage), and a
   tab that kept the answer it read at load would go on with the old one. Left
   on the plain entry, it is the tab that takes over listening (the 5 second
   heartbeat) once the one where local was picked closes, and it would send
   the audio to Google while this browser's choice says it stays here. A
   session already open was built for the other entry, so it is dropped and
   the next one goes through the hold.

   Both the storage event below and the 5 second poll come through here. The
   event alone is not enough: it never reaches the tab that wrote the flag,
   and a tab asleep or not yet loaded never hears it at all. */
function followOnDeviceFlag() {
  if (!canLocalASR || !onDeviceFlagKept) return false;
  const local = readOnDeviceFlag(store);
  if (local === onDeviceLocal) return false;
  onDeviceLocal = local;
  // A model is per entry as much as per language, and Chrome's refusal was
  // about the one being left
  onDeviceRefused = false;
  onDeviceProblem = '';
  /* Whether a session belongs open at all has just changed with the entry,
     while the mic is off: the on-device entry keeps one and the plain entry
     keeps none. Worked out before the restart below, or moving to the plain
     entry from another tab while muted would restart straight into a session
     that sends to Google what the mute was about. */
  syncRecWanted();
  // Unconditional, the same as the dropdown's own: a tab held off for a
  // missing model has no session open to close, and it is exactly that tab
  // that has to open one now that the plain entry is the one chosen.
  restartRecognition();
  paintEnginePick();
  paintBrowserAsr();
  paint();
  return true;
}

addEventListener('storage', ev => {
  if (ev.key !== null && ev.key !== 'vs.' + ON_DEVICE_FLAG) return;
  followOnDeviceFlag();
});

/* The download button. SR.install() has to be the very first thing the press
   does: Chrome only starts a download from inside a press, and even one await
   before it can let that go. It hands back no progress, so the status line
   shows downloading and available() is asked every 2 seconds until it says
   otherwise (askOnDevice starts listening when it does).

   The button sits in the settings sheet, which moves into the floating window.
   Whether a press there counts for this page's SR is Chrome's call, and if it
   says no (NotAllowedError) the line says to bring the window back and press
   it in the tab. */
el.onDeviceDownload.onclick = () => startOnDeviceInstall();

function startOnDeviceInstall() {
  const lang = browserLang();
  // Armed, the press that lands on the button itself gets here twice: once
  // through the capture listener on pointerdown, once through the button's own
  // click. The second would take the id the first is waiting on (settle drops
  // anything but the newest), leaving the line saying downloading for good.
  // A plain read of two variables, so install() is still the first thing the
  // press that does get through does.
  if (onDeviceInstalling && onDeviceInstallLang === lang) return;
  let asked;
  try {
    asked = SR.install({langs: [lang], processLocally: true});
  } catch (e) {
    asked = Promise.reject(e);
  }
  const id = ++onDeviceInstallId;
  onDeviceInstalling = true;
  onDeviceInstallLang = lang;
  onDeviceSawDownloading = false;
  onDeviceRefused = false;
  onDeviceProblem = '';
  paintOnDevice();
  keepPollingOnDevice();
  const settle = problem => {
    if (id !== onDeviceInstallId || !onDeviceInstalling) return;
    onDeviceInstalling = false;
    onDeviceProblem = browserLang() === lang ? problem : '';
    paintOnDevice();
    askOnDevice();
  };
  Promise.resolve(asked).then(
    ok => settle(ok ? '' : 'onDeviceDownloadFailed'),
    e => settle(e && e.name === 'NotAllowedError' ? 'onDevicePressMain' : 'onDeviceDownloadFailed'));
  /* Nothing promises install() ever settles. Left waiting on one that never
     does, the line would say downloading forever with the button greyed out
     and no way on short of a reload. If Chrome has not so much as begun after
     a while, the button comes back with the line saying it did not go through. */
  setTimeout(() => {
    if (!onDeviceSawDownloading && onDeviceNow() !== 'available') settle('onDeviceDownloadFailed');
  }, 45000);
}

/* ── Letting any press do it ──
   Ideally the model would just be got ready by voice-shell with nobody
   pressing anything. Chrome will not have that: install() only counts from
   inside a press. What it does not ask is that the press be on our button.
   So when the server has looked and Chrome already holds the model, the
   listener below rides along on the very next press anywhere on the page,
   whatever that press was for, and hands it to install() before the button
   or the field under the finger gets it (capture). Nothing is fetched, it is
   over in a few seconds, and from where you sit the local entry simply
   started working after you pressed something.

   keydown counts as a press for this too, so a keyboard is not left out.
   Both go on and come off together, and the first one to fire takes both off
   so the other cannot fire into a second install. paintOnDevice decides when
   it is on at all (onDeviceMayAutoInstall), and the guards are read again
   here at the moment of the press, since a press can land at any time. */
function armOnDeviceInstall() {
  if (onDeviceArmed) return;
  const fire = () => {
    // Not every keypress is a press as Chrome counts it. Escape (which closes
    // the settings sheet) and the modifiers on their own hand out no
    // activation, and install() would throw NotAllowedError, which the line
    // reads as the floating window and tells you to go back to the tab, which
    // is nonsense for a key. Stay armed for a press that really is one.
    try {
      if (navigator.userActivation && !navigator.userActivation.isActive) return;
    } catch {}
    disarmOnDeviceInstall();
    if (!onDeviceMayAutoInstall(onDeviceLocal, asrChosen, onDeviceNow(), onDeviceRefused,
                                onDeviceInstalling, onDeviceDiskNow())) return;
    // As with the button, install() has to be the first thing the press does
    startOnDeviceInstall();
  };
  onDeviceArmed = fire;
  addEventListener('pointerdown', fire, true);
  addEventListener('keydown', fire, true);
}

function disarmOnDeviceInstall() {
  if (!onDeviceArmed) return;
  const fire = onDeviceArmed;
  onDeviceArmed = null;
  removeEventListener('pointerdown', fire, true);
  removeEventListener('keydown', fire, true);
}

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
  await releaseWakeLock();
  wakeTarget = win;
  win.addEventListener('visibilitychange', syncWakeLock);
  syncWakeLock();
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
    releaseWakeLock();
    wakeTarget = window;
    syncWakeLock();
  });
};

// Same toggle a second press of floatBtn itself would run (closes the small
// window if one is open, which is always true while this button shows).
el.floatStandBack.onclick = () => el.floatBtn.onclick();

/* ── Keep the screen awake while listening ─────────────────────
   Voice-only work touches neither the keyboard nor the mouse, so left alone
   the screen goes dark mid-sentence exactly as it would on a machine no one
   is using at all.

   A wake lock only holds while its own window is the one on screen, and
   which window that is changes here: the ordinary tab most of the time, the
   small floating window once one is open (by then the tab it moved out of
   sits empty and Chrome counts it as hidden, same as any other background
   tab). wakeTarget is switched by hand alongside floatParts itself, right
   where the small window opens and where its pagehide brings everything back. */
const canWakeLock = target => { try { return !!(target && target.navigator && target.navigator.wakeLock); } catch { return false; } };
let wakeLockPref = store.get('wakeLockOnMic', '1') !== '0';
let wakeSentinel = null;
let wakeLockRequesting = false;
let wakeTarget = window;

el.wakeLockField.hidden = !canWakeLock(window);
el.wakeLockNote.hidden = !canWakeLock(window);
if (canWakeLock(window)) el.wakeLockOn.checked = wakeLockPref;

el.wakeLockOn.onchange = () => {
  wakeLockPref = el.wakeLockOn.checked;
  store.set('wakeLockOnMic', wakeLockPref ? '1' : '0');
  syncWakeLock();
};

async function releaseWakeLock() {
  const s = wakeSentinel;
  if (!s) return;
  wakeSentinel = null;
  try { await s.release(); } catch {}
}

async function syncWakeLock() {
  const want = wakeLockPref && route !== 'off' && (engineOnish() || asrActive())
    && canWakeLock(wakeTarget) && wakeTarget.document.visibilityState === 'visible';
  if (!want) { releaseWakeLock(); return; }
  if (wakeSentinel && !wakeSentinel.released) return;   // already held
  if (wakeLockRequesting) return;   // a request from a call earlier in this same tick is still in flight
  wakeLockRequesting = true;
  try {
    const s = await wakeTarget.navigator.wakeLock.request('screen');
    wakeSentinel = s;
    s.addEventListener('release', () => { if (wakeSentinel === s) wakeSentinel = null; });
  } catch {
    wakeSentinel = null;
  } finally {
    wakeLockRequesting = false;
  }
}
document.addEventListener('visibilitychange', syncWakeLock);

/* A page cannot open chrome://, so pressing it only copies.

   Two things were wrong in the small floating window. The clipboard was asked
   of this document's navigator while the button itself had been moved into the
   other window (floatParts), and Chrome turns down a write from a document that
   is not the focused one, so it threw every time. wakeTarget already takes the
   same care for the wake lock, so the window the button is actually living in
   is what gets asked here too. And the refusal was swallowed whole, which left
   pressing it looking like nothing at all happened. Whatever comes of it is
   said now, right under the address, because the settings sheet covers the main
   screen's hint line and a word written there would never be read. */
async function pressMicSettings(clip, url, show, tr) {
  try {
    await clip.writeText(url);
    show(true, tr('micSettingsCopied'));
    return true;
  } catch {
    show(false, tr('micSettingsCopyFailed', {url}));
    return false;
  }
}

el.micSettingsLink.onclick = async () => {
  const url = el.micSettingsLink.textContent.trim();
  const win = el.micSettingsLink.ownerDocument.defaultView || window;
  await pressMicSettings(win.navigator.clipboard, url, (ok, line) => {
    el.micSettingsSaid.textContent = line;
    el.micSettingsSaid.hidden = false;
    // The address is the label, so on a refusal it has to stay readable
    if (!ok) return;
    const was = el.micSettingsLink.textContent;
    el.micSettingsLink.textContent = t('copied');
    setTimeout(() => { el.micSettingsLink.textContent = was; }, 1400);
  }, t);
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
const CMD_DROP = /[ \t　。、．，・…！？!?.,\-~〜"'「」『』()（）]/g;
const cmdNormal = s => toHalfWidth(s.trim()).replace(CMD_DROP, '').toLowerCase();

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

  // The plain browser entry cuts the mic the instant it mutes, so the word
  // can never be heard under that one to begin with, unlike the daemon's mute
  // (mic_command_shape keeps listening for it on purpose) and unlike the
  // on-device entry, which keeps listening because nothing leaves the machine.
  // Not the same thing as switched off, that is a choice made here and undone
  // here. This is a fact of the entry currently running, so the switch itself
  // is held still (whatever it was set to keeps its place for the next time
  // something that can hear it is running) and only the line under it changes.
  const deadHere = g.id === 'unmute' && asrChosen && !onDeviceLocal;
  if (deadHere) useBox.disabled = true;

  const what = document.createElement('p');
  what.className = 'dict-label';
  box.append(what);
  /* Switched off, this line says what happens instead of what the signal does.
     The wordings below stay on screen so they can be read before switching it back
     on, and left with the old sentence above them they would read as still working.
     One line carries it. Nothing new is put up for it. */
  const paintUse = () => {
    // The second sentence only where that entry exists at all (Chrome 139 and
    // later). Pointing at something the picker does not show helps nobody.
    what.textContent = deadHere ? unmuteDeadLine()
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
  // Held off, the route here is the screen's alone, so the touch asks the
  // server where it really stands and refreshState takes it from off to that
  // through applyRouteSideEffects. Just clearing the flag and starting left
  // the screen saying live with recognition never started (#118). Not when
  // the touch is on a mic, though: its click is the switch on, and had the
  // answer come back first, that click would read live and switch it off.
  const arm = ev => {
    vizArmed = true;
    // Touched now, so a refusal from here on is a real one (autoResumed)
    autoResumed = false;
    if (armPending) {
      armPending = false;
      const onMic = [el.segOff, el.miniMic, el.helpMini]
        .some(b => { try { return b.contains(ev.target); } catch { return false; } });
      if (!onMic) refreshState();
    }
    if (recWanted) startRecognition();
  };
  addEventListener('pointerdown', arm, {once:true});
  addEventListener('keydown', arm, {once:true});
}
// What the tab had going the moment it was reloaded, if that was just now
let resume = null;
try { resume = takeResume(sessionStorage, Date.now()); } catch {}
if (resume) restoreDraft(resume);
// A floating window cannot be reopened without a press. The bubble that asks
// to float it shows on every load anyway (paintFloatAsk), so that press is one
// click away and the snapshot does not need to note it.
loadEngines().then(() => {
  if (!recWanted) return;
  if (vizArmed) { startRecognition(); return; }
  // It was listening right up to the reload, so carry on without waiting for
  // a touch. The meter still waits for one (armViz), and a refusal falls back
  // to the held-off start below (autoResumed, in onerror).
  if (resume?.live) {
    autoResumed = true;
    // Text put back in the box while in instant mode was left sitting there,
    // and what was said next went straight out ahead of it: the second half
    // of a sentence arrived before the first. It rides along with the next
    // utterance instead, the same as switching back from draft with text
    // still in the box (carryIntoNext).
    // Whether it was instant is read from the server (not paused), not from
    // anything the old page wrote down, so it holds even for a page that
    // predates this.
    // Recognition starts only once that is settled. Started alongside it, a
    // quick first word could beat the switch and go out ahead of the box, or
    // land before the carry and not count as the one that sends it.
    if (el.draft.value.trim()) {
      fetch('/api/state').then(r => r.json()).then(st => {
        if (st.paused || route === 'off' || carryDraft || !el.draft.value.trim()) return;
        const rev = routeRevision + 1;
        return setRoute('hold').then(() => {
          if (routeRevision === rev && route === 'hold' && el.draft.value.trim()) carryIntoNext();
        });
      }).catch(() => {}).finally(() => startRecognition());
    } else {
      startRecognition();
    }
    return;
  }
  // By browser rule the microphone cannot open until the screen has been
  // touched once. Instead of asking anyone to please click, we start switched
  // off. Pressing the mic to turn it on, the obvious thing to do, is itself the
  // touch.
  armPending = true;
  route = 'off';
  // Make it really off, not only on screen, so that leaving it takes the
  // same way back as any other off (see arm above and refreshState).
  applyRouteSideEffects('off');
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
