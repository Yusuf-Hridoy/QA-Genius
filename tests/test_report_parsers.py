"""JUnit XML and Playwright JSON parsing. Uploaded files are treated as hostile."""

import pathlib

import pytest

from qagenius.report_parsers import ReportError, parse_report

FIXTURES = pathlib.Path("tests/fixtures/reports")


def _load(name: str):
    return parse_report(name, (FIXTURES / name).read_bytes())


def _by_name(report, name: str):
    return next(test for test in report.tests if test.name == name)


def test_junit_basic_counts_and_labels() -> None:
    report = _load("junit_basic.xml")

    assert report.label == "junit_basic"
    assert report.format == "junit"
    assert len(report.tests) == 6
    counts = {status: 0 for status in ("passed", "failed", "skipped", "flaky")}
    for test in report.tests:
        counts[test.status] += 1
    assert counts == {"passed": 3, "failed": 2, "skipped": 1, "flaky": 0}


def test_junit_reads_the_failure_message_from_the_attribute() -> None:
    test = _by_name(_load("junit_basic.xml"), "pay with a saved card")

    assert test.status == "failed"
    assert test.message == "Timeout 30000ms exceeded waiting for locator('#pay')"
    assert test.details == "at checkout.spec.ts:42:5"
    assert test.suite == "checkout.spec"
    assert test.test_id == "checkout.spec::pay with a saved card"
    assert test.duration_s == 1.25


def test_junit_falls_back_to_the_first_line_of_the_error_text() -> None:
    test = _by_name(_load("junit_basic.xml"), "apply a promo code")

    assert test.status == "failed"
    assert test.message == "Could not reach the promo service"
    assert "second line of the stack" in test.details


def test_junit_uses_the_parent_suite_name_when_there_is_no_classname() -> None:
    test = _by_name(_load("junit_basic.xml"), "remove the last item")

    assert test.status == "skipped"
    assert test.suite == "cart"
    assert test.message == ""


def test_junit_reads_a_single_testsuite_root() -> None:
    report = _load("junit_single_suite.xml")

    assert len(report.tests) == 2
    assert {test.suite for test in report.tests} == {"search"}
    failed = _by_name(report, "no results shows a hint")
    assert failed.status == "failed"
    assert failed.message == "Expected 'No matches' but found ''"


def test_junit_reruns_are_flaky_unless_the_test_ends_red() -> None:
    report = _load("junit_flaky.xml")

    retried = _by_name(report, "remember me")
    assert retried.status == "flaky"
    assert retried.message == "Timeout 5000ms exceeded waiting for locator('#remember')"

    still_red = _by_name(report, "lock after five tries")
    assert still_red.status == "failed"
    assert still_red.message == "Expected the account to lock"


def test_junit_keeps_document_order() -> None:
    names = [test.name for test in _load("junit_basic.xml").tests]

    assert names[0] == "pay with card"
    assert names[-1] == "remove the last item"


def test_playwright_statuses_ids_and_durations() -> None:
    report = _load("playwright_basic.json")

    assert report.format == "playwright"
    assert len(report.tests) == 3

    failed = _by_name(report, "checkout › pay with card [chromium]")
    assert failed.status == "failed"
    assert failed.suite == "checkout.spec.ts"
    assert failed.test_id == "checkout.spec.ts::checkout › pay with card::chromium"
    assert failed.duration_s == pytest.approx(1.2)

    flaky = _by_name(report, "checkout › pay with card [firefox]")
    assert flaky.status == "flaky"
    assert flaky.test_id.endswith("::firefox")
    # Both attempts are counted, not just the last one.
    assert flaky.duration_s == pytest.approx(1.25)


def test_playwright_strips_ansi_colour_codes() -> None:
    failed = _by_name(_load("playwright_basic.json"), "checkout › pay with card [chromium]")

    assert failed.message == "Timeout 30000ms exceeded waiting for locator('#pay')"
    assert "\x1b[" not in failed.message
    assert "\x1b[" not in failed.details
    assert "at checkout.spec.ts:42:5" in failed.details


def test_playwright_expected_but_all_results_skipped_is_skipped() -> None:
    skipped = _by_name(_load("playwright_basic.json"), "guest checkout [chromium]")

    assert skipped.status == "skipped"
    assert skipped.message == ""


def test_an_xml_bomb_is_refused_without_expanding() -> None:
    with pytest.raises(ReportError) as error:
        _load("junit_bomb.xml")

    assert "junit_bomb.xml" in str(error.value)
    assert "lollollol" not in str(error.value)


def test_an_external_entity_is_refused() -> None:
    with pytest.raises(ReportError) as error:
        _load("junit_entity.xml")

    assert "junit_entity.xml" in str(error.value)
    assert "passwd" not in str(error.value)


def test_broken_xml_says_not_valid_xml() -> None:
    with pytest.raises(ReportError) as error:
        _load("junit_broken.xml")

    assert "not valid XML" in str(error.value)


def test_broken_json_says_not_valid_json() -> None:
    with pytest.raises(ReportError) as error:
        _load("playwright_broken.json")

    assert "not valid JSON" in str(error.value)


def test_plain_text_is_unsupported() -> None:
    with pytest.raises(ReportError) as error:
        _load("notes.txt")

    assert "Unsupported file: notes.txt" in str(error.value)


def test_json_without_suites_and_config_is_unsupported() -> None:
    with pytest.raises(ReportError) as error:
        _load("not_a_report.json")

    assert "Unsupported file: not_a_report.json" in str(error.value)


def test_too_many_tests_is_refused() -> None:
    cases = "".join(
        f'<testcase classname="big" name="case {n}" time="0.1"/>' for n in range(20_001)
    )
    content = f'<testsuites><testsuite name="big">{cases}</testsuite></testsuites>'

    with pytest.raises(ReportError) as error:
        parse_report("big.xml", content.encode("utf-8"))

    assert "max 20,000" in str(error.value)


def test_a_byte_order_mark_and_bad_bytes_do_not_stop_a_read() -> None:
    raw = (FIXTURES / "junit_single_suite.xml").read_bytes()
    report = parse_report("bom report.xml", b"\xef\xbb\xbf" + raw)

    assert report.label == "bom report"
    assert len(report.tests) == 2


def test_a_long_file_name_is_trimmed_to_sixty_characters() -> None:
    raw = (FIXTURES / "junit_single_suite.xml").read_bytes()

    assert len(parse_report("n" * 90 + ".xml", raw).label) == 60


def test_a_run_without_named_projects_keeps_a_plain_test_id() -> None:
    raw = (FIXTURES / "playwright_basic.json").read_text(encoding="utf-8")
    report = parse_report("single.json", raw.replace('"projectName"', '"unusedName"').encode())

    plain = _by_name(report, "checkout › pay with card")
    assert plain.test_id == "checkout.spec.ts::checkout › pay with card"
