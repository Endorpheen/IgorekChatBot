import type { ChatMessage, ChatResponse, ThreadSettings } from '../types/chat';

export const buildApiUrl = (path: string): string => {
  const envBase = import.meta.env.VITE_AGENT_API_BASE?.trim();
  const runtimeOrigin = typeof window !== 'undefined' ? window.location.origin : undefined;

  const shouldFallbackToOrigin = (() => {
    if (!envBase || !runtimeOrigin) {
      return !envBase && !!runtimeOrigin;
    }

    try {
      const envUrl = new URL(envBase);
      const runtimeUrl = new URL(runtimeOrigin);
      const internalHosts = new Set(['localhost', '127.0.0.1', '0.0.0.0', 'chatbot']);
      const envHost = envUrl.hostname.toLowerCase();
      const runtimeHost = runtimeUrl.hostname.toLowerCase();

      if (internalHosts.has(envHost) && envHost !== runtimeHost) {
        return true;
      }
    } catch {
      return !!runtimeOrigin;
    }

    return false;
  })();

  const base = shouldFallbackToOrigin
    ? runtimeOrigin
    : envBase ?? runtimeOrigin ?? 'http://localhost:8018';

  return `${base.replace(/\/$/, '')}${path}`;
};

interface OpenRouterMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | { type: string; text?: string; image_url?: { url: string } }[];
  tool_call_id?: string;
}

interface AgentApiMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export const callOpenRouter = async (payload: { message: string; thread_id?: string; history?: ChatMessage[]; useTools?: boolean }, settings: { openRouterApiKey?: string; openRouterModel?: string; }, threadSettings: ThreadSettings) => {
  if (!settings.openRouterApiKey) {
    throw new Error('API ключ OpenRouter не указан');
  }

  const customSystemPrompt = localStorage.getItem('systemPrompt');

  const messages: OpenRouterMessage[] = [
    {
      role: 'system',
      content: customSystemPrompt || (payload.useTools
        ? "You are an AI assistant with access to tools for searching and fetching notes from a vault. Always use the search tool first to find the correct note ID, then use fetch with the exact ID. Do not assume note IDs, always search to confirm. Use the tools when needed to answer questions about the user's notes."
        : "You are a helpful AI assistant. You can analyze images when provided.")
    }
  ];
  if (payload.history) {
    for (const msg of payload.history) {
      const role = msg.type === 'user' ? 'user' : 'assistant';
      if (msg.contentType === 'image' && role === 'user') {
        messages.push({
          role,
          content: [
            { type: 'text', text: 'Анализируй это изображение.' },
            { type: 'image_url', image_url: { url: msg.content } }
          ]
        });
      } else {
        messages.push({ role, content: msg.content });
      }
    }
  }
  if (payload.message) {
    messages.push({ role: 'user', content: payload.message });
  }
  const historyLength = Math.max(1, Math.min(50, threadSettings.historyMessageCount ?? 5));
  if (messages.length > historyLength + 2) {
    messages.splice(1, messages.length - historyLength - 2);
  }
  const tools = payload.useTools ? [
    {
      type: "function",
      function: {
        name: "search",
        description: "Search notes in vault",
        parameters: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search query" },
            since: { type: "string", description: "Filter by time, e.g., 7d, 12h" }
          },
          required: ["query"]
        }
      }
    },
    {
      type: "function",
      function: {
        name: "fetch",
        description: "Fetch note by id",
        parameters: {
          type: "object",
          properties: {
            id: { type: "string", description: "Note ID" }
          },
          required: ["id"]
        }
      }
    }
  ] : undefined;
  const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${settings.openRouterApiKey}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': window.location.origin,
      'X-Title': 'Roo Control Terminal',
    },
    body: JSON.stringify({
      model: settings.openRouterModel,
      messages: messages,
      tools: tools,
      tool_choice: payload.useTools ? "auto" : undefined,
      temperature: 0.7,
      max_tokens: 2048,
    }),
  });
  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`;
    let errorDetails = '';
    try {
      const error = await response.json();
      errorMessage = error.error?.message || error.message || response.statusText;
      errorDetails = JSON.stringify(error, null, 2);
    } catch {
      errorMessage = response.statusText;
    }
    console.error('OpenRouter API error details:', errorDetails);
    throw new Error(`OpenRouter API error: ${errorMessage}`);
  }
  const data = await response.json();
  const message = data.choices[0]?.message;
  const content = message?.content || '';
  const toolCalls = message?.tool_calls;
  let finalResponse = content;
  if (toolCalls && toolCalls.length > 0) {
    messages.push(message);
    for (const toolCall of toolCalls) {
      const toolName = toolCall.function.name;
      const arguments_ = JSON.parse(toolCall.function.arguments);
      let result;
      if (toolName === 'search') {
        result = await executeMCPTool('search', arguments_);
      } else if (toolName === 'fetch') {
        result = await executeMCPTool('fetch', arguments_);
      } else {
        result = 'Unknown tool';
      }
      messages.push({
        role: 'tool',
        tool_call_id: toolCall.id,
        content: JSON.stringify(result, null, 2)
      });
    }
    const followupResponse = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${settings.openRouterApiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': window.location.origin,
        'X-Title': 'Roo Control Terminal',
      },
      body: JSON.stringify({
        model: settings.openRouterModel,
        messages: messages,
        temperature: 0.7,
        max_tokens: 2048,
      }),
    });
    if (followupResponse.ok) {
      const followupData = await followupResponse.json();
      finalResponse = followupData.choices[0]?.message?.content || content;
    }
  }
  return {
    status: 'success',
    response: finalResponse,
    thread_id: payload.thread_id,
  };
};

export const callAgent = async (payload: { message: string; thread_id?: string; user_id: string; history?: ChatMessage[]; openRouterApiKey?: string; openRouterModel?: string }) => {
  const systemPrompt = (typeof window !== 'undefined' ? localStorage.getItem('systemPrompt') : null)?.trim();

  const messages: AgentApiMessage[] = [];

  if (systemPrompt) {
    messages.push({ role: 'system', content: systemPrompt });
  }

  if (payload.history) {
    for (const pastMessage of payload.history) {
      if (pastMessage.contentType !== 'text') {
        continue;
      }
      messages.push({
        role: pastMessage.type === 'user' ? 'user' : 'assistant',
        content: pastMessage.content,
      });
    }
  }

  const trimmedMessage = payload.message.trim();
  if (trimmedMessage) {
    messages.push({ role: 'user', content: trimmedMessage });
  }

  const requestBody = messages.length > 0
    ? { ...payload, messages }
    : payload;

  const response = await fetch(buildApiUrl('/chat'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Agent API error: ${response.status} ${errorText}`);
  }

  const data = (await response.json()) as ChatResponse;
  return data;
};

