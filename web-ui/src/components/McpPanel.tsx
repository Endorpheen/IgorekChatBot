import React, { useState } from 'react';
import { mcpSearch, mcpFetch, callAgent } from '../utils/api';
import { ApiError } from '../utils/api';
import { Copy, Timer, HardDrive } from 'lucide-react';
import { useChatState } from '../hooks/useChatState';
import './McpPanel.css';

const McpPanel: React.FC = () => {
  const { persistMessage, threadId } = useChatState();

  const [query, setQuery] = useState('');
  const [fetchId, setFetchId] = useState('');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [responseTime, setResponseTime] = useState<number | null>(null);
  const [responseSize, setResponseSize] = useState<number | null>(null);
  const [sendingToChat, setSendingToChat] = useState(false);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(err => {
      console.error('Failed to copy text: ', err);
    });
  };

  const handleAskIgorek = async () => {
    if (!result || !result.data) {
      alert('Нет данных трейса для отправки');
      return;
    }

    // Используем тот же threadId что и в основном чате
    const activeThreadId = threadId || 'default';
    if (!activeThreadId) {
      alert('Нет активного чата, создайте новый тред в интерфейсе Игорька');
      return;
    }

    setSendingToChat(true);

    try {
      const jsonContent = JSON.stringify(result.data, null, 2);
      const prompt = `Прокомментируй эту заметку в человекочитаемом виде:\n${jsonContent}`;

      // Сохраняем запрос пользователя в историю (как в основном чате)
      persistMessage({
        type: 'user',
        contentType: 'text',
        content: prompt,
        threadId: activeThreadId,
      });

      // Проверяем результат API вызова
      console.log('[MCP ASK IGOREK] Calling callAgent with:', {
        message: prompt.substring(0, 100) + '...',
        thread_id: activeThreadId,
      });

      const response = await callAgent({
        message: prompt,
        thread_id: activeThreadId,
      });

      console.log('[MCP ASK IGOREK] Raw API response:', response);
      console.log('[MCP ASK IGOREK] Response type:', typeof response);
      console.log('[MCP ASK IGOREK] Response keys:', response ? Object.keys(response) : 'null');

      // Проверяем что ответ успешен
      console.log('[MCP ASK IGOREK] Checking response validity...');
      console.log('[MCP ASK IGOREK] Response object:', response);
      console.log('[MCP ASK IGOREK] Response status value:', response?.status);

      if (response && response.status === 'Message processed') {
        // Сохраняем ответ бота в историю (как в основном чате)
        persistMessage({
          type: 'bot',
          contentType: 'text',
          content: response.response || 'Ответ получен, но не удалось извлечь текст',
          threadId: response.thread_id || activeThreadId,
        });

        console.log('[MCP ASK IGOREK] Success! Message saved to history, redirecting to chat...');
        // Редирект на главную страницу чата только после успешного ответа
        window.location.href = '/';
      } else {
        console.error('[MCP ASK IGOREK] Invalid response structure:', {
          hasResponse: !!response,
          status: response?.status,
          responseKeys: response ? Object.keys(response) : [],
          fullResponse: response
        });
        throw new Error(`Не удалось отправить сообщение в чат. Ответ сервера: ${JSON.stringify(response)}`);
      }
    } catch (error) {
      console.error('Ошибка отправки в чат:', error);
      alert('Ошибка при отправке в чат: ' + (error as Error).message);
    } finally {
      setSendingToChat(false);
    }
  };

  const handleRequest = async (apiCall: () => Promise<any>) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setResponseTime(null);
    setResponseSize(null);
    const startTime = performance.now();

    try {
      const response = await apiCall();
      const endTime = performance.now();
      const duration = Math.round(endTime - startTime);
      const size = new TextEncoder().encode(JSON.stringify(response)).length;

      setResult(response);
      setResponseTime(duration);
      setResponseSize(size);

      console.log(`MCP Request Trace ID: ${response.trace_id}, Duration: ${duration}ms, Status: 200`);
    } catch (e) {
      const endTime = performance.now();
      const duration = Math.round(endTime - startTime);
      let errorMsg: string;
      let statusCode: number | string = 'N/A';

      if (e instanceof ApiError) {
        statusCode = e.status;
        errorMsg = `Error ${e.status} (${e.code || 'N/A'}): ${e.message}`;
      } else {
        errorMsg = (e as Error).message;
      }
      setError(errorMsg);
      console.log(`MCP Request Failed. Duration: ${duration}ms, Status: ${statusCode}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => handleRequest(() => mcpSearch({ query }));
  const handleFetch = () => handleRequest(() => mcpFetch({ id: fetchId }));

  const renderResult = () => {
    if (loading) {
      return <p>Loading...</p>;
    }
    if (!error && !result) {
      return null;
    }

    const jsonString = result ? JSON.stringify(result.data, null, 2) : '';

    return (
      <div className="mcp-result-container">
        <div className="mcp-result-header">
          <div className="status-item">
            <span>Trace:</span>
            <span>{result?.trace_id || 'N/A'}</span>
            {result?.trace_id && <Copy size={14} className="copy-icon" onClick={() => copyToClipboard(result.trace_id)} />}
          </div>
          <div className="status-item">
            <Timer size={14} />
            <span>{responseTime ?? '0'} ms</span>
          </div>
          <div className="status-item">
            <HardDrive size={14} />
            <span>{responseSize ? (responseSize / 1024).toFixed(2) : '0'} KB</span>
          </div>
        </div>
        {result && (
          <div className="mcp-action-buttons">
            <button className="copy-json-button" onClick={() => copyToClipboard(jsonString)}>
              Copy JSON
            </button>
            <button
              className="ask-igorek-button"
              onClick={handleAskIgorek}
              disabled={sendingToChat}
            >
              {sendingToChat ? 'Отправка...' : 'Спросить у Игорька'}
            </button>
          </div>
        )}
        {error ? (
          <div className="mcp-error-message">{error}</div>
        ) : (
          <pre>{jsonString}</pre>
        )}
      </div>
    );
  };

  return (
    <div className="mcp-panel">
      <h2>MCP Obsidian</h2>
      <div className="mcp-input-group">
        <h3>Search</h3>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter search query"
          disabled={loading}
          className="mcp-input"
        />
        <button onClick={handleSearch} disabled={loading} className="mcp-button">
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>
      <div className="mcp-input-group">
        <h3>Fetch</h3>
        <input
          type="text"
          value={fetchId}
          onChange={(e) => setFetchId(e.target.value)}
          placeholder="Enter note ID to fetch"
          disabled={loading}
          className="mcp-input"
        />
        <button onClick={handleFetch} disabled={loading} className="mcp-button">
          {loading ? 'Fetching...' : 'Fetch'}
        </button>
      </div>
      <div className="mcp-result-wrapper">
        {renderResult()}
      </div>
    </div>
  );
};

export default McpPanel;
