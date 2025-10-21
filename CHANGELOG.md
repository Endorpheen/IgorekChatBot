# Changelog

## [1.2.1] — 2025-10-21
### Изменено / Changed
- 🇷🇺 Унифицирован интерфейс выбора провайдера генерации изображений.  
  Вместо трёх кнопок (`Together AI`, `Replicate`, `Stability AI`) теперь используется единый выпадающий список, аналогичный панели выбора провайдера чата.  
  Это улучшает визуальную согласованность и удобство.
- 🇬🇧 Unified the image provider selection interface.  
  Replaced three buttons (`Together AI`, `Replicate`, `Stability AI`) with a single dropdown list, consistent with the chat provider selection panel.  
  This improves visual consistency and usability.

## [1.2.0] — 2025-10-20
### Добавлено / Added
- 🇷🇺 Улучшен поиск моделей: теперь проще находить нужные варианты (FLUX, Ideogram и другие).
- 🇬🇧 Enhanced the model search, making it easier to find the right options (FLUX, Ideogram, and others).
- 🇷🇺 Добавлены избранные модели (⭐) — теперь ключевые модели отображаются первыми.
- 🇬🇧 Introduced favorite models (⭐) so that key models appear at the top of the list.
- 🇷🇺 Повышена стабильность и отзывчивость интерфейса при поиске и генерации изображений.
- 🇬🇧 Improved interface stability and responsiveness while searching and generating images.

### Изменено / Changed
- 🇷🇺 Обновлена логика отображения моделей: при очистке поиска список корректно возвращается к базовому состоянию.
- 🇬🇧 Refined the model display logic so the list resets to its default state after clearing the search.
- 🇷🇺 Уточнена фильтрация моделей Replicate (по `display_name` и `id`).
- 🇬🇧 Clarified Replicate model filtering by using both `display_name` and `id`.

### Внутреннее / Internal
- 🇷🇺 Подготовлена инфраструктура для дальнейшего расширения списка провайдеров.
- 🇬🇧 Prepared the infrastructure for expanding the provider catalogue.
