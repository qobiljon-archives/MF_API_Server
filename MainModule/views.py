# coding=utf-8
from json import JSONDecodeError

from django.contrib.auth import authenticate
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
import calendar as cal
import datetime
import tempfile
import zipfile
import random
import json
import os

from MainModule.models import ActivityRecognitionData
from MainModule.models import AppUsageStats
from MainModule.models import LocationData
from MainModule.models import Intervention
from MainModule.models import Evaluation
from MainModule.models import Survey
from MainModule.models import Event
from MainModule.models import User


class Result:
    OK = 0
    FAIL = 1
    BAD_REQUEST = 2


def time_add(_time, _add):
    res = datetime.datetime(
        year=int(_time / 1000000),
        month=int(_time / 10000) % 100,
        day=int(_time / 100) % 100,
        hour=int(_time % 100)
    )
    if _add >= 0:
        res += datetime.timedelta(hours=int(_add / 60))
    else:
        res -= datetime.timedelta(hours=int(-_add / 60))
    return int("%02d%02d%02d%02d" % (res.year % 100, res.month, res.day, res.hour))


def is_user_occupied(user, from_ts, till_ts, except_event_id=None):
    if except_event_id is None:
        return Event.objects.filter(owner=user, start_ts__range=(from_ts, till_ts - 1)).exists() \
               or Event.objects.filter(owner=user, end_ts__range=(from_ts + 1, till_ts)).exists() \
               or Event.objects.filter(owner=user, start_ts__lte=from_ts, end_ts__gte=till_ts).exists()
    else:
        return Event.objects.filter(owner=user, start_ts__range=(from_ts, till_ts - 1)).exclude(id=except_event_id).exists() \
               or Event.objects.filter(owner=user, end_ts__range=(from_ts + 1, till_ts)).exclude(id=except_event_id).exists() \
               or Event.objects.filter(owner=user, start_ts__lte=from_ts, end_ts__gte=till_ts).exclude(id=except_event_id).exists()


def extract_weekday(millis):
    temp = datetime.datetime.fromtimestamp(millis / 1000)
    return cal.weekday(year=temp.year, month=temp.month, day=temp.day)


def add_timedelta(ts, delta):
    res = datetime.datetime.fromtimestamp(ts) + delta
    return int(res.timestamp())


def ts2readable(ts):
    return datetime.datetime.fromtimestamp(ts).strftime('%Y/%m/%d %H:%M')


def extract_post_params(request):
    _files = request.FILES
    if 'username' in _files:
        return json.loads('{"username": "%s", "password": "%s"}' % (
            _files['username'].read().decode('utf-8'),
            _files['password'].read().decode('utf-8')
        ))
    _post = request.POST
    if 'username' in _post:
        return _post
    else:
        try:
            return json.loads(request.body.decode('utf-8'))
        except JSONDecodeError:
            return {}


def are_params_filled(request_params, prerequisites):
    return len([outer for outer in prerequisites if outer not in request_params]) == 0


def seconds_to_readable_str(seconds):
    if seconds == 0:
        return '0'

    _hours = int(seconds / 3600)
    _minutes = int((seconds % 3600) / 60)
    _seconds = seconds % 60

    res = ''
    if _hours > 0:
        res += ' %d hours' % _hours
    if _minutes > 0:
        res += ' %d minutes' % _minutes
    if _seconds > 0:
        res += ' %d seconds' % _seconds

    return res[1:]


def retrieve_file_paths(root_dir):
    # setup file paths variable
    file_paths = []

    for subdir in os.listdir(root_dir):
        file_paths.append(subdir)
        if not os.path.isfile(os.path.join(root_dir, subdir)):
            for file in os.listdir(os.path.join(root_dir, subdir)):
                file_paths.append(os.path.join(subdir, file))

    # return all paths
    return file_paths


