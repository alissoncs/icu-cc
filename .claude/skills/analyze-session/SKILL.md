---
name: analyze-session
description: Read one activity from Intervals.icu and give a coaching read on it — what the session actually was, whether it did what it was supposed to, and what it says about fitness, pacing, durability and fueling. Use when the user asks about a specific ride ("how was yesterday", "look at my Saturday ride", "analyse activity 12345").
---

# Analyze a session

Turn one activity into the read a coach would give: what happened, what it means, what to
do about it. Numbers come from the library so they are consistent; the judgement is yours.

## 1. Get the activity

If the user named an activity ID, use `get_activity_details`. Otherwise use
`get_activities` with a small `limit` to find the ride they mean, then fetch its details.

Then pull the two things that carry most of the insight and are easy to forget:

- `get_activity_intervals` — how the intended intervals actually went, rep by rep. Fading
  power across a set is the single most informative thing in a workout file.
- `get_activity_streams` — only when you need something the summary lacks (a specific
  climb, a pacing question, where exactly HR drifted).

## 2. Put the numbers into the analyser

The MCP tools return formatted text, not JSON. Read the values out of that text and write
them into a JSON file in your scratchpad, then run the analyser:

```bash
cat > /tmp/.../activity.json <<'JSON'
{
  "name": "...", "type": "Ride", "start_date_local": "...",
  "moving_time": 12600,
  "icu_average_watts": 178, "icu_weighted_avg_watts": 196,
  "average_heartrate": 141, "max_heartrate": 172,
  "icu_training_load": 215, "icu_ftp": 250, "icu_power_hr": 11.4,
  "distance": 104300, "total_elevation_gain": 1420,
  "icu_zone_times": {"Z1": 900, "Z2": 5400, "Z3": 4200, "Z4": 1500, "Z5": 480}
}
JSON

.venv/bin/coach session /tmp/.../activity.json --tsb -18
```

Include every field you actually found — the analyser derives IF, TSS, VI and EF when they
are absent, and records what was missing so you can be honest about the gaps. Pass `--tsb`
when you know the form the rider carried in; it changes how a hard session should be read.

## 3. Write the read

Structure it as: **what this session was → how it went → what it tells us → what to do**.

Rules that keep this useful rather than flattering:

- **Compare to intent.** A 45-minute tempo block is a good session or a failed endurance
  ride depending on what was planned. Check the activity name, description and the
  calendar (`get_events`) before judging.
- **Interval-by-interval decay is the story.** If reps 4 and 5 dropped 8%, say so and say
  what it means — that is a pacing error, a fitness ceiling, or underfueling, and the
  intervals data usually distinguishes them.
- **Decoupling above 10% has causes, not just a number.** Underfueling, heat, starting too
  hard, or a duration past current durability. Use the fuel plan for that ride
  (`/fuel-plan` maths) and the weather to say which one it likely was.
- **Efficiency factor only means something as a trend.** Fetch two or three comparable
  past rides before claiming it moved.
- **Name the source when you prescribe.** The tags — `[COG19]`, `[SEI10]`, `[JEU14]` —
  map to `docs/evidence-base.md`.

## 4. Offer to write it back

Ask before posting. If the user says yes, `add_activity_message` puts your read on the
activity in Intervals.icu so it lives with the ride.

## Cautions

- If FTP in the activity differs from `athlete.yaml`, the analyser flags it. Resolve which
  is right before quoting TSS — every load number depends on it.
- One session is weak evidence. Resist diagnosing fitness from a single ride; say what
  would confirm it instead.
- If the file has no power, say what you cannot tell rather than reasoning from HR alone.
