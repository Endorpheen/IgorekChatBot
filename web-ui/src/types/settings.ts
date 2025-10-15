export interface ThreadSettings {
  openRouterEnabled: boolean;
  openRouterApiKey: string;
  openRouterModel: string;
  historyMessageCount: number;
  mcpBindings?: Record<string, string[]>;
}
