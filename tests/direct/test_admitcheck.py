import json

import pytest

URL = "https://www.rit.edu/study/computer-science-ms"

PAGE = """
Computer Science MS | RIT
Program overview
The MS in computer science prepares graduates for advanced work in software
systems, machine learning and distributed computing. The programme is offered on
campus in Rochester, New York.
Admissions requirements
Applicants must hold a bachelor's degree from an accredited institution with a
minimum cumulative GPA of 3.0 on a 4.0 scale. Applicants whose first language is
not English must submit a Test of English as a Foreign Language (TOEFL) score of
at least 88 internet based, or an IELTS score of 6.5 overall.
Deadlines and fees
Applications for fall entry are due by February 15, 2027. A non refundable
application fee of 65 USD is required with every application.
"""

QUOTE_DEGREE = "Applicants must hold a bachelor's degree from an accredited institution"
QUOTE_GPA = "minimum cumulative GPA of 3.0 on a 4.0 scale"
QUOTE_ENGLISH = "TOEFL) score of at least 88 internet based, or an IELTS score of 6.5 overall"
QUOTE_DEADLINE = "Applications for fall entry are due by February 15, 2027."
QUOTE_FEE = "A non refundable application fee of 65 USD is required"

CARD = {
    "program_name": "Computer Science MS",
    "degree_required": "BACHELOR",
    "gpa_min": "3.0",
    "gpa_scale": "4.0",
    "english_test": "ANY",
    "english_min": "6.5",
    "deadline_iso": "2027-02-15",
    "fee_amount": "65",
    "fee_currency": "USD",
    "quotes": {
        "degree_required": {"quote": QUOTE_DEGREE, "source": 1},
        "gpa": {"quote": QUOTE_GPA, "source": 1},
        "english": {"quote": QUOTE_ENGLISH, "source": 1},
        "deadline": {"quote": QUOTE_DEADLINE, "source": 1},
        "fee": {"quote": QUOTE_FEE, "source": 1},
    },
}

LLM_PATTERN = r"(?s).*You extract admission requirements.*"
WEB_PATTERN = r".*rit\.edu.*"

APPLICANT_OK = json.dumps({
    "degree_level": "BACHELOR",
    "gpa": 3.4,
    "gpa_scale": 4.0,
    "english_test": "IELTS",
    "english_score": 7.0,
    "needs_english_proof": True,
})


def _llm(card):
    return json.dumps(card)


@pytest.fixture
def contract(direct_vm, direct_deploy, direct_alice):
    direct_vm.sender = direct_alice
    direct_vm.mock_web(WEB_PATTERN, {"status": 200, "body": PAGE})
    direct_vm.mock_llm(LLM_PATTERN, _llm(CARD))
    return direct_deploy("contracts/admitcheck.py")


def test_index_and_read(contract, direct_alice):
    program_id = contract.index_program([URL])

    assert program_id == "G1"
    data = contract.get_program(program_id)
    assert data["id"] == "G1"
    assert data["version"] == 1
    assert data["urls"] == [URL]
    assert data["owner"].lower() == "0x" + direct_alice.hex()
    assert data["card"]["program_name"] == "Computer Science MS"
    assert data["card"]["deadline_iso"] == "2027-02-15"

    gate = data["gate"]
    assert gate["degree_required"] == "BACHELOR"
    assert gate["gpa_min"] == "3"
    assert gate["gpa_scale"] == "4"
    assert gate["english_test"] == "ANY"
    assert gate["english_min"] == "6.5"
    assert gate["deadline_iso"] == "2027-02-15"
    assert gate["fee_amount"] == "65"
    assert gate["fee_currency"] == "USD"

    assert contract.count() == 1
    assert contract.find_program(URL) == "G1"
    assert contract.find_program("https://example.org/other") == ""


def test_index_twice_reuses_id(contract):
    first = contract.index_program([URL])
    second = contract.index_program([URL])
    assert first == second
    assert contract.count() == 1


def test_index_rejects_bad_input(contract):
    with pytest.raises(Exception):
        contract.index_program([])
    with pytest.raises(Exception):
        contract.index_program([URL] * 2)
    with pytest.raises(Exception):
        contract.index_program(["http://insecure.example/page"])


def test_index_rejects_paraphrased_quote(direct_vm, contract):
    bad = json.loads(json.dumps(CARD))
    bad["quotes"]["gpa"] = {"quote": "you need a grade point average of three point zero", "source": 1}
    direct_vm.clear_mocks()
    direct_vm.mock_web(WEB_PATTERN, {"status": 200, "body": PAGE})
    direct_vm.mock_llm(LLM_PATTERN, _llm(bad))

    with direct_vm.expect_revert("QUOTE_NOT_GROUNDED"):
        contract.index_program([URL])


