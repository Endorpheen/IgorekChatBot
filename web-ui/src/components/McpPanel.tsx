import React, { useState } from 'react';
import { mcpSearch, mcpFetch } from '../utils/api';
import { ApiError } from '../utils/api';

const McpPanel: React.FC = () => {
  const [query, setQuery] = useState('');
  const [fetchId, setFetchId] = useState('');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await mcpSearch({ query });
      setResult(response);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`Error ${e.status} (${e.code || 'N/A'}): ${e.message}`);
      } else {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFetch = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await mcpFetch({ id: fetchId });
      setResult(response);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`Error ${e.status} (${e.code || 'N/A'}): ${e.message}`);
      } else {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '1rem', fontFamily: 'sans-serif' }}>
      <h2>MCP Obsidian</h2>
      <div style={{ marginBottom: '1.5rem', border: '1px solid #ccc', padding: '1rem', borderRadius: '4px' }}>
        <h3>Search</h3>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter search query"
          disabled={loading}
          style={{ marginRight: '0.5rem', padding: '0.5rem', minWidth: '300px' }}
        />
        <button onClick={handleSearch} disabled={loading} style={{ padding: '0.5rem' }}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>
      <div style={{ marginBottom: '1.5rem', border: '1px solid #ccc', padding: '1rem', borderRadius: '4px' }}>
        <h3>Fetch</h3>
        <input
          type="text"
          value={fetchId}
          onChange={(e) => setFetchId(e.target.value)}
          placeholder="Enter note ID to fetch"
          disabled={loading}
          style={{ marginRight: '0.5rem', padding: '0.5rem', minWidth: '300px' }}
        />
        <button onClick={handleFetch} disabled={loading} style={{ padding: '0.5rem' }}>
          {loading ? 'Fetching...' : 'Fetch'}
        </button>
      </div>
      {loading && <p>Loading...</p>}
      {error && <div style={{ color: 'red', marginTop: '1rem', whiteSpace: 'pre-wrap' }}><strong>Error:</strong> {error}</div>}
      {result && (
        <div style={{ marginTop: '1rem' }}>
          <h3>Result</h3>
          <p><strong>Trace ID:</strong> {result.trace_id}</p>
          <pre style={{ backgroundColor: '#f4f4f4', padding: '1rem', borderRadius: '4px', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {JSON.stringify(result.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

export default McpPanel;
