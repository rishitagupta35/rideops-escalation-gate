"""
RideOps Escalation Gate (v0)
User: L1 support agent.
Goal: cut open tickets by getting three L1 decisions right:
  1. Before escalating  -> config checks + required info + known-issue warning
  2. When returned      -> fix engineering's reason before re-escalating
  3. Before closing     -> client confirmation where reopens are common
Data: rideops_support_tickets.csv (pulled 30 Sep 2026). All logic runs on this file.
"""
from datetime import timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import streamlit as st

import rules

st.set_page_config(page_title="RideOps Escalation Gate", page_icon="🚦", layout="wide")

DATA = Path(__file__).parent / "rideops_support_tickets.csv"
PULL_TIME = pd.Timestamp("2026-09-30 23:59")
RETURNED = ["Config issue - returned to L1", "Insufficient info - returned to L1"]
AVOIDABLE = RETURNED + ["Duplicate of known issue", "Not a bug - how-to", "Not reproducible"]
HOURS_PER_EXTRA_TRIP = 55  # from data: median close 59h (1 trip), 110h (2), 170h (3)


# ---------------------------------------------------------------- data (SQL via DuckDB)
@st.cache_resource
def get_con():
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE t AS
        SELECT *,
               regexp_replace(description, '[0-9]+', 'N', 'g') AS issue,
               escalated_to_eng = 'Yes'                         AS esc
        FROM read_csv_auto('{DATA.as_posix()}', timestampformat='%Y-%m-%d %H:%M')
    """)
    return con


def q(sql, params=None):
    cur = get_con().cursor()
    return cur.execute(sql, params or []).df()


@st.cache_data
def tickets():
    return q("SELECT * FROM t ORDER BY created_at")


def py(ts):
    return pd.Timestamp(ts).to_pydatetime()


def issue_history(issue, as_of):
    """Outcomes of past escalations of this issue that were closed before `as_of` (no peeking at the future)."""
    return q("""
        SELECT eng_outcome AS outcome, count(*) AS tickets
        FROM t
        WHERE issue = ? AND esc AND first_closed_at < ?
        GROUP BY 1 ORDER BY 2 DESC
    """, [issue, py(as_of)])


def known_issue_hits(issue, as_of, ticket_id):
    """Engineering-confirmed duplicates of this issue in the last N days before `as_of`."""
    return q(f"""
        SELECT ticket_id, client_name, eng_ticket_id, first_closed_at
        FROM t
        WHERE issue = ? AND ticket_id <> ?
          AND eng_outcome = 'Duplicate of known issue'
          AND first_closed_at <  ?
          AND first_closed_at >= ? - INTERVAL {rules.KNOWN_ISSUE_WINDOW_DAYS} DAY
        ORDER BY first_closed_at DESC
    """, [issue, ticket_id, py(as_of), py(as_of)])


def reopen_rate(col, value, as_of):
    r = q(f"""
        SELECT avg(CASE WHEN reopen_count > 0 THEN 1 ELSE 0 END) AS rate, count(*) AS n
        FROM t WHERE {col} = ? AND final_closed_at < ?
    """, [value, py(as_of)])
    return (None if r.n[0] == 0 else float(r.rate[0])), int(r.n[0])


# ---------------------------------------------------------------- queue logic
def next_action(row):
    if row.status == "Open - with Engineering":
        return "⏳ Waiting on engineering"
    if row.esc and row.eng_outcome == "Fixed":
        return "3️⃣ Eng fixed → confirm & close"
    if row.esc and pd.notna(row.eng_outcome):
        return "2️⃣ Returned by eng → fix reason"
    return "1️⃣ Work it (run pre-check before escalating)"


ACTION_ORDER = {"2️⃣ Returned by eng → fix reason": 0, "3️⃣ Eng fixed → confirm & close": 1,
                "1️⃣ Work it (run pre-check before escalating)": 2, "⏳ Waiting on engineering": 3}


def suggested_checkpoint(row):
    if row.status.startswith("Open"):
        a = next_action(row)
        return {"2": 2, "3": 3}.get(a[0], 1)
    return 1


# ---------------------------------------------------------------- session log
if "log" not in st.session_state:
    st.session_state.log = []


def log(action, ticket):
    st.session_state.log.append({"ticket": ticket, "action": action})


# ---------------------------------------------------------------- UI: header + sidebar
df = tickets()
st.title("🚦 RideOps Escalation Gate")
st.caption("For L1 support agents · runs on the RideOps ticket file (2 Jul – 30 Sep 2026) · "
           "checklists are assumptions, see rules.py")

agents = sorted(df.assigned_agent.unique())
with st.sidebar:
    st.header("Agent")
    agent = st.selectbox("I am", agents, key="agent", index=agents.index("Rahul T") if "Rahul T" in agents else 0)
    st.caption(f"Queue shown as of data pull: {PULL_TIME:%d %b %Y}")
    st.divider()
    st.subheader("Actions this session")
    log_box = st.empty()

tab_queue, tab_ws, tab_impact, tab_weekly, tab_about = st.tabs(
    ["📥 My queue", "🎫 Ticket workspace", "📉 Impact (backtest)", "📊 Weekly metrics", "ℹ️ How it works"])

# ---------------------------------------------------------------- TAB 1: queue
with tab_queue:
    mine = df[(df.assigned_agent == agent) & df.status.str.startswith("Open")].copy()
    mine["next_action"] = mine.apply(next_action, axis=1)
    mine["age_days"] = ((PULL_TIME - mine.created_at).dt.total_seconds() / 86400).round(1)
    mine["_o"] = mine.next_action.map(ACTION_ORDER)
    mine = mine.sort_values(["_o", "priority", "age_days"], ascending=[True, True, False])

    c1, c2, c3 = st.columns(3)
    c1.metric("My open tickets", len(mine))
    c2.metric("Returned by eng (act now)", int((mine._o == 0).sum()))
    c3.metric("Waiting on engineering", int((mine._o == 3).sum()))

    if mine.empty:
        st.info("No open tickets for this agent on 30 Sep.")
    else:
        st.dataframe(
            mine[["ticket_id", "next_action", "priority", "age_days", "client_name", "category",
                  "description", "eng_handoffs"]].rename(columns={"eng_handoffs": "trips_to_eng"}),
            hide_index=True)
        st.caption("Sorted: returned tickets first, then P1→P4, then oldest. "
                   "Open the ticket in the Ticket workspace tab.")

    st.divider()
    st.subheader("Whole team on 30 Sep")
    allopen = df[df.status.str.startswith("Open")].copy()
    allopen["next_action"] = allopen.apply(next_action, axis=1)
    st.dataframe(allopen.groupby("next_action").size().rename("tickets").reset_index(),
                 hide_index=True)
    st.caption("29 of the 48 open tickets sit with L1, not engineering.")

# ---------------------------------------------------------------- TAB 2: ticket workspace
with tab_ws:
    ids = df.ticket_id.tolist()
    left, right = st.columns([2, 3])
    with left:
        demo = {"SUP-11155 · checkpoint 1 · known report-email bug (real: duplicate)": ("SUP-11155", 1),
                "SUP-10012 · checkpoint 2 · config issue that went to eng 3×": ("SUP-10012", 2),
                "SUP-11291 · checkpoint 2 · open today, returned as config": ("SUP-11291", 2),
                "SUP-10666 · checkpoint 3 · GPS ticket closed early, reopened 2×": ("SUP-10666", 3),
                "Pick any ticket…": (None, None)}
        choice = st.selectbox("Demo ticket", list(demo), key="demo")
        tid, demo_cp = demo[choice]
        if tid is None:
            tid = st.selectbox("Ticket ID", ids, index=ids.index("SUP-10012"), key="pick")
    row = df[df.ticket_id == tid].iloc[0]

    with right:
        cp = st.radio("Checkpoint", [1, 2, 3], index=(demo_cp or suggested_checkpoint(row)) - 1, horizontal=True,
                      format_func=lambda x: {1: "1 · Before escalating", 2: "2 · Returned by eng",
                                             3: "3 · Before closing"}[x])

    with st.container(border=True):
        a, b, c, d = st.columns(4)
        a.markdown(f"**{row.ticket_id}** · {row.priority}")
        b.markdown(f"{row.client_name} ({row.client_tier})")
        c.markdown(f"Agent: {row.assigned_agent}")
        d.markdown(f"Raised {row.created_at:%d %b %H:%M} via {row.channel}")
        st.markdown(f"**{row.category}** — {row.description}")
        st.caption(f"Demo only, hidden in real use. What actually happened: trips to eng = {row.eng_handoffs}, "
                   f"outcome = {row.eng_outcome if pd.notna(row.eng_outcome) else 'not escalated'}, "
                   f"status = {row.status}, reopens = {row.reopen_count}")

    as_of = row.created_at  # replay: the tool only sees data that existed when the ticket came in
    required = rules.REQUIRED_INFO.get(row.category, [])
    cfg = rules.CONFIG_CHECKS.get(row.issue)

    def history_panel():
        h = issue_history(row.issue, as_of)
        if h.empty:
            st.info("No past escalations of this issue yet (data starts 2 Jul).")
            return
        total = int(h.tickets.sum())
        bounced = int(h[h.outcome.isin(AVOIDABLE)].tickets.sum())
        st.markdown(f"**Past escalations of this issue (before this ticket): {total}** — "
                    f"**{bounced} ({bounced/total:.0%})** were not engineering work")
        st.dataframe(h, hide_index=True)

    def info_fields(key):
        vals = [st.text_input(f, key=f"{key}-{i}") for i, f in enumerate(required)]
        return all(v.strip() for v in vals), dict(zip(required, vals))

    # ----- Checkpoint 1
    if cp == 1:
        st.subheader("1 · Before escalating")
        col1, col2 = st.columns(2)
        with col1:
            history_panel()
            hits = known_issue_hits(row.issue, as_of, row.ticket_id)
            if not hits.empty:
                st.warning(f"⚠️ Engineering marked this issue as a **duplicate of a known bug** "
                           f"{len(hits)}× in the last {rules.KNOWN_ISSUE_WINDOW_DAYS} days. "
                           "Check with engineering whether it's the same bug before raising a new ticket.")
                st.dataframe(hits, hide_index=True)
                st.caption("Warning only, not a block: in backtest this rule caught 32 of 56 duplicates "
                           "but also fired on 53 real bugs.")
            else:
                st.success("No engineering-confirmed duplicate of this issue in the last 30 days.")
        with col2:
            cfg_done = True
            if cfg:
                st.markdown("**Config checks (suggested, ~3 min)**")
                cfg_done = all([st.checkbox(c, key=f"c1-{tid}-{i}") for i, c in enumerate(cfg["checks"])])
                result = st.text_input("Result of checks", key=f"c1r-{tid}")
                cfg_done = cfg_done and bool(result.strip())
            else:
                st.caption("No config checklist for this issue (config is rarely the cause).")
            st.markdown("**Required info for engineering**")
            info_ok, info = info_fields(f"c1i-{tid}")

        st.divider()
        b1, b2, b3 = st.columns(3)
        if b1.button("✅ Fixed at L1 → go to closure check", key=f"fix1-{tid}"):
            log("Fixed at L1 (no escalation)", tid); st.success("Logged. Run checkpoint 3 before closing.")
        if b2.button("👤 Client must change setting", key=f"cli1-{tid}",
                     disabled=not (cfg and cfg["client_side"])):
            log("Sent steps to client admin", tid)
            st.info("Logged. Message for the client admin:")
            st.code(f"Hi, we checked {row.description.lower()}. It's caused by a setting in your "
                    f"account. Please do the following: " + "; ".join(cfg["checks"]) +
                    ". Reply here once done and we'll confirm it's working.")
        can_escalate = cfg_done and info_ok
        if b3.button("🔁 Escalate to engineering", key=f"esc1-{tid}", disabled=not can_escalate, type="primary"):
            log("Escalated with full package", tid)
            st.success("Escalation package created:")
            st.code("\n".join([f"[{row.ticket_id}] {row.priority} · {row.client_name}",
                               f"Issue: {row.description}"] +
                              [f"{k}: {v}" for k, v in info.items()] +
                              ([f"Config checks done: {', '.join(cfg['checks'])}"] if cfg else [])))
        if not can_escalate:
            st.caption("🔒 Escalate unlocks when the config checks are ticked (with a result) "
                       "and every required field is filled.")

    # ----- Checkpoint 2
    elif cp == 2:
        st.subheader("2 · Returned by engineering")
        verdict = row.eng_outcome if pd.notna(row.eng_outcome) else None
        if verdict is None or verdict == "Fixed":
            st.info("This ticket was not returned by engineering. Pick checkpoint 1 or 3, or a returned ticket "
                    "(e.g. SUP-10012).")
        else:
            trips = int(row.eng_handoffs)
            st.error(f"**Engineering verdict:** {verdict}")
            st.markdown(f"**What to do:** {rules.RETURN_ACTIONS.get(verdict, '')}")
            st.caption(f"This ticket went to engineering {trips}× in real life. Each extra trip ≈ "
                       f"+{HOURS_PER_EXTRA_TRIP}h for the client. The specific reason text is not in "
                       "today's data; in rollout engineering fills a short return form.")
            col1, col2 = st.columns(2)
            with col1:
                history_panel()
            with col2:
                done = True
                if verdict == "Config issue - returned to L1":
                    checks = cfg["checks"] if cfg else ["Check the client settings related to this issue"]
                    done = all([st.checkbox(c, key=f"c2-{tid}-{i}") for i, c in enumerate(checks)])
                    res = st.text_input("Result of checks", key=f"c2r-{tid}")
                    done = done and bool(res.strip())
                elif verdict in ("Insufficient info - returned to L1", "Not reproducible"):
                    if verdict == "Not reproducible":
                        done = st.checkbox("Confirmed with client it is still happening", key=f"c2s-{tid}")
                    ok, _ = info_fields(f"c2i-{tid}")
                    done = done and ok
                why = st.text_area("Why is this still an engineering issue?", key=f"why-{tid}")

            st.divider()
            b1, b2 = st.columns(2)
            if b1.button("✅ Resolved at L1 → closure check", key=f"fix2-{tid}"):
                log(f"Resolved at L1 after return ({verdict})", tid); st.success("Logged. Run checkpoint 3.")
            blocked = verdict in ("Duplicate of known issue", "Not a bug - how-to")
            can_re = done and bool(why.strip()) and not blocked
            if b2.button("🔁 Re-escalate", key=f"re2-{tid}", disabled=not can_re, type="primary"):
                log("Re-escalated with evidence", tid); st.success("Re-escalated with evidence.")
            if blocked:
                st.caption("🔒 Re-escalation is not allowed for this verdict.")
            elif not can_re:
                st.caption("🔒 Re-escalate unlocks when engineering's reason is addressed and you explain "
                           "why it's still a bug.")

    # ----- Checkpoint 3
    else:
        st.subheader("3 · Before closing")
        cat_rate, cat_n = reopen_rate("category", row.category, as_of)
        ag_rate, ag_n = reopen_rate("assigned_agent", row.assigned_agent, as_of)
        need = ((cat_rate or 0) > rules.CATEGORY_REOPEN_THRESHOLD) or ((ag_rate or 0) > rules.AGENT_REOPEN_THRESHOLD)
        m1, m2 = st.columns(2)
        m1.metric(f"Reopen rate · {row.category}", "—" if cat_rate is None else f"{cat_rate:.0%}",
                  help=f"Based on {cat_n} tickets closed before this ticket was raised")
        m2.metric(f"Reopen rate · {row.assigned_agent}", "—" if ag_rate is None else f"{ag_rate:.0%}",
                  help=f"Based on {ag_n} tickets closed before this ticket was raised")
        note = st.text_input("What was done to resolve it?", key=f"c3n-{tid}")
        conf = True
        if need:
            st.warning("Reopens are common here. Get the client to confirm it's fixed before closing.")
            st.code(f"Hi, we've fixed {row.description.lower()}. Could you confirm it's working on your side? "
                    "We'll close the ticket once you confirm.")
            conf = st.checkbox("Client confirmed it's fixed", key=f"c3c-{tid}")
        else:
            st.success("Low reopen risk. You can close once the resolution note is filled.")
        if st.button("Close ticket", key=f"close-{tid}", disabled=not (conf and note.strip()), type="primary"):
            log("Closed" + (" after client confirmation" if need else ""), tid)
            st.success("Closed and logged.")

# ---------------------------------------------------------------- TAB 3: impact (backtest)
@st.cache_data
def sim_inputs():
    d = tickets().copy()
    t0 = pd.Timestamp("2026-07-01")
    hrs = lambda s: (s - t0).dt.total_seconds() / 3600
    cr = hrs(d.created_at).values
    cl = hrs(d.final_closed_at).fillna(np.inf).values
    fc = hrs(d.first_closed_at).fillna(np.inf).values
    end = (PULL_TIME - t0).total_seconds() / 3600
    sep = np.arange((pd.Timestamp("2026-09-01") - t0).total_seconds() / 3600, end, 1.0)
    l1_med = d[~d.esc & d.final_closed_at.notna()].assign(
        h=lambda x: (x.final_closed_at - x.created_at).dt.total_seconds() / 3600
    ).groupby("category").h.median()
    one_trip = d[(d.eng_handoffs == 1) & d.final_closed_at.notna()].pipe(
        lambda x: ((x.final_closed_at - x.created_at).dt.total_seconds() / 3600).median())
    elapsed = np.minimum(cl, end) - cr
    ho = d.eng_handoffs.values
    out = d.eng_outcome
    l1 = d.category.map(l1_med).values
    # Checkpoint 1: config/how-to/duplicate resolved at normal L1 speed; info/not-repro go once, clean
    cfgish = out.isin(["Config issue - returned to L1", "Not a bug - how-to", "Duplicate of known issue"]).values
    infoish = out.isin(["Insufficient info - returned to L1", "Not reproducible"]).values
    cp1 = np.where(cfgish, cr + l1, np.where(infoish, cr + one_trip, np.inf))
    # Checkpoint 2: remove repeat trips (~55h each), never below a clean one-trip time
    cp2 = np.where(ho >= 2, cr + np.maximum(elapsed - (ho - 1) * HOURS_PER_EXTRA_TRIP, one_trip), np.inf)
    # Checkpoint 3: no reopen -> ticket ends at first close
    cp3 = np.where(d.reopen_count.values > 0, fc, np.inf)
    issues = d.issue.values
    sep_mask = (d.created_at >= "2026-09-01").values
    return dict(cr=cr, cl=cl, end=end, sep=sep, cp1=cp1, cp2=cp2, cp3=cp3,
                issues=issues, sep_mask=sep_mask, one_trip=one_trip)


def open_metrics(cr, cl, end, sep):
    cr_s, cl_s = np.sort(cr), np.sort(cl)
    count = lambda t: np.searchsorted(cr_s, t, "right") - np.searchsorted(cl_s, t, "right")
    return int(count(end)), float(np.mean(count(sep)))


@st.cache_data
def bug_ranking():
    """Issues ranked by how much they add to September's average open count."""
    S = sim_inputs()
    _, base = open_metrics(S["cr"], S["cl"], S["end"], S["sep"])
    contrib = {}
    for iss in pd.unique(S["issues"]):
        m = (S["issues"] == iss) & S["sep_mask"]
        c0 = S["cl"].copy(); c0[m] = S["cr"][m]
        contrib[iss] = base - open_metrics(S["cr"], c0, S["end"], S["sep"])[1]
    return sorted(contrib, key=contrib.get, reverse=True)


