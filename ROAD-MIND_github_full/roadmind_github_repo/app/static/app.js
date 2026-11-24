/* Roadmind officer dashboard. Plain JavaScript, no external libraries (works offline). */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const BN_DIGITS = "০১২৩৪৫৬৭৮৯";

const T = {
  en: {
    tagline: "Traffic lights that think about people", junction: "Junction", vehicles: "🚗 Vehicles", people: "👥 People",
    chatTitle: "Ask Roadmind", chatTag: "numbers from the camera", chatSend: "Ask", chatPh: "Ask in Bangla or English…", chatThinking: "Thinking…", chatBy: { gemini: "written by Gemini · every number from Roadmind", template: "Roadmind (offline) · numbers from the camera" }, chatExamples: ["A mela crowd is coming on Road 2, double, plan for 1 hour", "After office time Road 1 gets busy, 45 minute plan", "How many people on each road now?", "Why this advice?", "What about the rain?"],
    planBtn: "💬 Ask Roadmind", rainBtn: "🌧 Heavy rain", planTitle: "Plan ahead", planHelp: "The crowd on a road will change (festival, mela, match, school or office time). Roadmind suggests a green split for that time. For several roads at once, just ask in the chat box. The officer still decides.", planRoad: "Which road?", planGrowth: "How will the crowd change?", planMinutes: "For how many minutes?", planGo: "Get the plan", planFor: (i, m) => `plan for the next ${m} min (Road ${i} gets more green)`, planEnough: (m) => `Plan for the next ${m} min — see the details`, planRunning: (h) => `📅 Rush plan running until ${h}, then the normal timer comes back`, sigPlan: "Rush plan, accepted", rainOn: "Heavy rain is on", hiddenHold: "🌧 Some vehicles may be hidden behind a truck in the rain, so the counts are not sure. Roadmind will not cut any road's green time now.", rainOnly: "🌧 Rain: the camera view is unclear. Roadmind is extra careful.",
    assumptions: "Assumptions", lightsTitle: "Traffic lights", lightsNote: "Changes when the officer presses Accept or Override · yellow is a fixed 3 s", sigFixed: "Normal timer", sigAccepted: "Roadmind plan, accepted", sigOverridden: "Officer's plan", sigEmergency: "Emergency", phGreen: "Green", phYellow: "Yellow", phRed: "Red", sigGreenFor: "green", sigGreenIn: "green in", uploadVideo: "⬆ Upload video", addCamera: "📷 Camera", camAsk: "Camera link (phone: the IP Webcam address, e.g. http://192.168.0.5:8080) or 0 for this laptop's webcam:", zones: "Draw zones", emergency: "Emergency", cameraTitle: "Live junction camera · AI detection",
    lowConfTitle: "Low confidence", lowConfHint: "Roadmind will not guess — keep the fixed timer.", cancel: "Cancel",
    privacy: "Privacy: no number plates are read and no faces are identified. The traffic lights change only after the officer approves.",
    aiRec: "AI recommendation", speak: "Speak", why: "Why? Show the numbers", accept: "Accept", override: "Override",
    ovSeconds: "Change green time for this road by (seconds)", ovReason: "Reason", ovSave: "Save override",
    officerDecides: "The officer decides · the lights change only after Accept or Override", noZones: "No roads found yet.", findingRoads: "Finding the roads automatically… watching the traffic for about 20 seconds.",
    simTitle: "Roadmind vs fixed timer", simulated: "Simulated", simWait: "Waiting for advice…",
    previewNote: "Next 2 minutes if you accept (people waiting) · grey = fixed timer, colour = Roadmind",
    logTitle: "Decision log", logNote: "Every decision recorded", fcTitle: "Rhythm forecast · next 30 min",
    occTitle: "People per vehicle (assumptions)", occHelp: "Average people in each vehicle type. These are estimates, not exact counts — adjust them for this junction.",
    save: "Save", close: "Close", logDetail: "Decision details",
    peopleTitle: "People waiting per road", vehiclesTitle: "Vehicles per road", rankedPeople: "ranked by people", rankedVehicles: "ranked by vehicles",
    confidence: "Confidence", nextIn: (s) => `next advice in ${s}s`, madeAt: (h) => `made ${h} · `, noChange: "No change needed. Waiting for the next advice.", oneRoad: "Only one road found, so there is no other road to share green time with. Use a video or camera that shows two or more roads.", greenFor: (i, n) => `green for Road ${i}` + extraName(i, n),
    keepPlan: "Current plan fits the traffic", keepFixed: "Low confidence — keep the fixed timer", fixedTimer: "Fixed",
    emFor: (i) => `green first for Road ${i} (emergency, simulated)`, emBar: (i, s) => `Emergency priority (simulated): Road ${i} gets green first · ${s}s left`,
    pedLine: (n, e) => `🚶 ${n} people waiting to cross` + (e ? ` · +${e}s walk time` : ""), queued: "queued", wait: "longest wait",
    personWait: "Avg person wait", vehWait: "Avg vehicle wait", peopleMin: "People moved / min", fixed: "Fixed", roadmind: "Roadmind",
    deltaTxt: (p) => p <= 0 ? `Person waiting time ${p}% with Roadmind (simulated)` : `Person waiting time +${p}% with Roadmind (simulated)`,
    accepted: "Accepted", overridden: "Overridden", pending: "Waiting for officer", low_confidence: "Low confidence", emergencyS: "Emergency", no_response: "No response",
    savedDecision: (s) => `${s} ✓ — recorded in the log. Waiting for the next advice.`, chooseRoad: "Give green first to:", modelDetects: "Model detects",
    needFinetune: "CNG / rickshaw / leguna need the fine-tuned model", src: { llm: "Phrased by Gemini · numbers from Roadmind", template: "Template · numbers from Roadmind" },
    noVoice: "This browser has no voice for reading aloud", noBnVoice: "No internet for the Bangla voice, reading in English.", rush: (m, e) => `⏰ ${e} rush expected in ${m} min — prepare early`,
    road: "Road", green: "Green", fixedCol: "Now", change: "Change", peopleCol: "People", vehiclesCol: "Vehicles",
  },
  bn: {
    tagline: "যে ট্রাফিক বাতি মানুষের কথা ভাবে", junction: "মোড়", vehicles: "🚗 যানবাহন", people: "👥 মানুষ",
    chatTitle: "Roadmind-কে জিজ্ঞেস করুন", chatTag: "সংখ্যা ক্যামেরা থেকে", chatSend: "জিজ্ঞেস", chatPh: "বাংলা বা ইংরেজিতে লিখুন…", chatThinking: "ভাবছি…", chatBy: { gemini: "লিখেছে Gemini · সব সংখ্যা Roadmind-এর", template: "Roadmind (অফলাইন) · সংখ্যা ক্যামেরা থেকে" }, chatExamples: ["রোড ২-এ মেলার ভিড় আসছে, দ্বিগুণ হবে, ১ ঘণ্টার প্ল্যান দাও", "অফিস ছুটির পর রোড ১-এ ভিড় বাড়বে, ৪৫ মিনিট কী করব?", "এখন কোন রাস্তায় কত মানুষ?", "এই পরামর্শ কেন?", "বৃষ্টিতে কী করব?"],
    planBtn: "💬 Roadmind-কে জিজ্ঞেস", rainBtn: "🌧 ভারী বৃষ্টি", planTitle: "আগাম পরিকল্পনা", planHelp: "কোনো রাস্তায় ভিড় বদলাবে (উৎসব, মেলা, খেলা, স্কুল বা অফিস ছুটি)। Roadmind ওই সময়ের জন্য সবুজ সময়ের ভাগ বলে দেয়। একসাথে কয়েকটা রাস্তার জন্য চ্যাট বক্সে জিজ্ঞেস করুন। সিদ্ধান্ত অফিসারের।", planRoad: "কোন রাস্তা?", planGrowth: "ভিড় কেমন বদলাবে?", planMinutes: "কত মিনিটের জন্য?", planGo: "পরিকল্পনা দেখাও", planFor: (i, m) => `পরের ${bnNum(m)} মিনিটের পরিকল্পনা (রোড ${bnNum(i)}-এ বেশি সবুজ)`, planEnough: (m) => `পরের ${bnNum(m)} মিনিটের পরিকল্পনা — বিস্তারিত দেখুন`, planRunning: (h) => `📅 ভিড়ের পরিকল্পনা চলছে ${h} পর্যন্ত, তারপর সাধারণ টাইমার ফিরবে`, sigPlan: "ভিড়ের পরিকল্পনা, গৃহীত", rainOn: "ভারী বৃষ্টি চালু", hiddenHold: "🌧 বৃষ্টিতে কিছু গাড়ি ট্রাকের পেছনে ঢাকা পড়তে পারে, তাই গোনা নিশ্চিত না। Roadmind এখন কোনো রাস্তার সবুজ সময় কমাবে না।", rainOnly: "🌧 বৃষ্টি: ক্যামেরার ছবি অস্পষ্ট। Roadmind বেশি সাবধান।",
    assumptions: "অনুমান", lightsTitle: "ট্রাফিক বাতি", lightsNote: "অফিসার Accept বা Override চাপলে বদলায় · হলুদ সবসময় ৩ সেকেন্ড", sigFixed: "সাধারণ টাইমার", sigAccepted: "Roadmind পরিকল্পনা, গৃহীত", sigOverridden: "অফিসারের পরিকল্পনা", sigEmergency: "জরুরি", phGreen: "সবুজ", phYellow: "হলুদ", phRed: "লাল", sigGreenFor: "সবুজ", sigGreenIn: "সবুজ হবে", uploadVideo: "⬆ ভিডিও আপলোড", addCamera: "📷 ক্যামেরা", camAsk: "ক্যামেরার লিংক (ফোন: IP Webcam-এর ঠিকানা, যেমন http://192.168.0.5:8080) অথবা ল্যাপটপের ওয়েবক্যামের জন্য 0:", zones: "জোন আঁকুন", emergency: "জরুরি", cameraTitle: "সরাসরি মোড়ের ক্যামেরা · এআই শনাক্তকরণ",
    lowConfTitle: "নিশ্চয়তা কম", lowConfHint: "Roadmind অনুমান করবে না — নির্দিষ্ট টাইমার চালু রাখুন।", cancel: "বাতিল",
    privacy: "গোপনীয়তা: কোনো নম্বর প্লেট পড়া হয় না, কারো মুখ শনাক্ত করা হয় না। অফিসার রাজি হলেই শুধু ট্রাফিক বাতি বদলায়।",
    aiRec: "এআই পরামর্শ", speak: "শুনুন", why: "কেন? সংখ্যাগুলো দেখুন", accept: "গ্রহণ", override: "পরিবর্তন",
    ovSeconds: "এই রোডের সবুজ সময় কত সেকেন্ড বদলাবেন", ovReason: "কারণ", ovSave: "পরিবর্তন সংরক্ষণ",
    officerDecides: "সিদ্ধান্ত অফিসারের · Accept বা Override চাপলেই বাতি বদলায়", noZones: "এখনো কোনো রাস্তা পাওয়া যায়নি।", findingRoads: "রাস্তাগুলো নিজে খুঁজে বের করা হচ্ছে… প্রায় ২০ সেকেন্ড ট্রাফিক দেখা হচ্ছে।",
    simTitle: "Roadmind বনাম নির্দিষ্ট টাইমার", simulated: "সিমুলেশন", simWait: "পরামর্শের অপেক্ষায়…",
    previewNote: "গ্রহণ করলে আগামী ২ মিনিট (অপেক্ষমাণ মানুষ) · ধূসর = নির্দিষ্ট টাইমার, রঙিন = Roadmind",
    logTitle: "সিদ্ধান্তের লগ", logNote: "প্রতিটি সিদ্ধান্ত সংরক্ষিত", fcTitle: "ছন্দ পূর্বাভাস · আগামী ৩০ মিনিট",
    occTitle: "প্রতি যানবাহনে মানুষ (অনুমান)", occHelp: "প্রতিটি যানবাহনে গড়ে কতজন। এগুলো অনুমান, সঠিক গণনা নয় — এই মোড়ের জন্য ঠিক করে নিন।",
    save: "সংরক্ষণ", close: "বন্ধ", logDetail: "সিদ্ধান্তের বিস্তারিত",
    peopleTitle: "প্রতি রোডে অপেক্ষমাণ মানুষ", vehiclesTitle: "প্রতি রোডে যানবাহন", rankedPeople: "মানুষ অনুযায়ী", rankedVehicles: "যানবাহন অনুযায়ী",
    confidence: "নিশ্চয়তা", nextIn: (s) => `পরের পরামর্শ ${bnNum(s)} সেকেন্ডে`, madeAt: (h) => `${h}-এ তৈরি · `, noChange: "কোনো পরিবর্তন লাগবে না। পরের পরামর্শের অপেক্ষা।", oneRoad: "শুধু একটা রাস্তা পাওয়া গেছে, তাই সবুজ সময় ভাগ করার মতো অন্য রাস্তা নেই। দুই বা তার বেশি রাস্তা দেখা যায় এমন ভিডিও বা ক্যামেরা ব্যবহার করুন।", greenFor: (i, n) => `রোড ${bnNum(i)}-এ সবুজ` + extraName(i, n),
    keepPlan: "এখনকার টাইমিং ঠিক আছে", keepFixed: "নিশ্চয়তা কম — নির্দিষ্ট টাইমার রাখুন", fixedTimer: "নির্দিষ্ট",
    emFor: (i) => `রোড ${bnNum(i)}-এ আগে সবুজ (জরুরি, সিমুলেশন)`, emBar: (i, s) => `জরুরি অগ্রাধিকার (সিমুলেশন): রোড ${bnNum(i)} আগে সবুজ পাবে · বাকি ${bnNum(s)} সেকেন্ড`,
    pedLine: (n, e) => `🚶 ${bnNum(n)} জন রাস্তা পার হওয়ার অপেক্ষায়` + (e ? ` · +${bnNum(e)} সেকেন্ড হাঁটার সময়` : ""), queued: "সারিতে", wait: "সবচেয়ে দীর্ঘ অপেক্ষা",
    personWait: "গড় মানুষের অপেক্ষা", vehWait: "গড় যানবাহনের অপেক্ষা", peopleMin: "প্রতি মিনিটে মানুষ পার", fixed: "নির্দিষ্ট", roadmind: "Roadmind",
    deltaTxt: (p) => `Roadmind-এ মানুষের অপেক্ষা ${bnNum(p)}% (সিমুলেশন)`,
    accepted: "গৃহীত", overridden: "পরিবর্তিত", pending: "অফিসারের অপেক্ষায়", low_confidence: "নিশ্চয়তা কম", emergencyS: "জরুরি", no_response: "উত্তর নেই",
    savedDecision: (s) => `${s} ✓ — লগে সংরক্ষিত। পরের পরামর্শের অপেক্ষা।`, chooseRoad: "আগে সবুজ দিন:", modelDetects: "মডেল শনাক্ত করে",
    needFinetune: "সিএনজি / রিকশা / লেগুনার জন্য ফাইন-টিউন করা মডেল লাগবে", src: { llm: "Gemini দিয়ে লেখা · সংখ্যা Roadmind-এর", template: "টেমপ্লেট · সংখ্যা Roadmind-এর" },
    noVoice: "এই ব্রাউজারে পড়ে শোনানোর ভয়েস নেই", noBnVoice: "বাংলা ভয়েসের জন্য ইন্টারনেট নেই, ইংরেজিতে পড়া হচ্ছে।", rush: (m, e) => `⏰ ${bnNum(m)} মিনিটে ${e} ভিড় আসতে পারে — আগে প্রস্তুত হোন`,
    road: "রোড", green: "সবুজ", fixedCol: "এখন", change: "পরিবর্তন", peopleCol: "মানুষ", vehiclesCol: "যানবাহন",
  },
};
const REASON_BN = { "Dark": "আলো খুব কম", "Blur / rain": "ছবি ঝাপসা (বৃষ্টি?)", "View blocked": "ক্যামেরার দৃশ্য ঢাকা", "Low detection confidence": "শনাক্তকরণের নিশ্চয়তা কম" };
const TYPE_LABEL = { bus: "🚌 Bus", car: "🚗 Car", cng: "🛺 CNG", rickshaw: "🚲 Rickshaw", battery_rickshaw: "🛺 E-rickshaw", leguna: "🚐 Leguna",
  motorbike: "🏍 Motorbike", bicycle: "🚲 Bicycle", truck: "🚚 Truck", van: "🚐 Van", other: "• Other" };

