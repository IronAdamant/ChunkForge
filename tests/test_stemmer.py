"""Tests for stele_context.stemmer: stem() and split_identifier()."""

from __future__ import annotations

from stele_context.stemmer import split_identifier, stem


# ---------------------------------------------------------------------------
# stem()
# ---------------------------------------------------------------------------


class TestStemStep1a:
    def test_sses_suffix(self) -> None:
        # sses -> ss; step5b later collapses -ss -> -s, so result is "cares"
        assert stem("caresses") == "cares"

    def test_ies_suffix(self) -> None:
        assert stem("ponies") == "poni"

    def test_ies_short(self) -> None:
        assert stem("ties") == "ti"

    def test_s_suffix(self) -> None:
        assert stem("cats") == "cat"

    def test_ss_unchanged(self) -> None:
        assert stem("stress") == "stress"


class TestStemStep1b:
    def test_eed_with_measure_gt0(self) -> None:
        assert stem("agreed") == "agre"

    def test_eed_no_change_when_measure_0(self) -> None:
        assert stem("feed") == "feed"

    def test_ed_with_vowel_in_stem(self) -> None:
        assert stem("plastered") == "plaster"

    def test_ed_no_vowel_in_stem(self) -> None:
        assert stem("bled") == "bled"

    def test_ing_double_consonant_collapse(self) -> None:
        assert stem("hopping") == "hop"

    def test_ing_cvc_adds_e(self) -> None:
        assert stem("filing") == "file"

    def test_ing_falling(self) -> None:
        assert stem("falling") == "fall"

    def test_ing_hissing(self) -> None:
        assert stem("hissing") == "hiss"


class TestStemStep1c:
    def test_y_to_i_when_vowel_in_stem(self) -> None:
        assert stem("happy") == "happi"

    def test_y_unchanged_no_vowel_in_stem(self) -> None:
        assert stem("sky") == "sky"

    def test_y_to_i_multiple_vowels(self) -> None:
        assert stem("early") == "earli"


class TestStemShortWords:
    def test_length_1(self) -> None:
        assert stem("a") == "a"

    def test_length_2(self) -> None:
        assert stem("at") == "at"

    def test_length_2_uppercase_lowercased(self) -> None:
        assert stem("BE") == "be"


class TestStemAlreadyStemmed:
    def test_stem_word(self) -> None:
        assert stem("stem") == "stem"

    def test_run_word(self) -> None:
        assert stem("run") == "run"


class TestStemEdgeInputs:
    def test_empty_string(self) -> None:
        assert stem("") == ""

    def test_whitespace_only(self) -> None:
        assert stem("   ") == ""

    def test_leading_trailing_whitespace_stripped(self) -> None:
        assert stem("  cats  ") == "cat"

    def test_uppercase_lowercased(self) -> None:
        assert stem("RUNNING") == "run"

    def test_mixed_case_lowercased(self) -> None:
        assert stem("Running") == "run"


class TestStemProgrammingWords:
    def test_running(self) -> None:
        assert stem("running") == "run"

    def test_connections(self) -> None:
        assert stem("connections") == "connect"

    def test_hopeful(self) -> None:
        assert stem("hopeful") == "hope"

    def test_goodness(self) -> None:
        assert stem("goodness") == "good"

    def test_allowance(self) -> None:
        assert stem("allowance") == "allow"

    def test_inference(self) -> None:
        assert stem("inference") == "infer"

    def test_electrical(self) -> None:
        assert stem("electrical") == "electr"

    def test_generalization(self) -> None:
        assert stem("generalization") == "gener"

    def test_stressed(self) -> None:
        assert stem("stressed") == "stress"

    def test_tanned(self) -> None:
        assert stem("tanned") == "tan"


# ---------------------------------------------------------------------------
# split_identifier()
# ---------------------------------------------------------------------------


class TestSplitIdentifierCamelCase:
    def test_simple_camel(self) -> None:
        assert split_identifier("loginHandler") == ["login", "handler"]

    def test_camel_three_parts(self) -> None:
        assert split_identifier("getUserName") == ["get", "user", "name"]

    def test_camel_with_acronym(self) -> None:
        assert split_identifier("getHTTPSConnection") == ["get", "https", "connection"]


class TestSplitIdentifierPascalCase:
    def test_pascal_acronym(self) -> None:
        assert split_identifier("HTMLParser") == ["html", "parser"]

    def test_pascal_simple(self) -> None:
        assert split_identifier("UserAccount") == ["user", "account"]

    def test_all_caps(self) -> None:
        assert split_identifier("HTTP") == ["http"]


class TestSplitIdentifierSnakeCase:
    def test_snake_three_parts(self) -> None:
        assert split_identifier("get_user_name") == ["get", "user", "name"]

    def test_snake_two_parts(self) -> None:
        assert split_identifier("is_valid") == ["is", "valid"]

    def test_kebab_case(self) -> None:
        assert split_identifier("get-user-name") == ["get", "user", "name"]

    def test_leading_underscore(self) -> None:
        assert split_identifier("_private") == ["private"]


class TestSplitIdentifierNumbers:
    def test_version_prefix(self) -> None:
        assert split_identifier("v2API") == ["v", "2", "api"]

    def test_number_in_camel(self) -> None:
        assert split_identifier("base64Encode") == ["base", "64", "encode"]

    def test_number_only(self) -> None:
        assert split_identifier("123") == ["123"]


class TestSplitIdentifierEdgeInputs:
    def test_empty_string(self) -> None:
        assert split_identifier("") == []

    def test_whitespace_only(self) -> None:
        assert split_identifier("   ") == []

    def test_single_word_lowercase(self) -> None:
        assert split_identifier("word") == ["word"]

    def test_single_word_uppercase(self) -> None:
        assert split_identifier("WORD") == ["word"]

    def test_single_word_mixed(self) -> None:
        assert split_identifier("Word") == ["word"]