def attach_zip_data_extraction(response: HttpResponse):
    tmp_dir = tempfile.TemporaryDirectory()

    os.mkdir(os.path.join(tmp_dir.name, '1'))  # Users
    with open(os.path.join(tmp_dir.name, '1', 'Users.csv'), 'w', encoding='UTF8') as w:
        w.write('name,username\n')
        w.writelines([
            '"{0}","{1}"\n'.format(
                user.first_name,
                user.username
            ) for user in User.objects.filter(is_superuser=False)
        ])

    os.mkdir(os.path.join(tmp_dir.name, '2'))  # Events
    for _user in User.objects.filter(is_superuser=False):
        with open(os.path.join(tmp_dir.name, '2', '%s.csv' % _user), 'w', encoding='UTF8') as w:
            w.write('id,owner,title,start,end,intervention,intervention_selection_method,intervention_reminder,intervention_picked_time,expected_stress_level,expected_stress_type,expected_stress_cause,real_stress_level\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}","{4}","{5}","{6}","{7}","{8}","{9}","{10}","{11}","{12}"\n'.format(
                    event.id,
                    event.owner.username,
                    event.title,
                    datetime.datetime.fromtimestamp(event.start_ts).strftime('%d/%m/%y %H:%M:%S'),
                    datetime.datetime.fromtimestamp(event.end_ts).strftime('%d/%m/%y %H:%M:%S'),
                    event.intervention.description if event.intervention is not None else 'N/A',
                    ("system" if event.intervention.creation_method == Intervention.CREATION_METHOD_SYSTEM else ("self" if event.intervention.creator == event.owner else "peer")) if event.intervention is not None else 'N/A',
                    '%d mins %s' % (abs(event.intervention_reminder), "before" if event.intervention_reminder < 0 else "after") if event.intervention is not None else 'N/A',
                    datetime.datetime.fromtimestamp(event.intervention_last_picked_time).strftime('%d/%m/%y %H:%M:%S'),
                    event.expected_stress_level,
                    event.expected_stress_type,
                    event.expected_stress_cause if event.expected_stress_level != -1 and event.expected_stress_cause != '' else 'N/A',
                    Evaluation.objects.get(event=event).real_stress_level if Evaluation.objects.filter(event=event).exists() else 'N/A'
                ) for event in Event.objects.filter(owner=_user)
            ])

    os.mkdir(os.path.join(tmp_dir.name, '3'))  # Interventions
    for _user in User.objects.filter(is_superuser=False):
        with open(os.path.join(tmp_dir.name, '3', '%s.csv' % _user), 'w', encoding='UTF8') as w:
            w.write('description,creator,number_of_selections,number_of_likes,number_of_dislikes\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}","{4}"\n'.format(
                    intervention.description,
                    "system" if intervention.creation_method == Intervention.CREATION_METHOD_SYSTEM else intervention.creator.username,
                    intervention.number_of_selections,
                    intervention.number_of_likes,
                    intervention.number_of_dislikes
                ) for intervention in Intervention.objects.filter(creator=_user).order_by('creation_method').exclude(number_of_selections=0)
            ])
    with open(os.path.join(tmp_dir.name, '3', 'system.csv'), 'w', encoding='UTF8') as w:
        w.write('description,creator,number_of_selections,number_of_likes,number_of_dislikes\n')
        w.writelines([
            '"{0}","{1}","{2}","{3}","{4}"\n'.format(
                intervention.description,
                "system" if intervention.creation_method == Intervention.CREATION_METHOD_SYSTEM else intervention.creator.username,
                intervention.number_of_selections,
                intervention.number_of_likes,
                intervention.number_of_dislikes
            ) for intervention in Intervention.objects.filter(creator=None).order_by('creation_method').exclude(number_of_selections=0)
        ])

    os.mkdir(os.path.join(tmp_dir.name, '4'))  # Event Evaluations
    for _user in User.objects.filter(is_superuser=False):
        with open(os.path.join(tmp_dir.name, '4', '%s.csv' % _user), 'w', encoding='UTF8') as w:
            w.write('submitted_by,event_id,event_title,event_was_done,selected_intervention,intervention_effectiveness,intervention_was_done,expected_stress_level,real_stress_level,expected_stress_cause,real_stress_cause,journal\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}","{4}","{5}","{6}","{7}","{8}","{9}","{10}","{11}"\n'.format(
                    evaluation.event.owner.username,
                    evaluation.event.id,
                    evaluation.event.title,
                    evaluation.event_done,
                    evaluation.event.intervention.description if evaluation.event.intervention is not None else 'N/A',
                    evaluation.intervention_effectiveness if evaluation.event.intervention is not None else 'N/A',
                    evaluation.intervention_done,
                    evaluation.event.expected_stress_level,
                    evaluation.real_stress_level,
                    evaluation.event.expected_stress_cause,
                    evaluation.real_stress_cause,
                    evaluation.journal
                ) for evaluation in Evaluation.objects.filter(event__owner=_user)
            ])

    os.mkdir(os.path.join(tmp_dir.name, '5'))  # Surveys
    for _user in User.objects.filter(is_superuser=False):
        with open(os.path.join(tmp_dir.name, '5', '%s.csv' % _user), 'w', encoding='UTF8') as w:
            if Survey.objects.filter(user=_user).count() == 0:
                w.write('!!! EMPTY !!!\n')
            else:
                parts = list(Survey.QUESTIONS_LIST.keys())
                w.write('user,submission_time,%s\n' % ','.join([parts[0]] + (len(Survey.QUESTIONS_LIST[parts[0]]) - 1) * [''] + [parts[1]] + (len(Survey.QUESTIONS_LIST[parts[1]]) - 1) * [''] + [parts[2]] + (len(Survey.QUESTIONS_LIST[parts[2]]) - 1) * ['']))
                questions = ''
                for part in parts:
                    questions += '%s,' % ','.join(['"%s"' % question for question in Survey.QUESTIONS_LIST[part]])
                if questions.endswith(','):
                    questions = questions[:-1]
                w.write('"","",%s\n' % questions)
                w.writelines([
                    '"{0}","{1}",{2}\n'.format(
                        survey.user.username,
                        datetime.datetime.fromtimestamp(survey.timestamp).strftime('%d/%m/%y %H:%M:%S'),
                        ','.join('"%s"' % value for value in survey.values.split(','))
                    ) for survey in Survey.objects.filter(user=_user)
                ])

    os.mkdir(os.path.join(tmp_dir.name, '6'))  # App-Usages
    for _user in User.objects.filter(is_superuser=False):
        with open(os.path.join(tmp_dir.name, '6', '%s.csv' % _user), 'w', encoding='UTF8') as w:
            w.write('user,usage_start_time,usage_end_time,total_usage_by_far\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}"\n'.format(
                    usage.user.username,
                    datetime.datetime.fromtimestamp(usage.start_timestamp).strftime('%d/%m/%y %H:%M:%S'),
                    datetime.datetime.fromtimestamp(usage.end_timestamp).strftime('%d/%m/%y %H:%M:%S'),
                    seconds_to_readable_str(usage.total_time_in_foreground)
                ) for usage in AppUsageStats.objects.filter(user=_user).exclude(total_time_in_foreground=0).order_by('total_time_in_foreground')
            ])

    os.mkdir(os.path.join(tmp_dir.name, '7'))  # GPS Locations
    for _user in User.objects.filter(is_superuser=False):
        with open(os.path.join(tmp_dir.name, '7', '%s.csv' % _user), 'w', encoding='UTF8') as w:
            w.write('user,timestamp,latitude,longitude,altitude\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}","{4}"\n'.format(
                    location.user.username,
                    datetime.datetime.fromtimestamp(location.timestamp).strftime('%d/%m/%y %H:%M:%S'),
                    location.latitude,
                    location.longitude,
                    location.altitude
                ) for location in LocationData.objects.filter(user=_user).order_by('timestamp')
            ])

    os.mkdir(os.path.join(tmp_dir.name, '8'))  # Activity Recognitions
    for _user in User.objects.filter(is_superuser=False):
        with open(os.path.join(tmp_dir.name, '8', '%s.csv' % _user), 'w', encoding='UTF8') as w:
            w.write('8. Activity Recognitions\n')
            w.write('user,timestamp,detected_activity,confidence\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}"\n'.format(
                    activity.user.username,
                    datetime.datetime.fromtimestamp(activity.timestamp).strftime('%d/%m/%y %H:%M:%S'),
                    activity.activity,
                    activity.confidence
                ) for activity in ActivityRecognitionData.objects.filter(user=_user).order_by('timestamp')
            ])

    file_paths = retrieve_file_paths(tmp_dir.name)
    with zipfile.ZipFile(os.path.join(tmp_dir.name, 'result.zip'), 'w') as zip_file:
        for path in file_paths:
            os.chdir(tmp_dir.name)
            zip_file.write(path)
        with open(os.path.join(tmp_dir.name, 'result.zip'), 'rb') as r:
            response.write(r.read())