let lang = "en", view = "people", junctionId = null, es = null, pollTimer = null;
let decidedFor = null, state = null, adviceId = null, adviceSig = "", lastLogFetch = 0, junctionCache = {}, overrideReasons = [];

const t = (k, ...a) => { const v = T[lang][k] ?? T.en[k]; return typeof v === "function" ? v(...a) : v; };
function bnNum(v) { return String(v).replace(/[0-9]/g, (d) => BN_DIGITS[d]); }
const num = (v) => (lang === "bn" ? bnNum(v) : String(v));
function toast(msg) { const el = $("toast"); el.textContent = msg; el.classList.add("show"); clearTimeout(toast.h); toast.h = setTimeout(() => el.classList.remove("show"), 3200); }

function applyI18n() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { const v = t(el.dataset.i18n); if (typeof v === "string" && v) el.textContent = v; });   // keep the button's own text if a word is missing
  $("langEn").setAttribute("aria-pressed", lang === "en"); $("langBn").setAttribute("aria-pressed", lang === "bn");
  renderChatChips(); adviceSig = ""; if (state) render(state);
}

/* ---------- connection ---------- */
async function init() {
  const data = await (await fetch("/api/junctions")).json();
  overrideReasons = data.override_reasons || [];
  $("ovReason").innerHTML = overrideReasons.map((r) => `<option>${esc(r)}</option>`).join("");
  $("junction").innerHTML = data.junctions.map((j) => `<option value="${esc(j.id)}">${esc(j.name)}</option>`).join("");
  const start = data.junctions.some((j) => j.id === data.default) ? data.default : (data.junctions[0] || {}).id;
  if (start) { $("junction").value = start; openJunction(start); }
  applyI18n();
}
function openJunction(id) {
  junctionId = id; adviceId = null; adviceSig = ""; state = null;
  $("acceptBtn").disabled = true; $("overrideBtn").disabled = true; $("adviceTime").textContent = ""; $("decided").textContent = "";
  $("stream").src = `/api/stream/${encodeURIComponent(id)}`;
  if (es) es.close(); clearInterval(pollTimer);
  if ("EventSource" in window) {
    es = new EventSource(`/api/events/${encodeURIComponent(id)}`);
    es.onmessage = (e) => render(JSON.parse(e.data));
    es.onerror = () => { es.close(); startPolling(); };
  } else startPolling();
  loadLog();
}
// Browsers allow only ~6 open connections per site. Each dashboard tab keeps two
// (video + live data), so release them while the tab is hidden and reconnect on return.
const BLANK = "data:image/gif;base64,R0lGODlhAQABAAAAACw=";
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (es) { es.close(); es = null; }
    clearInterval(pollTimer); $("stream").src = BLANK;
  } else if (junctionId) openJunction(junctionId);
});

