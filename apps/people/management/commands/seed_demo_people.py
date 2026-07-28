from django.core.management.base import BaseCommand

from apps.people.models import Organization, Person, PersonSkill, ResponsibilityLevel, Skill, WorkSchedule


class Command(BaseCommand):
    help = "중간 시연용 People DB 합성 데이터를 생성하거나 갱신합니다."

    def handle(self, *args, **options):
        platform, _ = Organization.objects.update_or_create(
            code="AI-PLATFORM",
            defaults={"name": "AI Platform", "parent": None, "is_active": True},
        )
        delivery, _ = Organization.objects.update_or_create(
            code="DELIVERY",
            defaults={"name": "Delivery", "parent": None, "is_active": True},
        )

        levels = {}
        for code, name, rank in (("JUNIOR", "주니어", 1), ("SENIOR", "시니어", 2), ("LEAD", "리드", 3)):
            levels[code], _ = ResponsibilityLevel.objects.update_or_create(
                code=code,
                defaults={"name": name, "rank_order": rank},
            )

        skills = {}
        for name, category in (("Python", "Backend"), ("Django", "Backend"), ("React", "Frontend"), ("Jira", "Project Management")):
            skills[name], _ = Skill.objects.update_or_create(name=name, defaults={"category": category, "is_active": True})

        people = (
            ("EMP-001", "김철수", "kim.cs@example.com", platform, "Backend Developer", "SENIOR", {"Python": 5, "Django": 4, "Jira": 3}),
            ("EMP-002", "이영희", "lee.yh@example.com", delivery, "Project Manager", "LEAD", {"Jira": 5, "Python": 2}),
            ("EMP-003", "박민수", "park.ms@example.com", platform, "Frontend Developer", "JUNIOR", {"React": 4, "Jira": 3}),
        )

        for employee_id, name, email, organization, job_role, level_code, skill_levels in people:
            person, _ = Person.objects.update_or_create(
                employee_id=employee_id,
                defaults={
                    "name": name,
                    "email": email,
                    "organization": organization,
                    "responsibility_level": levels[level_code],
                    "job_role": job_role,
                    "employment_status": "ACTIVE",
                    "timezone": "Asia/Seoul",
                    "fte": 1.00,
                    "data_origin": "SYNTHETIC",
                    "is_active": True,
                },
            )
            WorkSchedule.objects.update_or_create(
                person=person,
                effective_from="2026-01-01",
                defaults={"weekly_hours": 40.00, "effective_to": None},
            )
            for skill_name, proficiency in skill_levels.items():
                PersonSkill.objects.update_or_create(
                    person=person,
                    skill=skills[skill_name],
                    defaults={"proficiency": proficiency, "confidence": 0.90},
                )

        self.stdout.write(self.style.SUCCESS("People DB 데모 데이터 3명, 조직 2개, Skill 4개를 준비했습니다."))
