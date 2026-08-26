# Failure & Recovery UX — Design Principles & Taxonomy

## Why This Matters

Primnox is an AI assistant that orchestrates multiple providers, tools, and infrastructure components. Failures are inevitable:
- **Provider unavailability** (Groq down, Anthropic rate-limited, OpenAI quota exhausted)
- **Tool execution failures** (sandbox error, file I/O, permission denied, timeout)
- **Network failures** (connection drop, DNS resolution, gateway timeout)
- **User action required** (quota exceeded, API key expired, permission grant needed)

A good failure UX does three things:
1. **Diagnoses clearly** — the user knows *what* failed and *why*
2. **Recovers automatically** — retry, fallback provider, degrade gracefully
3. **Unblocks the user** — actionable next step (retry button, add key, wait and try again, use workaround)

## Design Principles

### 1. Severity is Implicit, Not Decorative
Avoid red alert boxes for warnings. Visual weight should match the issue:
- **Terminal error** (provider auth failed, all fallbacks exhausted): bold block, actionable button
- **Degraded** (retrying on fallback provider): subtle status, no modal intrusion
- **Informational** (this took longer than expected): micro UI, out of flow

### 2. Root Cause Over Symptom
Show *why* it failed, not just *that* it failed.
- ❌ "Tool execution failed"
- ✅ "Sandbox permission denied: read access to /etc/shadow not allowed"

Pair it with **context** (which tool, which provider, which file).

### 3. Retry Is Not Always Recovery
Some failures should retry automatically (transient network). Others should surface immediately (auth expired, quota exhausted). The code decides; the UI does not.

**Automatic retry scenarios:**
- Transient provider timeout (429, 503)
- Network blip (connection reset)
- Rate limit with headroom to retry

**Immediate escalation:**
- Auth failure (invalid key, expired token)
- Capability mismatch (model unavailable, feature unsupported)
- User action needed (permission grant, quota add)

### 4. Fallback Is Failover, Not Demotion
If Groq fails, Primnox picks the next provider from the routing chain. Show this as a fact ("Retrying on Claude (Anthropic)"), not as an apology. The user chose multi-provider for exactly this reason.

### 5. Cancellation Is an Outcome, Not a Failure
If the user stops a turn, that's intentional. Show it neutrally. Only flag it as "error" if the cancellation itself failed (rare).

### 6. Recovery State Persists Until Outcome
Once a failure is detected, keep the failed state and recovery action visible until:
- The turn completes successfully
- The turn is permanently terminated (user cancels, max retries hit)
- The user navigates away

Do not auto-dismiss or hide recovery UI.

## Error Taxonomy

### Layer 1: Where It Failed
| Layer | Component | Examples |
|-------|-----------|----------|
| **Orchestration** | Turn, routing, context-building | "Failed to build context: 4 permissions pending" |
| **Model** | Provider, model selection | "Groq API key invalid (expired)" |
| **Tool** | Sandbox, execution runtime | "Python sandbox: permission denied" |
| **Network** | HTTP, socket, gateway | "Connection timeout (60s)" |
| **User** | Permission, quota, action | "Claude Opus not available in region" |

### Layer 2: Recovery Path
| Path | Trigger | Action | Status |
|------|---------|--------|--------|
| **Automatic Retry** | Transient error + retryable | Retry same provider after backoff | "Retrying (1/3)" |
| **Fallback Provider** | Primary exhausted, alternatives available | Route to next provider in chain | "Trying Anthropic (Groq failed)" |
| **Degrade** | Loss of capability, partial success possible | Use lighter model, drop optional tools | "Using smaller model" |
| **Escalate** | Auth error, quota exceeded, capability missing | Show action button, require user input | "Add API key to continue" |
| **Terminal** | Max retries exhausted, no fallback | Show full error, offer cancel/debug | "All providers failed. Last error: ..." |

### Layer 3: Actionability
| Category | User Action | UI Pattern |
|----------|-------------|-----------|
| **Retry-able** | (none, automatic) | Progress indicator + backoff countdown |
| **Fixable** | Add key, grant permission, increase quota | Modal or inline form |
| **Informational** | Wait a bit, try a different query | Explanation + dismiss button |
| **Unsupported** | Use different tool or provider | Link to docs or fallback suggestion |

## State Machine

```
Healthy
    ↓ (error detected)
    → Retrying (backoff)
        ↓ (timeout or max retries)
        → Failed
            ↓ (user hits Retry)
            → Retrying (restart counter)
    ↓ (fallback available)
    → Falling Back (switch provider)
        ↓ (attempt succeeds)
        → Healthy
        ↓ (attempt fails)
        → Failed → Escalate (all paths exhausted)
    ↓ (no retry possible)
    → Escalate
        ↓ (user fixes issue or cancels)
        → Terminal (success or cancelled)
```

## RecoveryBlock Component Scope

The `RecoveryBlock` component handles:
1. **Error detection & classification** — map backend error to actionable type
2. **Recovery UI** — show progress, actions, and reasoning
3. **State management** — track retries, timeouts, escalation
4. **Messaging** — context-aware explanations for the user

It does **NOT** handle:
- Retry logic itself (backend's `turn_manager.py` owns that)
- Fallback routing (backend's `brain.py` + `omni_route.py` own that)
- Permission grants (handled by `PermissionBlock.tsx`)
- Automatic modal display (caller decides when to show recovery UI)

See `RecoveryBlock.tsx` for implementation details.

---

## Examples

### Example 1: Transient Provider Timeout
```
Status: "Claude (Anthropic) is taking longer than expected"
Icon: Animated spinner (not error)
Action: (automatic, no button needed)
Timing: Shows after 5s, auto-resolves on success
```

### Example 2: Rate Limit with Fallback
```
Status: "Groq is rate-limited. Retrying on Ollama (local)."
Icon: ⏱️ (informational)
Progress: "Attempt 2/3, resuming in 8s"
Action: (automatic fallover, no button)
```

### Example 3: Auth Failure
```
Status: "Groq API key invalid (expired)"
Icon: 🔑 (actionable)
Action: [Update Key] button
Context: "This key last worked 3 days ago"
Retryable: No (blocks user until fixed)
```

### Example 4: Capability Mismatch
```
Status: "Claude Opus unavailable in your region (US West 2)"
Icon: 📍 (informational)
Action: [Use Claude Sonnet Instead] or [Change Region]
Suggestion: "Sonnet is 95% as capable and available now"
Retryable: No (degradation or manual intervention)
```

### Example 5: Sandbox Permission Denied
```
Status: "Python sandbox: Cannot write to /home (permission denied)"
Icon: 🔐 (informational)
Context: "The code tried to save a file outside the working directory"
Action: [Retry with /tmp] or [Manual Action]
Retryable: Depends (retry if code can be modified automatically)
```

### Example 6: Terminal Failure
```
Status: "Turn failed after 3 retries. Last error:"
Error: "Groq: 503 Service Unavailable"
Icon: ❌ (terminal)
Action: [Retry] [Debug] [Cancel Turn]
Context: "All fallback providers also failed"
```

## Next: Implementation Checklist

- [ ] Create `RecoveryBlock.tsx` component
- [ ] Add error classification helper (`error_classifier.ts`)
- [ ] Wire into `TurnBlock.tsx` to show for failed turns
- [ ] Wire into `ExecutionBlock.tsx` for tool execution failures
- [ ] Add backend error types to `Turn` + `Execution` payloads
- [ ] Add retry/recovery endpoints to backend API
- [ ] Test with synthetic failures (mock provider 503, sandbox permission denied, etc.)
- [ ] Surface in RoutingHealth for provider failovers
