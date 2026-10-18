#!/usr/bin/env python3
"""
LSAT nag bot, GitHub Actions edition.
GitHub runs this file every ~5 minutes. Each run: read your Telegram replies,
decide if it should text you, then save its memory to state.json.
No pip installs needed.
"""
import json
import os
import random
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ---------------- CONFIG (edit these if you want) ----------------
TZ = ZoneInfo("America/New_York")   # change if you're in another timezone
MORNING_START = 8.0                 # first text of the day (8.0 = 8:00 AM)
MORNING_START_PUSH = 7.5            # earlier start the day after a non-morning day
MORNING_END = 12.0                  # "morning quota" deadline (noon)
LATE_START = 21.0                   # 9 PM: beauty sleep spam begins
BEDTIME_CUTOFF = 23.5               # 11:30 PM: bot stops and tells you to sleep
# ------------------------------------------------------------------

TOKEN = os.environ["BOT_TOKEN"]
STATE_FILE = "state.json"
now = datetime.now(TZ)

DEFAULT = {
    "offset": 0, "chat_id": None, "date": None,
    "done": False, "done_at": None, "last_sent": None,
    "snooze_until": None, "snoozes": 0, "snooze_over_pending": False,
    "nags": 0, "bonus": None, "bonus_pinged": False, "final_sent": False,
    "streak": 0, "last_done_date": None,
    "prev_status": "morning",  # how yesterday went: morning / late / none
}

# ---------------- MESSAGES ----------------
FIRST_NORMAL = [
    "gm future lawyer ☀️ lsat quota first, THEN the day. morning is the move. lmk when ur done",
    "yo good morning!! let's knock out {task} before the day gets busy 📚 reply 'done' when ur done",
    "rise and grind bestie. doing it in the morning makes ur whole day feel lighter. i'm rooting for u fr",
]
FIRST_PUSH_LATE = [
    "gm. yesterday u did it late and it was giving stress. today we do {task} FIRST thing. morning. u got this 🫡",
    "ok reminder: we want mornings. yesterday was an afternoon-or-later situation. let's fix it today, start now ☀️",
]
FIRST_PUSH_NONE = [
    "gm. yesterday's quota never happened and we're not gonna spiral, but TODAY it's {task} FIRST. morning. before anything else. i believe in u 🫡",
    "not mad just disappointed 🥲 jk but fr, yesterday didn't happen so today we lock in EARLY. {task}. now-ish.",
]
FIRST_SAT = [
    "it's SATURDAY which means mock exam day 📝 full timed, phone away, no pausing. morning is best while ur brain is fresh. tell me when ur done!",
    "saturday = mock exam. that's the whole mission today. start it this morning and the rest of ur weekend is free 🫡",
]
FIRST_SAT_PUSH = [
    "mock exam day 📝 and since the morning thing hasn't been happening, this one is getting done in the MORNING. no negotiating. u got this",
]
MORNING_NAG = [
    "hey it's still morning, literally the best time for {task}. let's go 🫡",
    "no pressure but also yes pressure. {task}. this morning. u'll thank me at 9pm",
    "ur morning window is closing!! start with one section, momentum does the rest",
]
AFTERNOON_NAG = [
    "ok the morning came and went 😭 but the day isn't over. do {task} before it gets late",
    "afternoon check-in: where we at with {task}? don't make me say 'told u so' at 9pm",
    "tomorrow morning we fix this, but for NOW let's just get it done. lock in 🔒",
]
EVENING_NAG = [
    "evening check: still haven't done {task}?? ur future self does NOT want to do this at 10pm trust me",
    "bestie it's evening. do it now and enjoy the rest of ur night 🌙",
    "not me being the only one invested in ur LSAT score rn 😤 do it. then relax",
]
LATE_NAG = [
    "it's past 9 😴 ur beauty sleep is on the line. even 30 min of lsat and then bed",
    "ok the clock is ticking and i want u well-rested. quota. now. then sleep 🫡",
    "late-night nudge: do the thing, say 'done', go to bed. easiest win of ur day",
    "ur pillow is waiting but the quota comes first. i'll shut up the second u say done",
]
AFTER_SNOOZE = [
    "snooze is OVER 🫡 whatever it was is done, so it's lsat time. let's go",
    "welcome back!! ur break is up. {task}. now. i believe in u",
]
FINAL = [
    "ok it's late and i want u to sleep 😴 no more pings tonight. but tomorrow it's MORNING first thing, no negotiating. gn 🫡",
    "alright i'm clocking out so u can rest. we're not doing this late again tho. tomorrow morning, first thing. gn bestie 🌙",
]

