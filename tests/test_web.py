import pytest
from unittest.mock import patch, MagicMock
from agent_reach.channels.web import WebChannel


def test_web_read_success():
    """Test successful read with Jina Reader."""
    with patch('agent_reach.channels.web.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.text = "Test content from Jina Reader"
        mock_get.return_value = mock_response
        
        ch = WebChannel()
        result = ch.read('https://example.com/')
        
        assert result == "Test content from Jina Reader"
        mock_get.assert_called_once_with('https://r.jina.ai/https://example.com/', timeout=30)


def test_web_read_adds_https():
    """Test that read() adds https:// if missing."""
    with patch('agent_reach.channels.web.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.text = "Content"
        mock_get.return_value = mock_response
        
        ch = WebChannel()
        result = ch.read('example.com')
        
        mock_get.assert_called_once_with('https://r.jina.ai/https://example.com', timeout=30)


def test_web_read_preserves_existing_scheme():
    """Test that read() preserves http:// or https:// if already present."""
    with patch('agent_reach.channels.web.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.text = "Content"
        mock_get.return_value = mock_response
        
        ch = WebChannel()
        ch.read('http://example.com')
        
        mock_get.assert_called_once_with('https://r.jina.ai/http://example.com', timeout=30)


def test_web_read_request_exception():
    """Test that read() raises exception on HTTP errors."""
    with patch('agent_reach.channels.web.requests.get') as mock_get:
        mock_get.side_effect = Exception("Connection failed")
        
        ch = WebChannel()
        with pytest.raises(Exception, match="Connection failed"):
            ch.read('https://example.com/')


def test_web_read_http_error():
    """Test that read() raises for HTTP errors."""
    import requests
    with patch('agent_reach.channels.web.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_response
        
        ch = WebChannel()
        with pytest.raises(requests.exceptions.HTTPError):
            ch.read('https://example.com/')