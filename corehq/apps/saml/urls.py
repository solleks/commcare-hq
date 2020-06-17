
from django.conf.urls import url

from djangosaml2 import views

urlpatterns = [
    url(r'^login/', views.login, name='saml2_login'),
    url(r'^acs/', views.AssertionConsumerServiceView.as_view(), name='saml2_acs'),
    url(r'^logout/', views.logout, name='saml2_logout'),
    url(r'^ls/', views.logout_service, name='saml2_ls'),
    url(r'^ls/post/', views.logout_service_post, name='saml2_ls_post'),
    url(r'^metadata/', views.metadata, name='saml2_metadata'),
]
