"""Chromium windows — reading the page instead of the painting of it.

A browser is not one application, it is a different application per tab, and
its accessibility tree is the live DOM rather than a fixed set of controls.
UIA can see that tree, and does, at a price: measured on one ordinary browser
window, 221 elements taking 310 ms uncached and 83 ms cached, against a
BROWSER_MAX_ELEMENTS cap of 800 that a real page routinely blows through. The
model then reads a truncated view of a page and has no way to know which part
it lost.

Chromium already exposes exactly what is wanted, over its own protocol. The
same page read through CDP came back as 13 accessibility nodes — not a
compressed version of the 221, a semantically better one: the DOM's own roles
and names, with none of the browser chrome, none of the nodes that exist for
layout, and no truncation.

The design decision that matters here is what a CDP element LOOKS like to the
rest of this package, and the answer is: exactly like a UIA one. `_Node`
implements the same pattern-getter interface `actions.py` already calls, so
`actions.invoke`, `actions.set_value` and `tree.live_value` work on a page
element with no changes and no branch. One logical target, two execution
paths, and the model never learns which one carried it — which is the whole
point of having a substrate rather than a special case.

**This requires the browser to have been started with
`--remote-debugging-port`.** An ordinary browser has not been, and there is no
way to switch it on from outside: the flag is read at launch. So discovery
answers honestly — if the port is not there, this reports that it cannot help
and the UIA path handles the window as it always has. Turning it on for a
browser the user is already signed into is their decision to make, not
Primnox's, and it is worth them knowing that anything holding the port can
read every page in that browser.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from . import targets, tree

CDP_FLAG = "--remote-debugging-port="

# How long any single protocol call may take. A page mid-navigation can leave
# a request unanswered, and the caller is a turn worker that must not be lost
# to a browser tab.
TIMEOUT_S = 8.0

# Bounds cost one call per element, so they are fetched only for the elements
# that can actually be operated — which is where a coordinate is ever needed.
# A content-heavy page has thousands of nodes and tens of actionable ones.
MAX_BOUNDS_LOOKUPS = 120

# How a DOM role maps onto the vocabulary the rest of this package speaks, and
# what such an element can do. Derived from role rather than probed, because
# unlike UIA there is no per-element capability query — the DOM's contract is
# that a button is a thing you click.
ROLES = {
    "button": ("Button", ["invoke"]),
    "link": ("Hyperlink", ["invoke"]),
    "textbox": ("Edit", ["set_value", "read_text"]),
    "searchbox": ("Edit", ["set_value", "read_text"]),
    "combobox": ("ComboBox", ["set_value", "expand"]),
    "checkbox": ("CheckBox", ["toggle"]),
    "switch": ("CheckBox", ["toggle"]),
    "radio": ("RadioButton", ["select"]),
    "menuitem": ("MenuItem", ["invoke"]),
    "tab": ("TabItem", ["select"]),
    "option": ("ListItem", ["select"]),
    "heading": ("Text", ["read_text"]),
    "StaticText": ("Text", ["read_text"]),
    "paragraph": ("Text", ["read_text"]),
    "list": ("List", []),
    "listitem": ("ListItem", []),
    "table": ("Table", []),
    "img": ("Image", []),
    "image": ("Image", []),
}

# Structural roles that carry nothing and exist only to hold other nodes.
# Dropping them is the same judgement `NOISE_TYPES` makes for UIA.
SKIP_ROLES = frozenset({
    "generic", "none", "presentation", "InlineTextBox", "LineBreak",
    "RootWebArea", "group", "section",
})


class Unavailable(RuntimeError):
    """This window cannot be driven over CDP, and why."""


# ── Discovery ───────────────────────────────────────────────────────────────

def _http(endpoint: str, path: str):
    with urllib.request.urlopen(f"{endpoint}{path}", timeout=TIMEOUT_S) as response:
        return json.loads(response.read())


def _debug_port(pid: int) -> "int | None":
    """The debugging port a process was started with, if any.

    Walked up the process tree as well as checked directly, because a browser
    window belongs to a renderer or a window process whose parent holds the
    flag — asking only the window's own pid finds nothing on a real browser.
    """
    import psutil

    try:
        process = psutil.Process(pid)
    except Exception:
        return None
    for candidate in [process] + list(process.parents())[:4]:
        try:
            for argument in candidate.cmdline():
                if argument.startswith(CDP_FLAG):
                    port = argument[len(CDP_FLAG):].strip()
                    if port.isdigit() and int(port) > 0:
                        return int(port)
        except Exception:
            continue
    return None


def endpoint_for(target: targets.Target) -> "str | None":
    """The CDP endpoint serving this window, or None.

    None is the ordinary answer and not a failure: a browser started normally
    has no debugging port, and the UIA path reads it perfectly well. This only
    ever adds a route, it never removes one.
    """
    if not target.is_browser and "electron" not in target.process.lower():
        # Electron and WebView2 windows are Chromium too, and they do not
        # report as browsers. They are reachable the same way when their host
        # opted in, which is why this is not gated on `is_browser` alone.
        if target.window_class != "Chrome_WidgetWin_1":
            return None
    port = _debug_port(target.pid)
    if port is None:
        return None
    endpoint = f"http://127.0.0.1:{port}"
    try:
        _http(endpoint, "/json/version")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return endpoint


def _page_for(endpoint: str, target: targets.Target) -> dict:
    """Which tab this window is showing.

    Matched on title, because that is the only thing a window and a CDP target
    share. Ambiguity is refused rather than guessed for the same reason it is
    everywhere else here: two tabs with one title is exactly when picking the
    first one types into the wrong page.
    """
    pages = [p for p in _http(endpoint, "/json/list") if p.get("type") == "page"]
    if not pages:
        raise Unavailable("that browser has no pages open over the protocol")

    # A browser window is titled "<page title> - <browser>"; take the page's
    # own title as the prefix to match on.
    window_title = (target.title or "").strip()
    matches = [p for p in pages
               if p.get("title") and window_title.startswith(p["title"])]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise Unavailable(
            f"{len(matches)} open tabs are titled {matches[0]['title']!r}, so "
            "which one this window is showing cannot be decided from the "
            "title alone. Read this window through the accessibility tree "
            "instead.")
    if len(pages) == 1:
        return pages[0]
    raise Unavailable(
        f"none of the {len(pages)} open tabs match this window's title "
        f"{window_title!r}")


# ── One connection to one page ──────────────────────────────────────────────

class Page:
    """A protocol session against a single tab.

    Not pooled and not long-lived on purpose. A socket held open across turns
    is a socket that has to be reconciled with a tab that may have navigated,
    closed, or been moved to another window, and the reconciliation is more
    machinery than reconnecting costs — the handshake is a few milliseconds
    against a local port.
    """

    def __init__(self, ws_url: str) -> None:
        import websocket

        # `suppress_origin` matters. Chromium rejects a WebSocket carrying an
        # Origin header unless it was launched with --remote-allow-origins,
        # and requiring that flag would mean asking users to relax a
        # cross-origin protection to use this. Sending no Origin at all is
        # what a native client does and needs no flag.
        self._ws = websocket.create_connection(
            ws_url, timeout=TIMEOUT_S, suppress_origin=True)
        self._id = 0
        self._lock = threading.Lock()

    def send(self, method: str, params: "dict | None" = None) -> dict:
        with self._lock:
            self._id += 1
            message_id = self._id
            self._ws.send(json.dumps(
                {"id": message_id, "method": method, "params": params or {}}))
            while True:
                message = json.loads(self._ws.recv())
                # Events arrive interleaved with replies and are not wanted
                # here; the reply is the one carrying our id.
                if message.get("id") != message_id:
                    continue
                if "error" in message:
                    raise Unavailable(
                        f"{method} failed: {message['error'].get('message')}")
                return message.get("result", {})

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    def __enter__(self) -> "Page":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class Link:
    """A connection to one page that reopens itself when it is needed again.

    Sockets are not held across turns. A socket kept open has to be reconciled
    with a tab that may have navigated, closed, or moved to another window,
    and that reconciliation is more machinery than reconnecting costs — the
    handshake is a few milliseconds against a local port.

    So a read opens, reads, and drops the socket; the element refs it handed
    out keep working, because acting on one opens a new socket against the
    same tab. A ref survives the turn boundary exactly as a UIA element does,
    which is the property that lets the rest of the package stay ignorant of
    which backend it is talking to.
    """
    __slots__ = ("_url", "_page", "_lock")

    def __init__(self, ws_url: str) -> None:
        self._url = ws_url
        self._page: "Page | None" = None
        self._lock = threading.Lock()

    def send(self, method: str, params: "dict | None" = None) -> dict:
        with self._lock:
            for final in (False, True):
                try:
                    if self._page is None:
                        self._page = Page(self._url)
                    return self._page.send(method, params)
                except Unavailable:
                    # The protocol answered and said no. Reconnecting would
                    # ask the same question and get the same answer.
                    raise
                except Exception:
                    self.close_locked()
                    if final:
                        raise
        raise Unavailable("the page could not be reached")   # pragma: no cover

    def close_locked(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None

    def close(self) -> None:
        with self._lock:
            self.close_locked()


class _Node:
    """One DOM element, wearing the interface `actions.py` already calls.

    This is what makes the adapter an adapter rather than a second
    implementation. `actions.invoke` calls `control.GetInvokePattern().Invoke()`
    and does not care whether that reaches a UIA provider or a page; the
    verifier calls `GetValuePattern().Value` and gets a live read either way.

    Every call resolves the node fresh from its backend id. Holding a
    JavaScript object reference across calls would be faster and would break
    the moment the page re-rendered — a React list that re-keys invalidates
    every object id it handed out, and the failure is a stale reference
    silently pointing at a detached node.
    """
    __slots__ = ("_link", "_backend_id")

    def __init__(self, link: Link, backend_id: int) -> None:
        self._link = link
        self._backend_id = backend_id

    def _object_id(self) -> str:
        return self._link.send(
            "DOM.resolveNode", {"backendNodeId": self._backend_id}
        )["object"]["objectId"]

    def _call(self, body: str, *, returns: bool = False):
        result = self._link.send("Runtime.callFunctionOn", {
            "objectId": self._object_id(),
            "functionDeclaration": f"function() {{ {body} }}",
            "returnByValue": returns,
        })
        return result.get("result", {}).get("value") if returns else None

    # ── The pattern interface ───────────────────────────────────────────
    #
    # Instances, never classes. Returning the class looks identical until
    # something reads a property off it: `_Value.Value` on the CLASS hands
    # back the property descriptor object rather than the page's value, so
    # verification compared a write against `<property object at 0x...>` and
    # every check came back unconfirmed. It never raised — the shape was
    # right and the content was nonsense.
    def GetInvokePattern(self):
        return _Invoke(self)

    def GetValuePattern(self):
        return _Value(self)

    def GetTogglePattern(self):
        return _Toggle(self)

    def GetSelectionItemPattern(self):
        return _Clickable(self)

    def GetExpandCollapsePattern(self):
        return _Clickable(self)

    def GetTextPattern(self):
        return _Text(self)

    def bounds(self) -> "tuple[int, int, int, int]":
        try:
            model = self._link.send("DOM.getBoxModel",
                                    {"backendNodeId": self._backend_id})
            quad = model["model"]["border"]
        except Exception:
            return (0, 0, 0, 0)
        xs, ys = quad[0::2], quad[1::2]
        return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


class _Invoke:
    __slots__ = ("_node",)

    def __init__(self, node): self._node = node

    def Invoke(self):
        self._node._call("this.click();")


class _Clickable(_Invoke):
    """Select and Expand are both a click on the web. Naming them separately
    matters to the model choosing an action; the delivery is the same."""

    def Select(self):
        self.Invoke()

    def Expand(self):
        self.Invoke()


class _Value:
    __slots__ = ("_node",)

    def __init__(self, node): self._node = node

    @property
    def Value(self):
        return self._node._call(
            "return this.value ?? this.textContent ?? '';", returns=True) or ""

    def SetValue(self, text):
        # Assigning `.value` does not tell the page anything happened, and a
        # modern page is listening rather than polling. Without the events a
        # React or Vue field shows the new text while its own state still
        # holds the old — the write lands visually and is discarded on submit.
        # The native setter is used because frameworks replace the property on
        # the element instance to intercept exactly this.
        self._node._call(
            "this.focus();"
            "const d = Object.getOwnPropertyDescriptor("
            "  Object.getPrototypeOf(this), 'value');"
            f"if (d && d.set) d.set.call(this, {json.dumps(text)});"
            f"else this.value = {json.dumps(text)};"
            "this.dispatchEvent(new Event('input', {bubbles: true}));"
            "this.dispatchEvent(new Event('change', {bubbles: true}));")


class _Toggle:
    __slots__ = ("_node",)

    def __init__(self, node): self._node = node

    @property
    def ToggleState(self):
        return "On" if self._node._call("return !!this.checked;",
                                        returns=True) else "Off"

    def Toggle(self):
        self._node._call("this.click();")


class _Text:
    __slots__ = ("_node",)

    def __init__(self, node): self._node = node

    @property
    def DocumentRange(self):
        return self._node._call("return this.textContent ?? '';", returns=True)


# ── Reading ─────────────────────────────────────────────────────────────────

def read(target: targets.Target) -> tree.Snapshot:
    """The page as a Snapshot, in the same shape a UIA read produces.

    Raises `Unavailable` when this window cannot be reached over the protocol,
    which the caller turns into "use the accessibility tree instead" rather
    than into a failure.
    """
    endpoint = endpoint_for(target)
    if endpoint is None:
        raise Unavailable(
            "That browser was not started with --remote-debugging-port, so "
            "its pages cannot be read directly. The accessibility tree still "
            "works and is what this window will be read with.")

    page_info = _page_for(endpoint, target)
    link = Link(page_info["webSocketDebuggerUrl"])
    try:
        link.send("Accessibility.enable")
        nodes = link.send("Accessibility.getFullAXTree").get("nodes", [])

        elements: list[tree.Element] = []
        named_already: set[str] = set()
        depths = _depths(nodes)
        bounds_left = MAX_BOUNDS_LOOKUPS

        for node in nodes:
            role = (node.get("role") or {}).get("value") or ""
            if role in SKIP_ROLES:
                continue
            if node.get("ignored"):
                continue
            mapped = ROLES.get(role)
            if mapped is None:
                continue
            our_role, patterns = mapped
            backend_id = node.get("backendDOMNodeId")
            if backend_id is None:
                continue

            name = ((node.get("name") or {}).get("value") or "")[:200]
            # A button's label is also a StaticText child carrying the same
            # words, and an input's value shows up twice for the same reason.
            # Keeping both doubles the read to say nothing — this is the same
            # judgement `NOISE_TYPES` makes about UIA's decorative nodes,
            # applied where the DOM makes it.
            if our_role == "Text" and name and name in named_already:
                continue
            named_already.add(name)

            handle = _Node(link, backend_id)
            value = ((node.get("value") or {}).get("value") or "")
            box = (0, 0, 0, 0)
            if patterns and bounds_left > 0:
                box = handle.bounds()
                bounds_left -= 1

            elements.append(tree.Element(
                ref=f"e{len(elements) + 1}",
                role=our_role,
                name=name,
                value=str(value)[:400],
                patterns=list(patterns),
                bounds=box,
                enabled=not _disabled(node),
                depth=depths.get(node.get("nodeId"), 0),
                hwnd=target.hwnd,
                control=handle,
            ))

        return tree.Snapshot(handle=target.handle, title=target.title,
                             elements=elements)
    finally:
        # The socket is dropped and the `_Node`s outlive it, which is
        # deliberate: they are identifiers, not connections. Acting on one
        # reopens, so a ref stays usable across the turn boundary in exactly
        # the way a UIA element does.
        link.close()


def _depths(nodes: list) -> dict:
    """Nesting depth per node, so a page renders with the same shape a window
    does. The AX tree gives parent/child by id and no depth of its own."""
    children = {n.get("nodeId"): n.get("childIds") or [] for n in nodes}
    roots = set(children) - {c for kids in children.values() for c in kids}
    depths: dict = {}
    stack = [(root, 0) for root in roots]
    while stack:
        node_id, depth = stack.pop()
        if node_id in depths:
            continue
        depths[node_id] = depth
        stack.extend((child, depth + 1) for child in children.get(node_id, []))
    return depths


def _disabled(node: dict) -> bool:
    for prop in node.get("properties") or []:
        if prop.get("name") == "disabled":
            return bool((prop.get("value") or {}).get("value"))
    return False
