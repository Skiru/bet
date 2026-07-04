from bet.tipsters.compliance import compliance_check
from bet.tipsters.contracts import ComplianceVerdict
from bet.tipsters.source_registry import SOURCES


class DummyRobots:
    def __init__(self, value):
        self.value = value
    def allowed(self, url):
        return self.value


def test_robots_block_is_fail_closed():
    check = compliance_check(SOURCES["sportsgambler"], "https://www.sportsgambler.com/admin/x", robots=DummyRobots(False), terms_reviewed=True)
    assert check.verdict == ComplianceVerdict.BLOCK_ROBOTS


def test_terms_review_required_before_allow():
    check = compliance_check(SOURCES["sportsgambler"], "https://www.sportsgambler.com/predictions/today/", robots=DummyRobots(True), terms_reviewed=False)
    assert check.verdict == ComplianceVerdict.UNKNOWN_REVIEW_REQUIRED


def test_allow_after_robots_and_terms_review():
    check = compliance_check(SOURCES["sportsgambler"], "https://www.sportsgambler.com/predictions/today/", robots=DummyRobots(True), terms_reviewed=True)
    assert check.verdict == ComplianceVerdict.ALLOW
