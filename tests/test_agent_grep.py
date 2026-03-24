"""Tests for LLM-optimized agent_grep search."""

from __future__ import annotations

import pytest

from stele_context.engine import Stele


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def engine_with_python(tmp_path):
    """Engine with a multi-function Python file indexed."""
    engine = Stele(storage_dir=str(tmp_path / "storage"))
    f = tmp_path / "app.py"
    f.write_text(
        "import os\n"
        "\n"
        "# Configuration constants\n"
        "MAX_RETRIES = 3\n"
        "\n"
        "def connect_db(host, port):\n"
        "    '''Connect to database.'''\n"
        "    retries = MAX_RETRIES\n"
        "    return os.getenv('DB_URL')\n"
        "\n"
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return {'id': user_id}\n"
        "\n"
        "    def delete_user(self, user_id):\n"
        "        # TODO: add logging\n"
        "        pass\n"
    )
    engine.index_documents([str(f)])
    return engine


@pytest.fixture
def engine_with_multi_files(tmp_path):
    """Engine with multiple Python files for dedup/grouping tests."""
    engine = Stele(storage_dir=str(tmp_path / "storage"))
    files = []
    for name in ("auth.py", "api.py", "utils.py"):
        f = tmp_path / name
        f.write_text(
            f"# {name} module\n"
            "import os\n"
            "\n"
            "def validate(data):\n"
            "    if not data:\n"
            "        raise ValueError('empty')\n"
            "    return True\n"
        )
        files.append(str(f))
    engine.index_documents(files)
    return engine


# -- Basic search tests ------------------------------------------------------


class TestBasicSearch:
    def test_text_match(self, engine_with_python):
        result = engine_with_python.agent_grep("MAX_RETRIES")
        assert result["total_matches"] >= 1
        assert result["groups"]
        assert any(
            "MAX_RETRIES" in m["excerpt"]
            for g in result["groups"]
            for m in g["matches"]
        )

    def test_regex_match(self, engine_with_python):
        result = engine_with_python.agent_grep(r"def \w+_user", regex=True)
        assert result["total_matches"] >= 1
        excerpts = [m["excerpt"] for g in result["groups"] for m in g["matches"]]
        assert any("def get_user" in e or "def delete_user" in e for e in excerpts)

    def test_no_matches(self, engine_with_python):
        result = engine_with_python.agent_grep("NONEXISTENT_SYMBOL_XYZ")
        assert result["total_matches"] == 0
        assert result["groups"] == []
        assert "0 match" in result["summary"]

    def test_document_path_filter(self, engine_with_multi_files, tmp_path):
        result = engine_with_multi_files.agent_grep(
            "validate", document_path=str(tmp_path / "auth.py")
        )
        assert result["total_matches"] >= 1
        for g in result["groups"]:
            for m in g["matches"]:
                assert "auth.py" in m["file"]


# -- Scope annotation tests --------------------------------------------------


class TestScopeAnnotation:
    def test_scope_included_by_default(self, engine_with_python):
        result = engine_with_python.agent_grep("user_id")
        for g in result["groups"]:
            for m in g["matches"]:
                assert "scope" in m

    def test_scope_shows_enclosing_function(self, engine_with_python):
        result = engine_with_python.agent_grep("retries")
        scopes = [m.get("scope") for g in result["groups"] for m in g["matches"]]
        # "retries = MAX_RETRIES" is inside connect_db
        assert any(s == "connect_db" for s in scopes if s)

    def test_scope_disabled(self, engine_with_python):
        result = engine_with_python.agent_grep("MAX_RETRIES", include_scope=False)
        for g in result["groups"]:
            for m in g["matches"]:
                assert "scope" not in m


# -- Classification tests ----------------------------------------------------


class TestClassification:
    def test_comment_classified(self, engine_with_python):
        result = engine_with_python.agent_grep("TODO")
        classifications = [
            m.get("classification") for g in result["groups"] for m in g["matches"]
        ]
        assert "comment" in classifications

    def test_import_classified(self, engine_with_python):
        result = engine_with_python.agent_grep("import os")
        classifications = [
            m.get("classification") for g in result["groups"] for m in g["matches"]
        ]
        assert "import" in classifications

    def test_definition_classified(self, engine_with_python):
        result = engine_with_python.agent_grep("def connect_db")
        classifications = [
            m.get("classification") for g in result["groups"] for m in g["matches"]
        ]
        assert "definition" in classifications

    def test_classify_disabled(self, engine_with_python):
        result = engine_with_python.agent_grep("MAX_RETRIES", classify=False)
        for g in result["groups"]:
            for m in g["matches"]:
                assert "classification" not in m


# -- Token budget tests ------------------------------------------------------


