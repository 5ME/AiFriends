import {createRouter, createWebHistory} from 'vue-router'
import HomepageIndex from "@/views/homepage/HomepageIndex.vue";
import FriendIndex from "@/views/friend/FriendIndex.vue";
import CreateIndex from "@/views/create/CreateIndex.vue";
import NotFoundIndex from "@/views/error/NotFoundIndex.vue";
import LoginIndex from "@/views/user/account/LoginIndex.vue";
import RegisterIndex from "@/views/user/account/RegisterIndex.vue";
import SpaceIndex from "@/views/user/space/SpaceIndex.vue";
import ProfileIndex from "@/views/user/profile/ProfileIndex.vue";
import {useUserStore} from "@/stores/user.js";
import UpdateCharacter from "@/views/create/character/UpdateCharacter.vue";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      name: 'homepage-index',
      path: '/',
      component: HomepageIndex,
      meta: {
        needLogin: false
      }
    },
    {
      name: 'friend-index',
      path: '/friend/',
      component: FriendIndex,
      meta: {
        needLogin: true
      }
    },
    {
      name: 'create-index',
      path: '/create/',
      component: CreateIndex,
      meta: {
        needLogin: true
      }
    },
    {
      name: 'update-character',
      path: '/create/character/update/:character_id/',
      component: UpdateCharacter,
      meta: {
        needLogin: true
      }
    },
    {
      name: '404-index',
      path: '/404/',
      component: NotFoundIndex,
      meta: {
        needLogin: false
      }
    },
    {
      name: 'user-account-login-index',
      path: '/user/account/login/',
      component: LoginIndex,
      meta: {
        needLogin: false
      }
    },
    {
      name: 'user-account-register-index',
      path: '/user/account/register/',
      component: RegisterIndex,
      meta: {
        needLogin: false
      }
    },
    {
      name: 'user-space-index',
      path: '/user/space/:user_id/',
      component: SpaceIndex,
      meta: {
        needLogin: true
      }
    },
    {
      name: 'user-profile-index',
      path: '/user/profile/',
      component: ProfileIndex,
      meta: {
        needLogin: true
      }
    },
    {
      name: 'not-found-index',
      path: '/:pathMatch(.*)*',
      component: NotFoundIndex,
      meta: {
        needLogin: false
      }
    },
  ],
})

router.beforeEach((to, from) => {
  const user = useUserStore()
  if (to.meta.needLogin && user.hasPulledUserInfo && !user.isLogin()) {
    return {name: 'user-account-login-index'}
  }
  return true
})

export default router
