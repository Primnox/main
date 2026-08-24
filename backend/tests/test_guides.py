"""The in-app guides.

Content tests, mostly: a guide that promises a control which does not exist is
worse than no guide, so the ones that name a tunable or an endpoint are checked
against the real thing rather than trusted.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from primnox2 import guides                                      # noqa: E402
from primnox2.settings import tunables                           # noqa: E402


def test_every_guide_parses_and_has_a_title_and_summary():
    rows = guides.index()
    assert rows, "no guides shipped"
    for row in rows:
        assert row["title"] and not row["title"].startswith("None")
        assert len(row["summary"]) > 20, f"{row['slug']} has no useful summary"


def test_the_index_carries_no_bodies():
    """It renders as a menu; the bodies are most of the payload."""
    assert all("body" not in row for row in guides.index())


def test_guides_come_back_in_their_declared_order():
    orders = [g["order"] for g in guides.index()]
    assert orders == sorted(orders)


def test_a_guide_body_loads():
    slug = guides.index()[0]["slug"]
    guide = guides.get(slug)
    assert guide and len(guide["body"]) > 500


def test_an_unknown_slug_is_none_rather_than_an_error():
    assert guides.get("no-such-guide") is None


@pytest.mark.parametrize("slug", ["../app", "..\\app", "/etc/passwd", "guides/../app"])
def test_a_slug_cannot_escape_the_guides_directory(slug):
    """The slug is validated against the listing rather than joined onto a
    path, so traversal never reaches the filesystem."""
    assert guides.get(slug) is None


def test_every_tunable_a_guide_names_actually_exists():
    """A guide that tells someone to change `models.failover_attempts` is wrong
    the moment that knob is renamed, and wrong in the most annoying way: the
    reader assumes they are looking in the wrong place."""
    named = set()
    for row in guides.index():
        body = guides.get(row["slug"])["body"]
        named |= set(re.findall(r"`(models\.[a-z_]+|context\.[a-z_]+|tools\.[a-z_]+)`", body))
    assert named, "no tunables referenced — update this test if that is intended"
    unknown = named - set(tunables.REGISTRY)
    assert not unknown, f"guides reference tunables that do not exist: {sorted(unknown)}"


def test_the_privacy_guide_states_the_gateway_rule():
    """The localhost-gateway distinction is the least obvious privacy property
    in the product and the easiest to lose in an edit."""
    body = guides.get("what-leaves-your-device")["body"]
    assert "127.0.0.1" in body and "gateway" in body.lower()


def test_the_routing_guide_matches_the_shipped_breaker_defaults():
    """Numbers in prose drift away from the code they describe. These two are
    the ones a reader will act on."""
    body = guides.get("routing-and-failover")["body"]
    assert f"{int(tunables.REGISTRY['models.breaker_cooldown_s'].default)} seconds" in body
    assert "15 minutes" in body                 # breaker_cooldown_max_s = 900
    assert tunables.REGISTRY["models.breaker_cooldown_max_s"].default == 900.0


def test_the_guides_describe_the_gateway_rather_than_a_catalogue():
    """They used to quote 103/129/114 out of a 346-row port. That catalogue is
    gone; a guide still citing it would be describing a product that no longer
    exists, in the most confusing possible way — confidently."""
    body = guides.get("choosing-a-provider")["body"]
    assert "OmniRoute" in body
    assert "346" not in body or "briefly" in body, (
        "the guide cites the old catalogue size as if it were current")
    for channel in ("auto/coding", "auto/cheap"):
        assert channel in body, f"the guide does not mention the {channel} channel"


def test_the_channels_a_guide_names_are_the_ones_shipped():
    """A guide offering `auto/turbo` sends someone looking for a control that
    does not exist."""
    from primnox2.settings import models

    entry = models.primary_entry()
    shipped = set(entry["fallback_models"])
    body = guides.get("choosing-a-provider")["body"]
    named = {line.split("`")[1] for line in body.splitlines()
             if line.startswith("| `auto")}
    assert named and named <= shipped, f"guide names channels not shipped: {named - shipped}"
