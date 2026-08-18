"""Load a pack's conversations and assets through the HTTP API.

    python sdl/api_inject.py --from ./sdl-out/office-500 --host http://localhost:4109

Converts the synthetic pack into real Primnox conversations and assets, so
retrieval can be tested end-to-end through the API.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


async def inject_conversations(base_url: str, chats: list[dict],
                               emails: list[dict]) -> dict:
    """Create conversations from chats and emails."""
    async with httpx.AsyncClient() as client:
        created: dict[str, str] = {}  # chat_id -> conversation_id
        stats = {"conversations": 0, "turns": 0, "errors": 0}

        # One conversation per chat thread
        threads = {}
        for chat in chats:
            thread = chat["thread"]
            if thread not in threads:
                threads[thread] = []
            threads[thread].append(chat)

        for thread_id, messages in sorted(threads.items()):
            try:
                resp = await client.post(
                    f"{base_url}/conversations",
                    json={"title": f"Thread {thread_id[-3:]}",
                          "incognito": False})
                if resp.status_code != 200:
                    stats["errors"] += 1
                    continue
                conv = resp.json()
                conv_id = conv["id"]
                stats["conversations"] += 1

                # Add each message as a turn
                for msg in sorted(messages, key=lambda m: m["month"]):
                    created[msg["id"]] = conv_id
                    resp = await client.post(
                        f"{base_url}/conversations/{conv_id}/turns",
                        json={"text": msg["text"]})
                    if resp.status_code == 200:
                        stats["turns"] += 1
                    else:
                        stats["errors"] += 1
            except Exception as e:
                print(f"Error creating conversation from {thread_id}: {e}")
                stats["errors"] += 1

        return {"conversations": created, "stats": stats}


async def inject_assets(base_url: str, documents: list[dict],
                        notes: list[dict], photos: list[dict]) -> dict:
    """Create assets from documents, notes and photos."""
    async with httpx.AsyncClient() as client:
        created: dict[str, str] = {}  # doc_id -> asset_id
        stats = {"assets": 0, "errors": 0}

        for doc in documents[:50]:  # Limit to avoid API spam
            try:
                # Synthetic assets don't have real files, so we create metadata-only
                resp = await client.post(
                    f"{base_url}/assets",
                    json={"title": doc["name"], "kind": doc.get("kind", "document"),
                          "folder": doc.get("folder", "Documents"),
                          "size": 1024,  # dummy size
                          "mime_type": "application/octet-stream"})
                if resp.status_code == 200:
                    asset = resp.json()
                    created[doc["id"]] = asset["id"]
                    stats["assets"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                print(f"Error creating asset for {doc['id']}: {e}")
                stats["errors"] += 1

        for note in notes[:30]:
            try:
                resp = await client.post(
                    f"{base_url}/assets",
                    json={"title": note["title"], "kind": "note",
                          "folder": note.get("folder", "Notes"),
                          "size": 512, "mime_type": "text/plain"})
                if resp.status_code == 200:
                    asset = resp.json()
                    created[note["id"]] = asset["id"]
                    stats["assets"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                print(f"Error creating asset for note {note['id']}: {e}")
                stats["errors"] += 1

        return {"assets": created, "stats": stats}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Inject an SDL pack through the API")
    ap.add_argument("--from", dest="source", required=True,
                    help="a directory generate.py wrote")
    ap.add_argument("--host", default="http://localhost:4109",
                    help="Primnox API URL")
    args = ap.parse_args(argv)

    source = Path(args.source)
    if not (source / "chats.jsonl").exists():
        raise SystemExit(f"{source} does not have chats.jsonl")

    print(f"Loading from {source}")
    chats = [json.loads(line) for line in
             (source / "chats.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    emails = [json.loads(line) for line in
              (source / "emails.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]
    documents = [json.loads(line) for line in
                 (source / "documents.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    notes = [json.loads(line) for line in
             (source / "notes.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    photos = [json.loads(line) for line in
              (source / "photos.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]

    print(f"Connecting to {args.host}")
    try:
        import asyncio
        result = asyncio.run(_inject(args.host, chats, emails, documents, notes,
                                     photos))
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


async def _inject(host: str, chats: list[dict], emails: list[dict],
                  documents: list[dict], notes: list[dict],
                  photos: list[dict]) -> dict:
    """Run both injections."""
    conv_result = await inject_conversations(host, chats, emails)
    asset_result = await inject_assets(host, documents, notes, photos)

    print("\nResults:")
    print(f"  Conversations: {conv_result['stats']['conversations']}")
    print(f"  Turns: {conv_result['stats']['turns']}")
    print(f"  Assets: {asset_result['stats']['assets']}")
    print(f"  Errors: {conv_result['stats']['errors'] + asset_result['stats']['errors']}")

    return {"conversations": conv_result, "assets": asset_result}


if __name__ == "__main__":
    raise SystemExit(main())
