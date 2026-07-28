from strategy.pr_diff_cache import PRDiffSummaryCache, summarize_unified_diff


DIFF_TEXT = """diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -1 +1,2 @@
-old = 1
+new = 1
+added = True
"""


def test_summarize_unified_diff_extracts_file_counts_and_bullets():
    summary = summarize_unified_diff("repo", 12, "abc123", DIFF_TEXT)

    assert summary.changed_files == ("foo.py",)
    assert summary.files[0].additions == 2
    assert summary.files[0].deletions == 1
    assert summary.files[0].bullets[0].startswith("removes:")


def test_pr_diff_cache_reuses_same_head_sha_and_invalidates_new_sha(tmp_path):
    cache = PRDiffSummaryCache(tmp_path / "pr-cache.json")

    first = cache.get_or_create("repo", 12, "abc123", DIFF_TEXT)
    second = cache.get_or_create("repo", 12, "abc123", "diff --git a/bar.py b/bar.py")
    third = cache.get_or_create("repo", 12, "def456", "diff --git a/bar.py b/bar.py")

    assert second.digest == first.digest
    assert third.digest != first.digest
