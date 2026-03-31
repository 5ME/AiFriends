<script setup lang="ts">
import {ref} from "vue";
import UpdateIcon from "@/components/character/icons/UpdateIcon.vue";
import RemoveIcon from "@/components/character/icons/RemoveIcon.vue";
import {useUserStore} from "@/stores/user";
import Character from "@/components/character/Character.vue";
import api from "@/js/http/api";

const props = defineProps(['character', 'canEdit'])
const emit = defineEmits(['remove'])
const isHover = ref(false)
const user = useUserStore()

async function handleRemoveCharacter() {
  try {
    const response = await api.post('api/create/character/remove/', {
      character_id: props.character.id
    })
    if (response.data.message === 'success') {
      emit('remove', props.character.id)
    }
  } catch (e) {
    console.log(e)
  }
}
</script>

<template>
  <div>
    <div v-if="character" class="card card-border bg-base-100 h-100 w-60 shadow-sm cursor-pointer
                                transition-transform duration-300"
         :class="{'scale-105': isHover, 'shadow-2xl': isHover}"
         @mouseover="isHover=true" @mouseout="isHover=false">
      <figure>
        <img :src="character.background_image" alt="bg"/>
      </figure>
      <div class="card-body">
        <div class="flex gap-4">
          <div class="avatar">
            <div class="rounded-full w-10">
              <img :src="character.photo" alt=""/>
            </div>
          </div>
          <h2 class="card-title line-clamp-1 break-all">
            {{ character.name }}
          </h2>
        </div>
        <p class="line-clamp-2 break-all">
          {{ character.profile }}
        </p>
        <div class="card-actions justify-end"
             v-if="canEdit && character.author.user_id === user.id">
          <RouterLink class="btn btn-ghost btn-sm btn-circle bg-neutral-700"
                      :to="{name: 'update-character', params: {character_id: character.id}}">
            <UpdateIcon/>
          </RouterLink>
          <button class="btn btn-ghost btn-sm btn-circle bg-red-700"
                  @click="handleRemoveCharacter">
            <RemoveIcon/>
          </button>
        </div>
      </div>
    </div>
    <RouterLink class="flex items-center mt-2 gap-2"
                :to="{name: 'user-space-index', params: {user_id: character.author.user_id}}">
      <div class="avatar">
        <div class="rounded-full w-5">
          <img :src="character.author.photo" alt=""/>
        </div>
      </div>
      <div class="text-xs text-neutral-500 line-clamp-1 break-all">
        {{ character.author.username }}
      </div>
    </RouterLink>
  </div>
</template>

<style scoped>

</style>