import pytest
from unittest.mock import Mock, patch
from src.requester import Requester
from src.api_client import ApiClient, ApiError

class TestRequester:
    """测试 Requester 类"""
    
    @pytest.fixture
    def mock_client(self):
        """创建模拟的 ApiClient"""
        client = Mock(spec=ApiClient)
        return client
    
    @pytest.fixture
    def requester(self, mock_client):
        """创建 Requester 实例"""
        return Requester(mock_client)
    
    def test_init(self, mock_client):
        """测试 Requester 初始化"""
        req = Requester(mock_client)
        assert req.client == mock_client
    
    def test_init_invalid_client(self):
        """测试传入无效 client 的情况"""
        with pytest.raises(ValueError, match="client must be an ApiClient instance"):
            Requester("not_an_api_client")
    
    def test_fetch_popular_success(self, requester, mock_client):
        """测试成功获取热门电影"""
        # 模拟成功的响应
        mock_response = {
            "success": True,
            "results": [{"id": 1, "title": "Test Movie"}],
            "total_pages": 10
        }
        mock_client.get_movies.return_value = mock_response
        
        result = requester.fetch_popular(page=1)
        
        assert result["success"] is True
        assert len(result["results"]) == 1
        mock_client.get_movies.assert_called_once_with("movie/popular", {"page": 1})
    
    def test_fetch_popular_invalid_page(self, requester):
        """测试无效页码"""
        result = requester.fetch_popular(page=0)
        
        assert result["success"] is False
        assert "page 必须为正整数" in result["error"]
    
    def test_discover_movies_success(self, requester, mock_client):
        """测试成功发现电影"""
        mock_response = {
            "success": True,
            "results": [{"id": 2, "title": "Discovered Movie"}]
        }
        mock_client.discover_movies.return_value = mock_response
        
        params = {"year": 2020}
        result = requester.discover_movies(params)
        
        assert result["success"] is True
        mock_client.discover_movies.assert_called_once_with(params)
    
    def test_search_movies_success(self, requester, mock_client):
        """测试成功搜索电影"""
        mock_response = {
            "success": True,
            "results": [{"id": 3, "title": "Searched Movie"}]
        }
        mock_client.get_movies.return_value = mock_response
        
        result = requester.search_movies("test query", page=1)
        
        assert result["success"] is True
        mock_client.get_movies.assert_called_once_with(
            "search/movie", 
            {"query": "test query", "page": 1}
        )
    
    def test_get_movie_details_success(self, requester, mock_client):
        """测试成功获取电影详情"""
        mock_response = {
            "success": True,
            "id": 123,
            "title": "Movie Details"
        }
        mock_client.get_movies.return_value = mock_response
        
        result = requester.get_movie_details(123)
        
        assert result["success"] is True
        mock_client.get_movies.assert_called_once_with("movie/123", {})
    
    def test_api_error_handling(self, requester, mock_client):
        """测试 API 错误处理"""
        mock_client.get_movies.side_effect = ApiError("API Error")
        
        result = requester.fetch_popular(page=1)
        
        assert result["success"] is False
        assert "API Error" in result["error"]