# coding=utf-8
from django.core.validators import validate_comma_separated_integer_list
from django.contrib.auth.models import AbstractUser
from django.contrib.sessions.models import Session
from django.db import models
import datetime
import os

from MainModule.settings import BASE_DIR


class User(AbstractUser):
    def to_json(self):
        return {
            'username': self.username,
            'name': self.first_name
        }

    @staticmethod
    def create_user(username, password, name, is_superuser=False):
        if User.objects.all().filter(username=username).exists():
            return None
        else:
            if is_superuser:
                return User.objects.create_superuser(username=username, password=password, first_name=name)
            else:
                return User.objects.create(username=username, password=password, first_name=name)


class Intervention(models.Model):
    CREATION_METHOD_SYSTEM = 0
    CREATION_METHOD_USER = 1

    description = models.CharField(max_length=128, primary_key=True)
    creator = models.ForeignKey(to='User', null=True, on_delete=models.SET_NULL)
    creation_method = models.SmallIntegerField(default=CREATION_METHOD_SYSTEM)
    is_public = models.BooleanField(default=True)
    number_of_selections = models.IntegerField(default=0)
    number_of_likes = models.IntegerField(default=0)
    number_of_dislikes = models.IntegerField(default=0)

    def increment_selection_counter(self):
        self.number_of_selections += 1
        self.save()

    def increment_likes_counter(self):
        self.number_of_likes += 1
        self.save()

    def increment_dislikes_counter(self):
        self.number_of_dislikes += 1
        self.save()

    def to_json(self):
        return {
            'description': self.description,
            'creator': self.creator.username if self.creator is not None else 'SYSTEM',
            'creation_method': self.creation_method,
            'is_public': self.is_public,
            'number_of_selections': self.number_of_selections,
            'number_of_likes': self.number_of_likes,
            'number_of_dislikes': self.number_of_dislikes
        }

    @staticmethod
    def create_intervention(description, creator: User = None, make_public=False):
        if creator is None:
            return Intervention.objects.create(
                description=description,
                creator=creator,
                is_public=True,
                creation_method=Intervention.CREATION_METHOD_SYSTEM
            )
        else:
            return Intervention.objects.create(
                description=description,
                creator=creator,
                is_public=make_public,
                creation_method=Intervention.CREATION_METHOD_USER
            )

    @staticmethod
    def create_system_interventions():
        system_interventions = Intervention.objects.filter(creation_method=Intervention.CREATION_METHOD_SYSTEM)
        if system_interventions.exists():
            return  # TODO: swap thi sline with "system_interventions.delete()" in production

        print('Creating system interventions...')
        with open(os.path.join(BASE_DIR, 'assets', 'system_interventions.txt'), 'r', encoding='UTF8') as r:
            for line in r.readlines():
                Intervention.create_intervention(description=line[:-1])
        print('System interventions created')


