# Mom Test UX Analysis - Meme Coin Monitor Dashboard

Analysis date: 2026-01-29
Stashed version: dashboard-stash-20260129-205234

---

## The 6 UX Principles Review

### 1. CLARITY - Can mom understand what things mean?

| Confusing Element | Mom's Reaction | Severity | Fix |
|-------------------|----------------|----------|-----|
| "Risky" tab | "Risky how? To me?" | HIGH | Rename to "Dangerous Tokens" with subtitle |
| "Opportunities" tab | "Opportunity to do what?" | HIGH | Rename to "Safe Bets" or add explanation |
| "ML Data" tab | "What is M-L?" | CRITICAL | Rename to "Track Record" or "History" |
| "Rugged" / "RUGGED" | "What got rugged? Is that a carpet?" | CRITICAL | Use "Scam" or "Failed" |
| "Mooned" outcome | "The moon? What?" | HIGH | Use "Big Win" or "10x+" |
| Risk score "75" | "Is 75 good or bad? Out of what?" | CRITICAL | Add color scale + "75/100 (Dangerous)" |
| "5abc...xyz4" address | "That's not a real address" | MEDIUM | Add copy button icon, tooltip "Click to copy" |
| "CONFIDENCE" column | "Confident about what?" | HIGH | Rename to "Data Quality" or remove |
| "Top 10 HOLDERS" | "Who's holding what?" | MEDIUM | "Whale Concentration" with explainer |

### 2. SIMPLICITY - Can mom use it without training?

| Complex Element | Mom's Reaction | Severity | Fix |
|-----------------|----------------|----------|-----|
| 7 navigation tabs | "Where do I even start?" | HIGH | Consolidate to 4: Overview, Tokens, History, Settings |
| Settings "Display Limits" | "Why do I need to set limits?" | MEDIUM | Hide in advanced, use sensible defaults |
| Multiple filter dropdowns | "So many choices..." | MEDIUM | Single unified search/filter |
| Export CSV button | "What's a CSV?" | LOW | Rename to "Download Spreadsheet" |
| Watchlist with no view | "Where's my list?" | HIGH | Add visible watchlist section |

### 3. CONSISTENCY - Does same thing work same way?

| Inconsistency | Mom's Reaction | Fix |
|---------------|----------------|-----|
| Filter pills vs dropdown selects | "Why are these different?" | Use pills everywhere or dropdowns everywhere |
| "RISKY TOKENS" vs "HIGH RISK TOKENS" | "Are these different things?" | Use same terminology |
| Some panels have REFRESH, some don't | "How do I update this one?" | Add refresh to all or auto-refresh all |
| Tabs load on click vs auto-load | "Why is this empty?" | Pre-load all tabs or show loading state |

### 4. FEEDBACK - Does mom know what happened?

| Missing Feedback | Mom's Reaction | Fix |
|------------------|----------------|-----|
| Copy address - no feedback | "Did it copy? I don't know" | Show toast "Copied!" |
| Add to watchlist - small text | "Did that work?" | Show toast + animate button |
| Loading... forever | "Is it broken?" | Show progress or spinner with "Checking 47 tokens..." |
| Logout - no confirmation | "Wait I didn't mean to!" | Add "Are you sure?" |
| Tab switch - empty then loads | "Is it broken?" | Show skeleton/placeholder |

### 5. DISCOVERABILITY - Can mom find features?

| Hidden Feature | Mom's Reaction | Fix |
|----------------|----------------|-----|
| Click address to copy | "I didn't know I could do that" | Add copy icon, tooltip |
| Watchlist exists | "There's a watchlist? Where?" | Add Watchlist tab or sidebar |
| Settings in last tab | "I didn't see settings" | Use gear icon in header |
| Token lookup | "Can I search?" | Add search box in header |

### 6. FORGIVENESS - Can mom recover from mistakes?

| Unforgiving Element | Mom's Reaction | Fix |
|---------------------|----------------|-----|
| Remove from watchlist - instant | "Oops I didn't mean to remove that" | Add undo toast for 5 seconds |
| Logout - no confirm | "I accidentally logged out!" | Add confirmation dialog |
| No back button in lookup | "How do I get back?" | Add breadcrumb or back link |

---

## Biggest UX Failures (Ranked)

1. **CRYPTO JARGON EVERYWHERE** - "Rugged", "Mooned", "ML Data" mean nothing to normal humans
2. **SCORES WITHOUT CONTEXT** - "Risk: 75" - is that good? bad? out of 100? 1000?
3. **NO ACTION FEEDBACK** - Clicking things gives no visual confirmation
4. **TOO MANY TABS** - 7 tabs creates cognitive overload
5. **HIDDEN FEATURES** - Watchlist exists but isn't visible, copying requires discovery
6. **INCONSISTENT PATTERNS** - Pills here, dropdowns there, refresh buttons sometimes

---

## Quick Wins (Effort vs Impact)

| Fix | Effort | Impact | Priority |
|-----|--------|--------|----------|
| Add "Copied!" toast on address click | LOW | HIGH | DO FIRST |
| Rename "ML Data" to "Track Record" | LOW | HIGH | DO FIRST |
| Add score explanations (75 = Dangerous) | LOW | HIGH | DO FIRST |
| Replace "Rugged" with "Scam" | LOW | HIGH | DO FIRST |
| Replace "Mooned" with "Big Winner" | LOW | HIGH | DO FIRST |
| Add loading spinners with context | LOW | MEDIUM | DO SECOND |
| Merge Risky + Opportunities into "Tokens" | MEDIUM | HIGH | DO SECOND |
| Add tooltips to jargon terms | MEDIUM | HIGH | DO SECOND |
| Move Settings to header gear icon | MEDIUM | MEDIUM | DO THIRD |
| Add watchlist sidebar/panel | HIGH | MEDIUM | LATER |

---

## Implementation Plan

### Phase 1: Language Cleanup (DO NOW)
- Rename "ML Data" tab to "Track Record"
- Replace all "RUGGED" with "SCAM"
- Replace all "MOONED" with "BIG WIN"
- Add score context: "75/100 - Dangerous"
- Rename "CONFIDENCE" to "Data Quality"

### Phase 2: Feedback Systems (DO NOW)
- Add toast notification system
- Show "Copied!" when clicking addresses
- Add loading spinners with context text
- Add success/error animations

### Phase 3: Simplification (DO SECOND)
- Consolidate 7 tabs into 4
- Use consistent filter pattern (pills everywhere)
- Add global search in header
- Move settings to gear icon

### Phase 4: Discoverability (DO THIRD)
- Add copy icons next to addresses
- Add tooltips with explanations
- Add "What's this?" help links
- Make watchlist visible

---

## Before/After Examples

### Risk Score Display

BEFORE:
```
RISK: 75
```

AFTER:
```
RISK: 75/100
[======----] DANGEROUS
```

### Outcome Labels

BEFORE: `RUGGED` | `MOONED` | `DEAD` | `SURVIVED`

AFTER: `SCAM` | `BIG WIN (10x+)` | `FAILED` | `SURVIVED`

### Tab Names

BEFORE: Overview | Risky | Opportunities | Alerts | ML Data | Lookup | Settings

AFTER: Dashboard | Tokens | Alerts | Track Record | (Settings in header)

### Address Display

BEFORE:
```
5abc...xyz4
```

AFTER:
```
5abc...xyz4 [copy icon]
(Click to copy full address)
```
