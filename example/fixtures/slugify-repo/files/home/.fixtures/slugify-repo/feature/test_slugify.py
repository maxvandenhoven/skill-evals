from slugify import slugify


def test_basic():
    assert slugify("Hello World") == "hello-world"


def test_accents_are_transliterated():
    assert slugify("Crème Brûlée") == "creme-brulee"


def test_max_length():
    assert slugify("a" * 100) == "a" * 60
