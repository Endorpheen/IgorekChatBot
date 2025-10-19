/**
 * Copyright (c) 2024. All rights reserved.
 *
 * @company self
 * @author Andrei
 * @role Crush
 * @created 2024-10-16
 */

import React from 'react';
import clsx from 'clsx';
import styles from './HomepageFeatures.module.css';

const FeatureList = [
  {
    title: 'Многоязыковый Чат',
    Svg: () => (
      <svg width="200" height="200" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="200" height="200" rx="8" fill="#e3f2fd"/>
        <path d="M50 80 L150 80 L140 120 L60 120 Z" fill="#1976d2"/>
        <circle cx="80" cy="100" r="15" fill="#fff"/>
        <circle cx="120" cy="100" r="15" fill="#fff"/>
        <path d="M70 110 Q80 120 90 110" stroke="#fff" strokeWidth="2" fill="none"/>
      </svg>
    ),
    description: (
      <>
        Поддержка чата на русском и английском языках. Интеллектуальная обработка запросов и контекстно-зависимые ответы.
      </>
    ),
  },
  {
    title: 'Генерация Изображений',
    Svg: () => (
      <svg width="200" height="200" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="200" height="200" rx="8" fill="#f3e5f5"/>
        <rect x="60" y="50" width="80" height="60" rx="4" fill="#9c27b0"/>
        <circle cx="100" cy="80" r="20" fill="#fff"/>
        <path d="M90 70 L100 80 L110 60" stroke="#9c27b0" strokeWidth="3" fill="none"/>
        <rect x="40" y="130" width="30" height="20" rx="2" fill="#e1bee7"/>
        <rect x="130" y="130" width="30" height="20" rx="2" fill="#e1bee7"/>
      </svg>
    ),
    description: (
      <>
        Встроенная поддержка различных провайдеров генерации изображений: Stability AI, Replicate, Together AI и другие.
      </>
    ),
  },
  {
    title: 'Интеграция MCP',
    Svg: () => (
      <svg width="200" height="200" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="200" height="200" rx="8" fill="#e8f5e8"/>
        <rect x="50" y="60" width="100" height="80" rx="8" fill="#4caf50"/>
        <rect x="60" y="70" width="80" height="60" rx="4" fill="#fff"/>
        <circle cx="80" cy="90" r="8" fill="#4caf50"/>
        <circle cx="100" cy="90" r="8" fill="#4caf50"/>
        <circle cx="120" cy="90" r="8" fill="#4caf50"/>
        <path d="M70 110 Q100 130 130 110" stroke="#4caf50" strokeWidth="3" fill="none"/>
      </svg>
    ),
    description: (
      <>
        Расширения через Model Context Protocol. Доступ к внешним инструментам, базам данных и API.
      </>
    ),
  },
];

function Feature({Svg, title, description}) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <Svg className={styles.featureSvg} role="img" />
      </div>
      <div className="text--center padding-horiz--md">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}