class Event(models.Model):
    REPEAT_MODE_NONE = 0
    REPEAT_MODE_EVERYDAY = 1
    REPEAT_MODE_WEEKLY = 2

    id = models.AutoField(primary_key=True)
    owner = models.ForeignKey(to='User', on_delete=models.CASCADE)
    title = models.CharField(max_length=128)
    start_ts = models.BigIntegerField()
    end_ts = models.BigIntegerField()
    repetition_id = models.BigIntegerField(default=0)
    repeat_mode = models.SmallIntegerField()
    repeat_till = models.BigIntegerField(default=0)
    event_reminder = models.SmallIntegerField()
    intervention = models.ForeignKey(to='Intervention', null=True, on_delete=models.SET_NULL)
    intervention_reminder = models.SmallIntegerField(default=0)
    intervention_last_picked_time = models.BigIntegerField()
    expected_stress_level = models.PositiveSmallIntegerField()
    expected_stress_type = models.CharField(max_length=32)
    expected_stress_cause = models.CharField(max_length=128)
    real_stress_level = models.PositiveSmallIntegerField(default=0)
    evaluated = models.BooleanField(default=False)

    def to_json(self):
        return {
            'eventId': self.id,
            'ownerUsername': self.owner.username,
            'ownerFullName': self.owner.first_name,
            'title': self.title,
            'stressLevel': self.expected_stress_level,
            'realStressLevel': self.real_stress_level,
            'startTime': self.start_ts,
            'endTime': self.end_ts,
            'intervention': self.intervention.to_json() if self.intervention is not None else 'N/A',
            'interventionReminder': self.intervention_reminder,
            'interventionLastPickedTime': self.intervention_last_picked_time,
            'stressType': self.expected_stress_type,
            'stressCause': self.expected_stress_cause,
            'repeatMode': self.repeat_mode,
            'repeatId': self.repetition_id,
            'eventReminder': self.event_reminder,
            'isEvaluated': self.evaluated,
            'repeatTill': self.repeat_till
        }

    @staticmethod
    def create_event(owner: User, title, start_ts, end_ts, intervention: Intervention, intervention_reminder_timedelta, expected_stress_level, expected_stress_type, expected_stress_cause, event_reminder_timedelta, repeat_mode, repeat_till=-1, repetition_id=-1):
        if intervention is not None:
            intervention.increment_selection_counter()
        if repetition_id != -1:
            return Event.objects.create(
                owner=owner,
                title=title,
                start_ts=start_ts,
                end_ts=end_ts,
                repetition_id=repetition_id,
                repeat_mode=repeat_mode,
                repeat_till=repeat_till,
                event_reminder=event_reminder_timedelta,
                intervention=intervention,
                intervention_reminder=intervention_reminder_timedelta,
                intervention_last_picked_time=int(datetime.datetime.now().timestamp()),
                expected_stress_level=expected_stress_level,
                expected_stress_type=expected_stress_type,
                expected_stress_cause=expected_stress_cause
            )
        else:
            event = Event.objects.create(
                owner=owner,
                title=title,
                start_ts=start_ts,
                end_ts=end_ts,
                repeat_mode=repeat_mode,
                repeat_till=repeat_till,
                event_reminder=event_reminder_timedelta,
                intervention=intervention,
                intervention_reminder=intervention_reminder_timedelta,
                intervention_last_picked_time=int(datetime.datetime.now().timestamp()),
                expected_stress_level=expected_stress_level,
                expected_stress_type=expected_stress_type,
                expected_stress_cause=expected_stress_cause
            )
            event.repetition_id = event.id
            event.save()
            return event


class Evaluation(models.Model):
    event = models.OneToOneField(to='Event', primary_key=True, on_delete=models.CASCADE)
    start_ts = models.BigIntegerField()
    end_ts = models.BigIntegerField()
    real_stress_level = models.PositiveSmallIntegerField()
    real_stress_cause = models.CharField(max_length=128, default='')
    journal = models.CharField(max_length=128, default='')
    event_done = models.BooleanField()
    intervention_done = models.BooleanField()
    intervention_effectiveness = models.PositiveSmallIntegerField()

    def to_json(self):
        return {
            'id': self.id,
            'event': self.event.to_json(),
            'startTime': self.start_ts,
            'endTime': self.end_ts,
            'realStressLevel': self.real_stress_level,
            'realStressCause': self.real_stress_cause,
            'journal': self.journal,
            'eventDone': self.event_done,
            'interventionDone': self.intervention_done,
            'interventionEffectiveness': self.intervention_effectiveness
        }

    @staticmethod
    def submit_evaluation_singleton(event, start_ts, end_ts, real_stress_level, real_stress_cause, journal, event_done, intervention_done, intervention_effectiveness):
        if Evaluation.objects.filter(event=event).exists():
            evaluation = Evaluation.objects.get(event=event)
            evaluation.start_ts = start_ts
            evaluation.end_ts = end_ts
            evaluation.real_stress_level = real_stress_level
            evaluation.real_stress_cause = real_stress_cause
            evaluation.journal = journal
            evaluation.event_done = event_done
            evaluation.intervention_done = intervention_done
            evaluation.intervention_effectiveness = intervention_effectiveness
            evaluation.save()
        else:
            return Evaluation.objects.create(
                event=event,
                start_ts=start_ts,
                end_ts=end_ts,
                real_stress_level=real_stress_level,
                real_stress_cause=real_stress_cause,
                journal=journal,
                event_done=event_done,
                intervention_done=intervention_done,
                intervention_effectiveness=intervention_effectiveness
            )


