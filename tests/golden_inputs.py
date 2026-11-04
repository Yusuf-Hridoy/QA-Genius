"""The five reference runs, in the shape an agent sends them.

Same stories the rest of the suite is built on — the lockout, the coupon,
the big settings story, the nav bar and the photo upload — written out as
MCP input so the golden files can be regenerated from one place.

Not a test module; pytest does not collect it.
"""

from tests.factories import (
    BIG_CRITERIA,
    BIG_STORY,
    COUPON_CONTEXT,
    COUPON_CRITERIA,
    LOCKOUT_CRITERIA,
    LOCKOUT_STORY,
    NAVBAR_CRITERIA,
    NAVBAR_STORY,
    PHOTO_CONTEXT,
    PHOTO_CRITERIA,
    PHOTO_STORY,
)


def _criteria(texts: list[str]) -> list[dict]:
    return [{"text": text} for text in texts]


def _test(
    test_id: str,
    title: str,
    steps: list[str],
    expected: str,
    covers: list[str],
    test_data: str = "",
    kind: str = "normal",
) -> dict:
    return {
        "id": test_id,
        "title": title,
        "steps": steps,
        "expected": expected,
        "test_data": test_data,
        "covers": covers,
        "kind": kind,
    }


# ── lockout ───────────────────────────────────────────────────────────────
# Five tries and thirty minutes are two different things measured in two
# different units. A run once read them as one number disagreeing with
# itself; this fixture is here so that cannot come back.

LOCKOUT = {
    "tool": "review_tests",
    "input": {
        "story": LOCKOUT_STORY,
        "context": "Aurora Storefront sign-in. The counter is per account.",
        "criteria": _criteria(LOCKOUT_CRITERIA),
        "test_cases": [
            _test(
                "TC-01",
                "The account locks on the fifth wrong password",
                [
                    "Open the Aurora Storefront sign-in page",
                    "Enter the right email and a wrong password five times",
                ],
                "The page shows: Account locked for 30 minutes",
                ["AC-1"],
                "attempts=5",
                "at the limit",
            ),
            _test(
                "TC-02",
                "A fourth wrong password does not lock the account",
                [
                    "Open the Aurora Storefront sign-in page",
                    "Enter the right email and a wrong password four times",
                    "Enter the right password",
                ],
                "The shopper is signed in and no lock message is shown",
                ["AC-1"],
                "attempts=4",
                "at the limit",
            ),
            _test(
                "TC-03",
                "A locked account is still locked after 29 minutes",
                [
                    "Lock the account with five wrong passwords",
                    "Wait 29 minutes",
                    "Enter the right password",
                ],
                "The page shows: Account locked for 30 minutes",
                ["AC-2"],
                "wait=29 minutes",
                "at the limit",
            ),
            _test(
                "TC-04",
                "A locked account opens again after 30 minutes",
                [
                    "Lock the account with five wrong passwords",
                    "Wait 30 minutes",
                    "Enter the right password",
                ],
                "The shopper is signed in",
                ["AC-2"],
                "wait=30 minutes",
                "at the limit",
            ),
            _test(
                "TC-05",
                "An unknown email is refused without saying it is unknown",
                ["Enter an email no account uses", "Enter any password"],
                "The page shows: That email or password is wrong",
                ["AC-1"],
                "email=nobody@example.com",
                "wrong input",
            ),
        ],
    },
}


# ── coupon ────────────────────────────────────────────────────────────────
# The context says "at least $50" and AC-1 says "more than $50". Nobody has
# said what happens at exactly $50, and the two sentences disagree about it.

