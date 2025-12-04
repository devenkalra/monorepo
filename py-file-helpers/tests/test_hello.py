"""Hello unit test module."""

from py_file_helpers.hello import hello


def test_hello():
    """Test the hello function."""
    assert hello() == "Hello py-file-helpers"
