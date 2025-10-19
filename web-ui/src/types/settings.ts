export interface ThreadSettings {
  openRouterEnabled: boolean;
  openRouterApiKey: string;
  openRouterModel: string;
  historyMessageCount: number;

  // Chat provider selection
  chatProvider?: 'openrouter' | 'agentrouter';

  // AgentRouter settings (OpenAI-compatible)
  agentRouterBaseUrl?: string;
  agentRouterApiKey?: string;
  agentRouterModel?: string;
}