def attach_csv_data_extraction(response: HttpResponse):
    tmp_dir = tempfile.TemporaryDirectory()

    with open(os.path.join(tmp_dir.name, 'users.csv'), 'w', encoding='UTF8') as w:
        w.write('name,username\n')
        w.writelines([
            '"{0}","{1}"\n'.format(
                user.first_name,
                user.username
            ) for user in User.objects.filter(is_superuser=False)
        ])

    for _user in User.objects.filter(is_superuser=False):
        with open(os.path.join(tmp_dir.name, '%s.csv' % _user.username), 'w', encoding='UTF8') as w:
            w.write('1. EVENTS\n')
            w.write('id,owner,title,start,end,intervention,intervention_selection_method,intervention_reminder,intervention_picked_time,expected_stress_level,expected_stress_type,expected_stress_cause,real_stress_level\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}","{4}","{5}","{6}","{7}","{8}","{9}","{10}","{11}","{12}"\n'.format(
                    event.id,
                    event.owner.username,
                    event.title,
                    datetime.datetime.fromtimestamp(event.start_ts).strftime('%d/%m/%y %H:%M:%S'),
                    datetime.datetime.fromtimestamp(event.end_ts).strftime('%d/%m/%y %H:%M:%S'),
                    event.intervention.description if event.intervention is not None else 'N/A',
                    ("system" if event.intervention.creation_method == Intervention.CREATION_METHOD_SYSTEM else ("self" if event.intervention.creator == event.owner else "peer")) if event.intervention is not None else 'N/A',
                    '%d mins %s' % (abs(event.intervention_reminder), "before" if event.intervention_reminder < 0 else "after") if event.intervention is not None else 'N/A',
                    datetime.datetime.fromtimestamp(event.intervention_last_picked_time).strftime('%d/%m/%y %H:%M:%S'),
                    event.expected_stress_level,
                    event.expected_stress_type,
                    event.expected_stress_cause if event.expected_stress_level != -1 and event.expected_stress_cause != '' else 'N/A',
                    Evaluation.objects.get(event=event).real_stress_level if Evaluation.objects.filter(event=event).exists() else 'N/A'
                ) for event in Event.objects.filter(owner=_user)
            ])
            w.write('\n')

            w.write('2. INTERVENTIONS\n')
            w.write('description,creator,number_of_selections,number_of_likes,number_of_dislikes\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}","{4}"\n'.format(
                    intervention.description,
                    intervention.creator.username,
                    intervention.number_of_selections,
                    intervention.number_of_likes,
                    intervention.number_of_dislikes
                ) for intervention in Intervention.objects.filter(creator=_user).order_by('creation_method').exclude(number_of_selections=0)
            ])
            w.write('\n')

            w.write('3. EVENT EVALUATIONS\n')
            w.write('submitted_by,event_id,event_title,event_was_done,selected_intervention,intervention_effectiveness,intervention_was_done,expected_stress_level,real_stress_level,expected_stress_cause,real_stress_cause,journal\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}","{4}","{5}","{6}","{7}","{8}","{9}","{10}","{11}"\n'.format(
                    evaluation.event.owner.username,
                    evaluation.event.id,
                    evaluation.event.title,
                    evaluation.event_done,
                    evaluation.event.intervention.description if evaluation.event.intervention is not None else 'N/A',
                    evaluation.intervention_effectiveness if evaluation.event.intervention is not None else 'N/A',
                    evaluation.intervention_done,
                    evaluation.event.expected_stress_level,
                    evaluation.real_stress_level,
                    evaluation.event.expected_stress_cause,
                    evaluation.real_stress_cause,
                    evaluation.journal
                ) for evaluation in Evaluation.objects.filter(event__owner=_user)
            ])
            w.write('\n')

            w.write('4. SURVEYS\n')
            if Survey.objects.all().count() == 0:
                w.write('!!! EMPTY !!!\n')
            else:
                parts = list(Survey.QUESTIONS_LIST.keys())
                w.write('user,submission_time,%s\n' % ','.join([parts[0]] + (len(Survey.QUESTIONS_LIST[parts[0]]) - 1) * [''] + [parts[1]] + (len(Survey.QUESTIONS_LIST[parts[1]]) - 1) * [''] + [parts[2]] + (len(Survey.QUESTIONS_LIST[parts[2]]) - 1) * ['']))
                questions = ''
                for part in parts:
                    questions += '%s,' % ','.join(['"%s"' % question for question in Survey.QUESTIONS_LIST[part]])
                if questions.endswith(','):
                    questions = questions[:-1]
                w.write('"","",%s\n' % questions)
                w.writelines([
                    '"{0}","{1}",{2}\n'.format(
                        survey.user.username,
                        datetime.datetime.fromtimestamp(survey.timestamp).strftime('%d/%m/%y %H:%M:%S'),
                        ','.join('"%s"' % value for value in survey.values.split(','))
                    ) for survey in Survey.objects.filter(user=_user)
                ])
            w.write('\n')

            w.write('5. APP USAGE\n')
            w.write('user,usage_start_time,usage_end_time,total_usage_by_far\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}"\n'.format(
                    usage.user.username,
                    datetime.datetime.fromtimestamp(usage.start_timestamp).strftime('%d/%m/%y %H:%M:%S'),
                    datetime.datetime.fromtimestamp(usage.end_timestamp).strftime('%d/%m/%y %H:%M:%S'),
                    seconds_to_readable_str(usage.total_time_in_foreground)
                ) for usage in AppUsageStats.objects.filter(user=_user).exclude(total_time_in_foreground=0).order_by('total_time_in_foreground')
            ])
            w.write('\n')

            w.write('6. GPS Locations\n')
            w.write('user,timestamp,latitude,longitude,altitude\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}","{4}"\n'.format(
                    location.user.username,
                    datetime.datetime.fromtimestamp(location.timestamp).strftime('%d/%m/%y %H:%M:%S'),
                    location.latitude,
                    location.longitude,
                    location.altitude
                ) for location in LocationData.objects.filter(user=_user).order_by('timestamp')
            ])
            w.write('\n')

            w.write('7. Activity Recognitions\n')
            w.write('user,timestamp,detected_activity,confidence\n')
            w.writelines([
                '"{0}","{1}","{2}","{3}"\n'.format(
                    activity.user.username,
                    datetime.datetime.fromtimestamp(activity.timestamp).strftime('%d/%m/%y %H:%M:%S'),
                    activity.activity,
                    activity.confidence
                ) for activity in ActivityRecognitionData.objects.filter(user=_user).order_by('timestamp')
            ])

    file_paths = retrieve_file_paths(tmp_dir.name)
    with zipfile.ZipFile(os.path.join(tmp_dir.name, 'result.zip'), 'w') as zip_file:
        for path in file_paths:
            os.chdir(tmp_dir.name)
            zip_file.write(path)
        with open(os.path.join(tmp_dir.name, 'result.zip'), 'rb') as r:
            response.write(r.read())


