export type MessageAuthor = 'user' | 'bot';
export type MessageContentType = 'text' | 'image' | 'document' | 'attachment';

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
  size?: number;
  description?: string | null;
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

export interface ChatAttachmentItem {
  filename: string;
  url: string;
  contentType: string;
  size: number;
  description?: string | null;
}

export interface RawChatAttachmentItem {
  filename: string;
  url: string;
  content_type: string;
  size: number;
  description?: string | null;
}

export interface RawChatResponse {
  status: string;
  response: string;
  thread_id?: string;
  attachments?: RawChatAttachmentItem[];
}

export interface ChatResponse {
  status: string;
  response: string;
  thread_id?: string;
  attachments?: ChatAttachmentItem[];
}
