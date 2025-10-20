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
    component: ComponentCreator('/guide/docs', '779'),
    routes: [
      {
        path: '/guide/docs',
        component: ComponentCreator('/guide/docs', 'ca4'),
        routes: [
          {
            path: '/guide/docs',
            component: ComponentCreator('/guide/docs', '2b9'),
            routes: [
              {
                path: '/guide/docs/guide/architecture',
                component: ComponentCreator('/guide/docs/guide/architecture', '576'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/guide/docs/guide/features',
                component: ComponentCreator('/guide/docs/guide/features', 'b71'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/guide/docs/guide/mcp_integration',
                component: ComponentCreator('/guide/docs/guide/mcp_integration', '456'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/guide/docs/guide/overview',
                component: ComponentCreator('/guide/docs/guide/overview', '8ad'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/guide/docs/guide/setup',
                component: ComponentCreator('/guide/docs/guide/setup', 'c05'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
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
