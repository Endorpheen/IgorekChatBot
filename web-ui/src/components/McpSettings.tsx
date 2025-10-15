import React, { useEffect, useMemo, useState } from 'react';
import type { McpBinding, McpProbeResponse, McpServer, McpServerForm, McpTool } from '../types/mcp';
import {
  bindMcpServer,
  fetchMcpBindings,
  fetchMcpServerTools,
  fetchMcpServers,
  probeMcpServer,
  runMcpTool,
  saveMcpServer,
} from '../utils/api';

interface McpSettingsProps {
  threadId: string;
  isOpen: boolean;
  onServersUpdated?: (servers: McpServer[]) => void;
  onBindingsUpdated?: (bindings: Record<string, string[]>) => void;
}

interface EditableServer extends McpServerForm {
  isNew?: boolean;
  lastProbe?: McpProbeResponse;
  tools?: McpTool[];
}

const defaultServerForm = (): EditableServer => ({
  id: '',
  name: '',
  transport: 'http-sse',
  url: '',
  headers: [{ key: '', value: '' }],
  timeout_s: undefined,
  max_output_kb: undefined,
  notes: undefined,
  allow_tools: [],
  max_calls_per_minute_per_thread: undefined,
  isNew: true,
});

const statusLabels: Record<string, string> = {
  ok: 'Доступен',
  unreachable: 'Недоступен',
  invalid_url: 'Некорректный URL',
  timeout: 'Таймаут',
  ssrf_blocked: 'Заблокировано политиками',
  error: 'Ошибка',
};

const transportLabels = {
  'http-sse': 'HTTP/SSE',
  websocket: 'WebSocket',
};

