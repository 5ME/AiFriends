# Optimize Bare Except and Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all 17 bare `except:` statements with `except Exception as e:` plus `logger.exception()` calls, add Django LOGGING config, and remove debug `print()` calls that leak credentials.

**Architecture:** Every Django view follows the same anti-pattern: a bare `except:` that silently swallows all exceptions and returns a generic "系统异常" 500 response with zero diagnostic info. The fix is mechanical: add `import logging` + module-level logger, change `except:` to `except Exception as e:`, add `logger.exception()` before the error return. Also add Django `LOGGING` dict to `settings.py` so errors actually go somewhere.

**Tech Stack:** Django 6.0, Python `logging` stdlib

---

### Task 1: Add Django LOGGING configuration

**Files:**
- Modify: `backend/backend/settings.py`

- [ ] **Step 1: Add LOGGING dict to settings.py**

Append to the end of `backend/backend/settings.py`:

```python
# 日志配置
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {process:d} {thread:d}: {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {asctime} {module}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'web.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'web': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

- [ ] **Step 2: Verify settings load correctly**

```bash
cd backend && python manage.py check
```
Expected: "System check identified no issues (0 silenced)."

- [ ] **Step 3: Commit**

```bash
git add backend/backend/settings.py
git commit -m "feat: add Django LOGGING configuration with console and rotating file handlers"
```

---

### Task 2: Fix bare excepts in user account views (4 files)

**Files:**
- Modify: `backend/web/views/user/account/login.py`
- Modify: `backend/web/views/user/account/register.py`
- Modify: `backend/web/views/user/account/refresh_token.py`
- Modify: `backend/web/views/user/account/get_user_info.py`

- [ ] **Step 1: Fix login.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 36 from:
```python
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('用户登录异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 2: Fix register.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Remove the three debug `print()` lines (19, 21, 23):
```python
            print(username, password)
            print(user)
            print(user_profile)
```

Change line 36 from:
```python
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('用户注册异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 3: Fix refresh_token.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 30 from:
```python
        except:
            return Response({'message': 'refresh_token 过期'},
                            status=status.HTTP_401_UNAUTHORIZED)
```
to:
```python
        except Exception as e:
            logger.exception('刷新token异常: %s', e)
            return Response({'message': 'refresh_token 过期'},
                            status=status.HTTP_401_UNAUTHORIZED)
```

- [ ] **Step 4: Fix get_user_info.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 23 from:
```python
        except:
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('获取用户信息异常: %s', e)
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 5: Verify imports and syntax**

```bash
cd backend && python -c "from web.views.user.account import login, register, refresh_token, get_user_info; print('OK')"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/web/views/user/account/login.py backend/web/views/user/account/register.py backend/web/views/user/account/refresh_token.py backend/web/views/user/account/get_user_info.py
git commit -m "fix: replace bare excepts with logger.exception in user account views"
```

---

### Task 3: Fix bare excepts in friend views (5 files)

**Files:**
- Modify: `backend/web/views/friend/get_list.py`
- Modify: `backend/web/views/friend/remove.py`
- Modify: `backend/web/views/friend/is_friend.py`
- Modify: `backend/web/views/friend/get_or_create.py`
- Modify: `backend/web/views/friend/message/get_history.py`

- [ ] **Step 1: Fix get_list.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 40 from:
```python
        except:
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('获取好友列表异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 2: Fix remove.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 17 from:
```python
        except:
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('删除好友异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 3: Fix is_friend.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 23 from:
```python
        except:
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('检查好友关系异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 4: Fix get_or_create.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 43 from:
```python
        except:
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('获取或创建好友异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 5: Fix get_history.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 28 from:
```python
        except:
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('获取聊天历史异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 6: Verify imports**

```bash
cd backend && python -c "from web.views.friend import get_list, remove, is_friend, get_or_create; from web.views.friend.message import get_history; print('OK')"
```
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/web/views/friend/get_list.py backend/web/views/friend/remove.py backend/web/views/friend/is_friend.py backend/web/views/friend/get_or_create.py backend/web/views/friend/message/get_history.py
git commit -m "fix: replace bare excepts with logger.exception in friend views"
```

---

### Task 4: Fix bare except in homepage index view

**Files:**
- Modify: `backend/web/views/homepage/index.py`

- [ ] **Step 1: Fix index.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 37 from:
```python
        except:
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('首页加载异常: %s', e)
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 2: Verify import**

```bash
cd backend && python -c "from web.views.homepage import index; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/homepage/index.py
git commit -m "fix: replace bare except with logger.exception in homepage index view"
```

---

### Task 5: Fix bare excepts in create character views (5 files)

**Files:**
- Modify: `backend/web/views/create/character/get_list.py`
- Modify: `backend/web/views/create/character/create.py`
- Modify: `backend/web/views/create/character/remove.py`
- Modify: `backend/web/views/create/character/update.py`
- Modify: `backend/web/views/create/character/get_single.py`

- [ ] **Step 1: Fix get_list.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 44 from:
```python
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('获取角色列表异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 2: Fix create.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 39 from:
```python
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('创建角色异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 3: Fix remove.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 21 from:
```python
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('删除角色异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 4: Fix update.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 52 from:
```python
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('更新角色异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 5: Fix get_single.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 36 from:
```python
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('获取角色详情异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 6: Verify imports**

```bash
cd backend && python -c "from web.views.create.character import get_list, create, remove, update, get_single; print('OK')"
```
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/web/views/create/character/get_list.py backend/web/views/create/character/create.py backend/web/views/create/character/remove.py backend/web/views/create/character/update.py backend/web/views/create/character/get_single.py
git commit -m "fix: replace bare excepts with logger.exception in create character views"
```

---

### Task 6: Fix bare except in voice and profile views (2 files)

**Files:**
- Modify: `backend/web/views/create/character/voice/get_list.py`
- Modify: `backend/web/views/user/profile/update.py`

- [ ] **Step 1: Fix voice/get_list.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 23 from:
```python
        except:
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('获取音色列表异常: %s', e)
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 2: Fix user/profile/update.py**

Add after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 49 from:
```python
        except:
            return Response(data={'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
to:
```python
        except Exception as e:
            logger.exception('更新用户资料异常: %s', e)
            return Response(data={'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 3: Verify imports**

```bash
cd backend && python -c "from web.views.create.character.voice import get_list; from web.views.user.profile import update; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/web/views/create/character/voice/get_list.py backend/web/views/user/profile/update.py
git commit -m "fix: replace bare excepts with logger.exception in voice and profile views"
```

---

### Task 7: Replace print() with logging in document utilities

**Files:**
- Modify: `backend/web/documents/utils/insert_documents.py`

- [ ] **Step 1: Fix insert_documents.py**

Add at top after existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Change line 17 from:
```python
    print(f'已切分成 {len(chunks)} 个片段')
```
to:
```python
    logger.info('已切分成 %d 个片段', len(chunks))
```

Change lines 31-32 from:
```python
    print(f'{type(lance_db)}')
    print(f'已插入 {lance_db._table.count_rows()} 行数据')
```
to:
```python
    logger.info('%s', type(lance_db))
    logger.info('已插入 %d 行数据', lance_db._table.count_rows())
```

- [ ] **Step 2: Verify import**

```bash
cd backend && python -c "import web.documents.utils.insert_documents; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/web/documents/utils/insert_documents.py
git commit -m "fix: replace print() with logger.info in document insertion utility"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run Django system check**

```bash
cd backend && python manage.py check
```
Expected: "System check identified no issues (0 silenced)."

- [ ] **Step 2: Verify no bare excepts remain**

```bash
grep -rn "except:" backend/web/views/
```
Expected: no matches (empty output)

- [ ] **Step 3: Verify no debug print() in register.py**

```bash
grep -n "print(" backend/web/views/user/account/register.py
```
Expected: no matches (empty output)

- [ ] **Step 4: Verify LOGGING is in settings**

```bash
grep -c "LOGGING" backend/backend/settings.py
```
Expected: `1`

- [ ] **Step 5: Commit any remaining changes**

```bash
git status
```
Expected: clean working tree
