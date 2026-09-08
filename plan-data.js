// Shared plan data — single source of truth for road-to-13.html and week.html
// so plan targets/details never drift out of sync between pages again.

const PLAN_ID = 'road-to-13';
const PLAN_NAME = 'Road to 13';
const GOAL_DATE = '2026-11-01';

const planWeeks = [{"week":"2026-08-17","total":12,"long":6},{"week":"2026-08-24","total":23.5,"long":10},{"week":"2026-08-31","total":23.5,"long":11},{"week":"2026-09-07","total":11,"long":3.1},{"week":"2026-09-14","total":22,"long":10},{"week":"2026-09-21","total":26,"long":13},{"week":"2026-09-28","total":20,"long":9},{"week":"2026-10-05","total":30,"long":12},{"week":"2026-10-12","total":28.5,"long":13},{"week":"2026-10-19","total":22,"long":10},{"week":"2026-10-26","total":29.5,"long":13},{"week":"2026-11-02","total":25,"long":13}];

const PLAN_DETAILS = {
  "2026-08-17": { longRun:"6 mi easy", tempo:"Skip — travel week", easy:"2 short runs (3–4 mi), fit around travel", note:"Priority is just not losing the habit. Don't stress about pace." },
  "2026-08-24": { longRun:"10 mi", tempo:"~5.5 mi total — 1mi warmup, 3×1mi @ 8:45–9:00/mi w/ 400m jog recovery between reps, 1mi cooldown", easy:"2 runs, 4–5 mi, easy", note:"Back to normal routine." },
  "2026-08-31": { longRun:"11 mi", tempo:"~4.3 mi total — 1mi warmup, 20 min tempo @ 8:45/mi (~2.3mi), 1mi cooldown", easy:"2 runs, 4–5 mi, easy" },
  "2026-09-07": { longRun:"None this week — the race is the effort (see Tempo/Speed). Optional easy 2mi shakeout Sunday.", tempo:"5K RACE (3.1 mi) — Saturday 9/12. This is the week's hard effort.", easy:"2 easy runs (3–4 mi) early week (Mon/Tue), light taper", note:"Taper early in the week, race Saturday, recover Sunday, back to normal volume next week." },
  "2026-09-14": { longRun:"10 mi — easing back in, should feel recovered by now", tempo:"~4 mi total — 1mi warmup, 15 min @ moderate effort informed by 5K result, 1mi cooldown", easy:"2 runs, 4–5 mi, easy", note:"First week back to full volume after the race. Resume structured tempo work here." },
  "2026-09-21": { longRun:"13 mi — first time at goal distance, go slow, just finish", tempo:"~5 mi total — 1mi warmup, 25 min tempo @ pace informed by 5K result (~3mi), 1mi cooldown", easy:"2 runs, 4–5 mi, easy" },
  "2026-09-28": { longRun:"9 mi", tempo:"3 mi easy, no hard effort", easy:"2 runs, 4 mi, easy", note:"Cutback week." },
  "2026-10-05": { longRun:"12 mi", tempo:"~8 mi total — 1mi warmup, 5×1mi @ 8:15/mi w/ 400m jog recovery between reps, 1mi cooldown", easy:"2 runs, 5 mi, easy" },
  "2026-10-12": { longRun:"13 mi", tempo:"~5.5 mi total — 1mi warmup, 30 min tempo @ 8:15/mi (~3.6mi), 1mi cooldown", easy:"2 runs, 5 mi, easy" },
  "2026-10-19": { longRun:"10 mi", tempo:"4 mi easy", easy:"2 runs, 4 mi, easy", note:"Cutback week." },
  "2026-10-26": { longRun:"13 mi, last 3 mi @ 8:00–8:15/mi", tempo:"~6.3 mi total — 1mi warmup, 6×800m @ 7:50/mi w/ 400m jog recovery between reps, 1mi cooldown", easy:"2 runs, 5 mi, easy", note:"Combining endurance work with goal pace." },
  "2026-11-02": { longRun:"13 mi, aim for overall pace under 9:00/mi", tempo:"4 mi easy", easy:"2 runs, 4–5 mi, easy", note:"Goal week — should feel stronger than the first 13-miler in September." }
};

// Race marker used by the Long Run Progression chart on road-to-13.html
const RACE_WEEK = '2026-09-07';
