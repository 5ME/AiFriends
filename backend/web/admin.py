from django.contrib import admin

from web.models.document import UserDocument, DocumentChunk
from web.models.character import Character, Voice
from web.models.friend import Friend, Message, SystemPrompt
from web.models.usage import APIUsage
from web.models.user import UserProfile


# Register your models here.
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    raw_id_fields = ("user",)


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    raw_id_fields = ("author", "voice")


admin.site.register(Voice)


@admin.register(Friend)
class FriendAdmin(admin.ModelAdmin):
    raw_id_fields = ("user_profile", "character",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    raw_id_fields = ("friend",)


admin.site.register(SystemPrompt)


@admin.register(UserDocument)
class UserDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'file_type', 'status',
                    'chunks_count', 'created_at')
    search_fields = ('title', 'owner__user__username')
    list_filter = ('status', 'file_type')
    readonly_fields = ('chunks_count', 'celery_task_id', 'error_message',
                       'created_at', 'updated_at')
    raw_id_fields = ('owner',)
    list_select_related = ('owner__user',)


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_index', 'token_count', 'owner', 'created_at')
    search_fields = ('content', 'document__title')
    list_filter = ('document__file_type',)
    exclude = ('embedding',)
    list_select_related = ('document__owner__user', 'owner__user')
    raw_id_fields = ('document', 'owner')


@admin.register(APIUsage)
class APIUsageAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'api_type', 'model_name',
                    'token_count', 'duration_ms', 'success', 'created_at')
    search_fields = ('user__user__username', 'model_name')
    list_filter = ('api_type', 'success', 'created_at')
    readonly_fields = ('id', 'user', 'api_type', 'model_name',
                       'token_count', 'duration_ms', 'success',
                       'error_message', 'created_at')
    list_select_related = ('user__user',)
