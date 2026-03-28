from django.urls import path, re_path

from web.views.index import index
from web.views.user.account.get_user_info import GetUserInfoView
from web.views.user.account.login import LoginView
from web.views.user.account.logout import LogoutView
from web.views.user.account.refresh_token import RefreshTokenView
from web.views.user.account.register import RegisterView

urlpatterns = [
    path('api/user/account/login/', LoginView.as_view()),
    path('api/user/account/logout/', LogoutView.as_view()),
    path('api/user/account/register/', RegisterView.as_view()),
    path('api/user/account/refresh_token/', RefreshTokenView.as_view()),
    path('api/user/account/get_user_info/', GetUserInfoView.as_view()),

    path('', index, name='index'),

    # 兜底路由，在前端任意路径（静态文件除外）下刷新时，django都自动路由到根路径下，剩下的路由交由前端处理
    re_path(r'^(?!media/|static/|assets/).*$', index),
]