interface UploadImagesParams {
  files: File[];
  threadId: string;
  history: ChatMessage[];
  settings: ThreadSettings;
  systemPrompt?: string | null;
  prompt?: string;
}

export interface ImageUploadResponse {
  status: string;
  response: string;
  thread_id: string;
  image?: {
    content: string;
    content_type: string;
  };
  images?: {
    content: string;
    content_type: string;
  }[];
}

export const uploadImagesForAnalysis = async ({ files, threadId, history, settings, systemPrompt, prompt }: UploadImagesParams): Promise<ImageUploadResponse> => {
  const formData = new FormData();
  files.forEach(file => {
    formData.append('files', file);
  });
  formData.append('thread_id', threadId);
  formData.append('history', JSON.stringify(history));

  const historyLimit = Math.max(1, Math.min(50, settings.historyMessageCount ?? 5));
  formData.append('history_message_count', String(historyLimit));

  if (prompt !== undefined) {
    formData.append('message', prompt ?? '');
  }
  if (systemPrompt && systemPrompt.trim()) {
    formData.append('system_prompt', systemPrompt);
  }
  if (settings.openRouterApiKey) {
    formData.append('open_router_api_key', settings.openRouterApiKey);
  }
  if (settings.openRouterModel) {
    formData.append('open_router_model', settings.openRouterModel);
  }

  const response = await fetch(buildApiUrl('/image/analyze'), {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Image upload error: ${response.status} ${errorText}`);
  }

  return (await response.json()) as ImageUploadResponse;
};

export const callMCP = async (method: string, params: Record<string, unknown>) => {
  const mcpUrl = import.meta.env.VITE_MCP_URL;
  if (!mcpUrl) {
    throw new Error('VITE_MCP_URL не настроен');
  }

  const token = import.meta.env.VITE_AUTH_TOKEN;
  if (!token) {
    throw new Error('VITE_AUTH_TOKEN не настроен');
  }

  const payload = {
    jsonrpc: '2.0',
    id: 1,
    method,
    params,
  };

  const response = await fetch(mcpUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`MCP API error: ${response.status}`);
  }

  const data = await response.json();
  if (data.error) {
    throw new Error(`MCP RPC error: ${data.error}`);
  }

  return data.result;
};

export const executeMCPTool = async (toolName: string, args: Record<string, unknown>) => {
  try {
    if (toolName === 'search') {
      const result = await callMCP('tools/call', {
        name: 'search',
        arguments: { query: args.query, since: args.since },
      });
      const contentItems = result.content || [];
      if (contentItems.length > 0) {
        const first = contentItems[0];
        if (first.json) {
          return first.json.results || [];
        }
      }
      return [];
    } else if (toolName === 'fetch') {
      const result = await callMCP('tools/call', {
        name: 'fetch',
        arguments: { id: args.id },
      });
      const contentItems = result.content || [];
      if (contentItems.length > 0) {
        const first = contentItems[0];
        if (first.json) {
          return first.json.content || '';
        }
      }
      return '';
    }
    return 'Unknown tool';
  } catch (error) {
    console.error(`Ошибка выполнения MCP tool ${toolName}:`, error);
    return `Ошибка: ${error}`;
  }
};
