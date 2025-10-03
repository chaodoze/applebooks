"""Test suite for geocoding resolver with ground truth fixtures."""

import pytest

# Ground truth test fixtures based on known locations
GROUND_TRUTHS = [
    {
        "test_id": "fountain_factory",
        "place_name": "Apple factory",
        "note": "Fountain, Colorado manufacturing facility, 1980s",
        "story_context": "Apple established a manufacturing facility in Fountain, Colorado in the early 1980s to produce Apple II computers.",
        "expected_address": "702 Bandley Dr, Fountain, CO 80817",
        "expected_lat": 38.6822,  # Approximate
        "expected_lon": -104.7011,  # Approximate
        "expected_precision": "address",
        "min_confidence": 0.8,
        "is_residence": False,
    },
    {
        "test_id": "crist_drive_residence",
        "place_name": "Patty Jobs residence",
        "note": "Los Altos, California - where Patty Jobs helped assemble circuit boards in the garage, late 1970s",
        "story_context": "In the late 1970s, Steve Jobs' sister Patty helped assemble Apple circuit boards at the family home in Los Altos.",
        "expected_address": "2066 Crist Dr, Los Altos, CA 94024",
        "expected_lat": 37.3688,  # Approximate
        "expected_lon": -122.1088,  # Approximate
        "expected_precision": "address",
        "min_confidence": 0.8,
        "is_residence": True,
    },
    {
        "test_id": "cupertino_hq",
        "place_name": "Apple headquarters",
        "note": "Cupertino, California - One Infinite Loop campus",
        "story_context": "Apple's headquarters at One Infinite Loop in Cupertino served as the company's main campus from 1993 to 2017.",
        "expected_address": "1 Infinite Loop, Cupertino, CA 95014",
        "expected_lat": 37.3318,
        "expected_lon": -122.0312,
        "expected_precision": "address",
        "min_confidence": 0.9,
        "is_residence": False,
    },
    {
        "test_id": "fremont_factory",
        "place_name": "Fremont manufacturing plant",
        "note": "Fremont, California - early Macintosh production facility, 1984",
        "story_context": "Apple opened a highly automated factory in Fremont, California in 1984 to manufacture the original Macintosh computer.",
        "expected_address": "6400 Dumbarton Cir, Fremont, CA 94555",
        "expected_lat": 37.5485,
        "expected_lon": -122.0312,
        "expected_precision": "address",
        "min_confidence": 0.7,
        "is_residence": False,
    },
]


@pytest.fixture
def ground_truth_fixtures():
    """Provide ground truth test cases."""
    return GROUND_TRUTHS


def test_ground_truth_structure(ground_truth_fixtures):
    """Ensure all ground truth fixtures have required fields."""
    required_fields = [
        "test_id",
        "place_name",
        "note",
        "story_context",
        "expected_address",
        "expected_precision",
        "min_confidence",
    ]

    for truth in ground_truth_fixtures:
        for field in required_fields:
            assert field in truth, f"Missing field '{field}' in {truth['test_id']}"


@pytest.mark.skip(reason="Resolution pipeline not yet implemented")
def test_fountain_factory_resolution():
    """
    Test: Resolve 'Apple factory in Fountain, Colorado' to precise address.

    Expected: 702 Bandley Dr, Fountain, CO 80817
    """
    from abxgeo.resolver import resolve_location

    loc = {
        "place_name": "Apple factory",
        "note": "Fountain, Colorado manufacturing facility, 1980s",
    }

    story_context = "Apple established a manufacturing facility in Fountain, Colorado in the early 1980s to produce Apple II computers."

    result = resolve_location(loc, story_context, email="test@example.com", cache_conn=None, api_key="test")

    assert result is not None
    assert "702 Bandley Dr" in result["resolved_address"]
    assert result["resolution_confidence"] >= 0.8
    assert result["resolved_precision"] == "address"