function startPolling() {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => { try { render(await (await fetch(`/api/state/${encodeURIComponent(junctionId)}`)).json()); } catch (_) {} }, 500);
}

/* ---------- render ---------- */
// "Road 2 · CDA Avenue", but just "Road 2" when the zone still has its default name.
function extraName(i, name) { return name && !/^road\s*\d+$/i.test(name.trim()) ? ` · ${name}` : ""; }
function roadLabel(i, name) { return `${esc(t("road"))} ${num(i)}${esc(extraName(i, name))}`; }

function render(s) {
  state = s;
  if (s.features) applyFeatures(s.features);   // hide the switched-off panels even before the video starts
  if (s.status === "error") { $("fps").textContent = s.error; return; }
  if (s.status !== "running") return;
  $("fps").textContent = `${s.fps} fps${s.ai_fps != null ? ` (AI ${s.ai_fps})` : ""} · ${s.total_vehicles ?? 0} ${lang === "bn" ? "যানবাহন" : "vehicles"} · ${s.total_people_detected ?? 0} ${lang === "bn" ? "মানুষ" : "people"}`;
  const types = s.supported_types || [];
  $("modelNote").textContent = `${t("modelDetects")}: ${types.filter((x) => x !== "person").join(", ")}` + (types.includes("cng") ? "" : ` · ${t("needFinetune")}`);
  applyFeatures(s.features);
  renderConfidence(s.confidence || {});
  renderRoads(s);
  takeSignal(s);
  renderEmergency(s);
  renderAdvice(s.advice, s);
  renderRain(s);
  renderForecast(s.forecast);
  $("nextIn").textContent = s.next_advice_in_s != null ? t("nextIn", s.next_advice_in_s) : "";
  if (Date.now() - lastLogFetch > 10000) loadLog();
}

