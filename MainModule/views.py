# coding=utf-8
from json import JSONDecodeError

from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import calendar as cal
import datetime
import json
import os

from MainModule.settings import BASE_DIR

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
               or Event.objects.filter(owner=user, start_ts__lte=from_ts, endTime__gte=till_ts).exists()
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
            user.login()
            return JsonResponse(data={'result': Result.OK, 'name': user.first_name})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_logout(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']):
        if User.objects.filter(username=request['username'], password=request['password']).exists():
            User.objects.get(username=request['username']).logout(request)
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_event_create(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'title', 'stressLevel', 'startTime', 'endTime', 'intervention', 'interventionReminder', 'stressType', 'stressCause', 'repeatTill', 'repeatMode', 'eventReminder']) and User.objects.filter(username=params['username'], password=params['password']).exists() and Intervention.objects.filter(description=params['intervention']).exists():
        user = User.objects.get(username=params['username'])
        if user.logged_in():
            if params['repeatMode'] is Event.REPEAT_MODE_NONE:
                if not is_user_occupied(user=user, from_ts=params['startTime'], till_ts=params['endTime']):
                    # create a single event
                    Event.create_event(
                        owner=User.objects.get(username=params['username']),
                        title=params['title'],
                        expected_stress_level=params['stressLevel'],
                        start_ts=params['startTime'],
                        end_ts=params['endTime'],
                        intervention=Intervention.objects.get(description=params['intervention']),
                        intervention_reminder_timedelta=params['interventionReminder'],
                        expected_stress_type=params['stressType'],
                        expected_stress_cause=params['stressCause'],
                        repeat_mode=params['repeatMode'],
                        event_reminder_timedelta=params['eventReminder']
                    )
                    return JsonResponse(data={'result': Result.OK})
                else:
                    return JsonResponse(data={'result': Result.FAIL})
            elif params['repeatMode'] is Event.REPEAT_MODE_EVERYDAY:
                from_ts = params['startTime']
                till_ts = params['endTime']

                if till_ts - from_ts > 86400000:
                    return JsonResponse(data={'result': Result.FAIL, 'reason': 'event length is longer than a day'})

                repetition_id = -1
                while from_ts < params['repeatTill']:
                    if not is_user_occupied(user=user, from_ts=from_ts, till_ts=till_ts):
                        event = Event.create_event(
                            owner=user,
                            title=params['title'],
                            start_ts=from_ts,
                            end_ts=till_ts,
                            repeat_mode=params['repeatMode'],
                            repeat_till=params['repeatTill'],
                            repetition_id=repetition_id,
                            intervention=Intervention.objects.get(description=params['intervention']),
                            intervention_reminder_timedelta=params['interventionReminder'],
                            expected_stress_level=params['stressLevel'],
                            expected_stress_type=params['stressType'],
                            expected_stress_cause=params['stressCause'],
                            event_reminder_timedelta=params['eventReminder']
                        )
                        repetition_id = event.repetition_id
                    from_ts += 86400000
                    till_ts += 86400000

                return JsonResponse(data={'result': Result.OK})
            elif params['repeatMode'] is Event.REPEAT_MODE_WEEKLY:
                # create multiple events
                start = [
                    params['startTime'] if params['mon'] else None,
                    params['startTime'] if params['tue'] else None,
                    params['startTime'] if params['wed'] else None,
                    params['startTime'] if params['thu'] else None,
                    params['startTime'] if params['fri'] else None,
                    params['startTime'] if params['sat'] else None,
                    params['startTime'] if params['sun'] else None
                ]
                end = [
                    params['endTime'] if params['mon'] else None,
                    params['endTime'] if params['tue'] else None,
                    params['endTime'] if params['wed'] else None,
                    params['endTime'] if params['thu'] else None,
                    params['endTime'] if params['fri'] else None,
                    params['endTime'] if params['sat'] else None,
                    params['endTime'] if params['sun'] else None
                ]

                if params['endTime'] - params['startTime'] > 604800000:
                    return JsonResponse(data={'result': Result.FAIL, 'reason': 'event length is longer than a week'})

                repetition_id = -1
                for x in range(7):
                    if start[x] is None:
                        continue
                    day_delta = (7 - (extract_weekday(start[x]) - x)) % 7
                    start[x] = add_timedelta(start[x], datetime.timedelta(days=day_delta))
                    end[x] = add_timedelta(end[x], datetime.timedelta(days=day_delta))

                    while start[x] < params['repeatTill']:
                        if not is_user_occupied(user=user, from_ts=start[x], till_ts=end[x]):
                            event = Event.create_event(
                                owner=user,
                                title=params['title'],
                                start_ts=start[x],
                                end_ts=end[x],
                                repeat_mode=params['repeatMode'],
                                repeat_till=params['repeatTill'],
                                repetition_id=repetition_id,
                                intervention=Intervention.objects.get(description=params['intervention']),
                                intervention_reminder_timedelta=params['interventionReminder'],
                                expected_stress_level=params['stressLevel'],
                                expected_stress_type=params['stressType'],
                                expected_stress_cause=params['stressCause'],
                                event_reminder_timedelta=params['eventReminder']
                            )
                            repetition_id = event.repetition_id
                        start[x] += 604800000
                        end[x] += 604800000
                return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_event_edit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'eventId']) and User.objects.filter(username=params['username'], password=params['password']).exists():
        user = User.objects.get(username=params['username'])
        if user.logged_in() and Event.objects.filter(owner=user, id=params['eventId']).exists():
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
    if are_params_filled(params, ['username', 'password']) and ('eventId' in params or 'repeatId' in params) and User.objects.filter(username=params['username'], password=params['password']).exists():
        user = User.objects.get(username=params['username'])
        if user.logged_in():
            if 'eventId' in params and Event.objects.filter(owner=user, id=params['eventId']).exists():
                Event.objects.get(id=params['eventId']).delete()
                return JsonResponse(data={'result': Result.OK})
            elif 'repeatId' in params and Event.objects.filter(owner=user, repeatId=params['repeatId']).exists():
                deleted_events_count = 0
                for event in Event.objects.filter(owner=user, repeatId=params['repeatId']):
                    deleted_events_count += 1
                    event.delete()
                return JsonResponse(data={'result': Result.OK, 'deleted_events_count': deleted_events_count})
        return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_events_fetch(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']) and User.objects.filter(username=params['username'], password=params['password']).exists():
        user = User.objects.get(username=params['username'])
        if user.logged_in():
            from_ts = params['period_from']
            till_ts = params['period_till']
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
    if are_params_filled(params, ['username', 'password', 'interventionName']) and User.objects.filter(username=params['username'], password=params['password']).exists():
        user = User.objects.get(username=params['username'])
        if user.logged_in() and not Intervention.objects.filter(description=params['interventionName'], is_public=True).exists():
            Intervention.create_intervention(description=params['interventionName'], creator=user)
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_system_intervention_fetch(request):
    system_interventions = []
    for intervention in Intervention.objects.filter(creation_method=Intervention.CREATION_METHOD_SYSTEM, is_public=True):
        system_interventions += [intervention]
    return JsonResponse(data={'result': Result.OK, 'interventions': [intervention.to_json() for intervention in system_interventions]})


@csrf_exempt
@require_http_methods(['POST'])
def handle_peer_intervention_fetch(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']) and User.objects.filter(username=params['username'], password=params['password']).exists():
        user = User.objects.get(username=params['username'])
        if user.logged_in():
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
    if are_params_filled(params, ['username', 'password', 'eventId', 'interventionName', 'startTime', 'endTime', 'realStressLevel', 'realStressCause', 'journal', 'eventDone', 'interventionDone', 'sharedIntervention', 'intervEffectiveness']) and User.objects.filter(username=params['username'], password=params['password']).exists():
        user = User.objects.get(username=params['username'])
        if user.logged_in() and Event.objects.filter(id=params['eventId'], owner=user).exists():
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
    if are_params_filled(params, ['username', 'password', 'eventId']) and User.objects.filter(username=params['username']).exists() and Event.objects.filter(id=params['eventId'], owner__username=params['username']).exists():
        user = User.objects.get(username=params['username'])
        event = Event.objects.get(id=params['eventId'])
        if user.logged_in() and Evaluation.objects.filter(event=event).exists():
            return JsonResponse(data={'result': Result.OK, 'evaluation': Evaluation.objects.get(event=event).to_json()})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_survey_submit(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password', 'values']) and User.objects.filter(username=params['username'], password=params['password']).exists() and Survey.survey_str_matches(params['values']):
        user = User.objects.get(username=params['username'])
        if user.logged_in():
            Survey.create_survey(user=User.objects.get(username=user), values=params['values'])
            return JsonResponse(data={'result': Result.OK})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST,
                                  'reason': 'Username, password, or survey elements were not completely passed as a POST argument!'})


@csrf_exempt
@require_http_methods(['POST'])
def handle_survey_questions_fetch(request):
    params = extract_post_params(request)
    if are_params_filled(params, ['username', 'password']) and User.objects.filter(username=params['username'], password=params['password']).exists():
        user = User.objects.get(username=params['username'])
        if user.logged_in():
            return JsonResponse(data={'result': Result.OK, 'surveys': Survey.QUESTIONS_LIST})
        else:
            return JsonResponse(data={'result': Result.FAIL})
    else:
        return JsonResponse(data={'result': Result.BAD_REQUEST})


@csrf_exempt
@require_http_methods(['POST'])
def handle_extract_data_to_csv(request):
    return JsonResponse(data={'result': 'NOT IMPLEMENTED'})
