import { describe, it, expect } from 'vitest';
import { supportsVisionModel } from '../../src/utils/imageProvider';

describe('image analysis capability heuristics', () => {
  it('blocks non-vision agent models', () => {
    expect(supportsVisionModel('agentrouter', 'gpt-3.5-turbo')).toBe(false);
    expect(supportsVisionModel('agentrouter', 'gpt-4o-mini')).toBe(true);
  });

  it('detects OpenRouter vision models', () => {
    expect(supportsVisionModel('openrouter', 'openai/gpt-4o-mini')).toBe(true);
    expect(supportsVisionModel('openrouter', 'openai/gpt-3.5-turbo')).toBe(false);
  });
});