COUPON = {
    "tool": "review_tests",
    "input": {
        "story": (
            "As a shopper, I want to apply a discount coupon at checkout so "
            "that I pay less for my order."
        ),
        "context": COUPON_CONTEXT,
        "criteria": _criteria(COUPON_CRITERIA),
        "test_cases": [
            _test(
                "TC-01",
                "A valid coupon on a cart over the minimum",
                ["Put $60.00 of items in the cart", "Enter a valid coupon code"],
                "The order total drops by the discount and the new total is shown",
                ["AC-1"],
                "cart_total=$60.00",
            ),
            _test(
                "TC-02",
                "A valid coupon on a cart under the minimum",
                ["Put $40.00 of items in the cart", "Enter a valid coupon code"],
                'The page shows: This coupon needs an order of at least $50.',
                ["AC-2"],
                "cart_total=$40.00",
                "wrong input",
            ),
            _test(
                "TC-03",
                "The discount stops at the cap",
                ["Put $200.00 of items in the cart", "Enter a coupon for 20% off"],
                "The discount is $30.00, not $40.00",
                ["AC-3"],
                "cart_total=$200.00; coupon=20%",
                "at the limit",
            ),
            _test(
                "TC-04",
                "A coupon the account has already used",
                ["Enter a coupon this account used last week"],
                "The page shows: You have already used this coupon.",
                ["AC-4"],
                "coupon=SPRING20",
                "wrong input",
            ),
            _test(
                "TC-05",
                "An expired coupon",
                ["Enter a coupon whose expiry date has passed"],
                "The page shows: This coupon has expired.",
                ["AC-5"],
                "coupon=WINTER10",
                "wrong input",
            ),
        ],
    },
}


# ── the big story ─────────────────────────────────────────────────────────
# Eight things in one sentence. check_story has to name the features it
# found, two-factor among them.

BIG_STORY_CASE = {
    "tool": "check_story",
    "input": {
        "story": BIG_STORY,
        "context": "",
        "story_type": "user story",
    },
}

BIG_STORY_TESTS = {
    "tool": "review_tests",
    "input": {
        "story": BIG_STORY,
        "context": "",
        "criteria": _criteria(BIG_CRITERIA),
        "test_cases": [
            _test(
                "TC-01",
                "The profile page shows every field",
                ["Open the profile page"],
                "The page shows the full name, email, phone number and bio",
                ["AC-1"],
            ),
            _test(
                "TC-02",
                "Changing the password asks for the current one",
                ["Open the password form", "Submit without the current password"],
                "The form shows: Enter your current password",
                ["AC-2"],
                "",
                "wrong input",
            ),
            _test(
                "TC-03",
                "Enabling two-factor asks for a 6-digit code",
                ["Open security settings", "Press Enable two-factor"],
                "The page asks for a 6-digit verification code",
                ["AC-3"],
                "code_length=6",
            ),
        ],
    },
}


# ── nav bar ───────────────────────────────────────────────────────────────
# Every criterion is sound and every one has the tests it needs. The senior
# tester must have nothing to add: a tool that always adds something is a
# tool nobody believes the second time.