GENERIC = [
    "that's cute but is it 'done' tho? 🤨 reply 'done' when it's actually done",
    "mhm. and the LSAT? 👀",
    "i see u, but i need a status update: done or not done?",
]
NOT_YET = [
    "ok honesty is appreciated 🫡 now go do it and tell me when ur done",
    "fair. so what's the plan, because 'not yet' has an expiration date 😌",
]
TOMORROW = [
    "'tomorrow' is how we got here 😭 no. today. even 20 min of {task} counts",
    "tomorrow-u is already busy. do it today. even a lil bit. i believe in u",
]

# snooze replies: {dur} = how long, {task} = what u owe me
WD_CLASS = [
    "wait fr?? ...ok class is valid 🤨 go learn stuff. i'll check back in {dur}. when ur out, u OWE me {task}",
    "hmm convenient but i do know u have class 🙄 fine. {dur}. then we lock in",
]
WD_WORK = [
    "ok work is work 🫡 go get that bag. i'll leave u alone for {dur}, then it's lsat time",
    "skeptical but valid, u do have work sometimes. {dur} cool down, then u owe me {task}",
]
WD_LATER = [
    "'later' is doing a LOT of work rn 🤨 ...ok fine. {dur}. but then we're actually doing it",
    "mhm 'later'. i've heard that one. {dur}, then no more excuses",
]
WD_OUT = [
    "going out on a weekday?? ok i'll allow it but do 20 min BEFORE u leave or it's gonna be a late night 🫠 checking in in {dur}",
    "ok have fun but the lsat is not gonna do itself. {dur}. then home + lock in",
]
WE_CLASS = [
    "class on a WEEKEND?? 🧐 ok sure. i'm not buying it but ur getting {dur} max. then it's {task} no matter what",
    "nah. weekend class?? that's a stretch even for u. fine, {dur}. then u OWE me",
]
WE_WORK = [
    "work on the weekend... mhm 🙄 ok. {dur}, not a minute more. {task} is happening today",
    "weekends are the BEST time to study and ur telling me ur busy?? {dur}. then u're mine",
]
WE_LATER = [
    "'later' on a weekend?? u literally have nothing but time 😭 ok {dur}. that's it",
    "it's the weekend. 'later' is not a real answer. {dur}, then we start",
]
WE_OUT = [
    "going OUT?? u have time for that but not for the LSAT?? the audacity 😤 do 30 min BEFORE u leave. checking in in {dur}",
    "no ma'am. no sir. {task} comes before the fun. {dur} then u better report back",
]
SNOOZE_POOLS = {
    ("weekday", "class"): WD_CLASS, ("weekday", "work"): WD_WORK,
    ("weekday", "later"): WD_LATER, ("weekday", "out"): WD_OUT,
    ("weekend", "class"): WE_CLASS, ("weekend", "work"): WE_WORK,
    ("weekend", "later"): WE_LATER, ("weekend", "out"): WE_OUT,
}
LATE_CAP = [
    "it's past 9 so no long snoozes. 20 min, then we're locking in 😴 beauty sleep is calling",
]

DONE_MORNING = [
    "LETS GOOO ☀️ done before noon?? that's the move. {s}-day streak 🔥",
    "morning done = main character energy. {s}-day streak, i'm so proud",
]
DONE_LATER = [
    "ok slay, quota done 🫡 {s}-day streak. next time let's do it in the MORNING tho, deal?",
    "proud of u!! {s}-day streak. mornings next time tho, ur future self will thank u",
]
DONE_MOCK = [
    "MOCK EXAM DONE?? 📝 i'm actually so proud. {s}-day streak. review every wrong answer, that's where the points are",
]
BONUS_ASK = "if u have any energy left: can u squeeze in one more section or like 10 extra questions? no pressure if u really can't 🫶"
BONUS_ASK_MOCK = "bonus: can u review even a few of the ones u missed? no pressure if ur fried tho 🫶"
BONUS_ASK_LATE = "now go get that beauty sleep 😴"
BONUS_PING = [
    "hey 👀 still thinking about that bonus set. even one logic game before dinner? if ur really cooked it's ok, no stress",
]
BONUS_DECLINE = [
    "ok that's fair 🫶 rest is part of the plan too. proud of u. see u tomorrow",
]
BONUS_ACCEPT = [
    "ok SLAY, extra credit era 🔥 no need to report back, just crush it",
]
POST_DONE = [
    "👍 proud of u. go enjoy ur day",
    "u already did the thing 🫡 i'm good. go be a person",
]

