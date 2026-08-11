"""Tests for the Web Reach tools (backend/tools.py): fetch_webpage,
fetch_youtube_transcript, fetch_github_repo_info, fetch_rss_feed,
fetch_reddit_thread, fetch_tweet. All network calls are mocked — these never
hit the real internet in CI. Ported from agent-reach's zero-config channels
(web/YouTube/GitHub/RSS) natively rather than shelling out to its CLI, plus
Reddit/Twitter single-post reads via their stable public endpoints (no
cookies needed, unlike full search/timeline scraping).
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

import tools


# ── fetch_webpage ────────────────────────────────────────────────────────────

class TestFetchWebpage:
    def test_empty_url_returns_error(self):
        assert "Error" in tools.fetch_webpage("")

    @patch("tools.requests.get")
    def test_success_returns_page_text(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text="# Page Title\n\nSome content.")
        mock_get.return_value.raise_for_status = MagicMock()
        result = tools.fetch_webpage("example.com")
        assert "Page Title" in result
        # scheme-less input gets normalized before hitting Jina Reader
        called_url = mock_get.call_args[0][0]
        assert called_url == "https://r.jina.ai/https://example.com"

    @patch("tools.requests.get", side_effect=requests.exceptions.Timeout())
    def test_timeout_returns_clean_message(self, mock_get):
        result = tools.fetch_webpage("https://example.com")
        assert "Timed out" in result

    @patch("tools.requests.get", side_effect=requests.exceptions.ConnectionError())
    def test_connection_error_returns_clean_message(self, mock_get):
        result = tools.fetch_webpage("https://example.com")
        assert "Could not read" in result

    @patch("tools.requests.get")
    def test_blank_page_returns_friendly_message(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text="   ")
        mock_get.return_value.raise_for_status = MagicMock()
        assert "empty" in tools.fetch_webpage("https://example.com").lower()


# ── fetch_youtube_transcript ─────────────────────────────────────────────────

class TestExtractYoutubeId:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ])
    def test_extracts_id(self, url, expected):
        assert tools._extract_youtube_id(url) == expected

    def test_returns_empty_for_garbage(self):
        assert tools._extract_youtube_id("not a youtube url at all") == ""

    def test_returns_empty_for_blank(self):
        assert tools._extract_youtube_id("") == ""


class TestFetchYoutubeTranscript:
    def test_no_video_id_returns_error(self):
        assert "Error" in tools.fetch_youtube_transcript("not a video")

    def test_success_joins_snippet_text(self):
        snippet1 = MagicMock(text="Hello there")
        snippet2 = MagicMock(text="general Kenobi")
        fake_api = MagicMock()
        fake_api.fetch.return_value = [snippet1, snippet2]
        with patch.dict("sys.modules", {"youtube_transcript_api": MagicMock(YouTubeTranscriptApi=MagicMock(return_value=fake_api))}):
            result = tools.fetch_youtube_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert "Hello there general Kenobi" in result

    def test_library_exception_returns_clean_message(self):
        fake_api = MagicMock()
        fake_api.fetch.side_effect = Exception("No transcript available")
        with patch.dict("sys.modules", {"youtube_transcript_api": MagicMock(YouTubeTranscriptApi=MagicMock(return_value=fake_api))}):
            result = tools.fetch_youtube_transcript("dQw4w9WgXcQ")
        assert "Could not fetch transcript" in result


# ── fetch_github_repo_info ───────────────────────────────────────────────────

class TestExtractGithubRepo:
    @pytest.mark.parametrize("s,expected", [
        ("https://github.com/anthropics/claude-code", "anthropics/claude-code"),
        ("https://github.com/anthropics/claude-code.git", "anthropics/claude-code"),
        ("anthropics/claude-code", "anthropics/claude-code"),
    ])
    def test_extracts_repo(self, s, expected):
        assert tools._extract_github_repo(s) == expected

    def test_returns_empty_for_garbage(self):
        assert tools._extract_github_repo("just some text") == ""


class TestFetchGithubRepoInfo:
    def test_no_repo_returns_error(self):
        assert "Error" in tools.fetch_github_repo_info("nonsense")

    @patch("tools.requests.get")
    def test_success_includes_description_and_issues(self, mock_get):
        repo_resp = MagicMock(status_code=200)
        repo_resp.raise_for_status = MagicMock()
        repo_resp.json.return_value = {
            "full_name": "octocat/Hello-World", "description": "My first repo",
            "stargazers_count": 100, "language": "Python",
        }
        issues_resp = MagicMock(ok=True)
        issues_resp.json.return_value = [{"number": 1, "title": "Bug report"}]
        mock_get.side_effect = [repo_resp, issues_resp]

        result = tools.fetch_github_repo_info("octocat/Hello-World")
        assert "My first repo" in result
        assert "#1 Bug report" in result

    @patch("tools.requests.get")
    def test_404_returns_clean_message(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        result = tools.fetch_github_repo_info("octocat/does-not-exist")
        assert "not found" in result.lower()

    @patch("tools.requests.get", side_effect=requests.exceptions.Timeout())
    def test_timeout_returns_clean_message(self, mock_get):
        result = tools.fetch_github_repo_info("octocat/Hello-World")
        assert "Timed out" in result


# ── fetch_rss_feed ───────────────────────────────────────────────────────────

class TestFetchRssFeed:
    def test_empty_url_returns_error(self):
        assert "Error" in tools.fetch_rss_feed("")

    def test_success_lists_entries(self):
        fake_parsed = MagicMock()
        fake_parsed.bozo = False
        fake_parsed.entries = [{"title": "First post", "link": "http://x.com/1"}]
        fake_parsed.feed = {"title": "My Feed"}
        fake_feedparser = MagicMock()
        fake_feedparser.parse.return_value = fake_parsed
        with patch.dict("sys.modules", {"feedparser": fake_feedparser}):
            result = tools.fetch_rss_feed("http://x.com/feed")
        assert "My Feed" in result
        assert "First post" in result

    def test_unparseable_feed_returns_clean_message(self):
        fake_parsed = MagicMock()
        fake_parsed.bozo = True
        fake_parsed.entries = []
        fake_feedparser = MagicMock()
        fake_feedparser.parse.return_value = fake_parsed
        with patch.dict("sys.modules", {"feedparser": fake_feedparser}):
            result = tools.fetch_rss_feed("http://not-a-feed.com")
        assert "Could not parse" in result


# ── fetch_reddit_thread ──────────────────────────────────────────────────────

class TestFetchRedditThread:
    def test_non_reddit_url_returns_error(self):
        assert "Error" in tools.fetch_reddit_thread("https://example.com/thread")

    def test_empty_url_returns_error(self):
        assert "Error" in tools.fetch_reddit_thread("")

    @patch("tools.requests.get")
    def test_success_parses_post_and_comments(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = [
            {"data": {"children": [{"data": {"title": "AMA", "selftext": "Ask me anything"}}]}},
            {"data": {"children": [{"kind": "t1", "data": {"body": "Great question!"}}]}},
        ]
        result = tools.fetch_reddit_thread("https://www.reddit.com/r/test/comments/abc/ama/")
        assert "AMA" in result
        assert "Great question!" in result
        # .json appended correctly, query string stripped
        called_url = mock_get.call_args[0][0]
        assert called_url == "https://www.reddit.com/r/test/comments/abc/ama.json"

    @patch("tools.requests.get")
    def test_malformed_response_returns_clean_message(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"unexpected": "shape"}
        result = tools.fetch_reddit_thread("https://www.reddit.com/r/test/comments/abc/ama/")
        assert "Could not parse" in result


# ── fetch_tweet ──────────────────────────────────────────────────────────────

class TestExtractTweetId:
    def test_extracts_from_status_url(self):
        assert tools._extract_tweet_id("https://x.com/user/status/123456") == "123456"

    def test_bare_id_passes_through(self):
        assert tools._extract_tweet_id("123456") == "123456"

    def test_garbage_returns_empty(self):
        assert tools._extract_tweet_id("not a tweet") == ""


class TestFetchTweet:
    def test_no_id_returns_error(self):
        assert "Error" in tools.fetch_tweet("nonsense")

    @patch("tools.requests.get")
    def test_success_returns_text_and_author(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {
            "text": "hello world", "user": {"screen_name": "jack", "name": "Jack"},
        }
        result = tools.fetch_tweet("https://x.com/jack/status/123456")
        assert "hello world" in result
        assert "@jack" in result

    @patch("tools.requests.get")
    def test_missing_text_key_returns_not_found(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"error": "not found"}
        result = tools.fetch_tweet("123456")
        assert "not found" in result.lower()


# ── execute_tool dispatch ────────────────────────────────────────────────────

class TestExecuteToolDispatch:
    @patch("tools.fetch_webpage", return_value="page content")
    def test_dispatches_fetch_webpage(self, mock_fn):
        assert tools.execute_tool("fetch_webpage", {"url": "https://example.com"}) == "page content"
        mock_fn.assert_called_once_with("https://example.com")

    @patch("tools.fetch_youtube_transcript", return_value="transcript")
    def test_dispatches_fetch_youtube_transcript(self, mock_fn):
        assert tools.execute_tool("fetch_youtube_transcript", {"url": "abc"}) == "transcript"

    @patch("tools.fetch_github_repo_info", return_value="repo info")
    def test_dispatches_fetch_github_repo_info(self, mock_fn):
        assert tools.execute_tool("fetch_github_repo_info", {"repo": "a/b"}) == "repo info"

    @patch("tools.fetch_rss_feed", return_value="feed")
    def test_dispatches_fetch_rss_feed(self, mock_fn):
        assert tools.execute_tool("fetch_rss_feed", {"url": "http://x.com/feed"}) == "feed"

    @patch("tools.fetch_reddit_thread", return_value="thread")
    def test_dispatches_fetch_reddit_thread(self, mock_fn):
        assert tools.execute_tool("fetch_reddit_thread", {"url": "http://reddit.com/x"}) == "thread"

    @patch("tools.fetch_tweet", return_value="tweet")
    def test_dispatches_fetch_tweet(self, mock_fn):
        assert tools.execute_tool("fetch_tweet", {"url": "123"}) == "tweet"

    def test_all_new_tools_registered_in_definitions(self):
        names = {td["function"]["name"] for td in tools.TOOL_DEFINITIONS}
        expected = {
            "fetch_webpage", "fetch_youtube_transcript", "fetch_github_repo_info",
            "fetch_rss_feed", "fetch_reddit_thread", "fetch_tweet",
        }
        assert expected.issubset(names)
