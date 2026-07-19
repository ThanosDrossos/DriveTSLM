import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.citations import validate, number_supported, flatten_numbers  # noqa: E402

T2 = {"channels": {"accel_x": {"peak_abs_dev": 5.23, "peak_t": 8.13,
                               "integrated_delta_v_kmh": -23.4}}}
T3 = {"detections": [{"type": "impact_spike", "magnitude": 3.47, "peak_t": 8.13,
                      "criterion": "|a-baseline| > 2.5 g for >= 2 samples"}],
      "n_detections": 2}
RESULTS = {"T2": T2, "T3": T3}


def test_valid_citation_with_rounding():
    r = validate("The peak was [5.2 g at t=8.13 s](T2).", RESULTS)
    assert r.citations[0].status == "valid"
    assert r.fully_grounded


def test_rounding_must_be_consistent():
    # 5.23 rounds to 5.2 (ok) but NOT to 5.3
    r = validate("[peak of 5.3 g](T2)", RESULTS)
    assert r.citations[0].status == "invalid"
    assert any(u.startswith("5.3") for u in r.citations[0].unmatched)


def test_coarse_rounding_ok():
    # "3 g" is a fair statement of 3.47 at integer precision
    r = validate("[a roughly 3 g spike](T3)", RESULTS)
    assert r.citations[0].status == "valid"


def test_coarse_rounding_wrong():
    r = validate("[a roughly 4 g spike](T3)", RESULTS)
    assert r.citations[0].status == "invalid"


def test_unit_conversion_kmh_ms():
    # -23.4 km/h = -6.5 m/s
    r = validate("[speed change of 6.5 m/s](T2)", RESULTS)
    assert r.citations[0].status == "valid"


def test_unit_conversion_mph():
    # 23.4 km/h = 14.54 mph -> "about 15 mph" valid at integer precision
    r = validate("[about 15 mph](T2)", RESULTS)
    assert r.citations[0].status == "valid"


def test_unknown_tool_id():
    r = validate("[5.2 g](T9)", RESULTS)
    assert r.citations[0].status == "unknown_tool_id"
    assert not r.fully_grounded


def test_wrong_tool_id_number_not_there():
    # 5.2 g appears in T2 but not T3: citing T3 must fail
    r = validate("[5.2 g peak](T3)", RESULTS)
    assert r.citations[0].status == "invalid"


def test_uncited_quantitative_claim_flagged():
    r = validate("The vehicle hit a wall at 45 km/h and stopped.", RESULTS)
    assert r.n_uncited >= 1
    assert not r.fully_grounded


def test_uncited_count_noun_flagged():
    r = validate("There were two impacts in the window.", RESULTS)
    assert r.n_uncited == 1


def test_word_number_in_citation():
    r = validate("[two impact spikes were detected](T3)", RESULTS)
    assert r.citations[0].status == "valid"  # n_detections == 2


def test_qualitative_citation_ok():
    r = validate("[the vehicle decelerated sharply](T2)", RESULTS)
    assert r.citations[0].status == "valid"
    assert r.fully_grounded


def test_identifiers_not_treated_as_numbers():
    r = validate("[event vz_12345 shows a 5.2 g peak](T2) on accel_x at T2.", RESULTS)
    assert r.citations[0].status == "valid"
    assert r.n_uncited == 0


def test_negative_sign_and_unicode_minus():
    r = validate("[delta-v of −23.4 km/h](T2)", RESULTS)
    assert r.citations[0].status == "valid"


def test_flatten_includes_string_numbers():
    vals = flatten_numbers(T3)
    assert 2.5 in vals and 3.47 in vals


def test_number_supported_precision():
    assert number_supported("8.1", {8.13})
    assert not number_supported("8.2", {8.13})
