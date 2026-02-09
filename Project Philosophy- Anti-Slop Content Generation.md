# Project Philosophy: Anti-Slop Content Generation

## What We're Building

A system that transforms external content (blog posts, news articles, industry reports) into LinkedIn marketing posts for AFTA Systems that:

1. Don't sound like AI wrote them
2. Don't follow the same tired LinkedIn formulas everyone else uses
3. Actually get read instead of scrolled past

## The Core Problem

AI-generated LinkedIn content has a distinctive smell. People can detect it even if they can't articulate why. The tells:

- **Too smooth.** Every sentence flows perfectly into the next. Real humans write awkward sentences sometimes.
- **Too balanced.** Always presents both sides, hedges everything, never commits.
- **Too structured.** Hook → 3 points → CTA. Every single time.
- **Generic enthusiasm.** "Excited to share..." "Great insights from..." "This is huge!"
- **Even rhythm.** No variation in sentence length. No abrupt stops. No incomplete thoughts.
- **Specific-but-round numbers.** "I analyzed 47 projects" — real humans say "like 50" or give the ugly real number (2,843).

The irony: Most "best practices" for LinkedIn content ARE the AI-slop patterns. The hooks, the frameworks, the curiosity gaps — that's exactly what AI has been trained on millions of times.

## Our Approach

### 1. Style Through Samples, Not Descriptions

Don't tell the model to "write like Bourdain." Feed it actual Bourdain prose and say "write in this style."

Why: LLMs have seen "write like X" a million times and interpret it generically. Raw prose creates pattern-matching at the sentence level — the model mimics rhythm and structure, not just "vibe."

### 2. Break the Polish Deliberately

Real human writing has friction:
- Parenthetical asides that don't quite fit
- Sentences that start with "Look," or "Here's the thing —"
- Half-formed thoughts: "I'm still not sure about X, but..."
- References to mundane specifics (a Tuesday, a Slack ping, a cold coffee)
- One sentence that goes nowhere

AI writing is frictionless. Friction is human.

### 3. Kill the Transitions

AI smoothness comes largely from transition sentences. Every paragraph connects perfectly to the next. Real writing jumps. The reader fills the gaps.

Wildcard instruction: "No transition sentences. Jump between ideas."

### 4. Inject Actual Opinions

AI is diplomatic by default. It presents balanced views. It hedges.

Force commitment: "Take a mildly controversial stance" or "Disagree with one common assumption."

The provocateur persona exists for this. Use it.

### 5. Randomize to Avoid Patterns

Even good techniques become patterns if overused. The creativity engine exists to:
- Rotate hook styles (weighted, not uniform)
- Vary frameworks
- Inject wildcards that constrain in unexpected ways
- Select different author style samples

The goal: No two posts should feel like they came from the same template.

## The Author References

We use actual prose samples from four authors, each serving a different purpose:

### Anthony Bourdain
**Use for:** Provocateur, Witty, Storyteller
**What he brings:** Visceral, opinionated, no hedging. Physical/sensory details even for abstract ideas. Admits failures openly. Never explains the joke.

### Elmore Leonard
**Use for:** Professional, Minimalist, AI-Meta
**What he brings:** Invisible prose. "If it sounds like writing, I rewrite it." Leave out the parts readers skip. Incomplete sentences are fine.

### Raymond Carver
**Use for:** Minimalist, Storyteller
**What he brings:** What's NOT said carries weight. Short declarative sentences. Endings that just stop instead of wrapping up.

### Kurt Vonnegut
**Use for:** AI-Meta, Witty, Educator
**What he brings:** Deadpan absurdism. States dark truths as simple facts. Childlike sentences for profound ideas. Fourth-wall breaks that feel natural.

## What Each Persona Is For

| Persona | Voice | Best For |
|---------|-------|----------|
| Professional | Confident peer with data | Case studies, industry stats, credibility plays |
| Witty | Friend who knows stuff | Relatable pain points, industry inside jokes |
| AI-Meta | Self-aware, ironic | Meta-commentary, fourth-wall breaks about automation |
| Storyteller | Narrative-first | Before/after transformations, client scenarios |
| Provocateur | Blunt contrarian | Calling out industry BS, uncomfortable truths |
| Minimalist | Poetic brevity | Single powerful insights, memorable one-liners |
| Educator | Mentor with frameworks | Analogies, mental models, "aha" moments |

## Anti-Patterns to Enforce

### Never Do
- Emoji spam (max 1 per post)
- Multiple exclamation points
- "Excited to share..."
- "Here's what I learned..."
- Engagement bait questions at the end ("What do you think?")
- Bulleted lists in every post
- Vague claims ("many businesses", "significant improvement")
- Starting with weather or context-setting

### The Banned Words/Phrases List
- "Leverage"
- "Insights"
- "Game-changer"
- "Thought leadership"
- "Synergy"
- "At the end of the day"
- "It goes without saying"
- "In today's fast-paced world"
- "Unpack" (as in "let's unpack this")
- "Deep dive"

### Structure Tells to Avoid
- Hook → 3 bullets → CTA (the 2023 growth-hacker special)
- "Myth vs Reality" format
- "X things I learned from Y"
- Starting with a question
- Ending with "Agree?"

## The Quality Check

Before output, verify:

1. **Does this sound like writing?** If yes, rewrite it. (Leonard rule)
2. **Could you guess this was AI?** Be honest.
3. **Is there at least one moment of friction?** An awkward turn, an incomplete thought, a mundane detail?
4. **Does it commit to something?** Or does it hedge?
5. **Would you scroll past this?** If yes, it failed.

## Remember

The goal is not to trick people into thinking a human wrote it. The goal is to write something worth reading. The human detection problem solves itself when the writing is actually good.

Marketing frameworks are training wheels. The best LinkedIn posts don't follow them — they just say something interesting.

So it goes.
