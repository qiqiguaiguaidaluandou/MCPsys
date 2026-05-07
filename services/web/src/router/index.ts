import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import type { Role } from '@/api/types';
import { setupGuards } from './guards';

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean;
    roles?: Role[];
    layout?: 'app' | 'auth';
    title?: string;
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/LoginPage.vue'),
    meta: { requiresAuth: false, layout: 'auth', title: 'auth.login.title' },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/dashboard/DashboardPage.vue'),
    meta: { requiresAuth: true, layout: 'app', title: 'nav.dashboard' },
  },
  {
    path: '/services',
    name: 'ServiceList',
    component: () => import('@/views/services/ServiceListPage.vue'),
    meta: { requiresAuth: true, layout: 'app', title: 'nav.serviceList' },
  },
  {
    path: '/services/:id',
    name: 'ServiceDetail',
    component: () => import('@/views/services/ServiceDetailPage.vue'),
    meta: { requiresAuth: true, layout: 'app' },
  },
  {
    path: '/applications',
    name: 'ApplicationList',
    component: () => import('@/views/applications/ApplicationListPage.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'operator'], layout: 'app', title: 'nav.applications' },
  },
  {
    path: '/applications/:id',
    name: 'ApplicationDetail',
    component: () => import('@/views/applications/ApplicationDetailPage.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'operator'], layout: 'app' },
  },
  {
    path: '/api-keys',
    name: 'ApiKeyList',
    component: () => import('@/views/api-keys/ApiKeyListPage.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'operator'], layout: 'app', title: 'nav.apiKeys' },
  },
  {
    path: '/call-logs',
    name: 'CallLogList',
    component: () => import('@/views/call-logs/CallLogListPage.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'operator'], layout: 'app', title: 'nav.callLogs' },
  },
  {
    path: '/users',
    name: 'UserList',
    component: () => import('@/views/users/UserListPage.vue'),
    meta: { requiresAuth: true, roles: ['admin'], layout: 'app', title: 'nav.users' },
  },
  {
    path: '/users/:id',
    name: 'UserDetail',
    component: () => import('@/views/users/UserDetailPage.vue'),
    meta: { requiresAuth: true, roles: ['admin'], layout: 'app' },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/profile/ProfilePage.vue'),
    meta: { requiresAuth: true, layout: 'app', title: 'nav.profile' },
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/error/ForbiddenPage.vue'),
    meta: { requiresAuth: false, layout: 'app', title: 'error.forbidden.title' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/NotFoundPage.vue'),
    meta: { requiresAuth: false, layout: 'app', title: 'error.notFound.title' },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

setupGuards(router);

export default router;