class Survey(models.Model):
    class Meta:
        unique_together = ['user', 'timestamp']

    QUESTIONS_LIST = {
        'Part 1': [
            '예상치 않게 생긴 일 때문에 속상한 적이 얼마나 자주 있었습니까?',
            '중요한 일을 조절할 수 없다고 느낀 적이 얼마나 자주 있었습니까?',
            '불안하고 스트레스받았다고 느낀 적이 얼마나 자주 있었습니까?',
            '개인적인 문제를 잘 처리할 수 있다고 자신감을 가진 적이 얼마나 자주 있었습니까?',
            '일이 내 뜻대로 진행되고 있다고 느낀 적이 얼마나 자주 있었습니까?',
            '자신이 해야 할 모든 일에 잘 대처할 수 없었던 적이 얼마나 자주 있었습니까?',
            '일상에서 짜증나는 것을 잘 조절할 수 있었던 적이 얼마나 자주 있었습니까?',
            '자신이 일을 잘 해냈다고 느낀 적이 얼마나 자주 있었습니까?',
            '자신의 능력으로는 어떻게 해 볼 수 없는 일 때문에 화가 난 적이 얼마나 자주 있었습니까?',
            '어려운 일이 너무 많아져서 극복할 수 없다고 느낀 적이 얼마나 자주 있었습니까?'
        ],
        'Part 2': [
            '대다수의 사람들과 의견이 다를 경우에도, 내 의견을 분명히 말하는 편이다.',
            '나에게 주어진 상황은 내게 책임이 있다고 생각한다.',
            '현재의 내 활동반경(생활영역)을 넓힐 생각이 없다.',
            '대다수의 사람들은 나를 사랑스럽고 애정어리게 본다.',
            '그저 하루하루를 살아가고 있을 뿐 장래에 대해서는 별로 생각하지 않는다.',
            '살아 온 내 인생을 돌이켜 볼 때 현재의 결과에 만족한다.',
            '는 무슨 일을 결정하는 데 있어 다른 사람들의 영향을 받지 않는 편이다.',
            '매일매일 해야 하는 일들이 힘겹다.',
            '나 자신과 인생살이에 자극을 줄 만한 새로운 경험을 하는 것이 중요하다고 생각한다.',
            '남들과 친밀한 인간관계를 유지하는 것이 어렵고 힘들다.',
            '나는 삶의 방향과 목적에 대한 감각을 가지고 있다.',
            '나 자신에 대해 자부심과 자신감을 갖고 있다.',
            '나는 다른 사람들이 나를 어떻게 생각하는지 걱정하는 경향이 있다.',
            '나는 주변의 사람들과 지역사회에 잘 어울리지 않는다.',
            '지난 세월을 되돌아 보면, 내 자신이 크게 발전하지 못했다고 생각된다.',
            '나의 고민을 털어놓을 만한 가까운 친구가 별로 없어 가끔 외로움을 느낀다.',
            '가끔 매일 하는 일들이 사소하고 중요하지 않은 것처럼 느껴진다.',
            '내가 아는 많은 사람들은 인생에서 나보다 더 많은 것을 성취하는 것 같다.',
            '나는 강한 의견을 가진 사람으로부터 영향을 받는 편이다.',
            '매일의 생활에서 내가 해야 할 책임들을 잘 해내고 있다.',
            '그동안 한 개인으로서 크게 발전해 왔다고 생각한다.',
            '가족이나 친구들과 친밀한 대화를 나누는 것을 즐긴다.',
            '내 인생에서 무엇을 성취하려고 하는지 잘 모르겠다.',
            '내 성격의 거의 모든 면을 좋아한다.',
            '내 의견이 비록 다른 여러 사람들의 의견과 반대되는 경우에도, 나는 내 의견이 옳다고 확신한다.',
            '내가 해야 할 일들이 힘겹게 느껴질 때가 있다.',
            '현재의 생활방식을 바꿔야 할 새로운 상황에 처하는 것을 싫어한다.',
            '사람들은 나를 다른사람들에게 기꺼이 시간을 내어줄 수 있는 사람으로 묘사한다.',
            '미래의 계획을 짜고 그 계획을 실현시키려고 노력하는 것을 즐긴다.',
            '많은 면에서 내가 성취한 것에 대해 실망을 느낀다.',
            '논쟁의 여지가 있는 문제들에 대해서 내 자신의 의견을 내세우지 못한다.',
            '생활을 만족스럽게 꾸려 나가는 것이 쉽지 않다.',
            '나에게 있어서 삶은 끊임없이 배우고, 변화하고, 성장하는 과정이었다.',
            '다른 사람들과 다정하고 신뢰깊은 관계를 별로 경험하지 못했다.',
            '나는 인생목표를 가지고 살아간다.',
            '나는 나에 대해 다른사람들이 스스로 느끼는 것 만큼 긍정적이지 않다.',
            '내 스스로 정한 기준에 의해 내 자신을 평가하지, 남들의 기준에 의해 평가하지 않는다.',
            '내 가정과 생활방식을 내 맘에 들도록 꾸려올 수 있었다.',
            '내 인생을 크게 개선하거나 바꾸겠다는 생각은 오래 전에 버렸다.',
            '내 친구들은 믿을 수 있고, 그들도 나를 믿을 수 있다고 생각한다.',
            '나는 마치 내가 인생에서 해야 할 모든 것을 다한것처럼 느낀다.',
            '내 자신을 친구나 친지들과 비교할 때면 내 자신에 대해 흐뭇하게 느껴진다.'
        ],
        'Part 3': [
            '문제를 해결하려고 노력할 때 나는 직감을 믿으며 처음 떠오른 해결책을 적용한다.',
            '직장 상사, 동료, 배우자, 자녀와 미리 계획한 대화를 나눌 때도 나는 언제가 감정적으로 대응한다.',
            '앞으로의 건강이 걱정스럽다.',
            '당면한 과제에 집중하지 못하게 방해하는 어떤 것도 능숙하게 차단한다.',
            '첫 번째 해결책이 효과가 없으면 원점으로 돌아가서 문제가 해결될 때까지 다른 해결책을 끊임없이 시도한다.',
            '호기심이 많다.',
            '과제에 집중하게 도와줄 긍정적인 감정을 활용하지 못한다.',
            '새로운 것을 시도하기를 좋아한다.',
            '도전적이고 어려운 일보다는 자신있고 쉬운 일을 하는 것이 더 좋다.',
            '사람들 표정을 보면 그가 어떤 감정을 느끼는지 알아차린다.',
            '일이 잘 안풀리면 포기한다.',
            '문제가 생기면 여러가지 해결책을 강구한 후 문제를 해결하려고 노력한다.',
            '역경에 처할 때 감정을 통제할 수 있다.',
            '나에 대한 다른 사람들 생각은 내 행동에 영향을 미치지 못한다.',
            '문제가 일어나는 순간, 맨 처음에 떠오르는 생각이 무엇인지 알고있다.',
            '내가 유일한 책임지가 아닌 상황이 가장 편안하다.',
            '내 능력보다 타인의 능력에 의지할 수 있는 상황을 선호한다.',
            '언제나 문제를 해결할 수는 없지만 해결할 수 있다고 믿는 것이 더 낫다.',
            '문제가 일어나면 문제의 원인부터 철저히 파악한 후 해결을 시도한다.',
            '직장이나 가정에서 나는 내 문제 해결 능력을 의심한다.',
            '내가 통제할 수 없는 요인들에 대해 숙고하는데 시간을 허비하지 않는다.',
            '변함없이 단순한 일상적인 일을 하는 것을 좋아한다.',
            '내 감정에 휩쓸린다.',
            '사람들이 느끼는 감정의 원인을 간파하지 못한다.',
            '내가 어떤 생각을 하고 그것이 내 감정에 어떤 영향을 미치는지 잘 파악한다.',
            '누군가에게 화가 나도 일단 마음을 진정하고 그것에 관해 대화할 알맞은 순간까지 기다릴 수 있다.',
            '어떤 문제에 누군가 과잉 반응을 하면 그날 그 사람이 단지 기분이 나빠서 그런 거라고 생각한다.',
            '나는 대부분의 일을 잘 해낼 것이다.',
            '사람들은 문제 해결에 도움을 얻으려고 자주 나를 찾는다.',
            '사람들이 특정 방식으로 대응하는 이류를 간파하지 못한다.',
            '내 감정이 가정, 학교, 직장에서의 집중력에 영향을 미친다.',
            '힘든 일에는 언제나 보상이 따른다.',
            '과제를 완수한 후 부정적인 평가를 받을까 봐 걱정한다.',
            '누군가 슬퍼하거나 분노하거나 당혹스러워할 때 그 사람이 어떤 생각을 하고 있는지 정확히 알고 있다.',
            '새로운 도전을 좋아하지 않는다.',
            '직업, 학업, 재정과 관련해서 미리 계획하지 않는다.',
            '동료가 흥분할 때 그 원인을 꽤 정확하게 알아차린다.',
            '어떤 일이든 미리 계획하기보다는 즉흥적으로 하는 것을 좋아한다.그것이 별로 효과적이지 않아도 그렇다.',
            '대부분의 문제는 내가 통제할 수 없는 상황 때문에 일어난다.',
            '도전은 나 자신이 성장하고 배우는 한 가지 방법이다.',
            '내가 사건과 상황을 오해하고 있다는 말을 들은 적이 있다.',
            '누군가 내게 화를 내면 대응하기 전에 그의 말을 귀 기울여 듣는다.',
            '내 미래에 대해 생각할 때 성공한 내 모습이 상상되지 않는다.',
            '문제가 일어날 때 내가 속단해 버린다는 말을 들은 적이 있다.',
            '새로운 사람들을 만나는 것이 불편하다.',
            '책이나 영화에 쉽게 몰입한다.',
            '"예방이 치료보다 낫다."는 속담을 믿는다.',
            '거의 모든 상황에서 문제의 진짜 원인을 잘 파악한다.',
            '훌륭한 대처 기술을 갖고 있으며 대부분의 문제에 잘 대응한다.',
            '배우자나 가까운 친구들은 내가 그들을 이해하지 못한다고 말한다.',
            '판에 박힌 일과를 처리할 때 가장 편안하다.',
            '문제는 최대한 빨리 해결하는 것이 중요하다.설령 그 문제를 충분히 파악하지 못하더라도 그렇다.',
            '어려운 상황에 처할 때 나는 그것이 잘 해결될 거라고 자신한다.',
            '동료와 친구들은 내가 그들 말을 경청하지 않는다고 말한다.',
            '어떤 것이 갖고 싶으면 즉이 나가서 그것을 산다.',
            '동료나 가족과 "민감한"주제에 대해 의논할 때 감정을 자제할 수 있다.'
        ]
    }

    user = models.ForeignKey(to='User', on_delete=models.CASCADE)
    timestamp = models.BigIntegerField()
    values = models.CharField(validators=[validate_comma_separated_integer_list], max_length=500)

    def to_json(self):
        return {question: answer for question, answer in zip(Survey.QUESTIONS_LIST, self.values.split(','))}

    @staticmethod
    def survey_str_matches(values):
        return len(values.split(',')) == len([Survey.QUESTIONS_LIST[key] for key in list(Survey.QUESTIONS_LIST.keys())])

    @staticmethod
    def create_survey(user: User, values):
        return Survey.objects.create(user=user, timestamp=int(datetime.datetime.now().timestamp()), values=values)
