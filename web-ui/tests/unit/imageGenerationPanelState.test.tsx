/* @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest';

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  fetchProviderList: vi.fn(),
  fetchProviderModels: vi.fn(),
  fetchImageJobStatus: vi.fn(),
  createImageGenerationJob: vi.fn(),
  searchProviderModels: vi.fn(),
  validateProviderKey: vi.fn(),
}));

vi.mock('../../src/utils/api', async () => {
  const actual = await vi.importActual<typeof import('../../src/utils/api')>('../../src/utils/api');
  return {
    ...actual,
    fetchProviderList: apiMocks.fetchProviderList,
    fetchProviderModels: apiMocks.fetchProviderModels,
    fetchImageJobStatus: apiMocks.fetchImageJobStatus,
    createImageGenerationJob: apiMocks.createImageGenerationJob,
    searchProviderModels: apiMocks.searchProviderModels,
    validateProviderKey: apiMocks.validateProviderKey,
    buildApiUrl: (path: string) => `http://localhost${path}`,
  };
});

const storageMocks = vi.hoisted(() => ({
  loadMetadata: vi.fn(),
  loadProviderKey: vi.fn(),
}));

vi.mock('../../src/storage/togetherKeyStorage', () => ({
  InvalidPinError: class InvalidPinError extends Error {},
  loadMetadata: storageMocks.loadMetadata,
  loadProviderKey: storageMocks.loadProviderKey,
}));

const catalogMocks = vi.hoisted(() => ({
  readCatalog: vi.fn(),
  writeCatalog: vi.fn(),
  deleteCatalog: vi.fn(),
}));

vi.mock('../../src/storage/modelCatalogStorage', () => ({
  readCatalog: catalogMocks.readCatalog,
  writeCatalog: catalogMocks.writeCatalog,
  deleteCatalog: catalogMocks.deleteCatalog,
}));

const providerPreferenceMocks = vi.hoisted(() => ({
  listEnabledProviders: vi.fn(),
  isProviderEnabled: vi.fn(),
}));

vi.mock('../../src/storage/providerPreferences', () => ({
  listEnabledProviders: providerPreferenceMocks.listEnabledProviders,
  isProviderEnabled: providerPreferenceMocks.isProviderEnabled,
}));

import ImageGenerationPanel from '../../src/components/ImageGenerationPanel';

const mockModels = [
  {
    id: 'model-saved',
    display_name: 'Model saved',
    limits: {},
    defaults: {
      width: 1024,
      height: 1024,
      steps: 28,
      cfg: 4.5,
    },
    capabilities: {},
  },
];

describe('ImageGenerationPanel — состояние', () => {
  beforeEach(() => {
    apiMocks.fetchProviderList.mockResolvedValue({
      providers: [
        { id: 'provider-a', label: 'Provider A' },
        { id: 'provider-b', label: 'Provider B' },
      ],
    });
    apiMocks.fetchProviderModels.mockResolvedValue({ models: mockModels });
    apiMocks.searchProviderModels.mockResolvedValue({ models: mockModels });
    catalogMocks.readCatalog.mockResolvedValue(null);
    catalogMocks.writeCatalog.mockResolvedValue(undefined);
    catalogMocks.deleteCatalog.mockResolvedValue(undefined);
    storageMocks.loadMetadata.mockResolvedValue({ hasKey: true, encrypted: false });
    storageMocks.loadProviderKey.mockResolvedValue({ key: 'stub-key' });
    providerPreferenceMocks.listEnabledProviders.mockReturnValue({
      'provider-a': true,
      'provider-b': true,
    });
    providerPreferenceMocks.isProviderEnabled.mockReturnValue(true);
    apiMocks.validateProviderKey.mockResolvedValue(undefined);
    apiMocks.createImageGenerationJob.mockResolvedValue({});
    apiMocks.fetchImageJobStatus.mockResolvedValue({});
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
  });

  it('восстанавливает провайдера и промпт из sessionStorage', async () => {
    window.sessionStorage.setItem(
      'image-generation-state',
      JSON.stringify({
        providerId: 'provider-b',
        prompt: 'Сохранённый промпт',
        modelId: 'model-saved',
      }),
    );

    render(<ImageGenerationPanel />);

    const providerSelect = await screen.findByLabelText('Провайдер', { selector: 'select' });
    await waitFor(() => expect(providerSelect).toHaveValue('provider-b'));

    const promptTextarea = screen.getByLabelText('Промпт');
    expect(promptTextarea).toHaveValue('Сохранённый промпт');
  });

  it('сохраняет новое состояние в sessionStorage при изменении промпта', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');

    render(<ImageGenerationPanel />);

    const promptTextarea = await screen.findByLabelText('Промпт');
    await userEvent.clear(promptTextarea);
    await userEvent.type(promptTextarea, 'Новый промпт');

    await waitFor(() => {
      expect(setItemSpy).toHaveBeenCalledWith(
        'image-generation-state',
        expect.stringContaining('Новый промпт'),
      );
    });

    setItemSpy.mockRestore();
  });
});