class TestTokenBudget:
    def test_budget_limits_output(self, engine_with_multi_files):
        small = engine_with_multi_files.agent_grep("validate", max_tokens=200)
        large = engine_with_multi_files.agent_grep("validate", max_tokens=8000)
        assert small["shown_matches"] <= large["shown_matches"]

    def test_budget_reports_truncation(self, engine_with_multi_files):
        result = engine_with_multi_files.agent_grep("validate", max_tokens=50)
        # Truncated + shown + deduped should account for all matches
        accounted = result["shown_matches"] + result["truncated"]
        assert accounted <= result["total_matches"]

    def test_total_tokens_within_budget(self, engine_with_multi_files):
        budget = 500
        result = engine_with_multi_files.agent_grep("validate", max_tokens=budget)
        # total_tokens should be roughly within budget (some overhead expected)
        assert result["total_tokens"] <= budget


# -- Deduplication tests -----------------------------------------------------


class TestDeduplication:
    def test_identical_lines_collapsed(self, engine_with_multi_files):
        deduped = engine_with_multi_files.agent_grep(
            "raise ValueError", deduplicate=True
        )
        no_dedup = engine_with_multi_files.agent_grep(
            "raise ValueError", deduplicate=False
        )
        # With dedup, there should be fewer or equal matches shown
        assert deduped["shown_matches"] <= no_dedup["shown_matches"]

    def test_dedup_reports_also_in(self, engine_with_multi_files):
        result = engine_with_multi_files.agent_grep(
            "raise ValueError", deduplicate=True
        )
        matches = [m for g in result["groups"] for m in g["matches"]]
        # If there are duplicates, at least one match should have also_in
        collapsed = [m for m in matches if "also_in" in m]
        if result["total_matches"] > len(matches):
            assert collapsed

    def test_dedup_disabled(self, engine_with_multi_files):
        result = engine_with_multi_files.agent_grep(
            "raise ValueError", deduplicate=False
        )
        matches = [m for g in result["groups"] for m in g["matches"]]
        assert all("also_in" not in m for m in matches)


# -- Grouping tests ----------------------------------------------------------


class TestGrouping:
    def test_group_by_file(self, engine_with_multi_files):
        result = engine_with_multi_files.agent_grep(
            "validate", group_by="file", deduplicate=False
        )
        keys = [g["key"] for g in result["groups"]]
        # Each key should be a file path
        assert all(".py" in k for k in keys)

    def test_group_by_classification(self, engine_with_python):
        result = engine_with_python.agent_grep("os", group_by="classification")
        keys = [g["key"] for g in result["groups"]]
        assert all(
            k in ("comment", "import", "definition", "string", "code", "blank")
            for k in keys
        )

    def test_group_by_scope(self, engine_with_python):
        result = engine_with_python.agent_grep(
            "user_id", group_by="scope", deduplicate=False
        )
        # Should have groups for the enclosing functions
        keys = [g["key"] for g in result["groups"]]
        assert keys  # at least one group


# -- Context lines tests -----------------------------------------------------


class TestContextLines:
    def test_context_lines_default_zero(self, engine_with_python):
        result = engine_with_python.agent_grep("MAX_RETRIES")
        for g in result["groups"]:
            for m in g["matches"]:
                # With 0 context, excerpt should be a single line
                assert "\n" not in m["excerpt"]

    def test_context_lines_adds_surrounding(self, engine_with_python):
        result = engine_with_python.agent_grep("MAX_RETRIES", context_lines=1)
        has_multiline = any(
            "\n" in m["excerpt"] for g in result["groups"] for m in g["matches"]
        )
        assert has_multiline


# -- Line number tests -------------------------------------------------------


class TestLineNumbers:
    def test_line_numbers_present(self, engine_with_python):
        result = engine_with_python.agent_grep("connect_db")
        for g in result["groups"]:
            for m in g["matches"]:
                assert "line" in m
                assert isinstance(m["line"], int)
                assert m["line"] >= 1

    def test_line_numbers_ordering(self, engine_with_python):
        result = engine_with_python.agent_grep("user_id", deduplicate=False)
        for g in result["groups"]:
            lines = [m["line"] for m in g["matches"]]
            assert lines == sorted(lines)


# -- Summary format tests ----------------------------------------------------


class TestSummary:
    def test_summary_includes_counts(self, engine_with_python):
        result = engine_with_python.agent_grep("user_id")
        assert "match" in result["summary"]
        assert "file" in result["summary"]

    def test_summary_no_matches(self, engine_with_python):
        result = engine_with_python.agent_grep("ZZZZNOTFOUND")
        assert "0 match" in result["summary"]


# -- Edge cases --------------------------------------------------------------


class TestEdgeCases:
    def test_empty_pattern(self, engine_with_python):
        # Empty string matches everything (substring search)
        result = engine_with_python.agent_grep("")
        assert result["total_matches"] >= 0

    def test_special_regex_chars_in_text_mode(self, engine_with_python):
        # Dots and parens shouldn't be treated as regex
        result = engine_with_python.agent_grep("os.getenv(")
        assert result["total_matches"] >= 0  # should not crash

    def test_empty_index(self, tmp_path):
        engine = Stele(storage_dir=str(tmp_path / "storage"))
        result = engine.agent_grep("anything")
        assert result["total_matches"] == 0
        assert result["groups"] == []