@pytest.mark.skip(reason="Resolution pipeline not yet implemented")
def test_crist_drive_residence_resolution():
    """
    Test: Resolve 'Patty Jobs residence in Los Altos' to precise address.

    Expected: 2066 Crist Dr, Los Altos, CA 94024
    Flags: is_residence = True
    """
    from abxgeo.resolver import resolve_location

    loc = {
        "place_name": "Patty Jobs residence",
        "note": "Los Altos, California - where Patty Jobs helped assemble circuit boards in the garage, late 1970s",
    }

    story_context = "In the late 1970s, Steve Jobs' sister Patty helped assemble Apple circuit boards at the family home in Los Altos."

    result = resolve_location(loc, story_context, email="test@example.com", cache_conn=None, api_key="test")

    assert result is not None
    assert "2066 Crist Dr" in result["resolved_address"]
    assert result["resolution_confidence"] >= 0.8
    assert result["resolved_precision"] == "address"

    # Check that residence is flagged
    import json

    source = json.loads(result["resolution_source"])
    assert source.get("is_residence") is True


@pytest.mark.skip(reason="Resolution pipeline not yet implemented")
def test_all_ground_truths(ground_truth_fixtures):
    """
    Test all ground truth fixtures for resolution accuracy.

    This is the comprehensive validation test that will run once
    the resolution pipeline is implemented.
    """
    from abxgeo.resolver import resolve_location

    results = []

    for truth in ground_truth_fixtures:
        loc = {
            "place_name": truth["place_name"],
            "note": truth["note"],
        }

        result = resolve_location(
            loc,
            truth["story_context"],
            email="test@example.com",
            cache_conn=None,
            api_key="test",
        )

        # Validate result
        passed = True
        issues = []

        if not result:
            passed = False
            issues.append("No result returned")
        else:
            # Check address match (fuzzy - just check street name presence)
            expected_parts = truth["expected_address"].split(",")
            street = expected_parts[0].strip()
            if street not in result.get("resolved_address", ""):
                passed = False
                issues.append(f"Address mismatch: expected '{street}' in '{result.get('resolved_address')}'")

            # Check confidence
            if result.get("resolution_confidence", 0) < truth["min_confidence"]:
                passed = False
                issues.append(
                    f"Low confidence: {result.get('resolution_confidence')} < {truth['min_confidence']}"
                )

            # Check precision
            if result.get("resolved_precision") != truth["expected_precision"]:
                passed = False
                issues.append(
                    f"Precision mismatch: {result.get('resolved_precision')} != {truth['expected_precision']}"
                )

            # Check residence flag if applicable
            if "is_residence" in truth:
                import json

                source = json.loads(result.get("resolution_source", "{}"))
                if source.get("is_residence") != truth["is_residence"]:
                    passed = False
                    issues.append(
                        f"Residence flag mismatch: {source.get('is_residence')} != {truth['is_residence']}"
                    )

        results.append(
            {
                "test_id": truth["test_id"],
                "passed": passed,
                "issues": issues,
                "result": result,
            }
        )

    # Assert all passed
    failed = [r for r in results if not r["passed"]]
    if failed:
        failure_report = "\n".join(
            [f"{r['test_id']}: {', '.join(r['issues'])}" for r in failed]
        )
        pytest.fail(f"{len(failed)}/{len(results)} ground truth tests failed:\n{failure_report}")


if __name__ == "__main__":
    # Allow running tests directly for debugging
    print("Ground Truth Test Fixtures:")
    for truth in GROUND_TRUTHS:
        print(f"\n{truth['test_id']}:")
        print(f"  Place: {truth['place_name']}")
        print(f"  Note: {truth['note']}")
        print(f"  Expected: {truth['expected_address']}")
        print(f"  Precision: {truth['expected_precision']}")
        print(f"  Min Confidence: {truth['min_confidence']}")
        if truth.get("is_residence"):
            print(f"  ⚠️  Residence: {truth['is_residence']}")
