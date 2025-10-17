import React from 'react';
import ComponentCreator from '@docusaurus/ComponentCreator';

export default [
  {
    path: '/docs',
    component: ComponentCreator('/docs', '102'),
    routes: [
      {
        path: '/docs',
        component: ComponentCreator('/docs', '56f'),
        routes: [
          {
            path: '/docs',
            component: ComponentCreator('/docs', '9ee'),
            routes: [
              {
                path: '/docs/intro',
                component: ComponentCreator('/docs/intro', '61d'),
                exact: true,
                sidebar: "tutorialSidebar"
              }
            ]
          }
        ]
      }
    ]
  },
  {
    path: '/',
    component: ComponentCreator('/', '081'),
    exact: true
  },
  {
    path: '*',
    component: ComponentCreator('*'),
  },
];
