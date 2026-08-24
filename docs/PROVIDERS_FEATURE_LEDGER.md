# Providers, routing and guides — feature ledger

Built against the OmniRoute clone at `C:\OmniRoute` (MIT). Every row is either
**ported** (their logic, adapted to Primnox's runtime), **new** (Primnox-specific,
no OmniRoute equivalent), **data** (their catalogue, transformed), or
**incumbent** (already in Primnox, relied on here).

Status is evidence-based. `done` means implemented AND covered by a test, or
verified against the running app — never on the strength of having been typed.

**Suite: 719 passing** (was 611 before this work). 103 tests added across
`test_model_failover.py` (47), `test_provider_catalogue.py` (43), and
`test_guides.py` (13).

One caveat, stated rather than buried: `test_l2_integration.py::
TestPdfConversation::test_upload_ingest_context_chat` fails in roughly half of
full-suite runs and passes every time in isolation. It waits on PDF ingestion
with a 20-second `wait_until` deadline, and a longer suite makes that deadline
easier to breach. Pre-existing and timing-sensitive, not a logic break — left
alone rather than quietly raised to make this report look cleaner.

## Backend — catalogue (14)

| # | Feature | Source | Evidence |
|---|---------|--------|----------|
| 1 | 346-provider catalogue in `providers.json` | data | `test_the_catalogue_carries_every_ported_provider` |
| 2 | Endpoints merged from their model-discovery config | data | 103 entries carry a real base URL |
| 3 | Three states: ready / needs_url / unsupported | new | `test_the_catalogue_says_which_entries_it_cannot_actually_call` |
| 4 | Per-entry reason when Primnox cannot call it | new | same test asserts every reason is non-empty |
| 5 | Add-from-catalogue with everything known prefilled | new | `test_adding_from_the_catalogue_prefills_what_is_known` |
| 6 | Refuses to invent a missing endpoint | new | `test_an_entry_without_an_endpoint_refuses_to_be_guessed_at` |
| 7 | Refuses to add an unsupported entry | new | `test_an_unsupported_entry_cannot_be_added_at_all` |
| 8 | Facet counts describe the whole catalogue, not the view | new | `test_counts_describe_the_whole_catalogue_not_the_filtered_view` |
| 9 | Free / no-key detection | data | `test_every_facet_returns_only_rows_that_belong_to_it[free]` |
| 10 | 17 ToS-flagged providers, ported from their FREE_TIERS.md | data | `test_tos_flagged_providers_carry_the_clause_that_flagged_them` |
| 11 | Server-side search over name, id, category, hint | new | `test_search_matches_name_id_category_and_hint` |
| 12 | Case-insensitive search | new | `test_search_is_case_insensitive` |
| 13 | An unknown facet shows everything, not nothing | new | `test_an_unknown_facet_does_not_silently_empty_the_list` |
| 14 | One profile seeded, not 346 | new | `test_only_what_works_unconfigured_is_seeded` |

## Backend — connections (11)

| # | Feature | Source | Evidence |
|---|---------|--------|----------|
| 15 | Connection probe: endpoint + key, one verdict | new | `test_a_reachable_endpoint_reports_its_models_and_latency` |
| 16 | Reports latency and model count | new | same |
| 17 | Failures named by the routing classifier | ported | `test_a_rejected_key_is_named_by_the_same_classifier_the_chain_uses` |
| 18 | HTML-behind-200 called out, not reported generically | new | `test_html_with_a_200_is_called_out_rather_than_reported_as_generic` |
| 19 | Empty endpoint refused without a network call | new | `test_an_empty_endpoint_is_refused_without_a_network_call` |
| 20 | Versionless base tries `/v1/models` first | new | `test_a_versionless_base_tries_the_v1_path_first` |
| 21 | A passing probe closes a stale breaker | new | `test_a_successful_probe_closes_a_breaker_that_was_benching_the_provider` |
| 22 | Testing an unsaved candidate records no health | new | `test_testing_an_unsaved_candidate_records_no_health` |
| 23 | Test-all, sequential to avoid self-inflicted 429s | new | `test_test_all_returns_a_row_per_profile` |
| 24 | Bulk discovery survives one provider failing | new | `test_discover_all_covers_every_profile_and_survives_one_failing` |
| 25 | Unknown profile raises rather than guessing | new | `test_testing_an_unknown_profile_is_a_key_error` |

## Backend — portability and annotation (8)

| # | Feature | Source | Evidence |
|---|---------|--------|----------|
| 26 | Export profiles as JSON, keys excluded | new | `test_an_export_never_contains_a_key` |
| 27 | Import adds new and updates existing | new | `test_import_adds_what_is_new_and_updates_what_exists` |
| 28 | Import never removes a profile | new | `test_import_never_removes_an_existing_profile` |
| 29 | Import skips bad rows instead of failing the file | new | `test_import_skips_rows_it_cannot_use_instead_of_failing_the_file` |
| 30 | A non-export file says so | new | `test_a_file_that_is_not_an_export_says_so` |
| 31 | Export round-trips through import | new | `test_export_round_trips_through_import` |
| 32 | Pin a provider to the top | new | `test_pinning_moves_a_provider_to_the_top`, `test_unpinning_puts_it_back` |
| 33 | Per-provider notes, cleared rather than blanked | new | `test_a_note_survives...`, `test_clearing_a_note_removes_it...` |

