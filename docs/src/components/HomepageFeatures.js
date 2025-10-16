//
// Copyright (c) 2024. All rights reserved.
//
// @company self
// @author Andrei
// @role Crush
// @created 2024-10-16
//

import React from 'react';
import clsx from 'clsx';
import styles from './HomepageFeatures.module.css';

const FeatureList = [
  {
    title: 'Многоязыковый Чат',
    Svg: require('@site/static/img/undraw_docusaurus_mountain.svg').default,
    description: (
      <>
        Поддержка чата на русском и английском языках. Интеллектуальная обработка запросов и контекстно-зависимые ответы.
      </>
    ),
  },
  {
    title: 'Генерация Изображений',
    Svg: require('@site/static/img/undraw_docusaurus_tree.svg').default,
    description: (
      <>
        Встроенная поддержка различных провайдеров генерации изображений: Stability AI, Replicate, Together AI и другие.
      </>
    ),
  },
  {
    title: 'Интеграция MCP',
    Svg: require('@site/static/img/undraw_docusaurus_react.svg').default,
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