const McpSettings: React.FC<McpSettingsProps> = ({ threadId, isOpen, onServersUpdated, onBindingsUpdated }) => {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [bindings, setBindings] = useState<Record<string, string[]>>({});
  const [editingServer, setEditingServer] = useState<EditableServer | null>(null);
  const [isLoadingServers, setIsLoadingServers] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadServers = async () => {
    if (!isOpen) {
      return;
    }
    setIsLoadingServers(true);
    try {
      const data = await fetchMcpServers();
      setServers(data);
      setError(null);
      onServersUpdated?.(data);
    } catch (err) {
      console.error('Не удалось загрузить MCP сервера', err);
      setError(err instanceof Error ? err.message : 'Ошибка загрузки серверов');
    } finally {
      setIsLoadingServers(false);
    }
  };

  const loadBindings = async (tid: string) => {
    if (!isOpen || !tid) {
      setBindings({});
      onBindingsUpdated?.({});
      return;
    }
    try {
      const data = await fetchMcpBindings(tid);
      const mapping: Record<string, string[]> = {};
      data.forEach(binding => {
        mapping[binding.server_id] = binding.enabled_tools;
      });
      setBindings(mapping);
      onBindingsUpdated?.(mapping);
    } catch (err) {
      console.error('Не удалось получить привязки MCP', err);
    }
  };

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    loadServers();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    loadBindings(threadId);
  }, [threadId, isOpen]);

  useEffect(() => {
    if (!isOpen) {
      setEditingServer(null);
      setError(null);
    }
  }, [isOpen]);

  const resetForm = () => {
    setEditingServer(null);
  };

  const handleAddServer = () => {
    setEditingServer(defaultServerForm());
  };

  const handleEditServer = (server: McpServer) => {
    const form: EditableServer = {
      id: server.id,
      name: server.name,
      transport: server.transport,
      url: server.url,
      headers: server.headers.length > 0 ? server.headers.map(key => ({ key, value: '' })) : [{ key: '', value: '' }],
      timeout_s: server.timeout_s,
      max_output_kb: server.max_output_kb,
      notes: server.notes,
      allow_tools: server.allow_tools,
      max_calls_per_minute_per_thread: server.max_calls_per_minute_per_thread,
      isNew: false,
    };
    setEditingServer(form);
  };

  const handleHeaderChange = (index: number, key: 'key' | 'value', value: string) => {
    if (!editingServer) return;
    const headers = [...editingServer.headers];
    headers[index] = { ...headers[index], [key]: value };
    setEditingServer({ ...editingServer, headers });
  };

  const handleAddHeader = () => {
    if (!editingServer) return;
    setEditingServer({ ...editingServer, headers: [...editingServer.headers, { key: '', value: '' }] });
  };

  const handleRemoveHeader = (index: number) => {
    if (!editingServer) return;
    const headers = editingServer.headers.filter((_, idx) => idx !== index);
    setEditingServer({ ...editingServer, headers });
  };

  const handleSaveServer = async () => {
    if (!editingServer) return;
    setIsSubmitting(true);
    try {
      const payload = { ...editingServer };
      const saved = await saveMcpServer(payload);
      await loadServers();
      setEditingServer(null);
      setServers(prev => {
        const filtered = prev.filter(server => server.id !== saved.id);
        return [...filtered, saved];
      });
      setError(null);
    } catch (err) {
      console.error('Ошибка сохранения сервера', err);
      setError(err instanceof Error ? err.message : 'Не удалось сохранить настройки сервера');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleProbeServer = async (serverId: string) => {
    const target = editingServer?.id === serverId ? editingServer : null;
    try {
      const response = await probeMcpServer(serverId);
      if (target) {
        setEditingServer({ ...target, lastProbe: response, tools: response.tools });
      }
      await loadServers();
      setError(null);
    } catch (err) {
      console.error('Не удалось выполнить probe', err);
      setError(err instanceof Error ? err.message : 'Не удалось проверить сервер');
    }
  };

  const handleFetchTools = async (serverId: string) => {
    try {
      const tools = await fetchMcpServerTools(serverId);
      if (editingServer && editingServer.id === serverId) {
        setEditingServer({ ...editingServer, lastProbe: tools, tools: tools.tools });
      }
      setError(null);
    } catch (err) {
      console.error('Ошибка загрузки списка инструментов', err);
      setError(err instanceof Error ? err.message : 'Не удалось получить список инструментов');
    }
  };

  const handleToggleTool = async (serverId: string, toolName: string) => {
    const current = bindings[serverId] || [];
    const shouldEnable = !current.includes(toolName);
    const updated = shouldEnable ? [...current, toolName] : current.filter(tool => tool !== toolName);
    try {
      const binding: McpBinding = {
        server_id: serverId,
        thread_id: threadId,
        enabled_tools: updated,
      };
      await bindMcpServer(binding, 'owner');
      await loadBindings(threadId);
      setError(null);
    } catch (err) {
      console.error('Ошибка обновления привязки сервера', err);
      setError(err instanceof Error ? err.message : 'Не удалось обновить привязку');
    }
  };

  const handleRunTool = async (serverId: string, tool: McpTool) => {
    const args = {} as Record<string, unknown>;
    try {
      const result = await runMcpTool({
        server_id: serverId,
        tool_name: tool.name,
        arguments: args,
        thread_id: threadId,
      });
      alert(`Tool ${tool.name} result: ${result.status}\n${result.output ?? result.error ?? ''}`);
      setError(null);
    } catch (err) {
      console.error('Ошибка запуска инструмента', err);
      setError(err instanceof Error ? err.message : 'Не удалось выполнить инструмент');
    }
  };

  const currentBindings = useMemo(() => bindings, [bindings]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="mcp-settings">
      <div className="mcp-settings-header">
        <h3>MCP Servers</h3>
        <button type="button" className="settings-button" onClick={handleAddServer}>
          Добавить сервер
        </button>
      </div>
      {error && <div className="settings-error">{error}</div>}
      {isLoadingServers ? (
        <div className="settings-loading">Загрузка...</div>
      ) : servers.length === 0 ? (
        <div className="settings-empty">Серверов пока нет</div>
      ) : (
        <ul className="mcp-server-list">
          {servers.map(server => (
            <li key={server.id} className="mcp-server-item">
              <div className="mcp-server-main">
                <div className="mcp-server-name">{server.name}</div>
                <div className="mcp-server-info">
                  <span>{transportLabels[server.transport] ?? server.transport}</span>
                  <span>{server.url}</span>
                </div>
                <div className={`mcp-status-badge status-${server.status ?? 'unknown'}`}>
                  {server.status ? statusLabels[server.status] ?? server.status : '—'}
                </div>
              </div>
              <div className="mcp-server-actions">
                <button type="button" className="settings-button secondary" onClick={() => handleEditServer(server)}>
                  Изменить
                </button>
                <button type="button" className="settings-button secondary" onClick={() => handleProbeServer(server.id)}>
                  Probe
                </button>
                <button type="button" className="settings-button secondary" onClick={() => handleFetchTools(server.id)}>
                  Список инструментов
                </button>
              </div>
              {currentBindings[server.id] && currentBindings[server.id].length > 0 ? (
                <div className="mcp-server-binding">
                  <strong>Включенные инструменты:</strong> {currentBindings[server.id].join(', ')}
                </div>
              ) : (
                <div className="mcp-server-binding muted">Инструменты не включены</div>
              )}
            </li>
          ))}
        </ul>
      )}

      {editingServer && (
        <div className="mcp-server-editor">
          <h4>{editingServer.isNew ? 'Новый сервер' : `Редактирование ${editingServer.name}`}</h4>
          <div className="editor-field">
            <label>ID</label>
            <input
              type="text"
              value={editingServer.id}
              onChange={event => setEditingServer({ ...editingServer, id: event.target.value })}
              disabled={!editingServer.isNew}
            />
          </div>
          <div className="editor-field">
            <label>Название</label>
            <input
              type="text"
              value={editingServer.name}
              onChange={event => setEditingServer({ ...editingServer, name: event.target.value })}
            />
          </div>
          <div className="editor-field">
            <label>Транспорт</label>
            <select
              value={editingServer.transport}
              onChange={event => setEditingServer({ ...editingServer, transport: event.target.value as 'websocket' | 'http-sse' })}
            >
              <option value="http-sse">HTTP/SSE</option>
              <option value="websocket">WebSocket</option>
            </select>
          </div>
          <div className="editor-field">
            <label>URL</label>
            <input
              type="text"
              value={editingServer.url}
              onChange={event => setEditingServer({ ...editingServer, url: event.target.value })}
            />
          </div>
          <div className="editor-field">
            <label>Таймаут (сек)</label>
            <input
              type="number"
              min={1}
              value={editingServer.timeout_s ?? ''}
              onChange={event => setEditingServer({ ...editingServer, timeout_s: event.target.value ? Number(event.target.value) : undefined })}
            />
          </div>
          <div className="editor-field">
            <label>Макс. вывод (KB)</label>
            <input
              type="number"
              min={1}
              value={editingServer.max_output_kb ?? ''}
              onChange={event => setEditingServer({ ...editingServer, max_output_kb: event.target.value ? Number(event.target.value) : undefined })}
            />
          </div>
          <div className="editor-field">
            <label>Примечания</label>
            <textarea
              value={editingServer.notes ?? ''}
              onChange={event => setEditingServer({ ...editingServer, notes: event.target.value })}
            />
          </div>
          <div className="editor-field">
            <label>Заголовки</label>
            {editingServer.headers.map((header, index) => (
              <div key={index} className="header-row">
                <input
                  type="text"
                  placeholder="Header"
                  value={header.key}
                  onChange={event => handleHeaderChange(index, 'key', event.target.value)}
                />
                <input
                  type="text"
                  placeholder="Value"
                  value={header.value}
                  onChange={event => handleHeaderChange(index, 'value', event.target.value)}
                />
                <button type="button" className="settings-button secondary" onClick={() => handleRemoveHeader(index)}>
                  Удалить
                </button>
              </div>
            ))}
            <button type="button" className="settings-button secondary" onClick={handleAddHeader}>
              Добавить заголовок
            </button>
          </div>
          <div className="editor-field">
            <label>Разрешённые инструменты</label>
            <textarea
              value={editingServer.allow_tools.join(', ')}
              onChange={event => setEditingServer({ ...editingServer, allow_tools: event.target.value.split(',').map(item => item.trim()).filter(Boolean) })}
              placeholder="tool.search, tool.fetch"
            />
          </div>
          <div className="editor-field">
            <label>Лимит вызовов (шт/мин, per thread)</label>
            <input
              type="number"
              min={1}
              value={editingServer.max_calls_per_minute_per_thread ?? ''}
              onChange={event => setEditingServer({ ...editingServer, max_calls_per_minute_per_thread: event.target.value ? Number(event.target.value) : undefined })}
            />
          </div>
          <div className="editor-actions">
            <button type="button" className="settings-button" disabled={isSubmitting} onClick={handleSaveServer}>
              Сохранить
            </button>
            <button type="button" className="settings-button secondary" onClick={resetForm}>
              Отмена
            </button>
          </div>
          {editingServer.tools && editingServer.tools.length > 0 && (
            <div className="editor-tools">
              <h5>Инструменты</h5>
              <ul>
                {editingServer.tools.map(tool => (
                  <li key={tool.name}>
                    <div className="tool-header">
                      <strong>{tool.name}</strong>
                      <button type="button" className="settings-button secondary" onClick={() => handleToggleTool(editingServer.id, tool.name)}>
                        {bindings[editingServer.id]?.includes(tool.name) ? 'Отключить' : 'Включить'}
                      </button>
                      <button type="button" className="settings-button secondary" onClick={() => handleRunTool(editingServer.id, tool)}>
                        Запустить
                      </button>
                    </div>
                    {tool.description && <p>{tool.description}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default McpSettings;
