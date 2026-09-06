"""初始化内置配置数据 — 幂等，可反复执行。

覆盖三类数据：
1. 内置音色（longanyang 龙安洋 / longanhuan 龙安欢，阿里云百炼 cosyvoice-v3-flash）
   —— 代码拥有的系统资源，与代码保持一致（字段过期会更新）。
2. SystemPrompt（reply 框架约束 / memory 记忆摘要）
   —— 管理员可配置的默认模板，仅在缺失时创建，绝不覆盖管理员修改。
3. 超级用户（可选）—— 仅当 DJANGO_SUPERUSER_USERNAME + DJANGO_SUPERUSER_PASSWORD
   同时设置时创建；用户名已存在则跳过（不会重置密码）。

deploy/server-deploy.sh 每次部署都会执行本命令，因此必须保持幂等与非破坏性。
"""
import logging
import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from web.models.character import Voice
from web.models.friend import SystemPrompt

logger = logging.getLogger(__name__)

# 内置音色 — voice_id 是阿里云百炼 cosyvoice-v3-flash 官方音色 ID
BUILTIN_VOICES = [
    {'name': '龙安洋', 'voice_id': 'longanyang', 'profile': '阳光大男孩'},
    {'name': '龙安欢', 'voice_id': 'longanhuan', 'profile': '欢脱元气女'},
]

# title=reply — 聊天第 3 层（框架约束），管理员可后续在 /admin/ 调整
REPLY_PROMPT = """【角色定位】
你是 AI Friends 平台的虚拟角色，为玩家提供情绪价值。要像朋友或恋人一样自然互动——会调侃、会撒娇、会逗乐，语气亲密、有温度、有真实感。

【发言原则】
1. 回复简短自然：通常 1~3 句话，总长不超过 100 字，符合日常聊天节奏。
2. 情绪真实：用对话本身传递情绪，禁止动作描写和舞台指令。
3. 表达鲜活：多用口语短句，可适当用语气词开头；偶尔只说一句话，或留个反问让对话延续。
4. 避免重复：不重复前几轮说过的话，不用套话和模板句。
5. 正面回答：用户问问题，直接正面回答，不绕弯。

【格式约束（TTS 友好，务必遵守）】
- 以中文口语为主，可自然使用常见外语词（品牌名、英文缩写、OK/bye 这类语气词）。
- 禁用数学符号、emoji 和生僻特殊符号；避免整段外语（中文音色读大段英文会别扭）。
- 禁止破折号、括号、星号、省略号等符号，禁止「（笑）」「*点头*」这类动作标记。
- 不要客服腔、不要作文腔，要像真人吐槽一样自然。

【风格倾向】
- 灵活搭配：关心/鼓励、调侃/搞笑、暧昧/恋人、生活/日常、回忆/共享经历。
- 始终贴合角色的性格设定和与玩家的关系，措辞、语气、句式符合角色模板。"""

# title=memory — 记忆摘要指令（纯文本输出，代码不做 JSON 解析；
# Friend.memory 字段上限 5000 字，这里要求 2000 字留足余量）
MEMORY_PROMPT = """你是 AI Friends 平台的记忆管理模块。根据【原始记忆】和【最近对话】，提取值得长期保存的用户信息，更新记忆。

【规则】
1. 只记录用户（user）的信息，不记录 AI 自己的发言。
2. 不记纯闲聊和寒暄，只保留有价值的信息。
3. 不编造、不推测，只基于对话中的真实内容。
4. 没有新信息就原样保留现有记忆，不要为了改而改。
5. 合并重复信息，去掉冗余。
6. 重点记录：用户的偏好、习惯、个人情况，以及情绪与关系的变化。
7. 总长度控制在 2000 字以内（数据库字段上限是 5000 字，留足余量）。

【输出格式】
直接输出更新后的完整记忆文本——纯文本，不要 JSON、不要解释、不要 Markdown 代码块。
可用简短小标题分块，例如「基本信息」「关系与情绪」「关键事件」「近期状态」；某块没有内容就省略。"""

BUILTIN_SYSTEM_PROMPTS = [
    {'title': SystemPrompt.Title.REPLY, 'order_number': 0, 'prompt': REPLY_PROMPT},
    {'title': SystemPrompt.Title.MEMORY, 'order_number': 0, 'prompt': MEMORY_PROMPT},
]


class Command(BaseCommand):
    help = (
        '初始化内置配置数据（音色 + SystemPrompt + 可选超级用户）。'
        '幂等：音色与代码对齐；SystemPrompt/超级用户已存在则跳过。'
    )

    def handle(self, *args, **options):
        self._seed_voices()
        self._seed_system_prompts()
        self._seed_superuser()

    def _seed_voices(self):
        """内置音色是代码拥有的系统资源：缺失则创建，字段过期则更新。

        用 filter().first() + 逐字段比较而非 update_or_create：
        手动重复录入产生多行时不会抛 MultipleObjectsReturned。
        """
        for spec in BUILTIN_VOICES:
            voice = Voice.objects.filter(voice_id=spec['voice_id']).first()
            if voice is None:
                Voice.objects.create(**spec, is_builtin=True)
                self.stdout.write(self.style.SUCCESS(
                    f'创建音色: {spec["name"]} ({spec["voice_id"]})'
                ))
                logger.info('seed_builtins: 创建音色 %s (%s)', spec['name'], spec['voice_id'])
                continue
            changed = (
                voice.name != spec['name']
                or voice.profile != spec['profile']
                or not voice.is_builtin
            )
            if changed:
                voice.name = spec['name']
                voice.profile = spec['profile']
                voice.is_builtin = True
                voice.save(update_fields=['name', 'profile', 'is_builtin'])
                self.stdout.write(self.style.SUCCESS(
                    f'更新音色: {spec["name"]} ({spec["voice_id"]})'
                ))
                logger.info('seed_builtins: 更新音色 %s (%s)', spec['name'], spec['voice_id'])
            else:
                self.stdout.write(f'跳过音色（已是最新）: {spec["voice_id"]}')

    def _seed_system_prompts(self):
        """SystemPrompt 是管理员可配置的默认模板：只在缺失时创建，绝不覆盖。"""
        for spec in BUILTIN_SYSTEM_PROMPTS:
            prompt, created = SystemPrompt.objects.get_or_create(
                title=spec['title'],
                defaults=spec,
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'创建 SystemPrompt: {spec["title"]}'))
                logger.info('seed_builtins: 创建 SystemPrompt %s', spec['title'])
            else:
                self.stdout.write(f'跳过 SystemPrompt（已存在，保留现有内容）: {spec["title"]}')

    def _seed_superuser(self):
        """可选：环境变量同时提供用户名+密码时创建超级用户；已存在则跳过。"""
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        if not (username and password):
            self.stdout.write(
                '跳过管理员账号：未同时设置 DJANGO_SUPERUSER_USERNAME / '
                'DJANGO_SUPERUSER_PASSWORD（可后续手动 createsuperuser）'
            )
            return
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'跳过管理员账号（用户名已存在）: {username}')
            return
        User.objects.create_superuser(
            username=username,
            email=os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f'已创建管理员账号: {username}'))
        logger.info('seed_builtins: 创建超级用户 %s', username)
