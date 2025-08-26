import pytest
from src.endpoints import make_endpoint, POPULAR, SEARCH

@pytest.mark.parametrize("inp,expect", [
    ("/movie/popular", "movie/popular"),
    ("///search/movie?query=xx", "search/movie"),
    ("search//movie", "search/movie"),
    (" movie/popular ", "movie/popular"),
    ("movie/popular#frag", "movie/popular"),
    (POPULAR, "movie/popular"),
    (SEARCH, "search/movie"),
])
def test_make_endpoint_valid(inp, expect):
    assert make_endpoint(inp) == expect

@pytest.mark.parametrize("bad", [
    "", "   ", "/", "///", "/?q=1", "/#a", 123
])
def test_make_endpoint_invalid(bad):
    if not isinstance(bad, str):
        with pytest.raises(TypeError):
            make_endpoint(bad)
    else:
        with pytest.raises(ValueError):
            make_endpoint(bad)

def test_make_endpoint_rejects_whitespace_inside():
    with pytest.raises(ValueError):
        make_endpoint("movie/ bad")