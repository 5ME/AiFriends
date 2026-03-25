import { createRouter, createWebHistory } from 'vue-router'
import HomepageIndex from "@/views/homepage/HomepageIndex.vue";
import FriendIndex from "@/views/friend/FriendIndex.vue";
import CreateIndex from "@/views/create/CreateIndex.vue";
import NotFoundIndex from "@/views/error/NotFoundIndex.vue";
import LoginIndex from "@/views/user/account/LoginIndex.vue";
import RegisterIndex from "@/views/user/account/RegisterIndex.vue";
import SpaceIndex from "@/views/user/space/SpaceIndex.vue";
import ProfileIndex from "@/views/user/profile/ProfileIndex.vue";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      name: 'homepage-index',
      path: '/',
      component: HomepageIndex
    },
    {
      name: 'friend-index',
      path: '/friend/',
      component: FriendIndex
    },
    {
      name: 'create-index',
      path: '/create/',
      component: CreateIndex
    },
    {
      name: '404-index',
      path: '/404/',
      component: NotFoundIndex
    },
    {
      name: 'user-account-login-index',
      path: '/user/account/login/',
      component: LoginIndex
    },
    {
      name: 'user-account-register-index',
      path: '/user/account/register/',
      component: RegisterIndex
    },
    {
      name: 'user-space-index',
      path: '/user/space/:user_id/',
      component: SpaceIndex
    },
    {
      name: 'user-profile-index',
      path: '/user/profile/',
      component: ProfileIndex
    },
    {
      name: 'not-found-index',
      path: '/:pathMatch(.*)*',
      component: NotFoundIndex
    },
  ],
})

export default router
