from qagenius.vague import find_vague_words


def test_quickly_found() -> None:
    assert find_vague_words("lock quickly after 3 wrong passwords") == ["quickly"]


def test_too_many_wins_over_many() -> None:
    assert find_vague_words("after too many wrong passwords") == ["too many"]


def test_concrete_numbers_have_no_vague_words() -> None:
    assert find_vague_words("Lock after 5 failed attempts within 10 minutes") == []


def test_no_match_inside_longer_words() -> None:
    assert find_vague_words("highlight the maybe field") == []


def test_case_insensitive_in_appearance_order() -> None:
    assert find_vague_words("Account stays SAFE and secure") == ["safe", "secure"]


def test_hyphenated_word() -> None:
    assert find_vague_words("is it user-friendly") == ["user-friendly"]
