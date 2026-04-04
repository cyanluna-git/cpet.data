from scripts.intake_real_cpet_golden_corpus import _deterministic_even_sample


def test_even_sample_returns_stable_spread() -> None:
    values = [f"id_{idx}" for idx in range(10)]
    selected = _deterministic_even_sample(values, 4)
    assert selected == ["id_0", "id_3", "id_6", "id_9"]


def test_even_sample_caps_at_available_values() -> None:
    values = ["a", "b", "b", "c"]
    selected = _deterministic_even_sample(values, 10)
    assert selected == ["a", "b", "c"]