// Hide panels for features the server does not offer (older builds send a shorter list).
let featSig = null;
function applyFeatures(list) {
  if (!list) return;   // nothing known yet: keep the page as it is
  const sig = list.join(",");
  if (sig === featSig) return; featSig = sig;
  const has = (f) => !list || list.includes(f);
  $("confChip").hidden = !has("confidence");
  $("emBtn").hidden = !has("emergency");
  $("simPanel").hidden = !has("simulation");
  $("fcPanel").hidden = !has("forecast");
  document.querySelector(".bottom").style.setProperty("--cols", 1 + has("simulation") + has("forecast"));
}

function renderConfidence(c) {
  const chip = $("confChip"); const level = c.level || "High";
  chip.className = `chip conf-${level}`;
  const levelTxt = lang === "bn" ? { High: "বেশি", Medium: "মাঝারি", Low: "কম" }[level] : level;
  $("confText").textContent = `${t("confidence")}: ${levelTxt}` + (c.score != null ? ` · ${num(Math.round(c.score * 100))}%` : "");
  chip.title = (c.reasons || []).join(", ");
  const low = level === "Low" && !(state && state.emergency);
  $("lowConf").classList.toggle("show", low);
  $("lowConfReasons").textContent = (c.reasons || []).map((r) => (lang === "bn" ? REASON_BN[r] || r : r)).join(" · ");
}

/* Connected traffic lights: the server sends the plan in force; the browser shows the live phase. */
let sig = null, sigOffset = 0, sigSince = null;
function takeSignal(s) {
  if (!s.signal) return;
  if (sigSince !== null && s.signal.since !== sigSince) {   // a new plan just reached the lights
    setTimeout(() => document.querySelectorAll(".sig").forEach((el) => el.classList.add("flash")), 50);
  }
  sig = s.signal; sigSince = s.signal.since; sigOffset = s.signal.now - Date.now() / 1000;
}
function drawSignals() {
  const box = $("signals");
  if (!box) return;
  if (!sig || !sig.order || !sig.order.length) { box.innerHTML = ""; $("sigSource").textContent = ""; return; }
  const names = {};
  ((state && state.roads) || []).forEach((r, k) => { names[r.id] = { i: k + 1, name: r.name }; });
  const steps = sig.order.map((id) => ({ id, g: Math.max(1, sig.plan[id] || 0) }));
  const total = steps.reduce((a, st) => a + st.g + sig.yellow + sig.all_red, 0);
  const now = Date.now() / 1000 + sigOffset;
  const tt = ((now - sig.since) % total + total) % total;
  let active = 0, phase = "red", left = 0, start = 0;
  for (let k = 0; k < steps.length; k++) {
    const st = steps[k], len = st.g + sig.yellow + sig.all_red;
    if (tt < start + len) {
      active = k; const into = tt - start;
      if (into < st.g) { phase = "green"; left = st.g - into; }
      else if (into < st.g + sig.yellow) { phase = "yellow"; left = st.g + sig.yellow - into; }
      else { phase = "allred"; left = len - into; }
      break;
    }
    start += len;
  }
  const src = { fixed: "sigFixed", plan_ahead: "sigPlan", accepted: "sigAccepted", overridden: "sigOverridden", emergency: "sigEmergency" }[sig.source] || "sigFixed";
  $("sigSource").textContent = t(src);
  const flashing = box.querySelector(".flash") !== null;
  box.innerHTML = steps.map((st, k) => {
    let ph = "red", secs = 0;
    if (k === active && phase === "green") { ph = "green"; secs = left; }
    else if (k === active && phase === "yellow") { ph = "yellow"; secs = left; }
    else {   // time until this road turns green
      let wait = k === active ? left : 0, idx = active;
      if (k !== active) {
        wait = left + (phase === "green" ? sig.yellow + sig.all_red : phase === "yellow" ? sig.all_red : 0);
        idx = (active + 1) % steps.length;
        while (idx !== k) { wait += steps[idx].g + sig.yellow + sig.all_red; idx = (idx + 1) % steps.length; }
      }
      secs = wait;
    }
    const n = names[st.id] || { i: k + 1, name: st.id };
    const label = ph === "green" ? t("phGreen") : ph === "yellow" ? t("phYellow") : t("phRed");
    const sub = ph === "red" ? `${t("sigGreenIn")} ${num(Math.ceil(secs))}s` : `${num(st.g)}s ${t("sigGreenFor")}`;
    return `<div class="sig${flashing ? " flash" : ""}"><div class="lamps"><span class="lamp r${ph === "red" ? " on" : ""}"></span><span class="lamp y${ph === "yellow" ? " on" : ""}"></span><span class="lamp g${ph === "green" ? " on" : ""}"></span></div>
      <div class="nm">${roadLabel(n.i, n.name)}<div class="ph">${esc(label)} · ${esc(sub)}</div></div><div class="cd">${num(Math.ceil(secs))}</div></div>`;
  }).join("");
}
setInterval(drawSignals, 250);

