from scripts.clear_database import TARGET_COLLECTIONS, format_summary


def test_clear_database_targets_only_app_collections() -> None:
    assert TARGET_COLLECTIONS == (
        "runs",
        "episodes",
        "run_items",
        "transcripts",
        "leads",
    )


def test_clear_database_summary_formats_counts() -> None:
    summary = format_summary(
        {
            "runs": 2,
            "episodes": 5,
            "run_items": 10,
            "transcripts": 5,
            "leads": 5,
        },
    )

    assert summary == "runs=2, episodes=5, run_items=10, transcripts=5, leads=5"