NAVBAR = {
    "tool": "review_tests",
    "input": {
        "story": NAVBAR_STORY,
        "context": "A documentation site. The admin link is role-based.",
        "criteria": _criteria(NAVBAR_CRITERIA),
        "test_cases": [
            _test(
                "TC-01",
                "The item for the open page is highlighted",
                ["Open the Guides page", "Look at the sidebar"],
                "The sidebar shows Guides highlighted",
                ["AC-1"],
            ),
            _test(
                "TC-02",
                "No other sidebar item is highlighted at the same time",
                ["Open the Guides page", "Look at every sidebar item"],
                "Only Guides is highlighted",
                ["AC-1"],
                "",
                "unusual",
            ),
            _test(
                "TC-03",
                "Breadcrumbs show the path to the current page",
                ["Open Guides › Getting started", "Read the breadcrumb trail"],
                "The breadcrumbs read Home › Guides › Getting started",
                ["AC-2"],
            ),
            _test(
                "TC-04",
                "A breadcrumb step shows its hint on hover",
                ["Open Guides › Getting started", "Hover over the Guides step"],
                "A hint appears naming the Guides section",
                ["AC-2"],
            ),
            _test(
                "TC-05",
                "The menu button opens the menu on a phone",
                ["Open the site on a 390px wide screen", "Press the menu button"],
                "The sidebar menu is shown",
                ["AC-3"],
                "width=390px",
            ),
            _test(
                "TC-06",
                "The menu closes again on the second press",
                ["Open the menu on a phone", "Press the menu button again"],
                "The sidebar menu is hidden",
                ["AC-3"],
                "width=390px",
            ),
            _test(
                "TC-07",
                "The current item is bold",
                ["Open the Guides page", "Compare the Guides item with its neighbours"],
                "The Guides item is rendered in bold and the others are not",
                ["AC-4"],
            ),
            _test(
                "TC-08",
                "A reader without the admin role is refused the admin URL",
                ["Sign in as a reader", "Open /admin directly"],
                "The page shows: You do not have access to this page",
                ["AC-5"],
                "role=reader",
                "wrong input",
            ),
            _test(
                "TC-09",
                "A reader without the admin role is not shown the admin link",
                ["Sign in as a reader", "Look at the sidebar"],
                "No admin link is shown",
                ["AC-5"],
                "role=reader",
            ),
            _test(
                "TC-10",
                "An admin sees the admin link",
                ["Sign in as an admin", "Look at the sidebar"],
                "The admin link is shown",
                ["AC-5"],
                "role=admin",
            ),
            _test(
                "TC-11",
                "The API refuses an action whose button is hidden for this role",
                [
                    "Sign in as a reader and confirm the admin button is not shown",
                    "Call the admin action's endpoint directly with that session",
                    "Call the same endpoint as an admin",
                ],
                "The reader's call is refused with 403 and the admin's succeeds",
                ["AC-5"],
                "role=reader",
                "wrong input",
            ),
            _test(
                "TC-12",
                "The menu can be used by keyboard alone with a visible focus ring",
                [
                    "Press Tab from the top of the page through every menu item",
                    "Press Enter on one item",
                    "Open the menu on a phone and Tab through it",
                ],
                "Every item takes focus in order, shows a visible focus ring, "
                "and Enter opens it",
                ["AC-3"],
                "keys=Tab, Enter",
                "unusual",
            ),
            _test(
                "TC-13",
                "A role change takes effect without signing out",
                [
                    "Sign in as an admin in one browser and as that admin's "
                    "colleague in another",
                    "Change the colleague's role to reader",
                    "Reload an admin page in the colleague's open session",
                ],
                "The revoked role takes effect immediately: the admin page is "
                "refused in the existing session, without signing out and in again",
                ["AC-5"],
                "role=admin demoted to reader while signed in",
                "unusual",
            ),
        ],
    },
}


# ── photo upload ──────────────────────────────────────────────────────────
# Three criteria state the same 2 MB limit from different sides, and they do
# not agree about the photo that is exactly 2 MB.

PHOTO = {
    "tool": "review_tests",
    "input": {
        "story": PHOTO_STORY,
        "context": PHOTO_CONTEXT,
        "criteria": _criteria(PHOTO_CRITERIA),
        "test_cases": [
            _test(
                "TC-01",
                "A JPEG under the size limit is saved",
                ["Open the profile page", "Select a 1.5 MB JPEG", "Upload it"],
                "The photo is cropped to a square and shown on the profile",
                ["AC-1"],
                "size=1.5 MB; format=JPEG",
            ),
            _test(
                "TC-02",
                "A PNG under the size limit is saved",
                ["Open the profile page", "Select a 1.5 MB PNG", "Upload it"],
                "The photo is cropped to a square and shown on the profile",
                ["AC-2"],
                "size=1.5 MB; format=PNG",
            ),
            _test(
                "TC-03",
                "A photo over the size limit is refused",
                ["Open the profile page", "Select a 2.5 MB JPEG", "Upload it"],
                "The page shows a message about the 2 MB limit",
                ["AC-3"],
                "size=2.5 MB",
                "at the limit",
            ),
            _test(
                "TC-04",
                "A file in another format is refused",
                ["Open the profile page", "Select a GIF", "Upload it"],
                "The page shows: Use a JPEG or PNG image",
                ["AC-4"],
                "format=GIF",
                "wrong input",
            ),
        ],
    },
}


GOLDEN: dict[str, dict] = {
    "lockout": LOCKOUT,
    "coupon": COUPON,
    "big_story": BIG_STORY_CASE,
    "big_story_tests": BIG_STORY_TESTS,
    "navbar": NAVBAR,
    "photo": PHOTO,
}
