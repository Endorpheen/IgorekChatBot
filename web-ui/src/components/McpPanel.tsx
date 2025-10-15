import React, { useState } from 'react';
import { mcpSearch, mcpFetch } from '../utils/api';
import { ApiError } from '../utils/api';
import { Copy, Timer, HardDrive } from 'lucide-react';
import './McpPanel.css';

const McpPanel: React.FC = () => {
  const [query, setQuery] = useState('');
  const [fetchId, setFetchId] = useState('');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [responseTime, setResponseTime] = useState<number | null>(null);
  const [responseSize, setResponseSize] = useState<number | null>(null);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(err => {
      console.error('Failed to copy text: ', err);
    });
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
        {result && <button className="copy-json-button" onClick={() => copyToClipboard(jsonString)}>Copy JSON</button>}
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