## Backend — routing and resilience (20)

| # | Feature | Source | Evidence |
|---|---------|--------|----------|
| 34 | Failure classifier, ten named types | ported | `test_failures_are_named_the_way_omniroute_names_them` (12 cases) |
| 35 | A 429 about money is not a rate limit | ported | `test_a_429_about_money_is_not_a_rate_limit` |
| 36 | Status beats message text | ported | `test_status_beats_message_text` |
| 37 | Retry-After honoured | ported | `test_retry_after_is_read_off_the_header` |
| 38 | HTTP-date Retry-After ignored, not guessed | new | `test_an_http_date_retry_after_is_ignored_not_guessed` |
| 39 | A malformed request stops the chain | new | `test_a_malformed_request_stops_the_chain` |
| 40 | A rejected key does not stop the chain | new | `test_a_rejected_key_does_not_stop_the_chain` |
| 41 | Three-state breaker (closed/open/half_open) | ported | `test_the_breaker_opens_on_the_threshold_and_not_before` |
| 42 | Credentials trip at one, not two | ported | `test_a_rejected_credential_opens_it_immediately` |
| 43 | Exponential cooldown with a ceiling | ported | `test_cooldown_doubles_per_trip_and_respects_the_ceiling` |
| 44 | Retry-After beats the curve, up to a cap | ported | `test_a_longer_retry_after_wins_over_our_curve` |
| 45 | Half-open single-probe recovery | ported | `test_expired_cooldown_goes_half_open_and_one_probe_gets_through` |
| 46 | A failed probe reopens immediately | ported | `test_a_failed_probe_reopens_immediately_whatever_the_threshold` |
| 47 | Trip count decays rather than resetting | ported | `test_success_closes_it_and_decays_the_trip_count` |
| 48 | Penalty-model health score | ported | `test_health_score_penalises_state_not_success_rate` |
| 49 | Multiplicative scoring, nine factors | ported | `test_an_open_circuit_scores_zero_and_is_ineligible` |
| 50 | Every factor reported for debugging | ported | `test_every_factor_is_reported_for_debugging` |
| 51 | Ranking puts the healthier provider first | ported | `test_ranking_puts_the_healthier_provider_first` |
| 52 | Commit-on-first-token (no spliced answers) | new | `test_a_provider_that_dies_mid_stream_is_not_failed_over` |
| 53 | Skips do not consume the attempt budget | new | `test_a_skipped_candidate_does_not_spend_the_attempt_budget` |

## Backend — trust boundary (5)

| # | Feature | Source | Evidence |
|---|---------|--------|----------|
| 54 | A localhost gateway is not on-device | new | `test_a_gateway_on_localhost_is_not_treated_as_on_device` |
| 55 | Gateway payloads are scrubbed like any cloud provider | new | `test_a_gateway_payload_is_scrubbed_like_any_cloud_provider` |
| 56 | "Needs a key" is a separate question from "off-device" | new | `test_a_keyless_gateway_is_called_and_a_keyless_cloud_endpoint_is_not` |
| 57 | Local sessions never fall back to cloud | new | `test_a_local_session_never_falls_back_to_the_cloud` |
| 58 | Cloud → local is allowed | new | `test_a_cloud_session_may_fall_back_to_a_local_model` |

## Frontend (14)

| # | Feature | Source | Evidence |
|---|---------|--------|----------|
| 59 | Provider tab widened to its content (5xl vs xl) | new | live DOM |
| 60 | Profile rows carry a live status dot | new | live: Ollama shows `REACHABLE · 14MS` |
| 61 | Per-profile Test with the provider's own error text | new | live |
| 62 | Test-all, export, import in the section header | new | live |
| 63 | Pin and note per profile | new | live |
| 64 | Catalogue search, debounced, server-side | new | live: 104 rows, `cerebras` → 1 |
| 65 | Six facet chips with live counts | new | live |
| 66 | Keyboard nav: arrows move, enter opens, esc clears | new | live: `arrowMovesCursor`, `enterOpensRow` |
| 67 | ToS warning shown before the key field | new | live |
| 68 | Test-before-save in the add flow | new | live |
| 69 | Skeleton loading, not spinners in content | new | three skeleton components |
| 70 | Empty states that teach | new | `EmptyState` in both surfaces |
| 71 | Routing chain in try-order with score factors | new | live |
| 72 | Row wraps instead of overflowing at 375px | new | live: 0 offscreen elements |

## Accessibility (3)

| # | Feature | Evidence |
|---|---------|----------|
| 73 | Every text style on the surface clears WCAG AA 4.5:1 | measured in-page: 0 failures across 10 distinct styles |
| 74 | 125 interactive controls carry the focus-visible ring | live audit |
| 75 | Accessible names on every icon-only control | `aria-label` on all; `aria-pressed` on toggles |