# ---------------- REGEXES ----------------
DONE = r"\b(done|finished|completed|did it|crushed it|knocked it out)\b"
NEG = r"(\bnot\b|n't\b|\bnope\b|\bnever\b|\bhavent\b|\bdidnt\b|\bdont\b)"
FUTURE = r"\b(will|ill|i'll|gonna|going to|when|after|until|once|soon|about to|almost|nearly)\b"
OUT = r"\b(going out|go out|out tonight|party|partying|dinner|drinks|hanging out|hang out|brunch|date|plans|clubbing)\b"
CLASS = r"\b(class\w*|lecture|lab|midterm|seminar|recitation)\b"
WORK = r"(\bwork\b(?!\s+on)|\bshift\b|\bmy job\b|\bmeeting\b|\binternship\b)"
LATER = r"\b(later|wait|in a bit|in a min\w*|soon|hold on|one sec|give me|gimme|busy|after dinner|tonight|few hours)\b"
TMRW = r"\b(tomorrow|tmrw|tmr)\b"
DECLINE = r"(\bcan'?t\b|\bcant\b|\bno\b|\bnah\b|\bnope\b|\btired\b|\bexhausted\b|\bcooked\b|\bfried\b|\bdrained\b|\bpass\b|\bnext time\b|n't\b)"
ACCEPT = r"\b(ok|okay|yes|yeah|yep|yup|sure|bet|fine|will|lets go|let's go|i'll|ill)\b"

S = {}


# ---------------- HELPERS ----------------
def load():
    s = dict(DEFAULT)
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            s.update(json.load(f))
    return s


def save():
    with open(STATE_FILE, "w") as f:
        json.dump(S, f, indent=2)


