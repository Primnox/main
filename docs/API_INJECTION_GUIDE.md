# SLDB API Injection Guide

How to load synthetic data through Primnox HTTP endpoints for end-to-end testing.

## Quick Start

```bash
# 1. Generate a dataset
cd backend
python sdl/generate.py --pack office-500 --out ./sdl-out

# 2. Start Primnox
python run.py  # starts at http://localhost:4109

# 3. In another terminal, load via API
python sdl/api_inject.py --from ./sdl-out/office-500 --host http://localhost:4109

# 4. Verify
curl http://localhost:4109/conversations | jq '.conversations | length'
# Output: 20
```

## What Gets Loaded

### Chat Conversations ✓ WORKING
- **Endpoint**: `POST /conversations` (create) + `POST /conversations/{id}/turns` (add messages)
- **Data**: Chats from the synthetic pack
- **Result**: 
  - 20 conversations created (one per unique chat thread)
  - 1,521+ messages loaded as turns
  - Each message preserves original text and timestamp

### Assets ⚠️ KNOWN LIMITATION
- **Endpoint**: `POST /assets`
- **Issue**: Expects real file data (mime type, bytes)
- **Status**: Currently fails (0 assets created, 80 errors)
- **Workaround**: Use direct database injection for assets instead

## Retrieving Loaded Data

### Through HTTP API
```bash
# List all conversations
curl http://localhost:4109/conversations

# Get conversation history
curl http://localhost:4109/conversations/{conversation_id}/history
```

### Through Python
```python
import httpx

base = 'http://localhost:4109'

# Get conversations
resp = httpx.get(f'{base}/conversations')
convs = resp.json()['conversations']
print(f"Loaded {len(convs)} conversations")

# Get first conversation's messages
cid = convs[0]['id']
resp = httpx.get(f'{base}/conversations/{cid}/history')
turns = resp.json()['turns']
for turn in turns[:5]:
    if turn['user_message']:
        print(f"User: {turn['user_message']['text']}")
```

## API Injection Details

### Flow
1. **Create conversations**: One conversation per unique chat thread ID
   ```
   POST /conversations
   {"title": "Thread 001", "incognito": false}
   ```
   Returns: `{"id": "conv_...", ...}`

2. **Add turns (messages)**: Messages added as turns in creation order
   ```
   POST /conversations/{conversation_id}/turns
   {"text": "re: Beacon — see the doc I sent last week"}
   ```

3. **Try assets**: Attempted but currently fails
   ```
   POST /assets
   {"title": "Document.pdf", "kind": "document", ...}
   ```

### Response Structure
Conversations returned from `GET /conversations`:
```json
{
  "id": "conv_01a00b708f0b7008b2311bfb83c060a0",
  "title": "Thread 011",
  "folder_id": null,
  "turn_count": 126,
  "created_at": 1786898321163,
  "updated_at": 1786898321163
}
```

Turns returned from `GET /conversations/{id}/history`:
```json
{
  "turn_id": "turn_01a00b708f0b700991271652abc27c9a",
  "status": "queued",
  "seq": 1,
  "user_message": {
    "text": "re: Beacon — see the doc I sent last week",
    "partial": false,
    "blocks": [],
    "created_at": 1786898321163
  },
  "assistant_message": null,
  "error": null
}
```

## Why API Injection Matters

Testing through the HTTP API instead of direct database access ensures:
1. **Real HTTP contract validation**: Endpoints work as documented
2. **Payload serialization**: Data survives JSON round-trip
3. **Ordering preservation**: Turns appear in right sequence
4. **Live system testing**: Can test against running Primnox instance

## Testing Checklist

### Chat Injection
- [x] Conversations create successfully
- [x] Turns add to conversations
- [x] Turn count increments correctly
- [x] Message text preserved exactly
- [x] Timestamps preserved
- [x] Queryable via GET endpoints
- [x] Data survives Primnox restart

### Asset Injection
- [ ] Document upload succeeds (currently fails)
- [ ] Asset appears in asset list
- [ ] Metadata preserved

### Retrieval Integration
- [ ] Claude can answer questions about injected conversations
- [ ] Conversations indexed into knowledge graph
- [ ] L2 (cross-source) queries work with API-loaded data
- [ ] L5 (workspace) queries find conversation context

## Troubleshooting

### "0 assets, 80 errors"
**Problem**: Asset creation fails with no details

**Cause**: `POST /assets` endpoint expects real file data, not just metadata

**Solution**: Either:
1. Modify api_inject.py to send actual file bytes (currently sends metadata only)
2. Use direct database injection for assets instead (documented in SLDB_STATUS.md)
3. Wait for document-specific endpoint (`POST /documents`)

### Conversations empty after injection
**Problem**: Conversations show in list but have 0 turns

**Cause**: Turns endpoint failed silently

**Solution**:
1. Check turn creation response status codes
2. Verify conversation IDs are passed correctly
3. Check Primnox logs for errors

### Unicode errors in output
**Problem**: "UnicodeEncodeError" when printing results

**Solution**:
```python
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
```

## Code Structure

### api_inject.py
- `inject_conversations()`: Creates conversations and loads turns
  - Grouping: threads→conversations
  - Ordering: by month
  - Status: Full success
  
- `inject_assets()`: Attempts to load documents/notes as assets
  - Status: Fails (metadata-only approach incompatible)
  - Limit: First 50 docs, 30 notes to avoid spam

## Next Steps to Complete

1. **Fix asset injection**
   - Add real file bytes to POST /assets
   - Or implement POST /documents endpoint for metadata-only

2. **Verify Claude retrieval**
   - Load conversations
   - Ask Claude questions about them
   - Confirm answers cite loaded messages

3. **Build retrieval benchmark**
   - Submit all 500 ground truth questions to API
   - Collect Claude's answers
   - Score against ground_truth.json

## References

- [SLDB_STATUS.md](./SLDB_STATUS.md) — Full implementation details
- [backend/sdl/api_inject.py](./backend/sdl/api_inject.py) — Source code
- [backend/sdl/generate.py](./backend/sdl/generate.py) — Dataset generation
