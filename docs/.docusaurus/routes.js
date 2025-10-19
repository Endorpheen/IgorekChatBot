import React from 'react';
import ComponentCreator from '@docusaurus/ComponentCreator';

export default [
  {
    path: '/guide/',
    component: ComponentCreator('/guide/', '7ac'),
    exact: true
  },
  {
    path: '/guide/docs',
    component: ComponentCreator('/guide/docs', '2ae'),
    routes: [
      {
        path: '/guide/docs',
        component: ComponentCreator('/guide/docs', 'cb4'),
        routes: [
          {
            path: '/guide/docs',
            component: ComponentCreator('/guide/docs', '549'),
            routes: [
              {
                path: '/guide/docs/intro',
                component: ComponentCreator('/guide/docs/intro', '03c'),
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
    path: '*',
    component: ComponentCreator('*'),
  },
];