def api(method, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def hour():
    return now.hour + now.minute / 60


def task():
    return "the mock exam" if now.weekday() == 5 else "the lsat quota"


def pick(pool, **kw):
    kw.setdefault("task", task())
    return random.choice(pool).format(**kw)


def send(text):
    api("sendMessage", chat_id=S["chat_id"], text=text)
    S["last_sent"] = now.isoformat()
    print("sent:", text)


def minutes_since_last():
    if not S["last_sent"]:
        return 9999
    return (now - datetime.fromisoformat(S["last_sent"])).total_seconds() / 60


def dur(mins):
    if mins >= 120:
        return f"{mins // 60} hours"
    if mins == 60:
        return "1 hour"
    return f"{mins} min"


def roll_day(today):
    """Called on the first run of a new day. Remembers how yesterday went."""
    if S["date"]:
        if S["done"]:
            hr = datetime.fromisoformat(S["done_at"]).hour
            S["prev_status"] = "morning" if hr < MORNING_END else "late"
        else:
            S["prev_status"] = "none"
    S.update(date=today.isoformat(), done=False, done_at=None, last_sent=None,
             snooze_until=None, snoozes=0, snooze_over_pending=False, nags=0,
             bonus=None, bonus_pinged=False, final_sent=False)


# ---------------- HANDLING YOUR REPLIES ----------------
def mark_done():
    yday = (now.date() - timedelta(days=1)).isoformat()
    S["streak"] = S["streak"] + 1 if S["last_done_date"] == yday else 1
    S["last_done_date"] = now.date().isoformat()
    S["done"], S["done_at"], S["snooze_until"] = True, now.isoformat(), None
    sat = now.weekday() == 5
    pool = DONE_MOCK if sat else (DONE_MORNING if hour() < MORNING_END else DONE_LATER)
    if hour() >= LATE_START:
        ask, S["bonus"] = BONUS_ASK_LATE, "declined"
    else:
        ask, S["bonus"] = (BONUS_ASK_MOCK if sat else BONUS_ASK), "asked"
    send(pick(pool, s=S["streak"]) + "\n\n" + ask)


def handle_after_done(t):
    if S["bonus"] == "asked":
        if re.search(DECLINE, t):
            S["bonus"] = "declined"
            return send(pick(BONUS_DECLINE))
        if re.search(ACCEPT, t):
            S["bonus"] = "accepted"
            return send(pick(BONUS_ACCEPT))
    send(pick(POST_DONE))


def excuse_kind(t):
    if re.search(TMRW, t):
        return "tomorrow"
    if re.search(OUT, t):
        return "out"
    if re.search(CLASS, t):
        return "class"
    if re.search(WORK, t):
        return "work"
    if re.search(LATER, t):
        return "later"
    return None


def snooze(kind):
    if kind == "tomorrow":
        return send(pick(TOMORROW))
    weekend = now.weekday() >= 5
    mins = 60 if (weekend or kind == "later") else 120
    if hour() >= LATE_START:
        mins = 20
        msg = pick(LATE_CAP)
    else:
        msg = pick(SNOOZE_POOLS[("weekend" if weekend else "weekday", kind)], dur=dur(mins))
    S["snoozes"] += 1
    if S["snoozes"] >= 3:
        msg += f" (that's snooze #{S['snoozes']} today btw. i'm counting 👀)"
    S["snooze_until"] = (now + timedelta(minutes=mins)).isoformat()
    S["snooze_over_pending"] = True
    send(msg)


def handle(raw):
    t = raw.lower().replace("’", "'")
    if S["done"]:
        return handle_after_done(t)
    negative = re.search(NEG, t) or re.search(FUTURE, t)
    if re.search(DONE, t) and not negative:
        return mark_done()
    kind = excuse_kind(t)
    if kind:
        return snooze(kind)
    if re.search(NEG, t):
        return send(pick(NOT_YET))
    send(pick(GENERIC))


# ---------------- PROACTIVE NAGGING ----------------
def maybe_nag():
    if S["chat_id"] is None:
        return
    h = hour()

    if S["done"]:
        if (S["bonus"] == "asked" and not S["bonus_pinged"]
                and 17 <= now.hour < 21 and minutes_since_last() >= 90):
            S["bonus_pinged"] = True
            send(pick(BONUS_PING))
        return

    if S["snooze_until"] and now < datetime.fromisoformat(S["snooze_until"]):
        return

    if h >= BEDTIME_CUTOFF:
        if not S["final_sent"]:
            S["final_sent"] = True
            send(pick(FINAL))
        return

    push = S["prev_status"] != "morning"
    if h < (MORNING_START_PUSH if push else MORNING_START):
        return

    if h < MORNING_END:
        gap, pool = (30 if push else 45), MORNING_NAG
    elif h < 18:
        gap, pool = 120, AFTERNOON_NAG
    elif h < LATE_START:
        gap, pool = 60, EVENING_NAG
    else:
        gap, pool = 20, LATE_NAG

    if minutes_since_last() < gap - 2:
        return

    sat = now.weekday() == 5
    if S["snooze_over_pending"]:
        pool = AFTER_SNOOZE
        S["snooze_over_pending"] = False
    elif S["nags"] == 0 and h < MORNING_END:
        if sat:
            pool = FIRST_SAT_PUSH if push else FIRST_SAT
        elif S["prev_status"] == "none":
            pool = FIRST_PUSH_NONE
        elif push:
            pool = FIRST_PUSH_LATE
        else:
            pool = FIRST_NORMAL

    S["nags"] += 1
    send(pick(pool))


# ---------------- MAIN ----------------
def main():
    global S
    S = load()
    today = now.date()
    if S["date"] != today.isoformat():
        roll_day(today)

    updates = api("getUpdates", offset=S["offset"], timeout=0).get("result", [])
    for u in updates:
        S["offset"] = u["update_id"] + 1
        m = u.get("message")
        if not m or "text" not in m:
            continue
        cid = m["chat"]["id"]
        if S["chat_id"] is None:  # first person to message the bot = you
            S["chat_id"] = cid
            send("locked in 🫡 i will now (lovingly) ruin ur excuses. reply 'done' when ur quota is done")
            continue
        if cid != S["chat_id"]:
            continue
        handle(m["text"])

    maybe_nag()
    save()


if __name__ == "__main__":
    main()