@csrf_exempt
@require_http_methods(['POST'])
def handle_register(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'name']):
        if User.objects.filter(username=params['username']).exists():
            return JsonResponse(data={'result': Result.FAIL})
        else:
            user = User.create_user(
                username=params['username'],
                password=params['password'],
                name=params['name']
            )
            user.set_password(params['password'])
            user.save()
            return JsonResponse(data={'result': Result.OK})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_login(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            return JsonResponse(data={'result': Result.OK, 'name': user.first_name})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_event_create(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'title', 'stressLevel', 'startTime', 'endTime', 'intervention', 'interventionReminder', 'stressType', 'stressCause', 'repeatTill', 'repeatMode', 'eventReminder']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None and (len(params['intervention']) == 0 or Intervention.objects.filter(description=params['intervention']).exists()):
            intervention = Intervention.objects.get(description=params['intervention']) if len(params['intervention']) > 0 else None
            repeat_mode = int(params['repeatMode'])
            from_ts = int(params['startTime'])
            till_ts = int(params['endTime'])
            if repeat_mode is Event.REPEAT_MODE_NONE:
                if not is_user_occupied(user=user, from_ts=from_ts, till_ts=till_ts):
                    # create a single event
                    Event.create_event(
                        owner=User.objects.get(username=params['username']),
                        title=params['title'],
                        expected_stress_level=int(params['stressLevel']),
                        start_ts=from_ts,
                        end_ts=till_ts,
                        intervention=intervention,
                        intervention_reminder_timedelta=int(params['interventionReminder']),
                        expected_stress_type=params['stressType'],
                        expected_stress_cause=params['stressCause'],
                        repeat_mode=repeat_mode,
                        event_reminder_timedelta=int(params['eventReminder'])
                    )
                    return JsonResponse(data={'result': Result.OK})
                else:
                    return JsonResponse(data={'result': Result.FAIL})
            elif repeat_mode is Event.REPEAT_MODE_EVERYDAY:
                from_ts = int(params['startTime'])
                till_ts = int(params['endTime'])

                if till_ts - from_ts > 86400:
                    return JsonResponse(data={'result': Result.FAIL, 'reason': 'event length is longer than a day'})

                repetition_id = -1
                while from_ts < int(params['repeatTill']):
                    if not is_user_occupied(user=user, from_ts=from_ts, till_ts=till_ts):
                        event = Event.create_event(
                            owner=User.objects.get(username=params['username']),
                            title=params['title'],
                            start_ts=from_ts,
                            end_ts=till_ts,
                            intervention=intervention,
                            intervention_reminder_timedelta=int(params['interventionReminder']),
                            expected_stress_level=int(params['stressLevel']),
                            expected_stress_type=params['stressType'],
                            expected_stress_cause=params['stressCause'],
                            repeat_mode=repeat_mode,
                            repetition_id=repetition_id,
                            repeat_till=int(params['repeatTill']),
                            event_reminder_timedelta=int(params['eventReminder'])
                        )
                        repetition_id = event.repetition_id
                    from_ts += 86400
                    till_ts += 86400

                return JsonResponse(data={'result': Result.OK})
            elif repeat_mode is Event.REPEAT_MODE_WEEKLY:
                if int(params['endTime']) - int(params['startTime']) > 604800:
                    return JsonResponse(data={'result': Result.FAIL, 'reason': 'event length is longer than a week'})

                start_datetime = datetime.datetime.fromtimestamp(from_ts)
                end_datetime = datetime.datetime.fromtimestamp(till_ts)

                # create multiple events
                consider = [
                    bool(params['mon'].lower() == 'true'),
                    bool(params['tue'].lower() == 'true'),
                    bool(params['wed'].lower() == 'true'),
                    bool(params['thu'].lower() == 'true'),
                    bool(params['fri'].lower() == 'true'),
                    bool(params['sat'].lower() == 'true'),
                    bool(params['sun'].lower() == 'true'),
                ]

                repetition_id = -1
                repeat_till_date = datetime.datetime.fromtimestamp(int(params['repeatTill'])).replace(hour=0, minute=0, second=0)
                weekday = start_datetime.weekday()
                while start_datetime < repeat_till_date:
                    if consider[weekday]:
                        event = Event.create_event(
                            owner=User.objects.get(username=params['username']),
                            title=params['title'],
                            start_ts=int(start_datetime.timestamp()),
                            end_ts=int(end_datetime.timestamp()),
                            intervention=intervention,
                            intervention_reminder_timedelta=int(params['interventionReminder']),
                            expected_stress_level=int(params['stressLevel']),
                            expected_stress_type=params['stressType'],
                            expected_stress_cause=params['stressCause'],
                            repeat_mode=repeat_mode,
                            repetition_id=repetition_id,
                            repeat_till=int(params['repeatTill']),
                            event_reminder_timedelta=int(params['eventReminder'])
                        )
                        repetition_id = event.repetition_id
                    weekday = (weekday + 1) % 7
                    start_datetime += datetime.timedelta(days=1)
                    end_datetime += datetime.timedelta(days=1)
                return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_event_edit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'eventId']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            event = Event.objects.get(id=params['eventId'])
            if 'stressLevel' in params:
                event.stressLevel = params['stressLevel']
            if 'realStressLevel' in params:
                event.repeatId = params['realStressLevel']
            if 'title' in params:
                event.title = params['title']
            if are_params_filled(params, ['startTime', 'endTime']) and not is_user_occupied(user=user, from_ts=int(params['startTime']), till_ts=int(params['endTime']), except_event_id=event.id):
                event.start_ts = params['startTime']
                event.end_ts = params['endTime']
            if 'intervention' in params and Intervention.objects.filter(description=params['intervention']).exists():
                event.intervention = Intervention.objects.get(description=params['intervention'])
                event.intervention_last_picked_time = int(datetime.datetime.now().timestamp())
            if 'interventionReminder' in params:
                event.interventionReminder = params['interventionReminder']
            if 'stressType' in params:
                event.stressType = params['stressType']
            if 'stressCause' in params:
                event.stressCause = params['stressCause']
            if 'repeatMode' in params:
                event.repeatMode = params['repeatMode']
            if 'eventReminder' in params:
                event.eventReminder = params['eventReminder']
            if 'repeatId' in params:
                event.repeatId = params['repeatId']
            event.save()
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_event_delete(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']) and ('eventId' in params or 'repeatId' in params):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            if 'eventId' in params and Event.objects.filter(owner=user, id=params['eventId']).exists():
                Event.objects.get(id=params['eventId']).delete()
                return JsonResponse(data={'result': Result.OK})
            elif 'repeatId' in params and Event.objects.filter(owner=user, repetition_id=int(params['repeatId'])).exists():
                deleted_event_ids = []
                for event in Event.objects.filter(owner=user, repetition_id=int(params['repeatId'])):
                    deleted_event_ids += [event.id]
                    event.delete()
                return JsonResponse(data={'result': Result.OK, 'deleted_event_ids': deleted_event_ids})
            else:
                return JsonResponse(data={'result': Result.FAIL})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_events_fetch(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            from_ts = int(params['period_from'])
            till_ts = int(params['period_till'])
            matching_events = []

            for event in Event.objects.filter(owner=user, start_ts__range=(from_ts, till_ts - 1)):
                matching_events += [event]
            for event in Event.objects.filter(owner=user, end_ts__range=(from_ts + 1, till_ts)):
                if event not in matching_events:
                    matching_events += [event]
            for event in Event.objects.filter(owner=user, start_ts__lte=from_ts, end_ts__gte=till_ts):
                if event not in matching_events:
                    matching_events += [event]
            return JsonResponse(data={'result': Result.OK, 'array': [event.to_json() for event in matching_events]})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_intervention_create(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'interventionName']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None and not Intervention.objects.filter(description=params['interventionName'], is_public=True).exists():
            Intervention.create_intervention(description=params['interventionName'], creator=user)
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_system_intervention_fetch(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            system_interventions = []
            for intervention in Intervention.objects.filter(creation_method=Intervention.CREATION_METHOD_SYSTEM, is_public=True):
                system_interventions += [intervention]
            random.shuffle(system_interventions)
            return JsonResponse(data={'result': Result.OK, 'interventions': [intervention.to_json() for intervention in system_interventions]})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_peer_intervention_fetch(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            system_interventions = []
            for intervention in Intervention.objects.filter(creation_method=Intervention.CREATION_METHOD_USER, is_public=True):
                system_interventions += [intervention]
            random.shuffle(system_interventions)
            return JsonResponse(data={'result': Result.OK, 'interventions': [intervention.to_json() for intervention in system_interventions]})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_evaluation_submit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'eventId', 'interventionName', 'realStressLevel', 'realStressCause', 'journal', 'eventDone', 'interventionDone', 'sharedIntervention', 'intervEffectiveness']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None and Event.objects.filter(id=params['eventId'], owner=user).exists():
            event = Event.objects.get(id=params['eventId'])
            event.realStressLevel = params['realStressLevel']
            event.save()

            if event.intervention is not None:
                if 'like' in params and params['like']:
                    event.intervention.increment_likes_counter()
                elif 'dislike' in params and params['dislike']:
                    event.intervention.increment_dislikes_counter()

            Evaluation.submit_evaluation_singleton(
                event=event,
                real_stress_level=params['realStressLevel'],
                real_stress_cause=params['realStressCause'],
                journal=params['journal'],
                event_done=str(params['eventDone']).lower() == 'true',
                intervention_done=str(params['interventionDone']).lower() == 'true',
                intervention_effectiveness=params['intervEffectiveness']
            )
            event = Event.objects.get(id=params['eventId'])
            event.evaluated = True
            event.save()
            if params['sharedIntervention'].lower() == 'true' and Intervention.objects.filter(description=params['interventionName']).exists() and not Intervention.objects.filter(description=params['interventionName'], is_public=True).exists():
                intervention = Intervention.objects.get(description=params['interventionName'])
                intervention.is_public = True
                intervention.save()
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_evaluation_fetch(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'eventId']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None and Event.objects.filter(id=params['eventId'], owner=user).exists() and Evaluation.objects.filter(event__id=params['eventId']).exists():
            event = Event.objects.get(id=params['eventId'])
            return JsonResponse(data={'result': Result.OK, 'evaluation': Evaluation.objects.get(event=event).to_json()})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_survey_submit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'values']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None and Survey.survey_str_matches(params['values']):
            user = User.objects.get(username=params['username'])
            Survey.create_survey(user=User.objects.get(username=user), values=params['values'])
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_survey_questions_fetch(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            return JsonResponse(data={'result': Result.OK, 'surveys': Survey.QUESTIONS_LIST})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST', 'GET'])
def handle_extract_data_by_users(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None and user.is_superuser:
            response = HttpResponse(content_type='text/html')
            response['Content-Disposition'] = 'attachment; filename="MF_Data_%s.zip"' % datetime.datetime.now().strftime("%d-%m-%y %H-%M-%S")
            attach_zip_data_extraction(response)
            return response
        else:
            return JsonResponse(data={'result': Result.FAIL})
    elif request.method == 'GET':
        return render(request, template_name='data_extraction_page.html')
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST', 'GET'])
def handle_extract_data_by_data_sources(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None and user.is_superuser:
            response = HttpResponse(content_type='text/html')
            response['Content-Disposition'] = 'attachment; filename="MF_Data_%s.zip"' % datetime.datetime.now().strftime("%d-%m-%y %H-%M-%S")
            attach_csv_data_extraction(response)
            return response
        else:
            return JsonResponse(data={'result': Result.FAIL})
    elif request.method == 'GET':
        return render(request, template_name='data_extraction_page.html')
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_usage_stats_submit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'app_usage']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            for element in params['app_usage'].split(','):
                package_name, last_time_used, total_time_in_foreground = [int(value) if value.isdigit() else value for value in element.split(' ')]
                AppUsageStats.store_usage_changes(
                    user=user,
                    package_name=package_name,
                    end_timestamp=last_time_used,
                    total_time_in_foreground=total_time_in_foreground
                )
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_location_data_submit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'data']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            data = params['data']
            for line in data.split('\n'):
                timestamp, latitude, longitude, altitude = line.split(' ')
                timestamp, latitude, longitude, altitude = int(timestamp), float(latitude), float(longitude), float(altitude)
                LocationData.create_location_data(
                    user=user,
                    timestamp=timestamp,
                    latitude=latitude,
                    longitude=longitude,
                    altitude=altitude
                )
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_activity_recognition_submit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'data']):
        user = authenticate(username=params['username'], password=params['password'])
        if user is not None:
            data = params['data']
            for line in data.split('\n'):
                timestamp, activity, confidence = line.split(' ')
                timestamp, confidence = int(timestamp), float(confidence)
                ActivityRecognitionData.create_activity_recognition_data(
                    user=user,
                    timestamp=timestamp,
                    activity=activity,
                    confidence=confidence
                )
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
def page_index(request):
    return render(request, 'index.html')
