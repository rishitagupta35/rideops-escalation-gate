# RideOps Escalation Gate (v0)

An internal tool for **L1 support agents** at RideOps. It adds a short check at the three moments where tickets go wrong today, so fewer tickets bounce between L1 and engineering and fewer get reopened.

| Checkpoint | When | What it does | Problem in the data (Jul–Sep 2026) |
|---|---|---|---|
| 1 · Before escalating | Agent is about to escalate | Config checks for the issue, required info for engineering, known-issue warning | 275 of 486 escalations (57%) were not engineering work |
| 2 · Returned by eng | Engineering sends it back | Shows the verdict; re-escalation is locked until it's addressed | 291 of 777 trips to engineering were repeats |
| 3 · Before closing | Agent is about to close | Client confirmation where reopens are common | 151 tickets reopened; one agent caused 42% of them |

## What's in the app

**Primary user: the L1 agent.** The support lead gets one secondary view.

1. **Start here**: the problem, the three checkpoints and the replay impact on one screen, plus a 5-minute demo path.
2. **Agent · My queue**: an agent's open tickets on 30 Sep, sorted so returned tickets come first, then P1→P4, then oldest.
3. **Agent · Ticket workspace**: runs the checkpoint for any ticket. Buttons stay locked until the checks are done.
4. **Lead · Monday review**: (1) the success measures week by week, with the 4-week rolling sent-back rate against the 25% target; (2) recurring issues ranked by the open time they added, for a weekly top-5 review with engineering (the lever on incoming volume); (3) clients at risk this month, for the account managers.
5. **Impact (backtest)**: replays Jul–Sep with the checkpoints applied. You can change the adoption %, the hours saved per avoided trip (40–70 h) and switch on bug fixes.
6. **How it works**: summary and assumptions.

## Key results (from the Impact tab)

| Scenario | Avg open tickets in Sep (actual 42.7) | Cut |
|---|---|---|
| All 3 checkpoints, 50% adoption | ~33 | ~23% |
| All 3 checkpoints, 100% adoption | ~23.5 | ~45% |
| All 3 checkpoints, 100% + top 3 bugs fixed | ~20.4 | ~52% |

These are simulations with stated assumptions (see the Impact tab), not measured results. The result barely depends on the hours-per-trip estimate: at 50% adoption it stays at 22–23% for anything from 40 h to 70 h, because most of the gain comes from checkpoint 1.

## How to run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```
Then open the URL it prints (usually http://localhost:8501).

## How to put it on a shareable link (Streamlit Community Cloud)

1. Create a free GitHub account if you don't have one, then a new **public** repository.
2. Upload these files to the repo: `app.py`, `rules.py`, `requirements.txt`, `rideops_support_tickets.csv`, `README.md`.
3. Go to Streamlit Community Cloud, sign in with GitHub, click **Create app**, pick the repo, branch `main`, main file `app.py`, and deploy.
4. Copy the app URL into your submission email.

(Check Streamlit's current terms. If hosting gives trouble, the brief also accepts a repo with this readme.)

## Files

| File | What it is |
|---|---|
| `app.py` | The app. All data logic is SQL run with DuckDB on the CSV. |
| `rules.py` | Checklists (config checks, required info, return actions, thresholds). **These are assumptions** written from the ticket descriptions, meant to be owned by the support lead and engineering manager. |
| `rideops_support_tickets.csv` | The ticket data provided with the case. |

## Design choices

- **No peeking at the future.** When the tool replays an old ticket, issue history and reopen rates only use tickets closed *before* that ticket was raised.
- **Known-issue check is a warning, not a block.** In backtest it flagged 32 of 56 duplicates but also 53 real bugs, because the same description can be a new bug or an old one.
- **Rules, not AI.** Ticket descriptions are templated, so simple rules work, are easy to explain, and are easy for the support lead to edit.

## Known limitations

- The data records only the type of engineering verdict (e.g. "Config issue"), not the specific reason. In a real rollout, engineering would fill a short structured return form.
- No engineering-side timestamps, so time saved is estimated (~55h per avoided repeat trip, from the data's staircase of 59h → 110h → 170h).
- Checkpoint 1's "required info" step can't be backtested, because the data doesn't record what info agents included. It needs a live pilot.
- Not connected to a real ticketing tool; actions are logged only for the session.

## 5-minute demo script

0. **Start here**: the problem and impact in one screen (30 seconds).
1. **My queue** (Rahul T): 6 open tickets, 2 returned by engineering at the top.
2. **SUP-11155** (checkpoint 1): a report-email ticket. History shows 73% of past escalations of this issue weren't engineering work, and the known-issue warning fires. In real life it was escalated anyway and came back as a duplicate.
3. **SUP-10012** (checkpoint 2): config issue that went to engineering 3 times (~5.5 days). Show the re-escalate button locked until the config checks and the "why still a bug" note are done.
4. **SUP-10666** (checkpoint 3): GPS ticket closed early and reopened twice. Show the client-confirmation requirement.
5. **Impact tab**: 50% adoption → ~23% fewer open tickets; 100% → ~45%; add top 3 bug fixes → ~52%.
6. **Lead · Monday review**: the success measure, the bugs to send to engineering, and the 23 clients at risk (16 of 36 Enterprise clients).
