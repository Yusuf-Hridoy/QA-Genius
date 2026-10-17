"""Standard factors, and one matrix row turned into a Playwright project."""

import pytest

from qagenius.pairwise import build_matrix, validate
from qagenius.test_matrix_defaults import (
    DEVICE_PROFILES,
    STANDARD_FACTORS,
    STANDARD_RULES,
    playwright_project,
)


def test_the_standard_set_is_a_workable_matrix():
    assert validate(STANDARD_FACTORS, STANDARD_RULES) == []
    matrix = build_matrix(STANDARD_FACTORS, STANDARD_RULES)
    assert matrix.covered_pairs == matrix.valid_pairs
    assert matrix.all_combinations == 4 * 3 * 2


def test_the_standard_rules_keep_firefox_off_mobile():
    matrix = build_matrix(STANDARD_FACTORS, STANDARD_RULES)
    for row in matrix.rows:
        assert not (row[0] == "Firefox" and row[1] in ("Phone", "Tablet"))
        assert not (row[0] == "Edge" and row[1] == "Tablet")


@pytest.mark.parametrize(
    "browser,device,profile",
    [
        ("Chrome", "Desktop", "Desktop Chrome"),
        ("Chrome", "Phone", "Pixel 7"),
        ("Chrome", "Tablet", "Galaxy Tab S4"),
        ("Safari", "Desktop", "Desktop Safari"),
        ("Safari", "Phone", "iPhone 14"),
        ("Safari", "Tablet", "iPad (gen 7)"),
        ("Firefox", "Desktop", "Desktop Firefox"),
        ("Edge", "Desktop", "Desktop Edge"),
    ],
)
def test_every_browser_and_device_maps_to_its_playwright_profile(browser, device, profile):
    project = playwright_project({"Browser": browser, "Device": device})
    assert project["device"] == profile
    assert not project.get("manual_only")


def test_edge_asks_for_its_channel():
    project = playwright_project({"Browser": "Edge", "Device": "Desktop"})
    assert project["channel"] == "msedge"


def test_a_combination_playwright_cannot_drive_is_manual_only():
    """Edge on a phone is a real thing to test, just not with Playwright."""
    project = playwright_project({"Browser": "Edge", "Device": "Phone"})
    assert project["manual_only"] is True
    assert "device" not in project


def test_firefox_on_a_tablet_is_manual_only():
    assert playwright_project({"Browser": "Firefox", "Device": "Tablet"})["manual_only"]


@pytest.mark.parametrize(
    "value,locale",
    [("EN", "en-US"), ("BN", "bn-BD"), ("AR", "ar-SA"), ("DE", "de-DE"),
     ("FR", "fr-FR"), ("ES", "es-ES")],
)
def test_a_language_becomes_a_locale(value, locale):
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Language": value}
    )
    assert project["locale"] == locale


def test_a_value_already_shaped_like_a_locale_is_used_as_written():
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Language": "en-GB"}
    )
    assert project["locale"] == "en-GB"


def test_a_language_we_do_not_know_stays_as_metadata():
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Language": "Klingon"}
    )
    assert "locale" not in project
    assert project["metadata"]["language"] == "Klingon"


def test_signed_in_asks_for_a_stored_session():
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Signed in": "Yes"}
    )
    assert project["storageState"] == "auth/user.json"


def test_signed_out_has_no_stored_session():
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Signed in": "No"}
    )
    assert "storageState" not in project


def test_the_role_names_the_session_file_and_rides_along_as_metadata():
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Role": "Store admin", "Signed in": "Yes"}
    )
    assert project["storageState"] == "auth/store_admin.json"
    assert project["metadata"]["role"] == "Store admin"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_colour_scheme_is_passed_through(scheme):
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Color scheme": scheme.title()}
    )
    assert project["colorScheme"] == scheme


def test_a_factor_we_do_not_know_becomes_metadata():
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Payment method": "Gift card"}
    )
    assert project["metadata"] == {"payment_method": "Gift card"}


def test_the_project_name_reads_as_the_run():
    project = playwright_project(
        {"Browser": "Chrome", "Device": "Desktop", "Signed in": "Yes"}
    )
    assert project["name"] == "Chrome · Desktop · Yes"


def test_a_row_with_no_browser_still_gets_a_profile():
    """A matrix need not have a Browser factor at all."""
    project = playwright_project({"Language": "EN", "Role": "Shopper"})
    assert project["device"] == "Desktop Chrome"
    assert not project.get("manual_only")


def test_the_device_profiles_are_playwright_descriptor_names():
    """Checked against Playwright's published deviceDescriptorsSource.json."""
    assert set(DEVICE_PROFILES.values()) == {
        "Desktop Chrome",
        "Desktop Safari",
        "Desktop Firefox",
        "Desktop Edge",
        "Pixel 7",
        "Galaxy Tab S4",
        "iPhone 14",
        "iPad (gen 7)",
    }