def test_index_rejects_card_without_usable_requirements(direct_vm, contract):
    empty = {
        "program_name": "Some Programme",
        "degree_required": "UNKNOWN",
        "gpa_min": "",
        "gpa_scale": "",
        "english_test": "UNKNOWN",
        "english_min": "",
        "deadline_iso": "",
        "fee_amount": "",
        "fee_currency": "",
        "quotes": {
            "degree_required": {"quote": "The programme is offered on campus in Rochester", "source": 1},
            "gpa": {"quote": "prepares graduates for advanced work in software systems", "source": 1},
            "english": {"quote": "", "source": 0},
            "deadline": {"quote": "", "source": 0},
            "fee": {"quote": "", "source": 0},
        },
    }
    direct_vm.clear_mocks()
    direct_vm.mock_web(WEB_PATTERN, {"status": 200, "body": PAGE})
    direct_vm.mock_llm(LLM_PATTERN, _llm(empty))

    with direct_vm.expect_revert("NO_USABLE_REQUIREMENTS_ON_PAGE"):
        contract.index_program([URL])


def test_index_rejects_unreadable_page(direct_vm, contract):
    direct_vm.clear_mocks()
    direct_vm.mock_web(WEB_PATTERN, {"status": 200, "body": "Please enable JavaScript"})

    with direct_vm.expect_revert("SOURCE_EMPTY_OR_UNREADABLE"):
        contract.index_program([URL])


def test_validator_accepts_consistent_extraction(direct_vm, contract):
    contract.index_program([URL])
    assert direct_vm.run_validator() is True


def test_validator_rejects_different_deadline(direct_vm, contract):
    contract.index_program([URL])
    other = json.loads(json.dumps(CARD))
    other["deadline_iso"] = "2027-03-01"
    other["quotes"]["deadline"] = {"quote": QUOTE_DEADLINE, "source": 1}

    direct_vm.clear_mocks()
    direct_vm.mock_web(WEB_PATTERN, {"status": 200, "body": PAGE})
    direct_vm.mock_llm(LLM_PATTERN, _llm(other))

    assert direct_vm.run_validator() is False


def test_validator_rejects_quote_missing_from_page(direct_vm, contract):
    contract.index_program([URL])

    bad = json.loads(json.dumps(CARD))
    bad["quotes"]["english"] = {
        "quote": "IELTS 7.5 overall is required for all applicants",
        "source": 1,
    }

    # The leader claims a quote that does not exist on the page.
    assert direct_vm.run_validator(leader_result=bad) is False


def test_evaluate_eligible(contract):
    program_id = contract.index_program([URL])
    result = contract.evaluate(program_id, APPLICANT_OK)

    assert result["verdict"] == "ELIGIBLE"
    assert result["window"] == "OPEN"
    assert result["failed"] == 0
    assert result["unknown"] == 0
    assert [r["facet"] for r in result["rows"]] == ["degree", "gpa", "english"]


def test_evaluate_low_gpa_fails(contract):
    program_id = contract.index_program([URL])
    applicant = json.loads(APPLICANT_OK)
    applicant["gpa"] = 2.8

    result = contract.evaluate(program_id, json.dumps(applicant))
    gpa_row = [r for r in result["rows"] if r["facet"] == "gpa"][0]

    assert result["verdict"] == "NOT_ELIGIBLE"
    assert gpa_row["status"] == "FAIL"
    assert result["failed"] == 1


def test_evaluate_gpa_scales_are_compared_by_ratio(contract):
    program_id = contract.index_program([URL])
    applicant = json.loads(APPLICANT_OK)
    applicant["gpa"] = 9.0
    applicant["gpa_scale"] = 10

    result = contract.evaluate(program_id, json.dumps(applicant))
    gpa_row = [r for r in result["rows"] if r["facet"] == "gpa"][0]

    # 9/10 is above 3.0/4.0, so the different scale must not cause a failure.
    assert gpa_row["status"] == "PASS"
    assert result["verdict"] == "ELIGIBLE"


def test_evaluate_missing_degree_is_unknown(contract):
    program_id = contract.index_program([URL])
    applicant = json.loads(APPLICANT_OK)
    applicant["degree_level"] = ""

    result = contract.evaluate(program_id, json.dumps(applicant))

    assert result["verdict"] == "NEEDS_REVIEW"
    assert result["unknown"] == 1


