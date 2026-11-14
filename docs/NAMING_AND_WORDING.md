# Naming and wording

Proposals for J.C., researched 2026-11-14. Nothing here is applied to the board yet. Conflict checks are web searches, not a trademark search; run a formal search before committing to a name.

## Product name

The working name "ICU-Twin" is jargon to clinicians. The candidates are short, calm, easy to say at rounds, and not alarming.

| Name | Why | Conflict found (web search) |
|---|---|---|
| **Lookahead** | Says what it does: the next 24 h | None in health software; a UK charity of the same name works in another field. Common word, so a weak mark: use "Lookahead for the ICU" |
| **Roundview** | "The view for rounds" | None in hospitals; an unrelated chatbot product and a UK toolkit use the name |
| **Tidemark** | The tide line on a harbour wall; fits strain bands and a marker line | Used by a venture firm and a former analytics company |
| Dayline | A line through the day | None in healthcare |
| Rejected | Cadence (Epic scheduling module), Steady (Steady Health), Daybreak (Daybreak Health), Nextday (telemedicine) | conflicts |

Taglines, calmer than "Compute buys certainty" (which reads as a vendor claim): "The next 24 hours, in one place." · "One shared view for morning rounds." · "Where the unit stands today."

## Words on the board

Principles: plain language (NHS A to Z of health writing; NN/g: experts prefer plain text too), numbers with ranges and "to" (GOV.UK style), recognition over recall (NN/g heuristics), status never by colour alone (GOV.UK tag), calm vocabulary to avoid alarm fatigue (Lewandowska 2020, PMID 33202907), and words paired with numbers because verbal probability terms are read very differently.

| Element | Now | Proposed | Avoid |
|---|---|---|---|
| Strain index | Unit strain · 1.3× a typical day | Unit load today: 1.3 times a typical day (1.0 to 1.6) | strain score, stress index, a bare "×" |
| Bands | QUIET / USUAL / BUSY / VERY BUSY | keep, with the word always shown | critical, surge, red alert |
| Watch first | Watch first: room 20, 12, 7 | Rooms to check first | high risk, deteriorating, alerts |
| Tile bars | Low BP 56% | keep the number; test "1 in 2" with nurses | likely, unlikely |
| Status | ON TRACK / TIGHT / SHORT | test sentence case (On track) against the whiteboard capitals | colour alone |
| No capacity | no capacity set | Capacity not set | missing, invalid, no data |
| Shift brief | Shift brief (mock) | 07:00 brief: next 24 hours | report, sitrep, alert |
| Missing numbers | pending run | Not ready yet: shown after the first run | pending, stale, failed |
| Chat | Ask the board | Ask about this forecast; empty state with an example question | AI assistant, ask me anything |
| Rerun | Rerun forecast | Update forecast | execute, refresh model |
| Rerun refused | Forecast not started: the last run was under 20 minutes ago. | Updated 12 minutes ago. You can update again at 07:20. | error, denied, not allowed |
| Evidence note | Model evidence, not a cause. | These are what the forecast read. They do not show why something happens. | drivers, because, root cause |
| Research forecasts | Research only · not for staffing | Research forecast: not validated for care decisions | experimental AI, beta |
| Death | Death | keep "Death", same bar style as every event | mortality, expire, passing, red or skull styling |
| Room page | Room 20 | Room 20: next 24 hours | patient risk profile, twin |

Untested: "1.3 times" against "30% busier than usual"; percentages against "1 in 4"; capitals against sentence case; whether death belongs on wall-visible tiles or only on the room page. Test these with the charge nurses before the wording is final.

## Sources

NHS A to Z of health writing (service-manual.nhs.uk/content/a-to-z-of-nhs-health-writing) · GOV.UK A to Z style guide and tag component · NN/g ten usability heuristics and plain-language article · Carbon design system, dashboards · AHRQ health IT design guidance (overview plus detail on demand) · HEE and CIEHF, Human Factors and Healthcare · Zipkin 2014 (PMID 25133362), risk formats · Lewandowska 2020 (PMID 33202907), ICU alarm fatigue · Few, Information Dashboard Design · Wilcox 2020 (PMID 32141924) and Rewa 2018 (PMID 29587816), ICU strain.