function renderRoads(s) {
  const roads = s.roads || [];
  const key = view === "people" ? "people" : "total_vehicles";
  $("roadsTitle").textContent = view === "people" ? t("peopleTitle") : t("vehiclesTitle");
  $("rankNote").textContent = view === "people" ? t("rankedPeople") : t("rankedVehicles");
  if (!roads.length || (s.auto_setup && s.auto_setup.status === "finding")) {
    const a = s.auto_setup || {};
    const msg = a.status === "finding" ? t("findingRoads") : (a.status === "failed" && a.message) ? a.message : t("noZones");
    $("roads").innerHTML = `<p class="muted small">${esc(msg)}</p>`; $("ped").hidden = true; return;
  }
  const order = view === "people" ? s.rank_people : s.rank_vehicles;
  const byId = Object.fromEntries(roads.map((r, i) => [r.id, { ...r, index: i + 1 }]));
  const max = Math.max(1, ...roads.map((r) => r[key] || 0));
  $("roads").innerHTML = order.map((id, pos) => {
    const r = byId[id]; const v = r[key] || 0;
    const mix = Object.entries(r.vehicles || {}).map(([k, n]) => `<span>${esc(TYPE_LABEL[k] || k)} ${num(n)}</span>`).join("");
    const shown = view === "people" ? `~${num(Math.round(v))}` : num(v);
    return `<div class="road ${pos === 0 && v > 0 ? "top" : ""}">
      <div class="name"><span class="rank">${num(pos + 1)}</span>${roadLabel(r.index, r.name)}<span class="val">${shown}</span></div>
      <div class="bar"><i style="width:${(100 * v / max).toFixed(1)}%"></i></div>
      <div class="mix">${mix}<span>${esc(t("queued"))} ${num(r.queued)}</span><span>${esc(t("wait"))} ${num(Math.round(r.longest_wait_s))}s</span></div>
    </div>`;
  }).join("");
  const ext = s.advice && s.advice.walk_extension ? s.advice.walk_extension : 0;
  $("ped").hidden = !(s.crossings || []).length;
  $("ped").textContent = t("pedLine", s.pedestrians_waiting || 0, ext);
}

let emSig = "";
function renderEmergency(s) {
  const roads = s.roads || [];
  const sig = lang + "|" + roads.map((r) => r.id + r.name).join(",");
  if (sig !== emSig) { // rebuild the menu only when the roads change, so buttons stay clickable
    emSig = sig;
    $("emPop").innerHTML = `<p class="h">${esc(t("chooseRoad"))}</p>` + roads.map((r, i) =>
      `<button class="btn small" role="menuitem" data-road="${esc(r.id)}">${roadLabel(i + 1, r.name)}</button>`).join("");
    $("emPop").querySelectorAll("button[data-road]").forEach((b) => (b.onclick = () => startEmergency(b.dataset.road)));
  }
  const em = s.emergency;
  $("emBar").classList.toggle("show", !!em);
  if (em) { const idx = roads.findIndex((r) => r.id === em.road) + 1; $("emText").textContent = t("emBar", idx, em.remaining_s); }
}

function renderAdvice(a, s) {
  const card = $("adviceCard");
  if (!a) return;
  if (a.error) { $("what").textContent = a.error; return; }
  const sig = `${a.id}|${a.explanation && a.explanation.source}|${lang}`;
  if (sig === adviceSig) return; // only redraw when the advice or its text changes
  const isNew = a.id !== adviceId;
  adviceSig = sig; adviceId = a.id;
  card.classList.remove("mode-keep", "mode-emergency");
  const top = a.top;
  if (a.mode === "keep_fixed") {
    card.classList.add("mode-keep"); $("bigsec").textContent = t("fixedTimer"); $("what").textContent = t("keepFixed");
  } else if (a.mode === "emergency" && top) {
    card.classList.add("mode-emergency"); $("bigsec").textContent = `🚑 ${num(top.green)}s`; $("what").textContent = t("emFor", top.index);
  } else if (a.mode === "plan_ahead") {
    const mins = (a.numbers || {}).plan_minutes || 20;
    if (top && top.delta > 0) { countUp($("bigsec"), top.delta, isNew); $("what").textContent = t("planFor", top.index, mins); }
    else { $("bigsec").textContent = "✓"; $("what").textContent = t("planEnough", mins); }
  } else if (top) {
    countUp($("bigsec"), top.delta, isNew); $("what").textContent = t("greenFor", top.index, top.name);
  } else { $("bigsec").textContent = "✓"; $("what").textContent = t("keepPlan"); }

  const ex = a.explanation || {};
  $("explainText").innerHTML = `<div class="bn" lang="bn">${esc(ex.bn)}</div>` + (lang === "en" ? `<div class="small muted" style="margin-top:4px;font-family:Inter">${esc(ex.en)}</div>` : "");
  $("explainSrc").textContent = (T[lang].src || T.en.src)[ex.source] || "";

  const plan = a.plan || [];
  $("whyBody").innerHTML = plan.length ? `<table><tr><th>${esc(t("road"))}</th><th>${esc(t("peopleCol"))}</th><th>${esc(t("vehiclesCol"))}</th><th>${esc(t("fixedCol"))}</th><th>${esc(t("green"))}</th><th>${esc(t("change"))}</th></tr>` +
    plan.map((r) => `<tr><td>${num(r.index)} · ${esc(r.name)}</td><td>${num(Math.round(r.people))}</td><td>${num(r.vehicles)}</td><td>${num(r.fixed)}s</td><td>${num(r.green)}s</td><td>${r.delta > 0 ? "+" : ""}${num(r.delta)}s</td></tr>`).join("") +
    `</table><p class="muted small">${esc((a.reasons || []).join(" · "))}</p><p class="muted small">Walk: ${num(a.walk_seconds)}s · Cycle: ${num((a.numbers || {}).cycle || "")}s</p>` : "";

  // when this advice was made
  if (a.created_at) $("adviceTime").textContent = t("madeAt", new Date(a.created_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));

  // one decision per advice: after Accept or Override, wait for the next advice.
  // Nothing to decide when the advice is "keep the current plan".
  const changes = a.mode === "emergency" || (a.mode === "advise" && !!top) || (a.mode === "plan_ahead" && (a.plan || []).some((r) => r.delta !== 0));
  const actionable = changes && a.id !== decidedFor && a.status !== "accepted" && a.status !== "overridden";
  $("acceptBtn").disabled = !actionable; $("overrideBtn").disabled = !actionable;
  if (isNew) {
    const oneRoad = (a.plan || []).length === 1;
    $("decided").textContent = oneRoad ? t("oneRoad") : (!changes ? t("noChange") : "");
    $("overrideForm").classList.remove("show");
    $("ovSeconds").value = top ? top.delta : 0;
    card.classList.remove("flash"); void card.offsetWidth; card.classList.add("flash");
    renderSimulation(a.simulation); loadLog();
  }
}

