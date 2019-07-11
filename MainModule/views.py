# coding=utf-8
from json import JSONDecodeError

from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import calendar as cal
import datetime
import operator
import random
import json

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
            return None


def are_params_filled(request_params, prerequisites):
    return len([outer for outer in prerequisites if outer not in request_params]) == 0


@csrf_exempt
@require_http_methods(['POST'])
def handle_register(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'name']):
        if User.objects.filter(username=params['username']).exists():
            return JsonResponse(data={'result': Result.FAIL})
        else:
            User.create_user(
                username=params['username'],
                password=params['password'],
                name=params['name']
            )
            return JsonResponse(data={'result': Result.OK})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_login(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        if User.objects.filter(username=params['username'], password=params['password']).exists():
            user = User.objects.get(username=params['username'])
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
        if User.objects.filter(username=params['username'], password=params['password']).exists() and (len(params['intervention']) == 0 or Intervention.objects.filter(description=params['intervention']).exists()):
            user = User.objects.get(username=params['username'])
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
        if User.objects.filter(username=params['username'], password=params['password']).exists():
            user = User.objects.get(username=params['username'])
            event = Event.objects.get(id=params['eventId'])
            if 'stressLevel' in params:
                event.stressLevel = params['stressLevel']
            if 'realStressLevel' in params:
                event.repeatId = params['realStressLevel']
            if 'title' in params:
                event.title = params['title']
            if are_params_filled(params, ['startTime', 'endTime']) and not is_user_occupied(user=user, from_ts=params['startTime'], till_ts=params['endTime'], except_event_id=event.id):
                event.start_ts = params['startTime']
                event.end_ts = params['endTime']
            if 'intervention' in params:
                event.intervention = params['intervention']
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
        if User.objects.filter(username=params['username'], password=params['password']).exists():
            user = User.objects.get(username=params['username'])
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
        if User.objects.filter(username=params['username'], password=params['password']).exists():
            user = User.objects.get(username=params['username'])
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
        if User.objects.filter(username=params['username'], password=params['password']).exists() and not Intervention.objects.filter(description=params['interventionName'], is_public=True).exists():
            user = User.objects.get(username=params['username'])
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
        if User.objects.filter(username=params['username'], password=params['password']).exists():
            user = User.objects.get(username=params['username'])
            if 'sort' in params:
                if params['sort'] == 'recent_choice':
                    events = [event for event in Event.objects.filter(owner=user).exclude(intervention=None)]
                    events = sorted(events, key=operator.attrgetter(''))  # TODO: COME BACK
                elif params['sort'] == 'popularity':
                    pass
                else:
                    system_interventions = []
                    for intervention in Intervention.objects.filter(creation_method=Intervention.CREATION_METHOD_SYSTEM, is_public=True):
                        system_interventions += [intervention]
                    random.shuffle(system_interventions)
                    return JsonResponse(data={'result': Result.OK, 'interventions': [intervention.to_json() for intervention in system_interventions]})
            else:
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
        if User.objects.filter(username=params['username'], password=params['password']).exists():
            user = User.objects.get(username=params['username'])
            if 'sort' in params:
                if params['sort'] == 'recent_choice':
                    pass
                elif params['sort'] == 'popularity':
                    pass
                else:
                    system_interventions = []
                    for intervention in Intervention.objects.filter(creation_method=Intervention.CREATION_METHOD_USER, is_public=True):
                        system_interventions += [intervention]
                    return JsonResponse(data={'result': Result.OK, 'interventions': [intervention.to_json() for intervention in system_interventions]})
            else:
                system_interventions = []
                for intervention in Intervention.objects.filter(creation_method=Intervention.CREATION_METHOD_USER, is_public=True):
                    system_interventions += [intervention]
                return JsonResponse(data={'result': Result.OK, 'interventions': [intervention.to_json() for intervention in system_interventions]})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_evaluation_submit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'eventId', 'interventionName', 'startTime', 'endTime', 'realStressLevel', 'realStressCause', 'journal', 'eventDone', 'interventionDone', 'sharedIntervention', 'intervEffectiveness']):
        if User.objects.filter(username=params['username'], password=params['password']).exists() and Event.objects.filter(id=params['eventId'], owner__username=params['username']).exists():
            event = Event.objects.get(eventId=params['eventId'])
            event.realStressLevel = params['realStressLevel']
            event.save()

            if event.intervention is not None:
                if 'like' in params and params['like']:
                    event.intervention.increment_likes_counter()
                elif 'dislike' in params and params['dislike']:
                    event.intervention.increment_dislikes_counter()

            Evaluation.submit_evaluation_singleton(
                event=event,
                start_ts=params['startTime'],
                end_ts=params['endTime'],
                real_stress_level=params['realStressLevel'],
                real_stress_cause=params['realStressCause'],
                journal=params['journal'],
                event_done=params['eventDone'],
                intervention_done=params['interventionDone'],
                intervention_effectiveness=params['intervEffectiveness']
            )
            event = Event.objects.get(eventId=params['eventId'])
            event.evaluated = True
            event.save()
            if params['sharedIntervention'] and not Intervention.objects.filter(description=params['interventionName'], is_public=True).exists():
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
        if User.objects.filter(username=params['username']).exists() and Event.objects.filter(id=params['eventId'], owner__username=params['username']).exists() and Evaluation.objects.filter(event__id=params['eventId']).exists():
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
        if User.objects.filter(username=params['username'], password=params['password']).exists() and Survey.survey_str_matches(params['values']):
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
        if User.objects.filter(username=params['username'], password=params['password']).exists():
            return JsonResponse(data={'result': Result.OK, 'surveys': Survey.QUESTIONS_LIST})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_extract_data_to_csv(request):
    return JsonResponse(data={'result': 'NOT IMPLEMENTED'})