with tab_impact:
    S = sim_inputs()
    st.subheader("If agents had used the gate in Jul–Sep, how many tickets would have been open?")
    st.caption("Replays the real tickets with the checkpoints applied. Open count = tickets created minus "
               "tickets closed at each hour of September.")
    c1, c2, c3 = st.columns(3)
    use1 = c1.checkbox("Checkpoint 1 (before escalating)", True)
    use2 = c2.checkbox("Checkpoint 2 (when returned)", True)
    use3 = c3.checkbox("Checkpoint 3 (before closing)", True)
    adoption = st.slider("Adoption: % of eligible tickets where agents follow the gate", 0, 100, 50, 5)
    bugs = st.slider("Engineering lever: top recurring issues fixed from 1 Sep (removes their Sep tickets)", 0, 5, 0)

    base_snap, base_avg = open_metrics(S["cr"], S["cl"], S["end"], S["sep"])
    new = S["cl"].copy()
    best = np.full_like(new, np.inf)
    if use1: best = np.minimum(best, S["cp1"])
    if use2: best = np.minimum(best, S["cp2"])
    if use3: best = np.minimum(best, S["cp3"])
    eligible = best < new
    rng = np.random.default_rng(7)
    runs = []
    for _ in range(20):
        pick = eligible & (rng.random(len(new)) < adoption / 100)
        c = new.copy(); c[pick] = best[pick]
        if bugs:
            top = bug_ranking()[:bugs]
            m = np.isin(S["issues"], top) & S["sep_mask"]
            c[m] = S["cr"][m]
        runs.append(open_metrics(S["cr"], c, S["end"], S["sep"]))
        if adoption in (0, 100):
            break
    snap = np.mean([r[0] for r in runs]); avg = np.mean([r[1] for r in runs])

    m1, m2, m3 = st.columns(3)
    m1.metric("Avg open tickets in Sep", f"{avg:.1f}", f"{avg - base_avg:+.1f} vs actual {base_avg:.1f}",
              delta_color="inverse")
    m2.metric("Open on 30 Sep", f"{snap:.0f}", f"{snap - base_snap:+.0f} vs actual {base_snap}",
              delta_color="inverse")
    m3.metric("Cut in avg open", f"{1 - avg / base_avg:.0%}")
    if bugs:
        st.caption(f"Top {bugs} issue(s) fixed: " + ", ".join(top))

    st.markdown("**Assumptions (say these out loud in the demo)**")
    st.markdown(f"""
- Checkpoint 1: config, how-to and duplicate escalations are resolved at normal L1 speed for that category;
  insufficient-info / not-reproducible tickets go to engineering once, with the right info (median one-trip time
  ≈ {S['one_trip']:.0f}h).
- Checkpoint 2: each avoided repeat trip saves ≈ {HOURS_PER_EXTRA_TRIP}h (from the 59h → 110h → 170h staircase).
- Checkpoint 3: a ticket that was reopened would have ended at its first close (upper bound).
- Adoption picks a random share of eligible tickets (average of 20 runs).
- Bug fixes assume every September ticket with that description disappears (upper bound: some are config).
- The data has no engineering-side timestamps, so time saved is estimated, not measured.
""")

    with st.expander("Known-issue warning: how accurate is it? (backtest)"):
        kb = q(f"""
            WITH e AS (SELECT * FROM t WHERE esc),
            f AS (
              SELECT a.ticket_id, a.eng_outcome AS actual,
                     count(b.ticket_id) FILTER (WHERE b.eng_outcome = 'Duplicate of known issue'
                        AND b.first_closed_at <  a.created_at
                        AND b.first_closed_at >= a.created_at - INTERVAL {rules.KNOWN_ISSUE_WINDOW_DAYS} DAY) AS hits
              FROM e a LEFT JOIN e b ON a.issue = b.issue AND a.ticket_id <> b.ticket_id
              GROUP BY ALL)
            SELECT actual AS real_outcome, count(*) FILTER (WHERE hits > 0) AS warned, count(*) AS escalations
            FROM f GROUP BY 1 ORDER BY 3 DESC""")
        st.dataframe(kb, hide_index=True)
        st.caption("It warns on most duplicates but also on many real bugs. That's why it is a warning, not a block.")

