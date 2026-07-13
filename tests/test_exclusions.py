from open_knowledge_document.exclusions import ExclusionConfig, ExclusionMatcher, ExclusionStore, pattern_matches


def test_pattern_modes_and_invalid_regex() -> None:
    assert pattern_matches("Archive", "Engineering / Archive Folder")
    assert pattern_matches("*/draft/*", "team/draft/proposal")
    assert pattern_matches("re:^internal-", "Internal-only")
    assert not pattern_matches("re:[", "anything")


def test_match_reports_field_and_store_normalizes(tmp_path) -> None:
    config = ExclusionConfig(patterns=[" Draft ", "draft", "re:^secret"])
    store = ExclusionStore(tmp_path / "exclusions.json")
    store.save(config)
    loaded = store.load()
    assert loaded.patterns == ["Draft", "re:^secret"]
    match = ExclusionMatcher(loaded).match({"title": "Secret roadmap", "path": ["Product"]})
    assert match is not None
    assert match.field == "title"
    assert match.pattern == "re:^secret"


def test_disabled_config_does_not_match() -> None:
    matcher = ExclusionMatcher(ExclusionConfig(enabled=False, patterns=["secret"]))
    assert matcher.match({"title": "secret"}) is None