function countUp(el, target, animate) {
  const sign = target > 0 ? "+" : "";
  if (!animate) { el.textContent = `${sign}${num(target)}s`; return; }
  const start = performance.now(), dur = 700;
  const step = (now) => { const p = Math.min(1, (now - start) / dur); el.textContent = `${sign}${num(Math.round(target * (1 - Math.pow(1 - p, 3))))}s`; if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

function renderSimulation(sim) {
  if (!sim) { $("cmp").innerHTML = `<span class="muted small">${esc(t("simWait"))}</span>`; $("simDelta").textContent = ""; $("previewChart").innerHTML = ""; return; }
  const rows = [["personWait", "avg_person_wait_s", "s"], ["vehWait", "avg_wait_s", "s"], ["peopleMin", "people_moved_per_min", ""]];
  $("cmp").innerHTML = rows.map(([label, k, unit]) => {
    const f = sim.fixed[k], r = sim.roadmind[k], m = Math.max(f, r, 1);
    return `<span class="muted">${esc(t(label))}</span><span></span><span></span>
      <span class="small">${esc(t("fixed"))}</span><span class="b f"><i style="width:${(100 * f / m).toFixed(1)}%"></i></span><b>${num(f)}${unit}</b>
      <span class="small">${esc(t("roadmind"))}</span><span class="b r"><i style="width:${(100 * r / m).toFixed(1)}%"></i></span><b class="grad-text">${num(r)}${unit}</b>`;
  }).join("");
  $("simDelta").textContent = t("deltaTxt", sim.person_wait_change_pct);
  const p = sim.preview, all = [...p.fixed, ...p.roadmind], maxV = Math.max(1, ...all);
  const line = (arr) => arr.map((v, i) => `${(i / (arr.length - 1 || 1)) * 300},${100 - (v / maxV) * 90}`).join(" ");
  $("previewChart").innerHTML = `<defs><linearGradient id="pg" x1="0" x2="1"><stop offset="0" stop-color="#34D399"/><stop offset=".5" stop-color="#38BDF8"/><stop offset="1" stop-color="#A855F7"/></linearGradient></defs>
    <polyline points="${line(p.fixed)}" fill="none" stroke="#64748B" stroke-width="2" vector-effect="non-scaling-stroke"/>
    <polyline points="${line(p.roadmind)}" fill="none" stroke="url(#pg)" stroke-width="3" vector-effect="non-scaling-stroke"/>`;
}

function renderForecast(fc) {
  if (!fc) { $("fcNote").textContent = lang === "bn" ? "প্রথম পূর্বাভাস এক মিনিটের মধ্যে আসবে…" : "First forecast arrives within a minute…"; return; }
  $("fcNow").textContent = fc.now;
  const pts = fc.points || []; if (!pts.length) return;
  const maxV = Math.max(1, ...pts.map((p) => p.high));
  const x = (i) => (i / (pts.length - 1)) * 300, y = (v) => 100 - (v / maxV) * 88;
  const band = pts.map((p, i) => `${x(i)},${y(p.high)}`).join(" ") + " " + pts.slice().reverse().map((p, i) => `${x(pts.length - 1 - i)},${y(p.low)}`).join(" ");
  const markers = pts.map((p, i) => p.events.length ? `<line x1="${x(i)}" x2="${x(i)}" y1="0" y2="110" stroke="#FDE68A" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>` : "").join("");
  $("fcChart").innerHTML = `<polygon points="${band}" fill="rgba(168,85,247,.22)"/>${markers}
    <polyline points="${pts.map((p, i) => `${x(i)},${y(p.people)}`).join(" ")}" fill="none" stroke="#C4B5FD" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`;
  const b = fc.banner;
  $("fcBanner").innerHTML = b ? `<div class="banner">${esc(t("rush", b.minutes, lang === "bn" ? b.event_bn : b.event))}</div>` : "";
  $("fcNote").textContent = (lang === "bn" ? "রেকর্ড করা গণনা ও স্থানীয় ঘটনার ক্যালেন্ডার থেকে পূর্বাভাস; গুণকগুলো অনুমান।" : fc.note) + ` (${fc.history_points} pts)`;
}

/* ---------- log ---------- */
async function loadLog() {
  if (!junctionId) return; lastLogFetch = Date.now();
  try {
    const data = await (await fetch(`/api/log/${encodeURIComponent(junctionId)}`)).json();
    $("log").innerHTML = data.decisions.map((d) => {
      const time = new Date(d.created_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const top = d.advice.top; const label = d.status === "emergency" ? t("emergencyS") : t(d.status) || d.status;
      const what = d.advice.mode === "keep_fixed" ? t("keepFixed") : top ? `${t("road")} ${num(top.index)} ${top.delta > 0 ? "+" : ""}${num(d.advice.mode === "emergency" ? top.green : top.delta)}s` : t("keepPlan");
      const extra = d.status === "overridden" ? ` → ${d.chosen_seconds > 0 ? "+" : ""}${num(d.chosen_seconds)}s (${esc(d.reason)})` : "";
      return `<li><button data-id="${d.id}"><span class="st st-${esc(d.status)}">${esc(label)}</span><span>${esc(time)} · ${esc(what)}${extra}</span></button></li>`;
    }).join("") || `<li class="muted small">—</li>`;
    $("log").querySelectorAll("button[data-id]").forEach((b) => (b.onclick = () => showLog(data.decisions.find((d) => String(d.id) === b.dataset.id))));
  } catch (_) {}
}
function showLog(d) {
  if (!d) return;
  const ex = d.explanation || {};
  $("logBody").innerHTML = (d.thumb ? `<img class="thumb" src="/api/thumb/${encodeURIComponent(d.thumb)}" alt="Small blurred snapshot of the junction at that moment">` : "") +
    `<p class="bn">${esc(ex.bn)}</p><p class="muted small">${esc(ex.en)}</p>` +
    `<p class="small"><span class="st st-${esc(d.status)}">${esc(t(d.status) || d.status)}</span> ${d.reason ? esc(d.reason) : ""}</p>` +
    `<table class="small" style="width:100%">${(d.advice.plan || []).map((r) => `<tr><td>${num(r.index)} · ${esc(r.name)}</td><td>~${num(Math.round(r.people))} ${esc(t("peopleCol"))}</td><td>${num(r.fixed)}s → ${num(r.green)}s</td></tr>`).join("")}</table>`;
  $("logDialog").showModal();
}

/* ---------- actions ---------- */
async function decide(action, seconds, reason) {
  if (!adviceId) return;
  const res = await fetch("/api/decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: adviceId, action, seconds, reason }) });
  const data = await res.json();
  if (!res.ok) { toast(data.detail || "Error"); return; }
  decidedFor = adviceId;
  $("acceptBtn").disabled = true; $("overrideBtn").disabled = true;
  $("decided").textContent = t("savedDecision", action === "accept" ? t("accepted") : t("overridden"));
  $("overrideForm").classList.remove("show"); loadLog();
}
// heavy rain switch, hidden-vehicle hold and the running rush plan
function renderRain(s) {
  $("rainBtn").setAttribute("aria-pressed", String(!!s.rain_switch));
  const box = $("careful");
  let msg = s.hidden_risk ? t("hiddenHold") : (s.rain ? t("rainOnly") : "");
  if (s.plan_until) msg = (msg ? msg + " · " : "") + t("planRunning", new Date(s.plan_until * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
  box.hidden = !msg; box.textContent = msg;
}
// Ask Roadmind: chat box
function chatAdd(cls, text, by) {
  const el = document.createElement("div"); el.className = `msg ${cls}`; el.textContent = text;
  if (by) { const b = document.createElement("span"); b.className = "by"; b.textContent = by; el.appendChild(b); }
  $("chatLog").appendChild(el); $("chatLog").scrollTop = $("chatLog").scrollHeight; return el;
}
function renderChatChips() { $("chatInput").placeholder = t("chatPh"); }
let chatHistory = [];
function typeOut(el, text, by) {   // write the reply a few letters at a time, like a chat assistant
  el.textContent = ""; const chars = Array.from(text); let i = 0;
  const step = () => {
    i = Math.min(chars.length, i + 3); el.textContent = chars.slice(0, i).join("");
    $("chatLog").scrollTop = $("chatLog").scrollHeight;
    if (i < chars.length) setTimeout(step, 12);
    else if (by) { const b = document.createElement("span"); b.className = "by"; b.textContent = by; el.appendChild(b); }
  };
  step();
}
async function askRoadmind(q) {
  q = (q || "").trim(); if (!q || !junctionId) return;
  $("chatInput").value = ""; chatAdd("me", q);
  const wait = chatAdd("ai", t("chatThinking")); wait.classList.add("thinking");
  $("chatInput").disabled = true;
  try {
    const res = await fetch(`/api/chat/${encodeURIComponent(junctionId)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: q, history: chatHistory }) });
    const r = await res.json();
    wait.classList.remove("thinking");
    if (!res.ok) { wait.textContent = r.detail || "Error"; return; }
    const text = r.text || (r.lang === "bn" ? r.bn : r.en);
    chatHistory.push({ role: "user", text: q }, { role: "assistant", text });
    chatHistory = chatHistory.slice(-8);
    typeOut(wait, text, (t("chatBy") || {})[r.answered_by]);
  } catch (_) { wait.textContent = "Error"; }
  finally { $("chatInput").disabled = false; $("chatInput").focus(); }
}
async function startEmergency(roadId) {
  closePop();
  await fetch(`/api/emergency/${encodeURIComponent(junctionId)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ road_id: roadId }) });
}
function closePop() { $("emPop").classList.remove("show"); $("emBtn").setAttribute("aria-expanded", "false"); }

/* Read the advice aloud: the server's Bangla voice first; without internet, the browser's own voice. */
function loadVoices() {
  return new Promise((resolve) => {
    const v = speechSynthesis.getVoices();
    if (v.length) return resolve(v);
    const done = () => resolve(speechSynthesis.getVoices());
    speechSynthesis.addEventListener("voiceschanged", done, { once: true });
    setTimeout(done, 1500);
  });
}
let voicePlayer = null;
async function speak() {
  const ex = state && state.advice && state.advice.explanation;
  if (!ex) { toast(t("noVoice")); return; }
  // 1. Bangla voice made on the server: works in every browser (needs internet)
  try {
    $("speakBtn").disabled = true;
    const res = await fetch("/api/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: ex.bn, lang: "bn" }) });
    if (res.ok) {
      const url = URL.createObjectURL(await res.blob());
      if (voicePlayer) voicePlayer.pause();
      voicePlayer = new Audio(url); voicePlayer.volume = 1;
      await voicePlayer.play();
      return;
    }
  } catch (_) { /* fall back to the browser's own voice */ }
  finally { $("speakBtn").disabled = false; }
  // 2. No internet: the browser's own voice
  if (!("speechSynthesis" in window)) { toast(t("noVoice")); return; }
  const voices = await loadVoices();
  const bn = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("bn"));
  const en = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("en") && /natural|google|online/i.test(v.name))
          || voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("en"));
  const useBn = bn && ex.bn;
  const voice = useBn ? bn : en;
  const text = useBn ? ex.bn : (ex.en || ex.bn);
  if (!voice || !text) { toast(t("noVoice")); return; }
  if (!useBn) toast(t("noBnVoice"));
  const u = new SpeechSynthesisUtterance(text);
  u.voice = voice; u.lang = voice.lang; u.rate = 0.95; u.volume = 1;
  speechSynthesis.cancel(); speechSynthesis.resume();
  setTimeout(() => speechSynthesis.speak(u), 60);   // Chrome sometimes drops a speak() right after cancel()
}
if ("speechSynthesis" in window) loadVoices();

function openOccupancy() {
  const occ = (state && state.occupancy) || {};
  $("occGrid").innerHTML = Object.entries(occ).map(([k, v]) =>
    `<label for="occ_${esc(k)}">${esc(TYPE_LABEL[k] || k)}</label><input id="occ_${esc(k)}" data-type="${esc(k)}" type="number" min="0" max="200" step="0.1" value="${esc(v)}">`).join("");
  $("occDialog").showModal();
}

/* ---------- wiring ---------- */
$("junction").onchange = () => openJunction($("junction").value);
/* Upload a video from this computer: it becomes a new junction, and the roads are found automatically. */
$("camBtn").onclick = async () => {
  let last = "";
  try { last = localStorage.getItem("rm_cam") || ""; } catch (_) { /* storage blocked */ }
  const link = (window.prompt(t("camAsk"), last) || "").trim();
  if (!link) return;
  try { localStorage.setItem("rm_cam", link); } catch (_) { /* private mode */ }
  const res = await fetch("/api/camera", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: link, name: link === "0" ? "Laptop webcam" : "Phone camera" }) });
  const out = await res.json();
  if (!res.ok) { toast(out.detail || "Error"); return; }
  const data = await (await fetch("/api/junctions")).json();
  $("junction").innerHTML = data.junctions.map((j) => `<option value="${esc(j.id)}">${esc(j.name)}</option>`).join("");
  $("junction").value = out.junction;
  openJunction(out.junction);
};
$("vidBtn").onclick = () => $("vidFile").click();
$("vidFile").onchange = () => {
  const f = $("vidFile").files[0];
  if (!f) return;
  const btn = $("vidBtn"), label = $("vidText");
  btn.disabled = true;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/api/upload?new_junction=true&name=${encodeURIComponent(f.name)}`);
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) label.textContent = `⬆ ${Math.round((e.loaded / e.total) * 100)}%`; };
  xhr.onload = async () => {
    btn.disabled = false; $("vidFile").value = ""; label.textContent = t("uploadVideo");
    let out = {};
    try { out = JSON.parse(xhr.responseText); } catch (_) { /* not JSON */ }
    if (xhr.status !== 200 || !out.junction) { alertBox(out.detail || "Upload failed"); return; }
    const data = await (await fetch("/api/junctions")).json();
    $("junction").innerHTML = data.junctions.map((j) => `<option value="${esc(j.id)}">${esc(j.name)}</option>`).join("");
    $("junction").value = out.junction;
    openJunction(out.junction);
  };
  xhr.onerror = () => { btn.disabled = false; label.textContent = t("uploadVideo"); alertBox("Upload failed"); };
  xhr.send(f);
};
function alertBox(msg) { const el = $("roads"); if (el) el.innerHTML = `<p class="small" style="color:#fca5a5">${esc(msg)}</p>`; }
$("langEn").onclick = () => { lang = "en"; applyI18n(); };
$("langBn").onclick = () => { lang = "bn"; applyI18n(); };
$("acceptBtn").onclick = () => decide("accept", state && state.advice && state.advice.top ? state.advice.top.delta : null, null);
$("overrideBtn").onclick = () => $("overrideForm").classList.toggle("show");
$("overrideForm").onsubmit = (e) => { e.preventDefault(); decide("override", parseInt($("ovSeconds").value, 10), $("ovReason").value); };
$("refreshBtn").onclick = () => fetch(`/api/advice/${encodeURIComponent(junctionId)}/refresh`, { method: "POST" });
$("speakBtn").onclick = speak;
$("emBtn").onclick = (e) => { e.stopPropagation(); const show = !$("emPop").classList.contains("show"); $("emPop").classList.toggle("show", show); $("emBtn").setAttribute("aria-expanded", String(show)); };
document.addEventListener("click", (e) => { if (!$("emPop").contains(e.target)) closePop(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closePop(); $("chatPanel").hidden = true; } });
$("emCancel").onclick = () => fetch(`/api/emergency/${encodeURIComponent(junctionId)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cancel: true }) });
$("occBtn").onclick = openOccupancy;
$("planBtn").onclick = (e) => { e.stopPropagation(); const show = $("chatPanel").hidden; $("chatPanel").hidden = !show; $("planBtn").setAttribute("aria-expanded", String(show)); if (show) $("chatInput").focus(); };
$("chatClose").onclick = () => { $("chatPanel").hidden = true; $("planBtn").setAttribute("aria-expanded", "false"); };
$("chatForm").onsubmit = (e) => { e.preventDefault(); askRoadmind($("chatInput").value); };
renderChatChips();
$("rainBtn").onclick = () => {
  const on = $("rainBtn").getAttribute("aria-pressed") !== "true";
  $("rainBtn").setAttribute("aria-pressed", String(on));
  fetch(`/api/rain/${encodeURIComponent(junctionId)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on }) });
};
$("occClose").onclick = () => $("occDialog").close();
$("logClose").onclick = () => $("logDialog").close();
$("occForm").onsubmit = async (e) => {
  e.preventDefault();
  const occupancy = {}; $("occGrid").querySelectorAll("input").forEach((i) => (occupancy[i.dataset.type] = parseFloat(i.value)));
  const res = await fetch(`/api/junctions/${encodeURIComponent(junctionId)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ occupancy }) });
  if (res.ok) { $("occDialog").close(); toast(lang === "bn" ? "সংরক্ষিত ✓" : "Saved ✓"); } else toast((await res.json()).detail);
};
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => {};
init();
