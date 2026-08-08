"""Tests for the scoring rules and the vintage store.

The scoring rules are checked against closed-form answers, not against
themselves. If CRPS is subtly wrong every score in the archive is wrong in the
same direction and nobody finds out for decades.
"""

from __future__ import annotations

import numpy as np
import pytest

from popmodel.track import scoring, vintage


# --------------------------------------------------------------------- scoring


def test_crps_from_samples_matches_the_closed_form_for_a_normal():
    rng = np.random.default_rng(11)
    mean, sd, obs = 2.0, 0.5, 2.3
    samples = rng.normal(mean, sd, 200_000)
    assert scoring.crps_from_samples(samples, obs) == pytest.approx(
        scoring.crps_normal(mean, sd, obs), rel=0.01
    )


def test_crps_is_zero_for_a_perfect_certain_prediction():
    assert scoring.crps_from_samples(np.full(100, 3.0), 3.0) == pytest.approx(0.0)


def test_crps_punishes_a_confidently_wrong_prediction_more_than_a_vague_one():
    obs = 5.0
    confident_wrong = scoring.crps_from_samples(np.full(1000, 1.0), obs)
    vague = scoring.crps_from_samples(np.linspace(0.0, 6.0, 1000), obs)
    assert confident_wrong > vague


def test_crps_punishes_needless_width():
    """Two predictions centred on the truth; the narrower one must win.

    This is the property that makes the rule proper - you cannot buy safety by
    widening your interval.
    """
    rng = np.random.default_rng(3)
    obs = 0.0
    tight = scoring.crps_from_samples(rng.normal(0, 0.1, 50_000), obs)
    loose = scoring.crps_from_samples(rng.normal(0, 2.0, 50_000), obs)
    assert tight < loose


def test_crps_normal_grows_with_distance():
    a = scoring.crps_normal(0.0, 1.0, 0.5)
    b = scoring.crps_normal(0.0, 1.0, 3.0)
    assert b > a > 0


def test_pinball_loss_is_asymmetric_in_the_right_direction():
    # A 90th percentile that the observation exceeds should hurt more than one
    # the observation falls short of by the same amount.
    over = scoring.pinball_loss({0.9: 10.0}, 12.0)
    under = scoring.pinball_loss({0.9: 10.0}, 8.0)
    assert over > under


def test_pinball_loss_is_zero_when_the_median_is_exactly_right():
    assert scoring.pinball_loss({0.5: 7.0}, 7.0) == pytest.approx(0.0)


def test_interval_coverage():
    q = {0.05: 1.0, 0.5: 2.0, 0.95: 3.0}
    assert scoring.interval_coverage(q, 2.5, 0.05, 0.95)
    assert not scoring.interval_coverage(q, 3.5, 0.05, 0.95)
    with pytest.raises(KeyError):
        scoring.interval_coverage(q, 2.5, 0.1, 0.9)


# --------------------------------------------------------------------- vintages


def a_quantity(**kw):
    base = dict(
        id="world_2100",
        description="World population on 1 January 2100",
        unit="people",
        resolution_date="2100",
        source_of_truth="UN WPP estimates for 2100",
        is_project_claim=True,
        kind="samples",
        samples=[1.0, 2.0, 3.0],
    )
    base.update(kw)
    return vintage.Quantity(**base)


def test_a_quantity_must_name_when_and_how_it_resolves():
    with pytest.raises(ValueError, match="resolution date"):
        a_quantity(resolution_date="")
    with pytest.raises(ValueError, match="name the dataset"):
        a_quantity(source_of_truth="")


def test_a_point_prediction_must_explain_itself():
    with pytest.raises(ValueError, match="proper rule"):
        a_quantity(kind="point", point=1.0, samples=None, notes="")
    a_quantity(kind="point", point=1.0, samples=None, notes="deterministic engine run")


def test_kind_must_match_what_was_supplied():
    with pytest.raises(ValueError, match="no quantiles"):
        a_quantity(kind="quantiles", samples=None)


def test_writing_a_vintage_twice_raises(tmp_path):
    v = vintage.new_vintage(
        "test", "Test", model_name="t", model_phase=2, data_provenance={"revision": "WPP2024"}
    )
    v.quantities.append(a_quantity())
    vintage.write(v, root=tmp_path)
    with pytest.raises(vintage.VintageExists):
        vintage.write(v, root=tmp_path)


def test_an_empty_vintage_is_refused(tmp_path):
    v = vintage.new_vintage(
        "empty", "Empty", model_name="t", model_phase=2, data_provenance={}
    )
    with pytest.raises(ValueError, match="predicts nothing"):
        vintage.write(v, root=tmp_path)


def test_a_written_vintage_round_trips_and_verifies(tmp_path):
    v = vintage.new_vintage(
        "rt", "Round trip", model_name="t", model_phase=2, data_provenance={"revision": "WPP2024"}
    )
    v.quantities.append(a_quantity())
    vintage.write(v, root=tmp_path)
    loaded = vintage.load(v.vintage_id, root=tmp_path)
    assert loaded["quantities"][0]["samples"] == [1.0, 2.0, 3.0]
    assert loaded["data"]["revision"] == "WPP2024"
    assert all(ok for _, ok in vintage.verify_all(root=tmp_path))


def test_tampering_with_a_vintage_is_detected(tmp_path):
    v = vintage.new_vintage(
        "tamper", "Tamper", model_name="t", model_phase=2, data_provenance={}
    )
    v.quantities.append(a_quantity())
    d = vintage.write(v, root=tmp_path)
    body = (d / "prediction.json").read_text(encoding="utf-8")
    (d / "prediction.json").write_text(body.replace("3.0", "9.0"), encoding="utf-8")
    assert not all(ok for _, ok in vintage.verify_all(root=tmp_path))
