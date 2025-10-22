export type MessageAuthor = 'user' | 'bot';
export type MessageContentType = 'text' | 'image' | 'document';

export interface ChatMessage {
  id: string;
  type: MessageAuthor;
  contentType: MessageContentType;
  content: string;
  threadId: string;
  createdAt: string;
  fileName?: string;
  url?: string;
  mimeType?: string;
}

export interface ThreadNameMap {
  [threadId: string]: string;
}

export interface ThreadSettings {
  openRouterApiKey: string;
  openRouterModel: string;
  historyMessageCount: number;
  threadId?: string;

  // Chat provider selection
  chatProvider?: 'openrouter' | 'agentrouter';

  // OpenAI Compatible settings
  agentRouterBaseUrl?: string;
  agentRouterApiKey?: string;
  agentRouterModel?: string;
}

export interface ThreadSettingsMap {
  [threadId: string]: ThreadSettings;
}

export interface ChatResponse {
  status: string;
  response: string;
  thread_id?: string;
}
