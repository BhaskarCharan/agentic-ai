from app.agent.tools import multiply


def test_multiply():
    assert multiply.invoke({"a": 6, "b": 7}) == 42


def test_multiply_floats():
    assert multiply.invoke({"a": 2.5, "b": 4}) == 10.0