# ---------------------------------------------------------------- TAB 4: weekly metrics
with tab_weekly:
    st.subheader("Success measures, week by week")
    w = q("""
        SELECT date_trunc('week', created_at)::DATE AS week,
               count(*)                                                     AS tickets,
               count(*) FILTER (WHERE esc)                                  AS escalations,
               sum(eng_handoffs)                                            AS trips_to_eng,
               count(*) FILTER (WHERE eng_outcome IN ('Config issue - returned to L1',
                                                      'Insufficient info - returned to L1')) AS sent_back,
               count(*) FILTER (WHERE eng_outcome = 'Duplicate of known issue') AS duplicates,
               avg(CASE WHEN reopen_count > 0 THEN 1.0 ELSE 0 END)          AS reopen_rate
        FROM t GROUP BY 1 ORDER BY 1""")
    w["week"] = pd.to_datetime(w.week).dt.date
    w["pct_sent_back"] = (100 * w.sent_back / w.escalations).round(1)
    w["sent_back_4wk_rolling"] = (100 * w.sent_back.rolling(4, min_periods=4).sum()
                                  / w.escalations.rolling(4, min_periods=4).sum()).round(1)
    w["target"] = 25.0
    w["repeat_trips"] = w.trips_to_eng - w.escalations
    w["reopen_rate"] = (100 * w.reopen_rate).round(1)
    ns = lambda x: pd.to_datetime(x).astype("datetime64[ns]").values
    cr_s = np.sort(ns(df.created_at))
    cl_s = np.sort(ns(df.final_closed_at.fillna(pd.Timestamp("2100-01-01"))))
    ends = ns(pd.to_datetime(w.week) + timedelta(days=7))
    w["open_at_week_end"] = np.searchsorted(cr_s, ends, "right") - np.searchsorted(cl_s, ends, "right")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Main metric: % of escalations sent back (config + missing info)**")
        st.line_chart(w.set_index("week")[["pct_sent_back", "sent_back_4wk_rolling", "target"]])
        st.caption("Weekly values swing a lot, so the decision uses the 4-week rolling line against the 25% target.")
    with c2:
        st.markdown("**Outcome: open tickets at week end**")
        st.line_chart(w.set_index("week")[["open_at_week_end"]])
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**Repeat trips to engineering and duplicates**")
        st.line_chart(w.set_index("week")[["repeat_trips", "duplicates"]])
    with c4:
        st.markdown("**Guardrail: reopen rate (%)**")
        st.line_chart(w.set_index("week")[["reopen_rate"]])
    st.dataframe(w[["week", "tickets", "escalations", "pct_sent_back", "sent_back_4wk_rolling", "repeat_trips",
                    "duplicates", "reopen_rate", "open_at_week_end"]].rename(columns={"week": "week_starting"}),
                 hide_index=True)
    st.caption("Weeks start on Monday and are grouped by ticket creation date, so the first week (29 Jun) is partial. "
               "The last 1–2 weeks are incomplete: some of those tickets were still open on 30 Sep, so their "
               "outcomes aren't final.")
    st.info("Leading metric, % of escalations that went through the gate (target ≥ 80%), starts with the pilot. "
            "There is no history for it in this data.")

