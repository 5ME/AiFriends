import os

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from web.models.character import Character, Voice
from web.models.friend import Friend
from web.models.user import UserProfile


class Command(BaseCommand):
    help = '清理测试残留的脏数据'

    def add_arguments(self, parser):
        parser.add_argument(
            '--files',
            action='store_true',
            help='清理磁盘上无对应 DB 记录的孤儿文件',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='清理所有类型的脏数据（角色 + 文件 + 用户 + 音色）',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅列出，不实际删除',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clean_all = options['all']

        # 1. Characters with missing files
        dirty_ids = []
        for c in Character.objects.all():
            try:
                c.photo.url
                c.background_image.url
            except ValueError:
                dirty_ids.append(c.id)

        if dirty_ids:
            self.stdout.write(f'[角色] 发现 {len(dirty_ids)} 条无图片文件: {dirty_ids}')
            if not dry_run:
                deleted, _ = Character.objects.filter(id__in=dirty_ids).delete()
                self.stdout.write(self.style.SUCCESS(f'  已删除 {deleted} 条记录'))
        else:
            self.stdout.write(self.style.SUCCESS('[角色] 全部正常'))

        # 2. Orphan files on disk
        if options['files'] or clean_all:
            self._clean_orphan_files(dry_run)

        # 3. Orphan users & voices
        if clean_all:
            self._clean_orphan_users(dry_run)
            self._clean_orphan_voices(dry_run)

    def _clean_orphan_files(self, dry_run):
        valid_paths = set()
        for c in Character.objects.all():
            try:
                valid_paths.add(os.path.normpath(c.photo.name))
            except ValueError:
                pass
            try:
                valid_paths.add(os.path.normpath(c.background_image.name))
            except ValueError:
                pass

        media_root = str(settings.MEDIA_ROOT)
        orphan_count = 0

        for dir_name in ['character/photos', 'character/background_images']:
            dir_path = os.path.join(media_root, dir_name)
            if not os.path.isdir(dir_path):
                continue
            for filename in os.listdir(dir_path):
                file_rel = os.path.normpath(os.path.join(dir_name, filename))
                if file_rel not in valid_paths:
                    if dry_run:
                        self.stdout.write(f'  [DRY-RUN] 将删除文件: {file_rel}')
                    else:
                        os.remove(os.path.join(dir_path, filename))
                    orphan_count += 1

        if orphan_count:
            action = '发现' if dry_run else '已删除'
            self.stdout.write(self.style.SUCCESS(f'[文件] {action} {orphan_count} 个孤儿文件'))
        else:
            self.stdout.write(self.style.SUCCESS('[文件] 全部有对应 DB 记录'))

    def _clean_orphan_users(self, dry_run):
        orphan_ids = []
        for u in User.objects.all():
            profile = UserProfile.objects.filter(user=u).first()
            if not profile:
                continue
            chars = Character.objects.filter(author=profile).count()
            friends = Friend.objects.filter(user_profile=profile).count()
            if chars == 0 and friends == 0:
                orphan_ids.append((u.id, u.username))

        if orphan_ids:
            names = [name for _, name in orphan_ids]
            self.stdout.write(f'[用户] 发现 {len(orphan_ids)} 个无内容用户: {names}')
            if not dry_run:
                for uid, _ in orphan_ids:
                    User.objects.filter(id=uid).delete()
                self.stdout.write(self.style.SUCCESS(f'  已删除 {len(orphan_ids)} 个用户'))
        else:
            self.stdout.write(self.style.SUCCESS('[用户] 全部正常'))

    def _clean_orphan_voices(self, dry_run):
        orphan_ids = []
        for v in Voice.objects.filter(is_builtin=False):
            if Character.objects.filter(voice=v).count() == 0:
                orphan_ids.append((v.id, v.name, v.voice_id))

        if orphan_ids:
            if dry_run:
                for vid, name, voice_id in orphan_ids:
                    self.stdout.write(f'  [DRY-RUN] 将删除音色: id={vid} name={name} voice_id={voice_id}')
            else:
                deleted, _ = Voice.objects.filter(
                    id__in=[vid for vid, _, _ in orphan_ids]
                ).delete()
                self.stdout.write(self.style.SUCCESS(f'[音色] 已删除 {deleted} 个未使用的音色'))
        else:
            self.stdout.write(self.style.SUCCESS('[音色] 全部正常'))
