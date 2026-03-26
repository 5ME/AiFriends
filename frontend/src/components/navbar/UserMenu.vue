<script setup lang="ts">
import {useUserStore} from '@/stores/user';
import UserLogoutIcon from "@/components/navbar/icons/UserLogoutIcon.vue";
import UserSpaceIcon from "@/components/navbar/icons/UserSpaceIcon.vue";
import UserProfileIcon from "@/components/navbar/icons/UserProfileIcon.vue";

const user = useUserStore()

function closeMenu() {
  const element = document.activeElement
  if (element && element instanceof HTMLElement)
    element.blur()
}
</script>

<template>
  <div class="dropdown dropdown-end">
    <div tabindex="0" role="button" class="avatar btn btn-circle w-10 h-10 mr-6">
      <div class="w-10 rounded-full">
        <img :src="user.photo" alt="avatar"/>
      </div>
    </div>
    <ul tabindex="-1" class="dropdown-content menu bg-base-100 rounded-box z-1 w-52 p-2 shadow-lg">
      <li>
        <RouterLink :to="{name: 'user-space-index', params: {user_id: user.id}}"
                    @click="closeMenu">
          <div class="avatar">
            <div class="w-12 rounded-full">
              <img :src="user.photo" alt="avatar"/>
            </div>
          </div>
          <span class="text-base font-bold line-clamp-1">{{ user.username }}</span>
        </RouterLink>
      </li>
      <li>
        <RouterLink :to="{name: 'user-space-index', params: {user_id: user.id}}"
                    @click="closeMenu" class="text-base py-3">
          <UserSpaceIcon/>
          个人空间
        </RouterLink>
      </li>
      <li>
        <RouterLink :to="{name: 'user-profile-index'}" class="text-base py-3"
                    @click="closeMenu">
          <UserProfileIcon/>
          编辑资料
        </RouterLink>
      </li>
      <li></li>
      <li>
        <a @click="closeMenu" class="text-base py-3" style="color: firebrick">
          <UserLogoutIcon/>
          退出登录
        </a>
      </li>
    </ul>
  </div>
</template>

<style scoped>

</style>