# ---------------------------------------------------------------- TAB 5: about
with tab_about:
    st.markdown("""
### What this is
An internal tool for **L1 support agents** at RideOps. It puts a short check at the three moments where tickets
go wrong today:

| Checkpoint | When | What it does | Problem in the data |
|---|---|---|---|
| 1 · Before escalating | Agent is about to escalate | Config checks for the issue, required info for engineering, known-issue warning | 275 of 486 escalations (57%) were not engineering work |
| 2 · Returned by eng | Engineering sends it back | Shows the verdict; re-escalation locked until it's addressed | 291 of 777 trips to engineering were repeats |
| 3 · Before closing | Agent is about to close | Client confirmation where reopens are common | 151 tickets reopened; one agent caused 42% of them |

### How it uses the data
- All logic is SQL (DuckDB) on `rideops_support_tickets.csv`.
- Issue history and reopen rates only use tickets **closed before** the ticket was raised, so a replayed ticket
  never "sees the future".
- Checklists in `rules.py` are **assumptions** written from the ticket descriptions. They should be owned by the
  support lead and engineering manager.

### What it deliberately does not do
- No AI / text classification (descriptions are templated; rules are easier to trust and explain).
- No integration with a real ticketing tool, no logins.
- Doesn't fix the bugs themselves. The weekly metrics and the "engineering lever" in the Impact tab show why the
  top recurring issues should go to engineering's backlog.
""")


# ---------------------------------------------------------------- sidebar log (rendered last so clicks show)
with log_box.container():
    if st.session_state.log:
        st.dataframe(pd.DataFrame(st.session_state.log), hide_index=True)
    else:
        st.caption("Nothing yet. Actions you take in the Ticket workspace show here.")