def test_evaluate_low_english_score_fails(contract):
    program_id = contract.index_program([URL])
    applicant = json.loads(APPLICANT_OK)
    applicant["english_score"] = 6.0

    result = contract.evaluate(program_id, json.dumps(applicant))
    row = [r for r in result["rows"] if r["facet"] == "english"][0]

    assert row["status"] == "FAIL"
    assert result["verdict"] == "NOT_ELIGIBLE"


def test_evaluate_wrong_english_family_fails(direct_vm, contract):
    only_toefl = json.loads(json.dumps(CARD))
    only_toefl["english_test"] = "TOEFL"
    only_toefl["english_min"] = "88"
    direct_vm.clear_mocks()
    direct_vm.mock_web(WEB_PATTERN, {"status": 200, "body": PAGE})
    direct_vm.mock_llm(LLM_PATTERN, _llm(only_toefl))
    program_id = contract.index_program(["https://www.rit.edu/study/toefl-only-ms"])

    applicant = json.loads(APPLICANT_OK)
    applicant["english_test"] = "IELTS"
    result = contract.evaluate(program_id, json.dumps(applicant))
    row = [r for r in result["rows"] if r["facet"] == "english"][0]

    assert row["status"] == "FAIL"
    assert result["verdict"] == "NOT_ELIGIBLE"


def test_evaluate_declared_waiver_skips_english(contract):
    program_id = contract.index_program([URL])
    applicant = json.loads(APPLICANT_OK)
    applicant["needs_english_proof"] = False
    applicant["english_test"] = ""
    applicant["english_score"] = None

    result = contract.evaluate(program_id, json.dumps(applicant))
    row = [r for r in result["rows"] if r["facet"] == "english"][0]

    assert row["status"] == "PASS"
    assert result["verdict"] == "ELIGIBLE"


def test_evaluate_rejects_bad_json(contract):
    program_id = contract.index_program([URL])
    with pytest.raises(Exception):
        contract.evaluate(program_id, "not json")
    with pytest.raises(Exception):
        contract.unknown_program_call  # noqa: B018 - attribute access is not the point


def test_unknown_program(contract):
    with pytest.raises(Exception):
        contract.get_program("G404")
    with pytest.raises(Exception):
        contract.evaluate("G404", APPLICANT_OK)


def test_refresh_unchanged(direct_vm, contract):
    program_id = contract.index_program([URL])
    assert contract.refresh_program(program_id) == "UNCHANGED"

    data = contract.get_program(program_id)
    assert data["version"] == 1


def test_refresh_changed_bumps_version(direct_vm, contract):
    program_id = contract.index_program([URL])

    edited_page = PAGE.replace("February 15, 2027", "March 1, 2027")
    edited_card = json.loads(json.dumps(CARD))
    edited_card["deadline_iso"] = "2027-03-01"
    edited_card["quotes"]["deadline"] = {
        "quote": "Applications for fall entry are due by March 1, 2027.",
        "source": 1,
    }

    direct_vm.clear_mocks()
    direct_vm.mock_web(WEB_PATTERN, {"status": 200, "body": edited_page})
    direct_vm.mock_llm(LLM_PATTERN, _llm(edited_card))

    assert contract.refresh_program(program_id) == "CHANGED"

    data = contract.get_program(program_id)
    assert data["version"] == 2
    assert data["gate"]["deadline_iso"] == "2027-03-01"


def test_refresh_fetch_failure_keeps_card(direct_vm, contract):
    program_id = contract.index_program([URL])
    before = contract.get_program(program_id)

    direct_vm.clear_mocks()
    direct_vm.mock_web(WEB_PATTERN, {"status": 503, "body": ""})

    assert contract.refresh_program(program_id) == "FETCH_FAILED"

    after = contract.get_program(program_id)
    assert after["version"] == 1
    assert after["gate"] == before["gate"]


def test_list_programs(contract):
    contract.index_program([URL])
    items = contract.list_programs()
    assert len(items) == 1
    assert items[0]["id"] == "G1"
    assert items[0]["name"] == "Computer Science MS"
    assert items[0]["first_url"] == URL


def test_decimal_comma_is_parsed(direct_vm, contract):
    card = json.loads(json.dumps(CARD))
    card["gpa_min"] = "3,0"
    card["gpa_scale"] = "4,0"
    direct_vm.clear_mocks()
    direct_vm.mock_web(WEB_PATTERN, {"status": 200, "body": PAGE})
    direct_vm.mock_llm(LLM_PATTERN, _llm(card))

    program_id = contract.index_program(["https://www.rit.edu/study/comma-ms"])
    gate = contract.get_program(program_id)["gate"]

    assert gate["gpa_min"] == "3"
    assert gate["gpa_scale"] == "4"
