# coding=utf-8
from django.contrib import admin
from django.conf.urls import url
from django.urls import re_path

from MainModule.models import Intervention
from MainModule import views

Intervention.create_system_interventions()

urlpatterns = [
    url('admin/', admin.site.urls),

    re_path(r'^$', views.page_index),

    re_path(r'^register/?$', views.handle_register),
    re_path(r'^login/?$', views.handle_login),

    re_path(r'^event_create/?$', views.handle_event_create),
    re_path(r'^event_edit/?$', views.handle_event_edit),
    re_path(r'^event_delete/?$', views.handle_event_delete),
    re_path(r'^events_fetch/?$', views.handle_events_fetch),

    re_path(r'^intervention_create/?$', views.handle_intervention_create),
    re_path(r'^system_intervention_fetch/?$', views.handle_system_intervention_fetch),
    re_path(r'^peer_intervention_fetch/?$', views.handle_peer_intervention_fetch),

    re_path(r'^evaluation_submit/?$', views.handle_evaluation_submit),
    re_path(r'^evaluation_fetch/?$', views.handle_evaluation_fetch),

    re_path(r'^survey_submit/?$', views.handle_survey_submit),
    re_path(r'^survey_questions_fetch/?$', views.handle_survey_questions_fetch),

    re_path(r'^extract_data/separate_users?$', views.handle_extract_data_by_users),
    re_path(r'^extract_data/separate_data_sources?$', views.handle_extract_data_by_data_sources),

    re_path(r'^usage_stats_submit/?$', views.handle_usage_stats_submit),
    re_path(r'^location_data_submit/?$', views.handle_location_data_submit),
    re_path(r'^activity_recognition_submit/?$', views.handle_activity_recognition_submit)
]