## Catalogue families (5)

Taken from OmniRoute's own dashboard, which sections its provider grid by
category with a count on each. Regrouped on the way across: they file by how a
provider AUTHENTICATES, which is right for their router and wrong to show a
person — `apikey/regional` and `apikey/inference-hosts` are the same decision to
someone choosing one.

| # | Feature | Evidence |
|---|---------|----------|
| 76 | 16 families, ordered cheapest-to-start first | `test_families_come_back_cheapest_to_start_first` |
| 77 | Families partition the catalogue exactly | `test_families_partition_the_catalogue` |
| 78 | Filtering by family returns only that family | `test_filtering_by_family_returns_only_that_family` |
| 79 | No shipped category silently falls through to "Other" | `test_every_shipped_category_has_a_family_rather_than_falling_through` |
| 80 | Ready count per family never exceeds its total | `test_the_ready_count_per_family_never_exceeds_its_total` |

## Guides, inline (8)

Not a tab. A Guides tab is where documentation goes to die: it needs the reader
to already suspect an answer exists, leave the task, find it in a list, and
carry the answer back. Each guide is now a disclosure attached to the control
it explains — and not a modal, which would interrupt the task to explain the
task, nor a tooltip, which cannot hold 800 words and a table.

| # | Guide / behaviour | Where it lives | Evidence |
|---|-------------------|----------------|----------|
| 81 | Choosing a provider | above the catalogue | live: "Which one should I pick?" |
| 82 | Free providers, honestly | appears on the No-key facet | live |
| 83 | How routing and failover work | under the routing chain | live: 803 words, table renders |
| 84 | What leaves your device | under the routing chain | live |
| 85 | When a provider stops working | with the profiles that fail | live |
| 86 | Body fetched on first open, not on mount | — | 5 guides most sessions never expand |
| 87 | Surrounding controls stay usable while open | — | live: `chainStillVisible` |
| 88 | Guides served as data, front matter parsed | — | `test_every_guide_parses_and_has_a_title_and_summary` |
| 89 | Slug cannot escape the guides directory | — | `test_a_slug_cannot_escape_the_guides_directory` (4 cases) |
| 90 | Every tunable a guide names actually exists | — | `test_every_tunable_a_guide_names_actually_exists` |

## Not done

- **Screenshots of the finished surface.** The Browser pane is not displayed in
  this session, so every visual claim above was verified by reading the live
  DOM and computed styles instead. Worth an eyeball.
- **Live probes against a real cloud provider.** Every connection test above
  runs against a fake. The first real 401 from a real vendor is still untested.
- **The 129 `needs_url` endpoints.** Recoverable only from OmniRoute's published
  npm package, which the clone does not vendor.

## Mission Control (12)

One page, top to bottom in the order the questions arrive: is it working, what
have I got, which should I use, what else is out there, where will the next
turn go. No separate documentation destination — the guides are disclosures
inside those sections.

| # | Feature | Evidence |
|---|---------|----------|
| 91 | Five measured tiles: providers, resident locally, turns today, finished, this turn | live |
| 92 | Route map — the chain drawn, first/fallback/skipped | live |
| 93 | Session telemetry: first-token latency, turns, failures, benched | live |
| 94 | Connection test narrated line-by-line as each provider answers | live: real cloud endpoint, 397 ms, 7 models |
| 95 | Resident local models with real VRAM cost from Ollama `/api/ps` | live: `qwen2.5:7b · 4.7 GB` |
| 96 | Compare table from the capability registry, not invented ratings | `test_capabilities_are_facts_not_ratings` |
| 97 | Call count travels with every latency figure | live: `397 ms · 2 calls` |
| 98 | A measurement in one panel refreshes the others | live: Compare updates after the test |
| 99 | Polls only while a turn is live or a breaker is counting down | code: `busy` gate |
| 100 | Latency counts up rather than snapping | `useCountUp`, disabled under reduced-motion |
| 101 | The serving node breathes; unloaded local models sleep rather than grey out | `.px-breathe` / `.px-sleep` |
| 102 | Every text style on the surface clears AA | measured: 18 styles, 0 failures |

### Refused, and why

The brief asked for two things this does not ship.

**Tokens per second.** Nothing in Primnox times the gap between tokens. A
figure derived from total tokens over wall-clock would count the user's reading
time as slow inference. `test_the_snapshot_reports_only_things_it_measured`
fails if a `tokens_per_second` field ever appears.

**Star ratings for Speed / Coding / Vision.** Primnox has never run a
benchmark. A five-star coding column invented to fill a table is a published
benchmark whether or not it is labelled one, and someone would choose a
provider because of it. OmniRoute can show that column honestly because it
syncs Arena ELO into a database table; until Primnox does the same, the column
is decoration wearing the costume of data. PRODUCT.md forbids fabricating
benchmarks, and `test_capabilities_are_facts_not_ratings` enforces it.

What replaced them is measured and, on second look, more useful: how many turns
ran today, how many finished, and the real first-token latency with its call
count beside it.
